from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from lecture_search.api import create_api_app
from lecture_search.search_service import HybridSearchService, format_timestamp
from lecture_search.ui import build_demo, render_player


def test_format_timestamp_handles_minutes_and_hours():
    assert format_timestamp(65.9) == "01:05"
    assert format_timestamp(3661.2) == "01:01:01"


def test_render_player_uses_timestamp_and_media_route():
    result = {
        "lecture_id": "os_l23_fcfs",
        "lecture_title": "FCFS",
        "start": 27.25,
        "text": "The criteria is arrival time.",
        "video_available": True,
    }
    html = render_player(result)
    assert "/media/os_l23_fcfs#t=27.250" in html
    assert "The criteria is arrival time." in html


def test_render_player_explains_missing_media():
    html = render_player({
        "lecture_id": "os_l23_fcfs",
        "lecture_title": "FCFS",
        "start": 10,
        "text": "Example transcript",
        "video_available": False,
    })
    assert "Video file not found" in html


def test_catalog_and_media_path_are_restricted_to_project(tmp_path: Path):
    project = tmp_path / "project"
    (project / "data/processed").mkdir(parents=True)
    (project / "data/raw").mkdir(parents=True)
    video = project / "data/raw/os_l23_fcfs.mp4"
    video.write_bytes(b"fake-mp4")
    transcript = project / "data/processed/base_auto.jsonl"
    transcript.write_text(json.dumps({
        "lecture_id": "os_l23_fcfs",
        "video_path": "data/raw/os_l23_fcfs.mp4",
    }) + "\n", encoding="utf-8")

    service = HybridSearchService(root=project, retrieval_module=object())
    assert service.media_path("os_l23_fcfs") == video.resolve()
    assert service.media_path("unknown") is None


def test_api_health_lectures_and_media(tmp_path: Path):
    project = tmp_path / "project"
    (project / "data/processed").mkdir(parents=True)
    (project / "data/raw").mkdir(parents=True)
    (project / "data/index").mkdir(parents=True)
    video = project / "data/raw/os_l23_fcfs.mp4"
    video.write_bytes(b"fake-mp4")
    (project / "data/processed/base_auto.jsonl").write_text(
        json.dumps({"lecture_id": "os_l23_fcfs", "video_path": "data/raw/os_l23_fcfs.mp4"}) + "\n",
        encoding="utf-8",
    )
    service = HybridSearchService(root=project, retrieval_module=object())
    client = TestClient(create_api_app(service))

    assert client.get("/api/health").status_code == 200
    lectures = client.get("/api/lectures")
    assert lectures.status_code == 200
    assert lectures.json()[0]["lecture_id"] == "os_l23_fcfs"
    response = client.get("/media/os_l23_fcfs")
    assert response.status_code == 200
    assert response.content == b"fake-mp4"
    assert client.get("/media/../../etc/passwd").status_code in {404, 422}


def test_gradio_demo_builds():
    service = HybridSearchService(root=Path.cwd(), retrieval_module=object())
    demo = build_demo(service)
    assert demo is not None


def test_search_service_delegates_to_existing_hybrid_pipeline(tmp_path: Path):
    (tmp_path / "data/processed").mkdir(parents=True)
    (tmp_path / "data/raw").mkdir(parents=True)
    video = tmp_path / "data/raw/os_l23_fcfs.mp4"
    video.write_bytes(b"video")
    (tmp_path / "data/processed/base_auto.jsonl").write_text(
        json.dumps({"lecture_id": "os_l23_fcfs", "video_path": "data/raw/os_l23_fcfs.mp4"}) + "\n",
        encoding="utf-8",
    )

    class FakeRetrieval:
        MODEL_NAME = "fake-model"
        TextEmbedding = object

        @staticmethod
        def get_keyword_rankings(config, query, maximum_results):
            assert (config, query, maximum_results) == ("base_auto", "FCFS waiting time", 1000)
            return {"chunk-1": 1}, {"chunk-1": -1.0}, ["fcfs"], "fcfs"

        @staticmethod
        def load_dense_resources(config):
            assert config == "base_auto"
            metadata = [{"chunk_id": "chunk-1"}]
            return object(), metadata, {"chunk-1": metadata[0]}

        @staticmethod
        def get_dense_rankings(index, metadata, model, query, candidate_count):
            assert query == "FCFS waiting time"
            assert candidate_count == 50
            return {"chunk-1": 1}, {"chunk-1": 0.9}

        @staticmethod
        def semantic_query_text(query):
            return query

        @staticmethod
        def reciprocal_rank_fusion(keyword_ranks, dense_ranks, metadata_by_id):
            return [{"chunk_id": "chunk-1", "metadata": metadata_by_id["chunk-1"]}]

        @staticmethod
        def select_unique_segments(fused_chunks, query, model, semantic_query=None):
            assert semantic_query == query
            return [{
                "lecture_id": "os_l23_fcfs",
                "start": 42.5,
                "end": 46.0,
                "text": "FCFS uses arrival time.",
                "video_path": "data/raw/os_l23_fcfs.mp4",
                "hybrid_score": 0.75,
                "segment_similarity": 0.91,
                "intent_match_score": 2,
            }]

    service = HybridSearchService(
        root=tmp_path,
        retrieval_module=FakeRetrieval,
        model_factory=lambda _retrieval: object(),
    )
    results = service.search("FCFS waiting time", "base_auto", 5)
    assert len(results) == 1
    assert results[0]["lecture_id"] == "os_l23_fcfs"
    assert results[0]["timestamp"] == "00:42"
    assert results[0]["video_available"] is True
    assert results[0]["video_url"] == "/media/os_l23_fcfs#t=42.500"


def test_api_search_endpoint_returns_ranked_results():
    class FakeService:
        def search(self, query, config, limit):
            return [{
                "rank": 1,
                "lecture_id": "os_l23_fcfs",
                "lecture_title": "Lecture 23 · FCFS",
                "start": 42.5,
                "end": 46.0,
                "timestamp": "00:42",
                "text": "FCFS uses arrival time.",
                "hybrid_score": 0.75,
                "segment_similarity": 0.91,
                "intent_match_score": 2,
                "video_available": True,
                "video_url": "/media/os_l23_fcfs#t=42.500",
            }]

        def list_lectures(self):
            return []

        def health(self):
            return {"status": "ok", "assets": {}, "lecture_count": 0}

        def media_path(self, lecture_id):
            return None

    client = TestClient(create_api_app(FakeService()))
    response = client.post("/api/search", json={
        "query": "FCFS waiting time",
        "config": "base_auto",
        "limit": 10,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["results"][0]["timestamp"] == "00:42"
    assert payload["results"][0]["video_url"].endswith("#t=42.500")

    invalid = client.post("/api/search", json={"query": "test", "config": "invalid"})
    assert invalid.status_code == 422
