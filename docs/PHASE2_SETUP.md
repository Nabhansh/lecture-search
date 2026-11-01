# Phase 2: Application layer

This patch adds a FastAPI search API and a Gradio interface around the existing
hybrid retrieval pipeline. It does not rewrite or tune the retrieval algorithm.

## Files added

- `app.py`: combined FastAPI + Gradio entry point.
- `src/lecture_search/search_service.py`: cached adapter that calls the existing
  functions in `scripts/search_hybrid.py`.
- `src/lecture_search/api.py`: `/api/health`, `/api/lectures`, `/api/search`, and
  `/media/{lecture_id}` routes.
- `src/lecture_search/ui.py`: multilingual search UI, ranked results, and
  timestamp-aware HTML5 video playback.
- `tests/test_phase2_app.py`: API, media-path, player, and UI smoke tests.

## Install

Use the existing project virtual environment and install the app dependencies:

```bash
source ~/venvs/lecture-search/bin/activate
cd ~/Documents/lecture-search
pip install 'fastapi>=0.115' 'uvicorn[standard]>=0.30' 'gradio>=5,<7'
```

The existing project dependencies (`faiss-cpu`, `fastembed`, `numpy`) are still
required for an actual search. Keep the existing versions used to build the
indexes; do not rebuild indexes as part of this phase.

## Run

```bash
cd ~/Documents/lecture-search
source ~/venvs/lecture-search/bin/activate
python app.py
```

Open `http://127.0.0.1:7860`. The API is available at:

- `GET /api/health`
- `GET /api/lectures`
- `POST /api/search`
- `GET /media/{lecture_id}`
- `GET /docs` for interactive API documentation

Example API request:

```bash
curl -X POST http://127.0.0.1:7860/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"FCFS में वेटिंग टाइम कैसे निकाला जाता है?","config":"base_auto","limit":10}'
```

## Video files

The original MP4s are intentionally not included in Git or this patch. The
application reads the `video_path` values already stored in
`data/processed/base_auto.jsonl`. Keep the original five lecture files at those
paths (the existing `data/raw/` symlinks are acceptable). The media endpoint
only serves a lecture file whose resolved path remains inside the project root.

The player uses an HTML media fragment (`#t=<seconds>`) so the browser seeks to
the selected transcript segment when the video metadata is loaded. The API
serves byte-range-capable `FileResponse` streams for seeking.

## Validate

```bash
python -m pytest -q tests/test_phase2_app.py
python -m pytest -q tests/test_intent_logic.py
```

The Phase 2 tests use a small fake media file and do not invoke the embedding
model. The existing intent tests validate the unchanged ranking code. Run a
real English, Hindi, and Hinglish search through the browser before treating
Phase 2 as complete.

## Local-only deployment

The default server binds to `127.0.0.1`, so the interface is only accessible
from the Fedora machine. Do not bind to `0.0.0.0` or enable Gradio sharing for
private lecture recordings unless you deliberately intend to expose them.
