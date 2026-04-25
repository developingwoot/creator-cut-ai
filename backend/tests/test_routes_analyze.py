"""Tests for routes/analyze.py — the SSE analysis pipeline route."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from main import app
from models.clip import Clip, ClipAnalysis, ClipStatus
from models.edit_plan import EditPlan, EditPlanStatus, EditSegment
from models.project import Project, ProjectStatus
import storage.database as db_mod
from storage.local import db_path, ensure_project_dirs


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE response body into a list of event dicts."""
    return [
        json.loads(line[6:])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def _make_brief() -> dict:
    return {
        "title": "Test Video",
        "story_summary": "A test story",
        "target_duration_seconds": 60,
        "tone": "upbeat",
    }


def _make_analysis() -> ClipAnalysis:
    return ClipAnalysis(quality_score=0.9, scene_mood="energetic", is_usable=True)


def _make_edit_plan(project_id: str) -> EditPlan:
    return EditPlan(
        id=str(uuid.uuid4()),
        project_id=project_id,
        status=EditPlanStatus.draft,
        segments=[
            EditSegment(
                order=0,
                clip_id=str(uuid.uuid4()),
                source_start=0.0,
                source_end=5.0,
            ).model_dump()
        ],
        total_duration_seconds=5.0,
        reasoning="test plan",
    )


# ── Test DB fixture ───────────────────────────────────────────────────────────


@pytest.fixture()
def test_env(tmp_path, monkeypatch):
    """Isolated SQLite DB and base_dir for each test."""
    original_engine = db_mod._engine
    db_mod._engine = None

    from config import settings
    monkeypatch.setattr(settings, "base_dir", tmp_path)

    from storage.database import create_tables
    create_tables(db_path(tmp_path))

    yield tmp_path

    db_mod._engine = original_engine


def _seed_db(base_dir: Path, n_clips: int = 1) -> tuple[str, list[str]]:
    """Insert a project + N clips; return (project_id, clip_ids)."""
    engine = db_mod._engine
    project_id = str(uuid.uuid4())
    clip_ids = [str(uuid.uuid4()) for _ in range(n_clips)]
    ensure_project_dirs(base_dir, project_id)
    with Session(engine) as s:
        s.add(Project(id=project_id, name="Test Project", status=ProjectStatus.created))
        for i, cid in enumerate(clip_ids):
            s.add(Clip(
                id=cid,
                project_id=project_id,
                filename=f"clip_{i}.mp4",
                original_path="/dev/null",
                order=i,
                status=ClipStatus.uploaded,
            ))
        s.commit()
    return project_id, clip_ids


# ── Validation (pre-stream) ───────────────────────────────────────────────────


class TestAnalyzeValidation:
    def test_404_when_project_not_found(self, test_env):
        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{uuid.uuid4()}/analyze", json=_make_brief())
        assert resp.status_code == 404

    def test_422_when_no_clips(self, test_env):
        project_id = str(uuid.uuid4())
        ensure_project_dirs(test_env, project_id)
        with Session(db_mod._engine) as s:
            s.add(Project(id=project_id, name="Empty"))
            s.commit()

        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{project_id}/analyze", json=_make_brief())
        assert resp.status_code == 422


# ── SSE pipeline flow ─────────────────────────────────────────────────────────


# Patches shared across happy-path tests
_PIPELINE_PATCHES = [
    "routes.analyze.generate_proxy",
    "routes.analyze.transcribe_clip",
    "routes.analyze.run_pass1",
    "routes.analyze.run_pass2",
]


def _make_fake_pass1(project_id: str, clip_id: str, analysis: ClipAnalysis):
    async def fake_pass1(*args, **kwargs):
        clip = Clip(
            id=clip_id,
            project_id=project_id,
            filename="clip_0.mp4",
            original_path="/dev/null",
            proxy_path="/dev/null",
            status=ClipStatus.analyzed,
            transcript={"segments": []},
        )
        return [(clip, analysis)]
    return fake_pass1


class TestAnalyzePipelineStream:
    def test_happy_path_emits_expected_stages(self, test_env):
        project_id, clip_ids = _seed_db(test_env, n_clips=1)
        clip_id = clip_ids[0]
        analysis = _make_analysis()
        proxy_file = test_env / "fake_proxy.mp4"
        proxy_file.write_bytes(b"fake")

        with (
            patch("routes.analyze.generate_proxy", return_value=proxy_file),
            patch("routes.analyze.transcribe_clip", return_value={"segments": []}),
            patch("routes.analyze.run_pass1", side_effect=_make_fake_pass1(project_id, clip_id, analysis)),
            patch("routes.analyze.run_pass2", new=AsyncMock(return_value=_make_edit_plan(project_id))),
        ):
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/analyze", json=_make_brief())

        assert resp.status_code == 200
        stages = [e["stage"] for e in _parse_sse(resp.text)]
        assert "proxying" in stages
        assert "transcribing" in stages
        assert "analyzing" in stages
        assert "planning" in stages
        assert stages[-1] == "done"

    def test_done_event_carries_edit_plan_id(self, test_env):
        project_id, clip_ids = _seed_db(test_env, n_clips=1)
        clip_id = clip_ids[0]
        analysis = _make_analysis()
        proxy_file = test_env / "p.mp4"
        proxy_file.write_bytes(b"x")

        with (
            patch("routes.analyze.generate_proxy", return_value=proxy_file),
            patch("routes.analyze.transcribe_clip", return_value={"segments": []}),
            patch("routes.analyze.run_pass1", side_effect=_make_fake_pass1(project_id, clip_id, analysis)),
            patch("routes.analyze.run_pass2", new=AsyncMock(return_value=_make_edit_plan(project_id))),
        ):
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/analyze", json=_make_brief())

        events = _parse_sse(resp.text)
        done_events = [e for e in events if e["stage"] == "done"]
        assert len(done_events) == 1
        assert "edit_plan_id" in done_events[0]

    def test_pipeline_lock_emits_error(self, test_env):
        project_id, _ = _seed_db(test_env, n_clips=1)
        from storage.local import pipeline_lock_path
        from config import settings

        lock = pipeline_lock_path(settings.base_dir, project_id)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()

        try:
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/analyze", json=_make_brief())

            events = _parse_sse(resp.text)
            assert len(events) == 1
            assert events[0]["stage"] == "error"
            assert "already running" in events[0]["message"]
        finally:
            lock.unlink(missing_ok=True)

    def test_lock_released_after_success(self, test_env):
        project_id, clip_ids = _seed_db(test_env, n_clips=1)
        clip_id = clip_ids[0]
        proxy_file = test_env / "p.mp4"
        proxy_file.write_bytes(b"x")

        with (
            patch("routes.analyze.generate_proxy", return_value=proxy_file),
            patch("routes.analyze.transcribe_clip", return_value={"segments": []}),
            patch("routes.analyze.run_pass1", side_effect=_make_fake_pass1(project_id, clip_id, _make_analysis())),
            patch("routes.analyze.run_pass2", new=AsyncMock(return_value=_make_edit_plan(project_id))),
        ):
            with TestClient(app) as client:
                client.post(f"/api/projects/{project_id}/analyze", json=_make_brief())

        from storage.local import pipeline_lock_path
        from config import settings
        assert not pipeline_lock_path(settings.base_dir, project_id).exists()

    def test_lock_released_after_error(self, test_env):
        project_id, _ = _seed_db(test_env, n_clips=1)
        proxy_file = test_env / "p.mp4"
        proxy_file.write_bytes(b"x")

        async def fail_pass1(*args, **kwargs):
            raise RuntimeError("pass1 exploded")

        with (
            patch("routes.analyze.generate_proxy", return_value=proxy_file),
            patch("routes.analyze.transcribe_clip", return_value={"segments": []}),
            patch("routes.analyze.run_pass1", side_effect=fail_pass1),
        ):
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/analyze", json=_make_brief())

        events = _parse_sse(resp.text)
        assert any(e["stage"] == "error" for e in events)

        from storage.local import pipeline_lock_path
        from config import settings
        assert not pipeline_lock_path(settings.base_dir, project_id).exists()
