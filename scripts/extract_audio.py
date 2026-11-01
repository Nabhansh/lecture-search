#!/usr/bin/env python3
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
OUT = ROOT / "data/audio"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    videos = sorted(RAW.glob("*.mp4"))
    if not videos:
        print(f"No MP4 files found in {RAW}", file=sys.stderr)
        return 1
    for video in videos:
        target = OUT / f"{video.stem}.wav"
        if target.exists():
            print(f"SKIP {target} (already exists)")
            continue
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", str(target),
        ]
        print(f"Extracting {video.name} -> {target.name}")
        subprocess.run(cmd, check=True)
    print(f"Audio extraction complete: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
