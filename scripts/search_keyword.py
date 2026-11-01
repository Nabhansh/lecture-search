
import argparse
import json
import sqlite3
import unicodedata

from pathlib import Path


DB_PATH = Path("data/index/keyword_search.db")

TABLES = {
    "base_auto": "base_auto_fts",
    "small_hi": "small_hi_fts",
}

# Small, explicitly maintained vocabulary for the five lectures.
# Keep this dictionary versioned for reproducible evaluation.
QUERY_ALIASES = {
    "सेमाफोर": ["semaphore"],
    "सेमफोर": ["semaphore"],
    "बाइनरी": ["binary"],
    "काउंटिंग": ["counting"],
    "प्रोसेस": ["process", "processes"],
    "प्रोसेसेस": ["process", "processes"],
    "डेडलॉक": ["deadlock"],
    "मेमोरी": ["memory"],
    "शेड्यूलिंग": ["scheduling"],
    "क्रिटिकल": ["critical"],
    "सेक्शन": ["section"],

    "semaphore": ["सेमाफोर"],
    "binary": ["बाइनरी"],
    "counting": ["काउंटिंग"],
    "process": ["प्रोसेस", "processes"],
    "processes": ["प्रोसेस"],
    "deadlock": ["डेडलॉक"],
    "memory": ["मेमोरी"],
    "scheduling": ["शेड्यूलिंग"],
    "critical": ["क्रिटिकल"],
    "section": ["सेक्शन"],

    # SJF terminology and observed Whisper recognition variants.
    "sjf": ["shortest", "short", "test", "job", "first", "burst", "time", "शौट्तेश", "जौव", "बरस", "टाइम"],
    "एसजेएफ": ["shortest", "short", "test", "job", "first", "burst", "time", "शौट्तेश", "जौव", "बरस", "टाइम"],
}


def normalize_query(text: str) -> list[str]:
    """Tokenize English and Devanagari without removing marks."""

    text = unicodedata.normalize("NFKC", text).casefold()

    tokens = []
    current = []

    for char in text:
        category = unicodedata.category(char)

        if (
            category.startswith("L")
            or category.startswith("M")
            or category.startswith("N")
            or char in "_+#"
        ):
            current.append(char)
        else:
            if current:
                tokens.append("".join(current))
                current = []

    if current:
        tokens.append("".join(current))

    return list(dict.fromkeys(tokens))


def expand_query_terms(terms: list[str]) -> list[str]:
    """Add curated cross-script equivalents."""

    expanded = list(terms)

    for term in terms:
        for alias in QUERY_ALIASES.get(term, []):
            expanded.extend(normalize_query(alias))

    return list(dict.fromkeys(expanded))


def get_best_segment(segments: list, terms: list[str]):
    """Find the segment with the highest query-token overlap."""

    query_set = set(terms)

    best_segment = None
    best_score = -1

    for segment in segments:
        segment_terms = set(
            normalize_query(segment["text"])
        )

        score = len(query_set.intersection(segment_terms))

        if score > best_score:
            best_score = score
            best_segment = segment

    return best_segment, best_score


def search(config: str, query: str, limit: int = 10):

    if config not in TABLES:
        raise ValueError(f"Unknown configuration: {config}")

    if limit < 1:
        raise ValueError("Limit must be positive.")

    original_terms = normalize_query(query)

    if not original_terms:
        print("Query contains no searchable terms.")
        return

    expanded_terms = expand_query_terms(original_terms)

    fts_query = " OR ".join(
        f'"{term.replace(chr(34), chr(34) * 2)}"'
        for term in expanded_terms
    )

    table = TABLES[config]

    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Retrieve all matches before deduplication.
        # Only 178 chunks exist per configuration, so this is inexpensive.
        sql = f"""
            SELECT
                c.*,
                bm25({table}) AS bm25_score
            FROM {table}
            JOIN chunks c
                ON c.chunk_id = {table}.chunk_id
            WHERE {table} MATCH ?
            ORDER BY bm25_score ASC
        """

        rows = conn.execute(
            sql,
            (fts_query,)
        ).fetchall()

    finally:
        conn.close()

    # Collapse duplicate segments appearing in overlapping chunks.
    unique_results = {}

    for row in rows:
        segments = json.loads(row["segments_json"])

        best_segment, segment_score = get_best_segment(
            segments,
            expanded_terms
        )

        if best_segment is None or segment_score <= 0:
            continue

        segment_key = (
            row["lecture_id"],
            round(best_segment["start"], 2),
            round(best_segment["end"], 2),
            best_segment["text"].strip().casefold(),
        )

        result = {
            "lecture_id": row["lecture_id"],
            "bm25_score": row["bm25_score"],
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "segment": best_segment,
            "segment_score": segment_score,
            "video_path": row["video_path"],
        }

        # SQL is already sorted by best BM25 score.
        # setdefault keeps the best-ranked copy.
        unique_results.setdefault(segment_key, result)

    results = list(unique_results.values())[:limit]

    print(f"\nConfiguration: {config}")
    print(f"Query: {query}")
    print(f"Original terms: {original_terms}")
    print(f"Expanded terms: {expanded_terms}")
    print(f"Matching chunks: {len(rows)}")
    print(f"Unique segments: {len(unique_results)}")
    print(f"Displayed results: {len(results)}")
    print("=" * 65)

    for rank, result in enumerate(results, 1):

        segment = result["segment"]

        print(f"\nRank: {rank}")
        print(f"Lecture: {result['lecture_id']}")
        print(f"BM25 score: {result['bm25_score']:.6f}")

        print(
            f"Chunk window: "
            f"{result['window_start']}s - "
            f"{result['window_end']}s"
        )

        print(
            f"Suggested seek: {segment['start']:.2f}s"
        )

        print(f"Suggested segment: {segment['text']}")
        print(f"Segment keyword overlap: {result['segment_score']}")
        print(f"Video: {result['video_path']}")
        print("-" * 65)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Multilingual lecture keyword search"
    )

    parser.add_argument(
        "config",
        choices=["base_auto", "small_hi"]
    )

    parser.add_argument("query")

    parser.add_argument(
        "--limit",
        type=int,
        default=10
    )

    args = parser.parse_args()

    search(args.config, args.query, args.limit)