#!/usr/bin/env python3
"""Generate project benchmark figures from the final evaluation CSV exports.

Run from the repository root:
    python scripts/generate_benchmark_figures.py

The script prefers data/evaluation/results/*.csv. It uses the compact fallback
CSVs in benchmark_data/ only when the project evaluation exports are missing.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
PROJECT_RESULTS = ROOT / "data" / "evaluation" / "results"
FALLBACK = ROOT / "benchmark_data"
OUT = ROOT / "docs" / "figures"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def pick_source(name: str) -> Path:
    project_path = PROJECT_RESULTS / name
    if project_path.is_file():
        return project_path
    fallback_path = FALLBACK / name
    if fallback_path.is_file():
        print(f"Using fallback benchmark data: {fallback_path.relative_to(ROOT)}")
        return fallback_path
    raise FileNotFoundError(
        f"Neither project result nor fallback exists for {name}. "
        "Run the benchmark scorer or restore the benchmark_data directory."
    )


def number(row: dict[str, str], key: str) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid or missing numeric column {key!r} in row {row}") from exc
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"Expected {key} to be in [0, 1], found {value}")
    return value


def validate_overall(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    required = {"config", "strategy", "segment_recall@1", "segment_recall@5", "segment_recall@10", "reciprocal_rank"}
    if not rows:
        raise ValueError("Overall benchmark CSV is empty.")
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"Overall benchmark CSV is missing columns: {sorted(missing)}")
    output: list[dict[str, Any]] = []
    for row in rows:
        output.append({
            "label": f"{row['config']}\n{row['strategy']}",
            "config": row["config"],
            "strategy": row["strategy"],
            "r1": number(row, "segment_recall@1"),
            "r5": number(row, "segment_recall@5"),
            "r10": number(row, "segment_recall@10"),
            "mrr": number(row, "reciprocal_rank"),
        })
    return output


def validate_language(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    required = {"config", "strategy", "language", "segment_recall@1", "reciprocal_rank", "timestamp_hit@10"}
    if not rows:
        raise ValueError("Language benchmark CSV is empty.")
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"Language benchmark CSV is missing columns: {sorted(missing)}")
    chosen = [row for row in rows if row["config"] == "base_auto" and row["strategy"] == "hybrid"]
    if not chosen:
        raise ValueError("No base_auto + hybrid language rows found.")
    chosen.sort(key=lambda row: ["English", "Hindi", "Hinglish"].index(row["language"]) if row["language"] in {"English", "Hindi", "Hinglish"} else 99)
    return [{
        "language": row["language"],
        "r1": number(row, "segment_recall@1"),
        "mrr": number(row, "reciprocal_rank"),
        "timestamp_hit": number(row, "timestamp_hit@10"),
    } for row in chosen]


def save_recall_chart(rows: list[dict[str, Any]]) -> None:
    labels = [row["label"] for row in rows]
    x = list(range(len(rows)))
    width = 0.24
    fig, ax = plt.subplots(figsize=(11, 6))
    for offset, key, label in [(-width, "r1", "Recall@1"), (0, "r5", "Recall@5"), (width, "r10", "Recall@10")]:
        values = [row[key] for row in rows]
        bars = ax.bar([position + offset for position in x], values, width, label=label)
        ax.bar_label(bars, fmt="%.3f", padding=2, fontsize=8)
    ax.set_title("Timestamp-aware segment recall by configuration and strategy")
    ax.set_ylabel("Recall")
    ax.set_ylim(0, 1.15)
    ax.set_xticks(x, labels)
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "overall_recall_at_k.png", dpi=180)
    plt.close(fig)


def save_mrr_chart(rows: list[dict[str, Any]]) -> None:
    labels = [row["label"] for row in rows]
    values = [row["mrr"] for row in rows]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars = ax.bar(labels, values)
    ax.bar_label(bars, fmt="%.3f", padding=3)
    ax.set_title("Mean reciprocal rank by configuration and strategy")
    ax.set_ylabel("MRR")
    ax.set_ylim(0, 1.08)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "overall_mrr.png", dpi=180)
    plt.close(fig)


def save_language_chart(rows: list[dict[str, Any]]) -> None:
    labels = [row["language"] for row in rows]
    x = list(range(len(rows)))
    width = 0.34
    fig, ax = plt.subplots(figsize=(8, 5.5))
    r1 = ax.bar([i - width / 2 for i in x], [row["r1"] for row in rows], width, label="Recall@1")
    mrr = ax.bar([i + width / 2 for i in x], [row["mrr"] for row in rows], width, label="MRR")
    ax.bar_label(r1, fmt="%.3f", padding=2)
    ax.bar_label(mrr, fmt="%.3f", padding=2)
    timestamp_note = "Timestamp Hit@10: " + " · ".join(
        f"{row['language']} {row['timestamp_hit']:.3f}" for row in rows
    )
    ax.set_title("Language-level results: base_auto + hybrid")
    ax.set_ylabel("Score")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.22)
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.text(0.5, 0.015, timestamp_note, ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT / "language_performance.png", dpi=180)
    plt.close(fig)


def main() -> int:
    try:
        overall_path = pick_source("summary_overall.csv")
        language_path = pick_source("summary_by_language.csv")
        overall = validate_overall(read_csv(overall_path))
        language = validate_language(read_csv(language_path))
        OUT.mkdir(parents=True, exist_ok=True)
        save_recall_chart(overall)
        save_mrr_chart(overall)
        save_language_chart(language)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Generated benchmark figures:")
    for name in ("overall_recall_at_k.png", "overall_mrr.png", "language_performance.png"):
        print(f"  {OUT / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
