# AGENTS.md

Repository-specific guidance for agent sessions working in this project.

## Project

Hinglish Lecture Search — a local research prototype that searches timestamped Operating
Systems lecture transcripts with English, Hindi, and Hinglish queries. See `README.md` for
scope, results, and limitations, and `docs/ARCHITECTURE.md` for the pipeline.

## Environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-phase2.txt   # app layer; includes requirements.txt
```

Heavy retrieval dependencies (`faiss-cpu`, `fastembed`, `numpy`) are only needed to run real
searches, rebuild indexes, or regenerate `runs.jsonl`. The test suite does not require them.

## Commands

```bash
python -m pytest -q tests/                       # full suite (46 tests)
python -m pytest -q tests/test_intent_logic.py   # ranking-logic regressions only
python app.py                                    # FastAPI + Gradio on 127.0.0.1:7860
```

Benchmark pipeline (order matters):

```bash
python scripts/run_benchmark.py --overwrite      # needs indexes + embedding model
python scripts/score_benchmark.py --tolerance 10 # deterministic from runs.jsonl
python scripts/generate_benchmark_figures.py     # writes docs/figures/
```

## Conventions

- Retrieval/ranking logic lives in `scripts/search_hybrid.py`; the application layer in
  `src/lecture_search/` only adapts and caches it. Do not duplicate ranking logic in the app.
- `scripts/score_benchmark.py` is deterministic; keep it that way so reported metrics stay
  reproducible from the committed `runs.jsonl`.
- `data/evaluation/queries.jsonl` is the annotated ground truth. `queries_template.jsonl` is
  a blank template. Never overwrite annotations without manually checking the video clips.
- Lecture media (`data/raw/*.mp4`, `data/audio/*.wav`) is intentionally untracked. Never
  commit media, virtual environments, model caches, or secrets.
- `SHA256SUMS.txt` is a manifest of tracked files. Regenerate it after changing tracked files:
  `git ls-files -co --exclude-standard | grep -v '^SHA256SUMS.txt$' | sort | xargs sha256sum > SHA256SUMS.txt`

## Evaluation honesty

The 30-query benchmark is a **development set**, not a held-out test set. Do not describe its
metrics as generalization or unbiased test performance in docs, PRs, or demos.
