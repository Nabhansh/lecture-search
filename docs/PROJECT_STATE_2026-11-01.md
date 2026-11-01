# Project state: 1 November 2026

## Project goal
Search inside five Operating Systems lecture recordings using English, Hindi and Hinglish questions. Results should include the matching transcript segment and a timestamp that seeks into the lecture video. The intended product also includes a web interface and voice search; these frontend components were not completed in the recovered source package.

## Recovered dataset and indexes
- Five lecture transcript sources: `os_l23_fcfs`, `os_l24_sjf`, `os_l39`, `os_l41_deadlock`, `os_l58`.
- Two transcript configurations: `base_auto` and `small_hi`.
- `data/processed/base_auto.jsonl` and `small_hi.jsonl` contain the segment-level ASR outputs.
- Both chunk JSONL files are present (30-second windows, 20-second stride).
- SQLite FTS5 keyword database, two FAISS indexes, metadata JSONL files and the dense manifest are recovered.
- The videos and WAVs are not present in this archive.

## Retrieval stack
- FTS5 keyword retrieval, multilingual FastEmbed vectors with FAISS, reciprocal-rank fusion (RRF, k=60), timestamp-level segment scoring, overlap deduplication.
- Multilingual embedding model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions).
- Query-time cross-script aliases are present. SJF, FCFS and semaphore-purpose intents have targeted query expansion and timestamp scoring.
- SJF intent classes: definition, process selection, tie-break. FCFS ranking requires an FCFS anchor so unrelated SJF arrival-time mentions are not boosted. SJF selection question fragments receive a low score rather than being promoted as answer segments.

## Benchmark state
- 30 development queries, 10 per language (English, Hindi, Hinglish).
- 180 runs per complete benchmark (2 transcript configurations x 3 retrieval strategies x 30 queries).
- Latest aggregate metrics are in `data/evaluation/results/`.
- Historical baseline metrics and the full captured baseline per-query CSV are in `data/evaluation/baseline_before_sjf_fix/results/`.
- The latest raw `runs.jsonl` was not recovered.
- Latest aggregate results: `small_hi + hybrid` leads Recall@1 (0.50) and MRR (0.533); `base_auto + hybrid` leads Recall@5 (0.70) and Recall@10 (0.767).
- The existing 30-query set was used for tuning and is not a held-out test set. Create an independent test set before making general performance claims.

## Current known failure/audit items
See `FAILURE_AUDIT_2026-11-01.md`. Main open problems include waiting-time retrieval in FCFS, critical-section ranking, deadlock-definition ranking, semaphore terminology/ASR quality and paging annotation quality.

## Still required to reproduce the complete local pipeline
1. Restore the five source videos into `data/raw/` using the IDs above and `.mp4` names used by transcripts.
2. Restore audio in `data/audio/` or re-extract it from videos.
3. Set up the Fedora virtual environment and install `requirements.txt`.
4. Ensure the model cache is available; otherwise the multilingual embedding model must be downloaded once.
5. Run the benchmark again to regenerate latest `runs.jsonl` and query-level metrics for the reconstructed final code.
6. Manually audit Q015, Q024, Q026 and any alternative paging/deadlock/ semaphore answer intervals before treating all labels as verified.
7. Build the planned frontend and voice-search integration; these are not included.
