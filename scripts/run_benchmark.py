#!/usr/bin/env python3
"""Run keyword, dense, and hybrid retrieval for every benchmark query.

Run from the project root:
    python scripts/run_benchmark.py --overwrite

Writes one JSONL record per query/configuration/strategy to
    data/evaluation/runs.jsonl
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import search_hybrid as hybrid  # noqa: E402
import search_keyword as keyword  # noqa: E402

keyword.DB_PATH = hybrid.KEYWORD_DB

CONFIGS = ("base_auto", "small_hi")
STRATEGIES = ("keyword", "dense", "hybrid")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Expected object at {path}:{line_no}")
            rows.append(row)
    return rows


def clean_result(result: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "lecture_id": str(result["lecture_id"]),
        "start": float(result["start"]),
        "end": float(result["end"]),
        "text": str(result.get("text", "")),
        "score": float(result.get("score", 0.0)),
    }


def run_keyword(config: str, query: str, limit: int) -> list[dict[str, Any]]:
    original_terms = keyword.normalize_query(query)
    if not original_terms:
        return []
    terms = keyword.expand_query_terms(original_terms)
    fts_query = " OR ".join(
        f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms
    )
    table = keyword.TABLES[config]

    with sqlite3.connect(hybrid.KEYWORD_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""SELECT c.*, bm25({table}) AS bm25_score
                FROM {table}
                JOIN chunks c ON c.chunk_id = {table}.chunk_id
                WHERE {table} MATCH ?
                ORDER BY bm25_score ASC""",
            (fts_query,),
        ).fetchall()

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        segments = json.loads(row["segments_json"])
        segment, overlap = keyword.get_best_segment(segments, terms)
        if segment is None or overlap <= 0:
            continue
        key = (
            row["lecture_id"], round(float(segment["start"]), 2),
            round(float(segment["end"]), 2), segment["text"].strip().casefold(),
        )
        unique.setdefault(key, {
            "lecture_id": row["lecture_id"],
            "start": float(segment["start"]),
            "end": float(segment["end"]),
            "text": segment["text"],
            "score": -float(row["bm25_score"]),
        })
    selected = list(unique.values())[:limit]
    return [clean_result(item, rank) for rank, item in enumerate(selected, 1)]


def run_dense(
    config: str, query: str, limit: int,
    resources: tuple[Any, list[dict[str, Any]], dict[str, dict[str, Any]]],
    model: Any,
    candidate_count: int,
) -> list[dict[str, Any]]:
    index, metadata, metadata_by_id = resources
    ranks, similarities = hybrid.get_dense_rankings(
        index, metadata, model, query, candidate_count
    )
    candidates: list[dict[str, Any]] = []
    for chunk_id, rank in sorted(ranks.items(), key=lambda item: item[1]):
        record = metadata_by_id[chunk_id]
        for segment in record.get("segments", []):
            text = str(segment.get("text", "")).strip()
            if not text or "\ufffd" in text:
                continue
            candidates.append({
                "chunk_id": chunk_id,
                "lecture_id": str(record["lecture_id"]),
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": text,
                "chunk_rank": rank,
                "chunk_score": similarities[chunk_id],
            })

    if not candidates:
        return []

    vectors = hybrid.embed_texts(model, [item["text"] for item in candidates])
    q_vector = hybrid.embed_texts(model, [query])[0]
    segment_scores = vectors @ q_vector
    best_per_chunk: dict[str, dict[str, Any]] = {}
    for candidate, score in zip(candidates, segment_scores):
        candidate["segment_score"] = float(score)
        prior = best_per_chunk.get(candidate["chunk_id"])
        if prior is None or candidate["segment_score"] > prior["segment_score"]:
            best_per_chunk[candidate["chunk_id"]] = candidate

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for candidate in best_per_chunk.values():
        key = (
            candidate["lecture_id"], round(candidate["start"], 3),
            round(candidate["end"], 3), candidate["text"].strip().casefold(),
        )
        prior = unique.get(key)
        if prior is None or candidate["chunk_rank"] < prior["chunk_rank"]:
            unique[key] = candidate

    ordered = sorted(unique.values(), key=lambda item: item["chunk_rank"])
    final = [
        {**item, "score": item["chunk_score"]}
        for item in ordered[:limit]
    ]
    return [clean_result(item, rank) for rank, item in enumerate(final, 1)]


def run_hybrid(
    config: str, query: str, limit: int,
    resources: tuple[Any, list[dict[str, Any]], dict[str, dict[str, Any]]],
    model: Any,
    candidate_count: int,
) -> list[dict[str, Any]]:
    index, metadata, metadata_by_id = resources
    keyword_ranks, _keyword_scores, _tokens, _fts = hybrid.get_keyword_rankings(
        config, query, 1000
    )
    semantic_query = hybrid.semantic_query_text(query)
    dense_ranks, _dense_scores = hybrid.get_dense_rankings(
        index, metadata, model, semantic_query, candidate_count
    )
    fused = hybrid.reciprocal_rank_fusion(
        keyword_ranks, dense_ranks, metadata_by_id
    )
    results = hybrid.select_unique_segments(
        fused, query, model, semantic_query=semantic_query
    )
    final = []
    for item in results[:limit]:
        final.append({
            "lecture_id": item["lecture_id"],
            "start": item["start"],
            "end": item["end"],
            "text": item["text"],
            "score": item["hybrid_score"],
        })
    return [clean_result(item, rank) for rank, item in enumerate(final, 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queries", type=Path,
        default=ROOT / "data/evaluation/queries.jsonl",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "data/evaluation/runs.jsonl",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dense-candidates", type=int, default=50)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.limit < 1 or args.dense_candidates < 1:
        parser.error("--limit and --dense-candidates must be positive")
    if args.output.exists() and not args.overwrite:
        parser.error(f"{args.output} already exists; use --overwrite to replace it")

    queries = read_jsonl(args.queries)
    if not queries:
        parser.error("No queries found")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total_runs = len(queries) * len(CONFIGS) * len(STRATEGIES)
    print(f"Queries: {len(queries)} | Configurations: {len(CONFIGS)} | Strategies: {len(STRATEGIES)}")
    print(f"Total query runs: {total_runs}")
    print("Loading multilingual embedding model once...")
    model = hybrid.TextEmbedding(model_name=hybrid.MODEL_NAME)
    resources_by_config = {
        config: hybrid.load_dense_resources(config) for config in CONFIGS
    }

    count = 0
    with args.output.open("w", encoding="utf-8") as out:
        for query_row in queries:
            query_id = str(query_row["query_id"])
            query = str(query_row["query"])
            language = str(query_row["language"])
            for config in CONFIGS:
                resources = resources_by_config[config]
                for strategy in STRATEGIES:
                    if strategy == "keyword":
                        results = run_keyword(config, query, args.limit)
                    elif strategy == "dense":
                        results = run_dense(
                            config, query, args.limit, resources, model,
                            args.dense_candidates,
                        )
                    else:
                        results = run_hybrid(
                            config, query, args.limit, resources, model,
                            args.dense_candidates,
                        )
                    row = {
                        "query_id": query_id,
                        "language": language,
                        "query": query,
                        "config": config,
                        "strategy": strategy,
                        "results": results,
                    }
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1
            print(f"Completed {query_id} ({count}/{total_runs} runs)", flush=True)

    print(f"\nSaved {count} retrieval runs to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
