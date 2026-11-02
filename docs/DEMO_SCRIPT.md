# Demo Recording Script

**Target duration:** 3–4 minutes
**Format:** 1080p screen recording with clear microphone narration
**Application:** `http://127.0.0.1:7860`

## Before recording

1. Activate the project virtual environment and start `python app.py`.
2. Open the app in a clean browser window.
3. Confirm all five source MP4 files are available to the application.
4. Close unrelated terminals, notifications and private browser tabs.
5. Keep the API docs available in another tab only if you plan to demonstrate the API.

## Shot list and narration

### 0:00–0:20 — Problem and goal

**Show:** Project title and the search interface.

**Narration:** “Hinglish Lecture Search helps students find the exact moment a concept was explained in an Operating Systems lecture. Instead of manually scrubbing through long recordings, a student can ask a question in English, Hindi or Hinglish and receive timestamped transcript results.”

### 0:20–0:55 — Search in mixed language

**Enter:** `Processes resources ke liye wait karte rahein to kya situation banti hai?`

**Show:** Ranked results and the returned lecture/timestamp.

**Narration:** “The system accepts code-mixed queries. It combines lexical retrieval with multilingual semantic retrieval, then ranks timestamped transcript segments.”

### 0:55–1:30 — Jump to the relevant video moment

**Show:** Select the first result. Show the player and the timestamp label. Wait for playback and make the player's current position visible.

**Narration:** “Each result is connected to its source lecture. Selecting a result opens the recording at the corresponding segment time.”

Do not claim exact seeking unless the visible player position has been checked during the recording.

### 1:30–2:10 — Demonstrate language coverage and another topic

Use one Hindi or English query, for example:

- `FCFS में वेटिंग टाइम कैसे निकाला जाता है?`
- `What is the critical section in process synchronization?`
- `Why is a process divided into pages?`

**Show:** The returned transcript, lecture title and timestamp.

### 2:10–2:50 — Explain evaluation

**Show:** `docs/figures/overall_recall_at_k.png` and `docs/figures/overall_mrr.png`.

**Narration:** “We evaluated 30 manually checked development queries, ten per language, across two transcript configurations and three retrieval strategies. That produced 180 retrieval runs. The strongest configuration was base_auto with hybrid retrieval, with Recall@1 of 0.833 and MRR of 0.884. This is a development-set result, not a held-out test result.”

### 2:50–3:20 — Architecture and close

**Show:** The architecture diagram in `docs/ARCHITECTURE.md` or the API docs page.

**Narration:** “The pipeline uses timestamped speech transcription, SQLite FTS5 keyword search, multilingual embeddings with FAISS, reciprocal-rank fusion, and a local API and browser interface. The current prototype focuses on five Operating Systems lectures. Expanding the corpus and validating on an independent query set are the next research steps.”

## Recording checklist

- [ ] Search query is readable on screen.
- [ ] The correct lecture title is visible.
- [ ] The timestamp is visible in the selected result.
- [ ] Player visibly starts near the target timestamp.
- [ ] No error dialog or missing-video message appears.
- [ ] Benchmark figures are legible.
- [ ] The narration calls the 30-query evaluation a development set.
- [ ] No credentials, private tokens or unrelated personal data appear.
