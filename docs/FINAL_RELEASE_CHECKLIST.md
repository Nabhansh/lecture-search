# Final Release Checklist

## A. Browser timestamp validation

All five lecture videos passed manual browser testing. Selecting a search result loaded the corresponding video and moved playback to the displayed timestamp.

| Topic | Expected lecture ID | Media streaming | Visible timestamp seeking |
|---|---|---:|---:|
| FCFS | `os_l23_fcfs` | PASS | PASS |
| SJF | `os_l24_sjf` | PASS | PASS |
| Process Synchronization | `os_l39` | PASS | PASS |
| Deadlocks | `os_l41_deadlock` | PASS | PASS |
| Paging | `os_l58` | PASS | PASS |

**Result: 5/5 lecture videos passed browser timestamp-seeking verification.**

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

- [x] All five browser timestamp checks visibly pass.
- [ ] Automated test suite passes (recorded baseline: 46 tests).
- [ ] Overall and language benchmark figures generated from the final CSV exports.
- [ ] Research report and architecture documentation reviewed.
- [ ] Demo recording completed.
- [ ] No media, secrets, backup files or virtual environment staged.
- [ ] Commit pushed; local branch clean and synchronized.
