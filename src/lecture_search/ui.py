"""Gradio interface for the hybrid lecture search service."""
from __future__ import annotations

import html
import logging
from typing import Any

import gradio as gr

from lecture_search.search_service import HybridSearchService, format_timestamp

logger = logging.getLogger(__name__)

PHASE2_CSS = """
.player-card { border: 1px solid var(--border-color-primary); border-radius: 14px; padding: 14px; }
.player-heading { display:flex; justify-content:space-between; gap:12px; align-items:center; flex-wrap:wrap; }
.player-heading h3 { margin: 0 0 10px 0; }
.transcript-preview { padding: 10px 12px; border-left: 3px solid var(--color-accent); background: var(--background-fill-secondary); border-radius: 6px; }
.missing-video { color: var(--body-text-color); font-weight: 600; }
.video-placeholder { padding: 28px; border: 1px dashed var(--border-color-primary); border-radius: 14px; color: var(--body-text-color-subdued); }
"""


def render_player(result: dict[str, Any] | None) -> str:
    if not result:
        return "<div class='video-placeholder'>Run a search, then select a result to open its lecture.</div>"

    title = html.escape(str(result.get("lecture_title", "Lecture")))
    timestamp = html.escape(format_timestamp(float(result.get("start", 0.0))))
    lecture_id = html.escape(str(result.get("lecture_id", "")), quote=True)
    text = html.escape(str(result.get("text", "")))
    if not result.get("video_available"):
        return (
            "<section class='player-card'>"
            f"<h3>{title}</h3><p><strong>Timestamp:</strong> {timestamp}</p>"
            f"<p>{text}</p>"
            "<p class='missing-video'>Video file not found. Place the original lecture MP4 at its configured path under data/raw/.</p>"
            "</section>"
        )

    start = max(0.0, float(result.get("start", 0.0)))
    # HTML media fragments seek the video to the timestamp before playback.
    # The lecture_id is taken from the server-side catalogue and HTML-escaped.
    src = f"/media/{lecture_id}#t={start:.3f}"
    return (
        "<section class='player-card'>"
        f"<div class='player-heading'><h3>{title}</h3><span>Starts at {timestamp}</span></div>"
        f"<video controls playsinline preload='metadata' src='{src}' "
        "style='width:100%;max-height:520px;background:#111;border-radius:12px'></video>"
        f"<p class='transcript-preview'>{text}</p>"
        f"<a href='{src}' target='_blank' rel='noopener'>Open this lecture at {timestamp}</a>"
        "</section>"
    )


def build_demo(service: HybridSearchService) -> gr.Blocks:
    with gr.Blocks(title="Hinglish Lecture Search") as demo:
        gr.Markdown(
            "# Hinglish Lecture Search\n"
            "Search your Operating Systems lectures in **English, हिन्दी, or Hinglish**. "
            "Results point to the transcript segment and the exact video timestamp."
        )
        with gr.Row():
            query = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. sir ne deadlock ka example kahan samjhaya?",
                lines=2,
                scale=7,
            )
            config = gr.Radio(
                choices=["base_auto", "small_hi"],
                value="base_auto",
                label="Transcript",
                info="base_auto is the current benchmark default.",
                scale=2,
            )
        with gr.Row():
            limit = gr.Slider(1, 20, value=10, step=1, label="Number of results")
            search_button = gr.Button("Search lectures", variant="primary")
        status = gr.Markdown("Ready.")
        result_state = gr.State([])
        results_table = gr.Dataframe(
            headers=["Rank", "Lecture", "Timestamp", "Hybrid score", "Transcript segment"],
            datatype=["number", "str", "str", "number", "str"],
            type="array",
            interactive=False,
            wrap=True,
            label="Ranked timestamp results",
        )
        gr.Markdown("### Lecture playback")
        player = gr.HTML(render_player(None))
        gr.Markdown(
            "**Try:** `FCFS में वेटिंग टाइम कैसे निकाला जाता है?` · "
            "`What is the purpose of a semaphore?` · "
            "`Processes resources ke liye wait karte rahein to kya situation banti hai?`"
        )

        def run_search(text: str, selected_config: str, result_limit: float):
            if not str(text or "").strip():
                return "Enter a question to search.", [], [], render_player(None)
            try:
                results = service.search(text, selected_config, int(result_limit))
            except Exception as exc:
                logger.exception("Gradio search failed")
                return f"Search failed: {html.escape(str(exc))}", [], [], render_player(None)

            rows = [
                [
                    item["rank"],
                    item["lecture_title"],
                    item["timestamp"],
                    round(float(item["hybrid_score"]), 6),
                    item["text"],
                ]
                for item in results
            ]
            if not results:
                return "No matching segments found. Try another phrasing or transcript configuration.", rows, results, render_player(None)
            available = sum(bool(item["video_available"]) for item in results)
            summary = f"Found **{len(results)}** timestamped results. **{available}** have local video files. Select a row to change the player."
            return summary, rows, results, render_player(results[0])

        def select_result(state: list[dict[str, Any]], evt: gr.SelectData):
            if not state:
                return render_player(None)
            index = evt.index[0] if isinstance(evt.index, (tuple, list)) else evt.index
            try:
                selected = state[int(index)]
            except (TypeError, ValueError, IndexError):
                return render_player(None)
            return render_player(selected)

        search_button.click(
            run_search,
            inputs=[query, config, limit],
            outputs=[status, results_table, result_state, player],
        )
        query.submit(
            run_search,
            inputs=[query, config, limit],
            outputs=[status, results_table, result_state, player],
        )
        results_table.select(select_result, inputs=[result_state], outputs=[player])

    return demo
