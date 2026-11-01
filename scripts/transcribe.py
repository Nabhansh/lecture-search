#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lecture_search.io_utils import write_jsonl
from lecture_search.settings import AUDIO_DIR, PROCESSED_DIR, RAW_DIR


def parse_args():
    p = argparse.ArgumentParser(description="Transcribe WAV lectures with faster-whisper")
    p.add_argument("--config", choices=["base_auto", "small_hi", "small_auto"], required=True)
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    p.add_argument("--compute-type", default="int8", help="e.g. int8, float16, int8_float16")
    p.add_argument("--beam-size", type=int, default=5)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit("Install dependencies first: pip install -r requirements.txt") from exc

    model_size = "base" if args.config == "base_auto" else "small"
    language = "hi" if args.config == "small_hi" else None
    model = WhisperModel(model_size, device=args.device, compute_type=args.compute_type)

    audio_files = sorted(AUDIO_DIR.glob("*.wav"))
    if not audio_files:
        raise SystemExit(f"No WAV files found in {AUDIO_DIR}. Run scripts/extract_audio.py first.")

    for audio_path in audio_files:
        lecture_id = audio_path.stem
        output_path = PROCESSED_DIR / f"{args.config}.jsonl"
        # Build all results in memory so an interrupted run does not leave a partial JSONL.
        existing = []
        if output_path.exists() and not args.overwrite:
            from lecture_search.io_utils import read_jsonl
            existing = read_jsonl(output_path)
            if any(r.get("lecture_id") == lecture_id for r in existing):
                print(f"SKIP {lecture_id}: already present in {output_path.name}")
                continue

        print(f"Transcribing {lecture_id} with Whisper {model_size}, language={language or 'auto'}")
        segments, info = model.transcribe(
            str(audio_path), language=language, beam_size=args.beam_size,
            vad_filter=True, condition_on_previous_text=True,
        )
        rows = []
        video_path = RAW_DIR / f"{lecture_id}.mp4"
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            rows.append({
                "lecture_id": lecture_id,
                "transcript_type": args.config,
                "start": round(float(seg.start), 2),
                "end": round(float(seg.end), 2),
                "text": text,
                "video_path": str(video_path.relative_to(ROOT)) if video_path.exists() else f"data/raw/{lecture_id}.mp4",
                "audio_path": str(audio_path.relative_to(ROOT)),
            })
        if not rows:
            print(f"WARNING: no segments returned for {lecture_id}")
            continue
        merged = [r for r in existing if r.get("lecture_id") != lecture_id] + rows
        merged.sort(key=lambda r: (r["lecture_id"], r["start"]))
        write_jsonl(output_path, merged)
        print(f"  detected_language={info.language} p={info.language_probability:.3f}; segments={len(rows)}")
        print(f"  saved {output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
