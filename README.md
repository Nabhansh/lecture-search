# Hinglish Lecture Search

A research prototype for searching Operating Systems lecture recordings with natural-language queries in English, Hindi, and Hinglish. Results return ranked transcript segments with timestamps.

## Implementation

- Timestamped transcripts generated with Faster-Whisper.
- SQLite FTS5 keyword retrieval and FAISS dense retrieval with multilingual embeddings.
- Hybrid retrieval using Reciprocal Rank Fusion (RRF).
- Query-intent ranking for FCFS, SJF, semaphores, deadlocks, critical sections, and paging.
- Automated benchmark scripts and intent-logic regression tests.

## Dataset

Five local Operating Systems lectures cover FCFS, SJF, process synchronization, deadlocks, and related process concepts. Lecture media files are excluded from Git because of their size.

## Retrieval benchmark

The 30-query benchmark is a development set, not a held-out test set. A result is relevant when its timestamp is within 10 seconds of an annotated interval.

| Configuration | Strategy | Recall@1 | Recall@5 | Recall@10 | MRR |
|---|---|---:|---:|---:|---:|
| base_auto | dense | 0.133 | 0.467 | 0.600 | 0.255 |
| base_auto | hybrid | 0.833 | 0.933 | 1.000 | 0.884 |
| base_auto | keyword | 0.200 | 0.467 | 0.800 | 0.327 |
| small_hi | dense | 0.167 | 0.333 | 0.533 | 0.251 |
| small_hi | hybrid | 0.800 | 0.800 | 0.867 | 0.808 |
| small_hi | keyword | 0.167 | 0.533 | 0.600 | 0.299 |

`base_auto` is the current default. These results do not establish generalization to unseen lectures or queries. Q024 has two annotated intervals for valid explanations of the resource-waiting scenario.

## Tests

Activate the project virtual environment, then run:

```bash
python -m pytest -v tests/test_intent_logic.py
```

The current intent-logic test suite contains 33 passing tests.

## Project status

Transcription, indexing, retrieval, ranking, and evaluation are implemented. The remaining application work includes a search service/API, Gradio interface, timestamp-aware video playback, final documentation, and a demo recording.

Lecture video files are not committed. Keep local media and generated large artifacts on the development machine.
