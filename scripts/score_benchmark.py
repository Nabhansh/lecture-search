#!/usr/bin/env python3
"""Score benchmark retrieval runs against manually verified lecture intervals.

Run from the project root:
    python scripts/score_benchmark.py --tolerance 10

A result is a segment hit when its lecture matches and its [start, end] interval
intersects a manually labeled interval expanded by the given tolerance (seconds).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Expected object at {path}:{line_no}")
            rows.append(item)
    return rows


def overlaps(result: dict[str, Any], target: dict[str, Any], tolerance: float) -> bool:
    if str(result.get("lecture_id")) != str(target.get("lecture_id")):
        return False
    start = float(result.get("start", -1))
    end = float(result.get("end", -1))
    target_start = float(target["start"]) - tolerance
    target_end = float(target["end"]) + tolerance
    return start <= target_end and end >= target_start


def lecture_matches(result: dict[str, Any], targets: list[dict[str, Any]]) -> bool:
    return any(str(result.get("lecture_id")) == str(t["lecture_id"]) for t in targets)


def segment_matches(result: dict[str, Any], targets: list[dict[str, Any]], tolerance: float) -> bool:
    return any(overlaps(result, target, tolerance) for target in targets)


def metric_row(
    run: dict[str, Any], targets: list[dict[str, Any]], tolerance: float,
) -> dict[str, Any]:
    results = run.get("results", [])
    first_segment_rank = None
    first_lecture_rank = None
    for rank, result in enumerate(results, 1):
        if first_segment_rank is None and segment_matches(result, targets, tolerance):
            first_segment_rank = rank
        if first_lecture_rank is None and lecture_matches(result, targets):
            first_lecture_rank = rank

    row: dict[str, Any] = {
        "query_id": run["query_id"],
        "language": run["language"],
        "query": run["query"],
        "config": run["config"],
        "strategy": run["strategy"],
        "first_segment_hit_rank": first_segment_rank or "",
        "first_lecture_hit_rank": first_lecture_rank or "",
        "reciprocal_rank": (1.0 / first_segment_rank) if first_segment_rank else 0.0,
    }
    for k in (1, 5, 10):
        row[f"segment_recall@{k}"] = int(
            any(segment_matches(r, targets, tolerance) for r in results[:k])
        )
        row[f"lecture_recall@{k}"] = int(
            any(lecture_matches(r, targets) for r in results[:k])
        )
    row["timestamp_hit@10"] = row["segment_recall@10"]
    return row


def aggregate(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in group_fields)].append(row)

    output = []
    metric_fields = (
        "segment_recall@1", "segment_recall@5", "segment_recall@10",
        "lecture_recall@1", "lecture_recall@5", "lecture_recall@10",
        "reciprocal_rank", "timestamp_hit@10",
    )
    for key, items in sorted(groups.items()):
        result = {field: value for field, value in zip(group_fields, key)}
        result["n_queries"] = len(items)
        for field in metric_fields:
            result[field] = round(sum(float(item[field]) for item in items) / len(items), 4)
        output.append(result)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=ROOT / "data/evaluation/queries.jsonl")
    parser.add_argument("--runs", type=Path, default=ROOT / "data/evaluation/runs.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/evaluation/results")
    parser.add_argument("--tolerance", type=float, default=10.0)
    args = parser.parse_args()
    if args.tolerance < 0:
        parser.error("--tolerance cannot be negative")

    query_rows = read_jsonl(args.queries)
    verified: dict[str, dict[str, Any]] = {}
    skipped = []
    for query in query_rows:
        query_id = str(query.get("query_id", ""))
        targets = query.get("relevant", [])
        if query.get("verified") is True and targets:
            for target in targets:
                if not target.get("lecture_id") or target.get("start") is None or target.get("end") is None:
                    raise ValueError(f"Incomplete relevant interval in {query_id}: {target}")
                if float(target["end"]) <= float(target["start"]):
                    raise ValueError(f"Invalid interval in {query_id}: {target}")
            verified[query_id] = query
        else:
            skipped.append(query_id)

    if not verified:
        raise SystemExit(
            "No manually verified query labels found. Fill each query's 'relevant' "
            "intervals and set 'verified' to true before scoring."
        )

    run_rows = read_jsonl(args.runs)
    detail_rows = []
    seen = set()
    for run in run_rows:
        query_id = str(run.get("query_id", ""))
        if query_id not in verified:
            continue
        key = (query_id, run.get("config"), run.get("strategy"))
        if key in seen:
            raise ValueError(f"Duplicate run record: {key}")
        seen.add(key)
        detail_rows.append(metric_row(run, verified[query_id]["relevant"], args.tolerance))

    expected = len(verified) * 2 * 3
    if len(detail_rows) != expected:
        print(f"WARNING: expected {expected} run records for verified queries, found {len(detail_rows)}")

    summary = aggregate(detail_rows, ("config", "strategy"))
    by_language = aggregate(detail_rows, ("config", "strategy", "language"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "per_query_metrics.csv", detail_rows)
    write_csv(args.output_dir / "summary_overall.csv", summary)
    write_csv(args.output_dir / "summary_by_language.csv", by_language)

    print(f"Verified queries scored: {len(verified)}")
    print(f"Unverified queries skipped: {len(skipped)}")
    print(f"Timestamp tolerance: +/- {args.tolerance:.1f}s")
    print("\nOverall metrics (query-level hit rates):")
    for row in summary:
        print(
            f"{row['config']:10s} {row['strategy']:8s} "
            f"R@1={row['segment_recall@1']:.3f} "
            f"R@5={row['segment_recall@5']:.3f} "
            f"R@10={row['segment_recall@10']:.3f} "
            f"MRR={row['reciprocal_rank']:.3f}"
        )
    if skipped:
        print("\nStill unverified:", ", ".join(skipped))
    print(f"\nCSV files written to: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
