# Hinglish Lecture Search: Multilingual Retrieval over Timestamped Lecture Recordings

**Project report**
**Evaluation snapshot:** 2 November 2026
**System scope:** five Operating Systems lectures; English, Hindi and Hinglish text queries

## Abstract

This project investigates a practical retrieval system for locating relevant moments inside recorded university lectures when students ask questions in English, Hindi or Hinglish. The system transcribes lecture audio into timestamped segments, indexes overlapping transcript chunks using lexical and multilingual dense retrieval, fuses the two retrieval lists, and returns ranked transcript moments linked to a local video player. The evaluation compares keyword, dense and hybrid retrieval under two transcript configurations. On a 30-query development benchmark, the `base_auto` hybrid configuration achieved segment Recall@1 of 0.833, Recall@5 of 0.933, Recall@10 of 1.000 and mean reciprocal rank (MRR) of 0.884. The `small_hi` hybrid configuration achieved Recall@1 of 0.800 and MRR of 0.808. The findings support hybrid retrieval as the strongest current configuration on this development set, while the limited corpus and non-held-out query set prevent claims of generalization.

## 1. Problem statement

Students often remember an explanation but not the lecture number or timestamp where it occurred. Conventional video search is usually based on titles, descriptions or exact words. This is insufficient when a student phrases a question differently from the lecturer, switches between Hindi and English, or writes Hindi words in Roman script.

The objective is to build a local system that accepts a text question in English, Hindi or Hinglish and returns a ranked list of transcript segments from lecture recordings, with timestamps that can be used to jump to the relevant video moment.

## 2. Scope and dataset

The prototype covers five Operating Systems recordings:

1. Lecture 23: FCFS scheduling (`os_l23_fcfs`).
2. Lecture 24: SJF scheduling (`os_l24_sjf`).
3. Lecture 31: Process Synchronization (`os_l39`).
4. Lecture 41: Deadlocks (`os_l41_deadlock`).
5. Lecture 58: Paging and Memory Management (`os_l58`).

The benchmark contains 30 manually checked queries: 10 English, 10 Hindi and 10 Hinglish. The same query set was used during development and ranking refinement. It is therefore a development set, not an independent held-out test set.

## 3. Method

### 3.1 Speech transcription and chunking

Lecture audio is transcribed with `faster-whisper`. Segment start and end times are retained. Two transcript configurations are compared: `base_auto` and `small_hi`. The segment stream is converted to overlapping 30-second chunks with a 20-second stride. Chunk metadata preserves the source lecture and time interval.

### 3.2 Keyword retrieval

SQLite FTS5 supplies lexical search over transcript chunks. It provides a strong signal when query terms and spoken transcript terms overlap, but may be affected by ASR spelling variation, Hindi tokenization and code-mixed Romanized vocabulary.

### 3.3 Dense retrieval

The system uses the multilingual `paraphrase-multilingual-MiniLM-L12-v2` embedding model (384 dimensions) with FAISS nearest-neighbour search. Dense retrieval is intended to bridge surface-form differences, although semantic similarity alone can rank a related explanation above the exact answer segment.

### 3.4 Hybrid retrieval and ranking

The hybrid strategy combines keyword and dense rankings with Reciprocal Rank Fusion (`k=60`). A query-aware ranking stage then selects timestamped segments, applies targeted intent signals and reduces redundant overlap. Query expansion and intent handling cover lecture terms and variants observed in English, Hindi and Romanized Hindi. The system returns the original segment's timestamp rather than the wider chunk boundary.

### 3.5 Application and playback

A FastAPI service exposes health, lecture-catalogue, search and media endpoints. A Gradio interface provides the search box, transcript configuration, ranked results and HTML5 video player. The player uses a media time fragment to request playback at the selected result's start time. The media endpoint supports HTTP byte ranges, which are required for efficient browser seeking.

## 4. Evaluation protocol

The benchmark evaluates 30 queries against two transcript configurations and three retrieval strategies (`keyword`, `dense`, `hybrid`), producing 180 retrieval runs. Relevant intervals were manually annotated. A returned segment is treated as a timestamp hit when it matches the correct lecture and falls within the annotated interval expanded by ±10 seconds.

The primary measures are:

- **Segment Recall@K:** fraction of queries with at least one correct lecture-and-timestamp segment in the top K results.
- **MRR:** mean reciprocal rank of the first correct lecture-and-timestamp segment.
- **Timestamp Hit@10:** fraction of queries with a timestamp-level hit within the top ten results.

Recall is computed at query level. The tolerance is a scoring allowance for approximate timestamps; it does not mean the player can seek inaccurately by ten seconds.

## 5. Results

### 5.1 Overall retrieval results

| Transcript configuration | Strategy | Recall@1 | Recall@5 | Recall@10 | MRR |
|---|---|---:|---:|---:|---:|
| `base_auto` | dense | 0.133 | 0.467 | 0.600 | 0.255 |
| `base_auto` | hybrid | **0.833** | **0.933** | **1.000** | **0.884** |
| `base_auto` | keyword | 0.200 | 0.467 | 0.800 | 0.327 |
| `small_hi` | dense | 0.167 | 0.333 | 0.533 | 0.251 |
| `small_hi` | hybrid | 0.800 | 0.800 | 0.867 | 0.808 |
| `small_hi` | keyword | 0.167 | 0.533 | 0.600 | 0.299 |

