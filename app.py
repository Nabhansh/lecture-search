"""Run the FastAPI + Gradio Hinglish Lecture Search application."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import gradio as gr
import uvicorn

from lecture_search.api import create_api_app
from lecture_search.search_service import HybridSearchService
from lecture_search.ui import PHASE2_CSS, build_demo

service = HybridSearchService(root=ROOT)
api_app = create_api_app(service)
demo = build_demo(service)
app = gr.mount_gradio_app(api_app, demo, path="/", css=PHASE2_CSS)


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=7860, reload=False)
