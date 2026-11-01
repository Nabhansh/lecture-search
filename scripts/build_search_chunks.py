
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


# --------------------------------------------------
# Configuration
# --------------------------------------------------

INPUT_DIR = Path("data/processed")
OUTPUT_DIR = Path("data/processed")

CHUNK_SECONDS = 30
STRIDE_SECONDS = 20

INPUTS = {
    "base_auto": INPUT_DIR / "base_auto.jsonl",
    "small_hi": INPUT_DIR / "small_hi.jsonl",
}


# --------------------------------------------------
# Multilingual text normalization
# --------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Normalize text for retrieval while preserving:
    - English characters
    - Devanagari characters
    - Unicode combining marks (matras, virama, etc.)
    - Numbers
    - Technical symbols such as + and #

    Original transcript text is never modified.
    """

    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()

    chars = []

    for char in text:
        category = unicodedata.category(char)

        if (
            category.startswith("L")  # Letters
            or category.startswith("M")  # Combining marks
            or category.startswith("N")  # Numbers
            or char in "_+#"
        ):
            chars.append(char)
        else:
            chars.append(" ")

    return " ".join("".join(chars).split())


# --------------------------------------------------
# Load transcript records
# --------------------------------------------------

def load_records(path: Path) -> list:
    if not path.exists():
        raise FileNotFoundError(
            f"Transcript dataset not found: {path}"
        )

    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):

            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path}, line {line_number}"
                ) from exc

            required_fields = {
                "lecture_id",
                "transcript_type",
                "start",
                "end",
                "text",
                "video_path",
                "audio_path",
            }

            missing = required_fields - record.keys()

            if missing:
                raise ValueError(
                    f"Missing fields in {path}, "
                    f"line {line_number}: {missing}"
                )

            if record["end"] <= record["start"]:
                raise ValueError(
                    f"Invalid timestamps in {path}, "
                    f"line {line_number}"
                )

            records.append(record)

    return records


# --------------------------------------------------
# Build overlapping search chunks
# --------------------------------------------------

def build_chunks(
    records: list,
    transcript_type: str,
) -> tuple:
    lectures = defaultdict(list)

    for record in records:
        lectures[record["lecture_id"]].append(record)

    chunks = []

    for lecture_id, segments in sorted(lectures.items()):

        segments.sort(key=lambda item: item["start"])

        duration = max(
            segment["end"] for segment in segments
        )

        number_of_windows = math.ceil(
            duration / STRIDE_SECONDS
        )

        for window_index in range(number_of_windows):

            window_start = window_index * STRIDE_SECONDS
            window_end = window_start + CHUNK_SECONDS

            # Include complete segments that overlap this window.
            selected = [
                segment
                for segment in segments
                if (
                    segment["start"] < window_end
                    and segment["end"] > window_start
                )
            ]

            if not selected:
                continue

            original_text = " ".join(
                segment["text"].strip()
                for segment in selected
                if segment["text"].strip()
            ).strip()

            if not original_text:
                continue

            normalized_text = normalize_text(original_text)

            if not normalized_text:
                continue

            first_segment = selected[0]

            chunk = {
                "chunk_id": (
                    f"{lecture_id}_{transcript_type}_"
                    f"{window_start}"
                ),
                "lecture_id": lecture_id,
                "transcript_type": transcript_type,

                # Nominal search-window boundaries.
                "window_start": window_start,
                "window_end": window_end,

                # Actual boundaries of the included segments.
                "start": min(
                    segment["start"] for segment in selected
                ),
                "end": max(
                    segment["end"] for segment in selected
                ),

                # Preserve both original and normalized text.
                "text_original": original_text,
                "text_norm": normalized_text,

                "video_path": first_segment["video_path"],
                "audio_path": first_segment["audio_path"],

                # Preserve precise segment timestamps for playback.
                "segments": [
                    {
                        "start": segment["start"],
                        "end": segment["end"],
                        "text": segment["text"],
                    }
                    for segment in selected
                ],
            }

            chunks.append(chunk)

    return chunks, lectures


# --------------------------------------------------
# Save JSONL output
# --------------------------------------------------

def save_chunks(chunks: list, output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as output:
        for chunk in chunks:
            output.write(
                json.dumps(
                    chunk,
                    ensure_ascii=False,
                ) + "\n"
            )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 55)
    print("HINGLISH LECTURE SEARCH - CHUNK GENERATOR")
    print("=" * 55)

    for transcript_type, input_path in INPUTS.items():

        print(f"\nProcessing: {transcript_type}")

        records = load_records(input_path)

        if not records:
            raise ValueError(
                f"No transcript records found in {input_path}"
            )

        # Verify configuration consistency.
        for record in records:
            if record["transcript_type"] != transcript_type:
                raise ValueError(
                    f"Transcript type mismatch in {input_path}"
                )

        chunks, lectures = build_chunks(
            records,
            transcript_type,
        )

        # Verify unique chunk IDs.
        chunk_ids = [
            chunk["chunk_id"] for chunk in chunks
        ]

        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError(
                f"Duplicate chunk IDs in {transcript_type}"
            )

        output_path = (
            OUTPUT_DIR / f"{transcript_type}_chunks.jsonl"
        )

        save_chunks(chunks, output_path)

        print("\nLecture distribution:")

        for lecture_id in sorted(lectures):
            lecture_chunks = [
                chunk
                for chunk in chunks
                if chunk["lecture_id"] == lecture_id
            ]

            print(
                f"  {lecture_id}: "
                f"{len(lecture_chunks)} chunks"
            )

        print(f"\nInput segments: {len(records)}")
        print(f"Generated chunks: {len(chunks)}")
        print(f"Output: {output_path}")

        print("-" * 55)

    print("\nChunk generation completed successfully.")


if __name__ == "__main__":
    main()
