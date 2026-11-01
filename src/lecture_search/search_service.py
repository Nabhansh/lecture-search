"""Application-facing adapter for the existing hybrid retrieval pipeline.

This module deliberately delegates every retrieval/ranking decision to
scripts/search_hybrid.py. It adds caching and a stable result shape only.
"""
from __future__ import annotations

import importlib
import json
import math
import threading
from pathlib import Path
from typing import Any, Callable


SUPPORTED_CONFIGS = ("base_auto", "small_hi")
DEFAULT_CONFIG = "base_auto"
LECTURE_TITLES = {
    "os_l23_fcfs": "Lecture 23 · First Come First Serve (FCFS)",
    "os_l24_sjf": "Lecture 24 · Shortest Job First (SJF)",
    "os_l39": "Lecture 31 · Process Synchronization",
    "os_l41_deadlock": "Lecture 41 · Deadlocks",
    "os_l58": "Lecture 58 · Paging and Memory Management",
}


def format_timestamp(seconds: float) -> str:
    """Format a media offset as HH:MM:SS or MM:SS."""
    total = max(0, int(float(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


class HybridSearchService:
    """Cached, thread-safe facade over the repository's hybrid search code."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        retrieval_module: Any | None = None,
        model_factory: Callable[[Any], Any] | None = None,
        dense_candidates: int = 50,
        keyword_candidates: int = 1000,
    ) -> None:
        self.root = Path(root).resolve() if root else Path(__file__).resolve().parents[2]
        self.dense_candidates = max(1, int(dense_candidates))
        self.keyword_candidates = max(1, int(keyword_candidates))
        self._retrieval = retrieval_module
        self._model_factory = model_factory
        self._model: Any | None = None
        self._resources: dict[str, tuple[Any, list[dict[str, Any]], dict[str, dict[str, Any]]]] = {}
        self._catalog: dict[str, dict[str, Any]] | None = None
        self._lock = threading.RLock()

    def _get_retrieval(self) -> Any:
        if self._retrieval is None:
            # Import lazily so /api/health and /api/lectures work without
            # loading FAISS/FastEmbed or downloading the embedding model.
            self._retrieval = importlib.import_module("scripts.search_hybrid")
        return self._retrieval

    def _get_model(self, retrieval: Any) -> Any:
        if self._model is None:
            if self._model_factory:
                self._model = self._model_factory(retrieval)
            else:
                self._model = retrieval.TextEmbedding(model_name=retrieval.MODEL_NAME)
        return self._model

    def _get_resources(
        self, retrieval: Any, config: str
    ) -> tuple[Any, list[dict[str, Any]], dict[str, dict[str, Any]]]:
        if config not in self._resources:
            self._resources[config] = retrieval.load_dense_resources(config)
        return self._resources[config]

    def search(self, query: str, config: str = DEFAULT_CONFIG, limit: int = 10) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            raise ValueError("Enter a search query.")
        if len(query) > 500:
            raise ValueError("Search queries must be 500 characters or fewer.")
        if config not in SUPPORTED_CONFIGS:
            raise ValueError(f"Unsupported transcript configuration: {config}")
        if not 1 <= int(limit) <= 30:
            raise ValueError("Result limit must be between 1 and 30.")

        # FastEmbed model instances are shared. Serializing inference avoids
        # concurrent access to one runtime object from multiple web requests.
        with self._lock:
            retrieval = self._get_retrieval()
            keyword_ranks, _keyword_scores, _tokens, _fts_query = retrieval.get_keyword_rankings(
                config, query, self.keyword_candidates
            )
            index, metadata, metadata_by_id = self._get_resources(retrieval, config)
            model = self._get_model(retrieval)
            semantic_query = retrieval.semantic_query_text(query)
            dense_ranks, _dense_similarities = retrieval.get_dense_rankings(
                index, metadata, model, semantic_query, self.dense_candidates
            )
            fused_chunks = retrieval.reciprocal_rank_fusion(
                keyword_ranks, dense_ranks, metadata_by_id
            )
            ranked = retrieval.select_unique_segments(
                fused_chunks, query, model, semantic_query=semantic_query
            )

            output: list[dict[str, Any]] = []
            for rank, item in enumerate(ranked[: int(limit)], start=1):
                lecture_id = str(item.get("lecture_id", "unknown"))
                start = _finite_float(item.get("start", 0.0))
                end = _finite_float(item.get("end", start))
                catalog = self.get_lecture(lecture_id) or {}
                video_path = self._resolve_video_path(
                    str(item.get("video_path") or catalog.get("video_path") or "")
                )
                output.append({
                    "rank": rank,
                    "lecture_id": lecture_id,
                    "lecture_title": LECTURE_TITLES.get(lecture_id, _title_from_id(lecture_id)),
                    "start": start,
                    "end": end,
                    "timestamp": format_timestamp(start),
                    "text": str(item.get("text", "")),
                    "hybrid_score": _finite_float(item.get("hybrid_score", 0.0)),
                    "segment_similarity": _finite_float(item.get("segment_similarity", 0.0)),
                    "intent_match_score": int(item.get("intent_match_score", 0) or 0),
                    "video_available": bool(video_path and video_path.is_file()),
                    "video_url": f"/media/{lecture_id}#t={start:.3f}",
                })
            return output

    def list_lectures(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._catalog is None:
                catalog: dict[str, dict[str, Any]] = {}
                transcript_path = self.root / "data" / "processed" / "base_auto.jsonl"
                if transcript_path.exists():
                    with transcript_path.open("r", encoding="utf-8") as handle:
                        for line_number, line in enumerate(handle, start=1):
                            if not line.strip():
                                continue
                            try:
                                row = json.loads(line)
                            except json.JSONDecodeError as exc:
                                raise ValueError(
                                    f"Invalid JSON in {transcript_path}:{line_number}: {exc}"
                                ) from exc
                            lecture_id = str(row.get("lecture_id", "")).strip()
                            if lecture_id and lecture_id not in catalog:
                                video_path = str(row.get("video_path", ""))
                                path = self._resolve_video_path(video_path)
                                catalog[lecture_id] = {
                                    "lecture_id": lecture_id,
                                    "title": LECTURE_TITLES.get(lecture_id, _title_from_id(lecture_id)),
                                    "video_available": bool(path and path.is_file()),
                                    "video_path": video_path,
                                }
                self._catalog = catalog
            return [dict(item) for item in sorted(self._catalog.values(), key=lambda x: x["lecture_id"])]

    def get_lecture(self, lecture_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_lectures() if item["lecture_id"] == lecture_id), None)

    def _resolve_video_path(self, raw_path: str) -> Path | None:
        if not raw_path:
            return None
        path = Path(raw_path)
        candidate = path if path.is_absolute() else self.root / path
        try:
            resolved_root = self.root.resolve()
            resolved = candidate.resolve()
            resolved.relative_to(resolved_root)
        except (OSError, ValueError):
            return None
        if resolved.suffix.lower() not in {".mp4", ".webm", ".mov", ".m4v"}:
            return None
        return resolved

    def media_path(self, lecture_id: str) -> Path | None:
        lecture = self.get_lecture(lecture_id)
        if not lecture:
            return None
        path = self._resolve_video_path(str(lecture.get("video_path", "")))
        return path if path and path.is_file() else None

    def health(self) -> dict[str, Any]:
        index_dir = self.root / "data" / "index"
        assets = {
            "keyword_database": (index_dir / "keyword_search.db").is_file(),
            "dense_base_auto": (index_dir / "dense_base_auto.faiss").is_file()
            and (index_dir / "dense_base_auto_metadata.jsonl").is_file(),
            "dense_small_hi": (index_dir / "dense_small_hi.faiss").is_file()
            and (index_dir / "dense_small_hi_metadata.jsonl").is_file(),
            "transcripts": (self.root / "data" / "processed" / "base_auto.jsonl").is_file(),
        }
        return {
            "status": "ok" if all(assets.values()) else "degraded",
            "assets": assets,
            "lecture_count": len(self.list_lectures()),
        }


def _finite_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _title_from_id(lecture_id: str) -> str:
    return lecture_id.replace("_", " ").strip().title() or "Lecture"
