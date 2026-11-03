# Hinglish Lecture Search

[![CI](https://github.com/Nabhansh/lecture-search/actions/workflows/ci.yml/badge.svg)](https://github.com/Nabhansh/lecture-search/actions/workflows/ci.yml)

A local research prototype that searches Operating Systems lecture recordings with
natural-language questions written in **English, Hindi, or Hinglish**. It returns ranked
transcript segments with timestamps that seek directly into the matching video.

> **Scope note.** This is a research prototype evaluated on **five lectures** and a
> **30-query development set**. The reported numbers are development-set results, not
> held-out test performance, and do not establish generalization to other courses,
> instructors, accents, or query distributions. See [Scope and limitations](#scope-and-limitations).

## Highlights

- **Multilingual, code-mixed retrieval** — one query pipeline handles English, Devanagari
  Hindi, and Romanized Hinglish without a language switch.
- **Hybrid ranking** — SQLite FTS5 lexical retrieval fused with FAISS dense retrieval
  (multilingual embeddings) via Reciprocal Rank Fusion (RRF, `k=60`), then re-ranked with
  query-aware intent signals and overlap deduplication.
- **Timestamp-aware playback** — results carry the original segment start time; the HTML5
  player seeks to it through an HTTP byte-range media endpoint.
- **End-to-end app** — FastAPI service + Gradio interface + `/docs` OpenAPI page.
- **Reproducible evaluation** — 180 retrieval runs across 2 transcript configurations ×
  3 strategies × 30 queries, with timestamp-aware scoring.

## Retrieval benchmark

30 development queries (10 English, 10 Hindi, 10 Hinglish). A result is relevant when its
timestamp falls within 10 seconds of a manually annotated interval.

| Configuration | Strategy | Recall@1 | Recall@5 | Recall@10 | MRR |
|---|---|---:|---:|---:|---:|
| base_auto | dense | 0.133 | 0.467 | 0.600 | 0.255 |
| **base_auto** | **hybrid** | **0.833** | **0.933** | **1.000** | **0.884** |
| base_auto | keyword | 0.200 | 0.467 | 0.800 | 0.327 |
| small_hi | dense | 0.167 | 0.333 | 0.533 | 0.251 |
| small_hi | hybrid | 0.800 | 0.800 | 0.867 | 0.808 |
| small_hi | keyword | 0.167 | 0.533 | 0.600 | 0.299 |

`base_auto` + hybrid is the strongest configuration on this development set. These results
do **not** establish generalization to unseen lectures or queries. Q024 has two annotated
intervals for valid explanations of the resource-waiting scenario. Full analysis and
per-language breakdown: [`docs/RESEARCH_REPORT.md`](docs/RESEARCH_REPORT.md).

## Quickstart

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-phase2.txt

# 2. Run the app (FastAPI + Gradio on http://127.0.0.1:7860)
python app.py
```

The API is available at `http://127.0.0.1:7860`, interactive docs at
`http://127.0.0.1:7860/docs`.

```bash
# Example search
curl -X POST http://127.0.0.1:7860/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"FCFS में वेटिंग टाइम कैसे निकाला जाता है?","config":"base_auto","limit":10}'
```

> **Media files are not committed.** The five lecture MP4s are large and kept local. Place
> them under `data/raw/` using the IDs referenced by `data/processed/base_auto.jsonl`.
> Search, indexing, and scoring work without the videos; only in-browser playback needs them.

## Tests

```bash
python -m pytest -q tests/
```

The suite contains **46 tests** covering query-intent ranking logic and the Phase 2
application layer (API routes, media-path containment, timestamp formatting, and the
player renderer). The application tests do not download the embedding model.

## Reproducing the benchmark

```bash
python -m pytest -q tests/
python scripts/run_benchmark.py --overwrite      # 180 runs -> data/evaluation/runs.jsonl
python scripts/score_benchmark.py --tolerance 10 # -> data/evaluation/results/*.csv
python scripts/generate_benchmark_figures.py     # -> docs/figures/*.png
```

`scripts/score_benchmark.py` is deterministic: re-running it on the committed
`runs.jsonl` reproduces `data/evaluation/results/summary_overall.csv` and
`summary_by_language.csv` exactly. `scripts/run_benchmark.py` additionally requires the
dense indexes (`data/index/*.faiss`), the FTS5 database, and the embedding model.

## Repository layout

| Path | Responsibility |
|---|---|
| `app.py` | Combined FastAPI + Gradio entry point |
| `src/lecture_search/` | Application layer: API routes, search-service adapter, Gradio UI, settings |
| `scripts/` | Ingestion, indexing, retrieval, benchmark, and figure-generation scripts |
| `tests/` | Query-intent ranking and application-layer regression tests |
| `data/processed/` | Segment-level transcripts and overlapping 30s chunks |
| `data/index/` | SQLite FTS5 keyword database and FAISS dense indexes |
| `data/evaluation/` | Query set, run log, and score exports |
| `docs/` | Architecture, research report, demo script, release checklist, audit logs |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full pipeline and request flows.

## Dataset

Five Operating Systems lectures: FCFS scheduling, SJF scheduling, process synchronization,
deadlocks, and paging/memory management. Lecture media is excluded from Git. Two transcript
configurations are compared: `base_auto` (automatic-language base model) and `small_hi`
(Hindi-oriented small model).

## Scope and limitations

1. **Small corpus** — five Operating Systems lectures only; results may change substantially
   on other instructors, subjects, recording conditions, or accents.
2. **Development-set evaluation** — the same 30 queries informed debugging and ranking
   refinement, so the reported values are not unbiased held-out estimates.
3. **Small language groups** — ten queries per language; per-language figures are diagnostics,
   not a statistically reliable language ranking.
4. **ASR sensitivity** — automatic transcripts contain omissions, substitutions, and
   inconsistent transliteration that can block retrieval even when the audio holds the answer.
5. **Annotation tolerance** — the ±10s overlap tolerance is an evaluation rule and does not
   mean the player may seek inaccurately by ten seconds.
6. **Modality coverage** — the completed MVP indexes speech transcripts only; slide OCR, voice
   query input, and a learned reranker are not implemented.
7. **No user study** — usability and time-saved for students have not been measured with
   participants.

## Documentation

| Document | Contents |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design and request/data flows |
| [`docs/RESEARCH_REPORT.md`](docs/RESEARCH_REPORT.md) | Research-style report and full results |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | 3–4 minute demo sequence |
| [`docs/FINAL_RELEASE_CHECKLIST.md`](docs/FINAL_RELEASE_CHECKLIST.md) | Release verification record |
| [`docs/FAILURE_AUDIT_2026-11-01.md`](docs/FAILURE_AUDIT_2026-11-01.md) | Known retrieval misses and annotation review |
| [`docs/PHASE2_SETUP.md`](docs/PHASE2_SETUP.md) | Application-layer setup notes |
| [`docs/RECOVERY_MANIFEST.md`](docs/RECOVERY_MANIFEST.md) | Provenance of recovered assets |
| [`data/evaluation/README.md`](data/evaluation/README.md) | Benchmark annotation and scoring protocol |
