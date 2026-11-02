# Final Release Checklist

## A. Browser timestamp validation

The latest browser/server log shows `HTTP 206 Partial Content` for each of these media routes. That is evidence of byte-range delivery, not final proof of the visible timestamp position.

| Topic | Expected lecture ID | Media request observed | Visible seek verified |
|---|---|---:|---:|
| FCFS | `os_l23_fcfs` | Yes | Yes |
| SJF | `os_l24_sjf` | Yes | Pending |
| Process Synchronization | `os_l39` | Yes | Pending |
| Deadlocks | `os_l41_deadlock` | Yes | Pending |
| Paging | `os_l58` | Yes | Pending |

For each pending row:

1. Start the app with `python app.py` and open `http://127.0.0.1:7860`.
2. Run the search query below and select the corresponding result row.
3. Confirm the selected lecture is correct.
4. Confirm the player loads and its current time is near the timestamp shown in the selected result. Do not use the browser request log alone as proof.
5. Mark the row PASS only after observing the player position.

| Topic | Search query |
|---|---|
| SJF | `SJF में सबसे पहले कौन सा प्रोसेस execute होता है?` |
| Process Synchronization | `What is the critical section in process synchronization?` |
| Deadlocks | `Processes resources ke liye wait karte rahein to kya situation banti hai?` |
| Paging | `Why is a process divided into pages?` |

## B. Automated verification

From the Fedora project root:

```bash
cd ~/Documents/lecture-search
source ~/venvs/lecture-search/bin/activate
python -m pytest -q tests/
```

Expected recorded result: **46 passed**. Investigate any change from this count before release.

Run the chart generator:

```bash
python scripts/generate_benchmark_figures.py
```

The expected images are:

```text
docs/figures/overall_recall_at_k.png
docs/figures/overall_mrr.png
docs/figures/language_performance.png
```

The full benchmark was previously regenerated as 180 runs with all 30 verified queries scored and a ±10-second timestamp tolerance. Do not rerun it just to create figures if its current results CSVs already match the documented final metrics. If code or annotations have changed since that run, rerun and update the report and figures together.

## C. Repository hygiene

```bash
git status --short

git check-ignore -v data/raw/os_l23_fcfs.mp4

git check-ignore -v data/raw/os_l24_sjf.mp4

git check-ignore -v data/raw/os_l39.mp4

git check-ignore -v data/raw/os_l41_deadlock.mp4

git check-ignore -v data/raw/os_l58.mp4

git diff --name-only -- '*.mp4' '*.wav' '*.mp3'
```

Do not commit original lecture videos, extracted audio, virtual environments, model caches, API keys or backup files. Confirm the benchmark query file, run log, score CSVs, docs and generated figures are present and appropriately tracked.

## D. Commit and push

After the browser checks, automated tests and repository hygiene checks pass:

```bash
git add README.md docs/ scripts/generate_benchmark_figures.py data/evaluation/results/
git status --short
git diff --cached --stat
git diff --cached --name-only | grep -Ei '\.(mp4|wav|mp3)$' || echo 'No media files staged.'
git commit -m "Complete research documentation and benchmark figures"
git push origin main
git status -sb
```

Check that the working tree is clean and the local branch is synchronized with `origin/main`.

## E. Demo artifact

Record the demo using `docs/DEMO_SCRIPT.md`. Save the video locally and only commit it if the repository's size policy allows it. A hosted demo link or a release attachment may be more suitable than committing a large recording.

## Release acceptance criteria

- [ ] All five browser timestamp checks visibly pass.
- [ ] Automated test suite passes (recorded baseline: 46 tests).
- [ ] Overall and language benchmark figures generated from the final CSV exports.
- [ ] Research report and architecture documentation reviewed.
- [ ] Demo recording completed.
- [ ] No media, secrets, backup files or virtual environment staged.
- [ ] Commit pushed; local branch clean and synchronized.
