"""FastAPI routes for the Hinglish Lecture Search application."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from lecture_search.search_service import HybridSearchService

logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    config: Literal["base_auto", "small_hi"] = "base_auto"
    limit: int = Field(default=10, ge=1, le=30)


def create_api_app(service: HybridSearchService | None = None) -> FastAPI:
    engine = service or HybridSearchService()
    app = FastAPI(
        title="Hinglish Lecture Search API",
        description="Search Operating Systems lectures in English, Hindi, and Hinglish.",
        version="0.1.0",
    )
    app.state.search_service = engine

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        return engine.health()

    @app.get("/api/lectures", tags=["lectures"])
    def lectures() -> list[dict]:
        return [
            {key: value for key, value in item.items() if key != "video_path"}
            for item in engine.list_lectures()
        ]

    @app.post("/api/search", tags=["search"])
    def search(payload: SearchRequest) -> dict:
        try:
            results = engine.search(payload.query, payload.config, payload.limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FileNotFoundError, RuntimeError) as exc:
            logger.exception("Search resources unavailable")
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # keep implementation details out of client responses
            logger.exception("Unexpected search failure")
            raise HTTPException(status_code=500, detail="Search failed. Check the application log.") from exc
        return {
            "query": payload.query,
            "config": payload.config,
            "total": len(results),
            "results": results,
        }

    @app.get("/media/{lecture_id}", tags=["media"])
    def media(lecture_id: str) -> FileResponse:
        path = engine.media_path(lecture_id)
        if path is None:
            raise HTTPException(
                status_code=404,
                detail=f"Video for lecture '{lecture_id}' is unavailable. Check data/raw/ and the video filename.",
            )
        # FileResponse supports HTTP byte ranges in current Starlette releases,
        # allowing the browser to seek without downloading the whole lecture.
        return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "private, max-age=300"})

    return app
