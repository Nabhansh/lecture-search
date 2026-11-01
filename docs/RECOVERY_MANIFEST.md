# Recovery manifest

This ZIP is a recovered/reconstructed package, not a byte-for-byte copy of the deleted laptop folder. It combines exact assets available in the attached `lecture-search-review.zip` and `lecture-search-evaluation.zip`, plus code changes reconstructed from the recorded patch commands and benchmark logs.

## Exact recovered assets
- `data/processed/base_auto.jsonl` and `small_hi.jsonl`
- `data/processed/base_auto_chunks.jsonl` and `small_hi_chunks.jsonl`
- `data/index/keyword_search.db`
- `data/index/dense_base_auto.faiss`, `dense_small_hi.faiss`
- FAISS metadata and manifest
- Original 30-query benchmark JSONL and benchmark runner/scorer
- Baseline aggregate and per-query metrics parsed from a captured console export

## Reconstructed/updated code
- `scripts/search_hybrid.py`: starts from the recovered FCFS/semaphore version and incorporates the last recorded SJF classifier, semantic and phrase expansion, SJF tie-break/selection/definition scoring, FCFS anchor, and question-fragment guard.
- `scripts/search_keyword.py`: adds recorded SJF aliases.
- `scripts/search_dense.py`: adds recorded SJF query expansion before embedding.

## Not recovered
- Original five MP4 files and WAV files
- Exact latest raw `data/evaluation/runs.jsonl` and latest complete per-query CSV
- Model cache, venv, shell history, Git metadata and intermediate backup files
- Frontend / voice-search application if it existed outside the supplied files

The latest aggregate result CSVs are included, but because the raw latest run records were not attached, they cannot be used to regenerate every latest result row.