`base_auto` + hybrid is the strongest overall configuration on this development set. It retrieves a correct timestamped segment at rank 1 for 83.3% of queries, and at least one correct segment within the top ten for all 30 queries. `small_hi` + hybrid is the second strongest by Recall@1 and MRR.

Hybrid retrieval substantially improves ranking over dense-only and keyword-only search in both configurations. Keyword retrieval sometimes achieves useful Recall@10, but its low Recall@1 and MRR indicate that relevant passages often appear too far down the list. Dense retrieval alone also struggles to put the correct timestamped segment first. The hybrid combination is more effective at ranking precise transcript moments near the top.

### 5.2 Language-level results for the leading configuration

The following language-level figures are for `base_auto` + hybrid only:

| Query language | Queries | Recall@1 | MRR | Timestamp Hit@10 |
|---|---:|---:|---:|---:|
| English | 10 | 0.700 | 0.820 | 1.000 |
| Hindi | 10 | 0.800 | 0.831 | 1.000 |
| Hinglish | 10 | 1.000 | 1.000 | 1.000 |

These small per-language groups are useful diagnostics, not a statistically reliable language ranking. The perfect Hinglish score should not be generalized beyond the ten queries in this development set.

### 5.3 Figures

The following figures are generated by `scripts/generate_benchmark_figures.py` from the benchmark CSV exports:

- `figures/overall_recall_at_k.png`
- `figures/overall_mrr.png`
- `figures/language_performance.png`

## 6. Implementation verification

The project state recorded on 2 November 2026 includes:

- Five lecture sources represented in the transcript/index catalogue.
- Two transcript configurations and three retrieval strategies.
- A completed FastAPI and Gradio application layer.
- Health and lecture-catalogue endpoint checks.
- Search endpoint checks for English, Hindi and Hinglish examples.
- HTTP 206 byte-range responses for the five video media endpoints.
- 46 passing regression tests in the Fedora project environment.
- Browser timestamp seeking manually verified for all five lectures: FCFS, SJF, Process Synchronization, Deadlocks and Paging.

Browser testing subsequently confirmed that selecting search results for all five lectures loads the corresponding video and seeks playback to the displayed timestamp. All five lecture videos passed this manual timestamp-seeking verification.

## 7. Discussion

The results indicate that combining lexical evidence with multilingual semantic retrieval is useful for this small code-mixed lecture-search problem. Query-aware intent handling addresses a second problem: a passage can discuss the right subject without actually answering the question. The final ranking layer therefore needs to consider the requested intent and the content of the candidate segment, not only vector similarity or shared words.

The two transcript configurations also show that the Hindi-oriented transcription configuration does not automatically outperform the automatic-language configuration. Retrieval quality depends on more than the nominal ASR language setting: transcript recognition quality, query wording, vocabulary normalization, index contents and ranking behaviour all contribute. On the current benchmark, `base_auto` + hybrid is the best overall setting.

## 8. Limitations and threats to validity

1. **Small corpus:** only five Operating Systems lectures are indexed. Results may change substantially on other instructors, subjects, recording conditions or accents.
2. **Development-set evaluation:** the same 30 queries informed debugging and ranking refinement. The reported values are not unbiased held-out estimates.
3. **Small language groups:** each language has ten queries. Per-language results have high uncertainty and should be treated as diagnostic.
4. **ASR errors:** automatic transcripts can contain omissions, substitutions and inconsistent transliteration. Errors in the transcript can prevent retrieval even when the audio contains the answer.
5. **Annotation tolerance:** the ±10-second overlap tolerance is an evaluation rule. It may count a segment close to the answer as a hit even if a user would prefer a more precise jump.
6. **Limited modality coverage:** the completed MVP indexes speech transcripts. Slide OCR and visual slide retrieval are not implemented.
7. **Text-first interface:** voice query input and a learned reranker are outside the completed MVP.
8. **No user study:** usability, perceived answer quality and time saved for students have not been measured with participants.

## 9. Future work

The next research iteration should create a separately authored, held-out set of queries and annotate it before inspecting retrieval results. The corpus should expand to more lectures and courses. Additional work can evaluate transliteration-aware normalization, improved ASR for code-switched Hindi-English speech, slide OCR, a cross-encoder reranker, confidence-aware result presentation and user-centred usability. Voice input can be added as a separate interface feature after the text-search pipeline is stable.

## 10. Conclusion

The project delivers a working local prototype for searching timestamped Operating Systems lecture transcripts with English, Hindi and Hinglish text questions. Among the evaluated methods, hybrid retrieval with the `base_auto` transcript configuration achieved the strongest development-set performance (Recall@1 0.833, Recall@5 0.933, Recall@10 1.000 and MRR 0.884). The system also includes a FastAPI service, Gradio interface and range-capable video playback path. The next critical validation step is confirming visible timestamp seeking across every lecture and evaluating on a separate held-out query set before making broader performance claims.

## Reproduction commands

```bash
cd ~/Documents/lecture-search
source ~/venvs/lecture-search/bin/activate
python -m pytest -q tests/
python scripts/run_benchmark.py --overwrite
python scripts/score_benchmark.py --tolerance 10
python scripts/generate_benchmark_figures.py
python app.py
```

The benchmark commands regenerate the run log and score exports using the current code and local data. Preserve the exact code revision and query annotations used for every reported experiment.
