
import argparse
import json
import sys
from pathlib import Path

import faiss
import numpy as np
from fastembed import TextEmbedding


ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "data" / "index"

MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

BATCH_SIZE = 32

CONFIGURATIONS = ["base_auto", "small_hi"]


def load_metadata(path: Path) -> list:
    if not path.exists():
        raise FileNotFoundError(path)

    records = []

    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))

    return records


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)

    if not np.isfinite(vectors).all():
        raise ValueError("Embedding contains NaN or infinity.")

    faiss.normalize_L2(vectors)

    return vectors


def make_segment_key(lecture_id: str, segment: dict) -> tuple:
    return (
        lecture_id,
        round(float(segment["start"]), 3),
        round(float(segment["end"]), 3),
        segment["text"].strip().casefold(),
    )


def search(config: str, query: str, limit: int = 10):

    if config not in CONFIGURATIONS:
        raise ValueError(f"Unsupported configuration: {config}")

    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    if limit < 1:
        raise ValueError("Limit must be positive.")

    manifest_path = INDEX_DIR / "dense_manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(
            "Dense index not found. Run build_dense_index.py first."
        )

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    if manifest["model"] != MODEL_NAME:
        raise ValueError("Embedding model does not match the index.")

    config_info = manifest["configurations"][config]

    index_path = INDEX_DIR / config_info["index_file"]
    metadata_path = INDEX_DIR / config_info["metadata_file"]

    index = faiss.read_index(str(index_path))
    records = load_metadata(metadata_path)

    if index.ntotal != len(records):
        raise ValueError(
            "FAISS index and metadata record counts do not match."
        )

    print("Loading embedding model...")
    model = TextEmbedding(model_name=MODEL_NAME)

    # This multilingual MiniLM model uses direct text embeddings.
    # Do not apply E5-specific query:/passage: prefixes.
    # Expand SJF queries using the scheduling concept captured by the lecture.
    # The saved FAISS vectors and metadata remain unchanged.
    embedding_query = query
    query_terms = set(query.casefold().split())
    if (
        "sjf" in query_terms
        or "एसजेएफ" in query_terms
        or ("shortest" in query_terms and "job" in query_terms)
    ):
        embedding_query = (
            query
            + " shortest job first scheduling algorithm; "
            "select the ready process with the smallest CPU burst time; "
            "execute the shortest job first"
        )

    query_vector = normalize_vectors(
        np.asarray(
            list(model.embed([embedding_query], batch_size=1)),
            dtype=np.float32,
        )
    )

    candidate_k = min(
        index.ntotal,
        max(limit * 5, 30),
    )

    scores, indices = index.search(
        query_vector,
        candidate_k,
    )

    candidates = []

    for score, idx in zip(scores[0], indices[0]):

        if idx < 0:
            continue

        candidates.append({
            "chunk": records[int(idx)],
            "chunk_score": float(score),
        })

    # Gather unique segments from the retrieved chunks.
    segment_map = {}
    chunk_segment_keys = []

    for candidate in candidates:
        chunk = candidate["chunk"]
        keys = []

        for segment in chunk["segments"]:
            key = make_segment_key(
                chunk["lecture_id"],
                segment,
            )

            segment_map.setdefault(key, segment)
            keys.append(key)

        chunk_segment_keys.append(keys)

    unique_keys = list(segment_map.keys())

    if not unique_keys:
        print("No matching segments found.")
        return

    segment_texts = [
        segment_map[key]["text"]
        for key in unique_keys
    ]

    # Embed individual segments to select a precise playback moment.
    segment_vectors = normalize_vectors(
        np.asarray(
            list(
                model.embed(
                    segment_texts,
                    batch_size=BATCH_SIZE,
                )
            ),
            dtype=np.float32,
        )
    )

    segment_scores = segment_vectors @ query_vector[0]

    key_to_score = {
        key: float(segment_scores[position])
        for position, key in enumerate(unique_keys)
    }

    # Deduplicate identical segments shared by overlapping windows.
    results_by_segment = {}

    for candidate, keys in zip(candidates, chunk_segment_keys):

        if not keys:
            continue

        best_key = max(
            keys,
            key=lambda key: key_to_score[key],
        )

        segment = segment_map[best_key]
        chunk = candidate["chunk"]

        result = {
            "lecture_id": chunk["lecture_id"],
            "chunk_id": chunk["chunk_id"],
            "chunk_score": candidate["chunk_score"],
            "segment_score": key_to_score[best_key],
            "segment": segment,
            "video_path": chunk["video_path"],
        }

        previous = results_by_segment.get(best_key)

        if (
            previous is None
            or result["chunk_score"] > previous["chunk_score"]
        ):
            results_by_segment[best_key] = result

    results = sorted(
        results_by_segment.values(),
        key=lambda item: item["chunk_score"],
        reverse=True,
    )[:limit]

    print("\n" + "=" * 65)
    print("DENSE LECTURE SEARCH")
    print("=" * 65)
    print("Configuration:", config)
    print("Query:", query)
    print("Model:", MODEL_NAME)
    print("Retrieved chunks:", len(candidates))
    print("Unique segment results:", len(results_by_segment))
    print("Displayed results:", len(results))

    for rank, result in enumerate(results, 1):

        segment = result["segment"]

        print(f"\nRank: {rank}")
        print("Lecture:", result["lecture_id"])
        print(f"Chunk cosine similarity: {result['chunk_score']:.4f}")
        print(f"Segment cosine similarity: {result['segment_score']:.4f}")
        print(
            f"Suggested seek: {segment['start']:.2f}s"
        )
        print("Segment:", segment["text"])
        print("Video:", result["video_path"])
        print("-" * 65)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Multilingual dense lecture search"
    )

    parser.add_argument(
        "config",
        choices=CONFIGURATIONS,
    )

    parser.add_argument("query")

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    try:
        search(
            args.config,
            args.query,
            args.limit,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
