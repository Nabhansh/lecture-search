# Lecture Search: completion pack

This pack contains the research and release documentation for the current Hinglish Lecture
Search prototype.

## Files

- `docs/ARCHITECTURE.md`: system design and request/data flows.
- `docs/RESEARCH_REPORT.md`: research-style report with the final 30-query development benchmark results.
- `docs/DEMO_SCRIPT.md`: suggested 3–4 minute demo sequence and narration.
- `docs/FINAL_RELEASE_CHECKLIST.md`: release verification record and remaining steps.
- `scripts/generate_benchmark_figures.py`: regenerate the figures from the project's benchmark CSV files.
- `benchmark_data/`: compact metric exports used as a fallback if project CSVs are unavailable.
- `docs/figures/`: rendered benchmark figures.

## Apply to the Fedora project

Copy `lecture_search_completion_pack.zip` to Fedora, then run:

```bash
unzip -o lecture_search_completion_pack.zip -d ~/Documents/lecture-search
cd ~/Documents/lecture-search
source ~/venvs/lecture-search/bin/activate
python scripts/generate_benchmark_figures.py
```

The archive contains paths relative to the project root. `PACK_README.md` will not overwrite
the project's own `README.md`.

The chart script prefers `data/evaluation/results/summary_overall.csv` and
`summary_by_language.csv` from the project. It falls back to the included `benchmark_data`
files only when those project CSVs are absent.

The report uses the final results recorded for the 2 November project state. The 30-query
set was used during development/tuning, so the results must be described as development-set
results, not independent test-set performance.

## Verification boundary

Browser validation is recorded in `docs/FINAL_RELEASE_CHECKLIST.md`. Selecting a search
result loads the corresponding video and seeks playback to the displayed timestamp for all
five lectures (FCFS, SJF, Process Synchronization, Deadlocks, Paging); that checklist records
the pass/fail state per lecture and distinguishes successful HTTP byte-range delivery
(`HTTP 206`) from visible timestamp seeking.

For the retrieval pipeline, `scripts/score_benchmark.py` is deterministic: re-running it on
the committed `data/evaluation/runs.jsonl` reproduces the reported aggregate CSVs exactly.
Reproducing `runs.jsonl` itself additionally requires the dense indexes, the FTS5 database,
and the embedding model.
