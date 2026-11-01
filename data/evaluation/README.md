# Hinglish Lecture Search: Evaluation Benchmark

This folder starts the manual evaluation phase. It contains **30 candidate queries**: 10 English, 10 Hindi, and 10 Hinglish. The `topic_hint` is only a guide for the human annotator. It is not a ground-truth label.

## 1. Manually annotate the queries first

Open `data/evaluation/queries.jsonl` in VS Code. For each query, watch the relevant lecture and identify the actual passage that answers it. Fill the `relevant` array and set `verified` to `true` only after checking the video.

Example of an annotation:

```json
{
  "query_id": "Q001",
  "language": "English",
  "topic_hint": "FCFS scheduling",
  "query": "How does FCFS scheduling select the next process?",
  "relevant": [
    {
      "lecture_id": "os_l23_fcfs",
      "start": 0.3,
      "end": 5.8
    }
  ],
  "verified": true,
  "annotation_notes": "The lecturer introduces FCFS and states the selection rule here."
}
```

Rules:
- `start` and `end` are seconds from the beginning of the video.
- Use the shortest interval that contains the answer, not the entire 30-second search chunk.
- Add multiple objects to `relevant` when the answer is explained in more than one separate interval or lecture.
- If the lecture does not actually answer the query, do not invent a timestamp. Replace the query with one that is answerable, or leave it unverified and add a note.
- Set `verified` to `true` only after you have checked the video yourself.
- Keep the JSONL valid: one complete JSON object per line.

## 2. Run all retrieval systems

Run this from the project root, with the project virtual environment active:

```bash
source ~/venvs/lecture-search/bin/activate
python scripts/run_benchmark.py --overwrite
```

The runner executes each query against:
- `keyword` retrieval
- `dense` retrieval
- `hybrid` retrieval

It does this for both transcript configurations:
- `base_auto`
- `small_hi`

For 30 queries this creates 180 runs. The embedding model is loaded once and reused. Results are saved to `data/evaluation/runs.jsonl`.

The runner expects the current project versions of:
- `scripts/search_hybrid.py`
- `scripts/search_keyword.py`
- `data/index/keyword_search.db`
- both FAISS indexes and metadata JSONL files

It does not rebuild indexes or modify retrieval code.

## 3. Score verified queries

After annotating the labels and generating `runs.jsonl`, execute:

```bash
python scripts/score_benchmark.py --tolerance 10
```

The 10-second tolerance expands each manually labeled interval by 10 seconds on both sides. A returned segment counts as a timestamp hit when it belongs to the correct lecture and overlaps that expanded interval.

Metrics:
- `segment_recall@1/5/10`: fraction of queries with at least one matching lecture-and-time result in the top K.
- `lecture_recall@1/5/10`: fraction of queries with a result from the correct lecture in the top K, regardless of timestamp.
- `reciprocal_rank`: reciprocal rank of the first matching lecture-and-time result; zero when there is no hit in the retrieved list.
- `timestamp_hit@10`: same segment-level hit criterion at rank 10.

Output files:
- `data/evaluation/results/per_query_metrics.csv`
- `data/evaluation/results/summary_overall.csv`
- `data/evaluation/results/summary_by_language.csv`

## 4. Fair-comparison rules

- Annotate relevant lecture IDs and timestamps before inspecting comparative retrieval scores where practical.
- Keep query wording, labels, candidate counts, alias dictionaries, and tolerance fixed for all runs in one reported experiment.
- Do not tune ranking weights against the same queries and then report those queries as an unbiased test set. If you tune on this set, describe it as development data and create a separate held-out test set later.
- Report both `base_auto` and `small_hi`; do not merge their results.
- Report per-language results because an overall average can hide weak Hindi or Hinglish retrieval.
- Preserve `runs.jsonl` with the exact source version and configuration used. If retrieval code changes, rerun the benchmark and keep the previous run file as a separate version.

## 5. Current scope

The template is not ground truth yet. The relevant timestamp intervals are deliberately blank and must be reviewed against the source videos. Do not report benchmark metrics until the labels are verified.
