
import json
import sqlite3
from pathlib import Path

DATA_DIR = Path("data/processed")
INDEX_DIR = Path("data/index")
DB_PATH = INDEX_DIR / "keyword_search.db"

SOURCES = {
    "base_auto": DATA_DIR / "base_auto_chunks.jsonl",
    "small_hi": DATA_DIR / "small_hi_chunks.jsonl",
}

INDEX_DIR.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")

# Check FTS5 availability.
try:
    conn.execute(
        "CREATE VIRTUAL TABLE temp.fts5_check USING fts5(text)"
    )
    conn.execute("DROP TABLE temp.fts5_check")
except sqlite3.OperationalError as exc:
    conn.close()
    raise RuntimeError(
        "SQLite FTS5 is unavailable."
    ) from exc

# Create the metadata table.
conn.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        transcript_type TEXT NOT NULL,
        lecture_id TEXT NOT NULL,
        window_start INTEGER NOT NULL,
        window_end INTEGER NOT NULL,
        start REAL NOT NULL,
        end REAL NOT NULL,
        text_original TEXT NOT NULL,
        text_norm TEXT NOT NULL,
        video_path TEXT NOT NULL,
        audio_path TEXT NOT NULL,
        segments_json TEXT NOT NULL
    )
""")

# Important: drop old FTS tables so the new tokenizer
# configuration actually takes effect.
for config in SOURCES:
    conn.execute(f"DROP TABLE IF EXISTS {config}_fts")

    conn.execute(f"""
        CREATE VIRTUAL TABLE {config}_fts
        USING fts5(
            chunk_id UNINDEXED,
            text_norm,
            tokenize = "unicode61 categories 'L* N* Co M*' remove_diacritics 0"
        )
    """)

# Clear old metadata records.
conn.execute("DELETE FROM chunks")

total = 0

for config, source in SOURCES.items():

    if not source.exists():
        raise FileNotFoundError(source)

    records = []

    with source.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):

            if not line.strip():
                continue

            record = json.loads(line)

            if record["transcript_type"] != config:
                raise ValueError(
                    f"Transcript type mismatch: {source}, "
                    f"line {line_number}"
                )

            records.append(record)

    for record in records:

        conn.execute("""
            INSERT INTO chunks VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            record["chunk_id"],
            record["transcript_type"],
            record["lecture_id"],
            record["window_start"],
            record["window_end"],
            record["start"],
            record["end"],
            record["text_original"],
            record["text_norm"],
            record["video_path"],
            record["audio_path"],
            json.dumps(
                record["segments"],
                ensure_ascii=False
            ),
        ))

        conn.execute(f"""
            INSERT INTO {config}_fts (chunk_id, text_norm)
            VALUES (?, ?)
        """, (
            record["chunk_id"],
            record["text_norm"],
        ))

    print(f"{config}: indexed {len(records)} chunks")
    total += len(records)

conn.commit()
conn.close()

print(f"\nDatabase: {DB_PATH}")
print(f"Total indexed chunks: {total}")
print("Unicode-aware FTS5 indexing completed.")
