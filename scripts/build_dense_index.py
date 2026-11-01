
import json
import sys
from pathlib import Path

import faiss
import numpy as np
from fastembed import TextEmbedding


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data" / "processed"
INDEX_DIR = ROOT / "data" / "index"

MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

BATCH_SIZE = 32

SOURCES = {
    "base_auto": DATA_DIR / "base_auto_chunks.jsonl",
    "small_hi": DATA_DIR / "small_hi_chunks.jsonl",
}


def load_jsonl(path: Path) -> list:
    if not path.exists():
        raise FileNotFoundError(path)

    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON: {path}, line {line_number}"
                ) from exc

    return records


def embed_texts(model, texts: list[str]) -> np.ndarray:
    vectors = np.asarray(
        list(model.embed(texts, batch_size=BATCH_SIZE)),
        dtype=np.float32,
    )

    if vectors.ndim != 2:
        raise ValueError(f"Invalid embedding shape: {vectors.shape}")

    if len(vectors) != len(texts):
        raise ValueError("Embedding count does not match input count.")

    if not np.isfinite(vectors).all():
        raise ValueError("Embeddings contain invalid values.")

    faiss.normalize_L2(vectors)

    return vectors


def main():

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DENSE INDEX BUILDER")
    print("=" * 60)

    print("\nLoading model:", MODEL_NAME)
    model = TextEmbedding(model_name=MODEL_NAME)

    manifest = {
        "model": MODEL_NAME,
        "metric": "cosine_similarity",
        "index_type": "IndexFlatIP",
        "normalization": "L2",
        "embedding_dimensions": None,
        "configurations": {},
    }

    for config, source in SOURCES.items():

        print(f"\nProcessing: {config}")

        records = load_jsonl(source)

        if not records:
            raise ValueError(f"No records found in {source}")

        for record in records:
            if record["transcript_type"] != config:
                raise ValueError(
                    f"Transcript type mismatch: {record['chunk_id']}"
                )

        texts = [
            record["text_original"].strip()
            for record in records
        ]

        if any(not text for text in texts):
            raise ValueError("Empty text found in dataset.")

        print(f"Generating embeddings for {len(texts)} chunks...")

        vectors = embed_texts(model, texts)

        dimensions = vectors.shape[1]

        if manifest["embedding_dimensions"] is None:
            manifest["embedding_dimensions"] = dimensions

        elif manifest["embedding_dimensions"] != dimensions:
            raise ValueError("Embedding dimensions do not match.")

        # Exact cosine-similarity search using normalized vectors.
        index = faiss.IndexFlatIP(dimensions)
        index.add(vectors)

        index_path = INDEX_DIR / f"dense_{config}.faiss"
        metadata_path = (
            INDEX_DIR / f"dense_{config}_metadata.jsonl"
        )

        faiss.write_index(index, str(index_path))

        with metadata_path.open("w", encoding="utf-8") as output:
            for record in records:
                output.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                    ) + "\n"
                )

        manifest["configurations"][config] = {
            "chunks": len(records),
            "index_file": index_path.name,
            "metadata_file": metadata_path.name,
            "dimensions": dimensions,
        }

        print("Indexed chunks:", index.ntotal)
        print("Embedding dimensions:", dimensions)
        print("FAISS index:", index_path)
        print("Metadata:", metadata_path)

    manifest_path = INDEX_DIR / "dense_manifest.json"

    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("DENSE INDEX GENERATION COMPLETE")
    print("Dimensions:", manifest["embedding_dimensions"])
    print("Manifest:", manifest_path)
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise
