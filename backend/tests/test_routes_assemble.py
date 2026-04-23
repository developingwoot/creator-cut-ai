"""Tests for routes/assemble.py — edit plan approval and assembly SSE."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from main import app
from models.clip import Clip, ClipStatus
from models.edit_plan import EditPlan, EditPlanStatus, EditSegment
from models.project import Project, ProjectStatus
import storage.database as db_mod
from storage.local import db_path, ensure_project_dirs, pipeline_lock_path


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_sse(text: str) -> list[dict]:
    return [
        json.loads(line[6:])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def _make_segment(clip_id: str) -> dict:
    return EditSegment(
        order=0, clip_id=clip_id, source_start=0.0, source_end=2.0
    ).model_dump()


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


def _seed_project(base_dir: Path, with_plan: bool = False, plan_status: EditPlanStatus = EditPlanStatus.draft) -> tuple[str, str | None]:
    """Insert a project + one clip; optionally insert an edit plan. Returns (project_id, plan_id|None)."""
    engine = db_mod._engine
    project_id = str(uuid.uuid4())
    clip_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4()) if with_plan else None
    ensure_project_dirs(base_dir, project_id)

    with Session(engine) as s:
        s.add(Project(id=project_id, name="Test Project", status=ProjectStatus.ready_to_review))
        s.add(Clip(
            id=clip_id, project_id=project_id, filename="clip.mp4",
            original_path="/dev/null", status=ClipStatus.analyzed,
        ))
        s.commit()

    if with_plan:
        with Session(engine) as s:
            plan = EditPlan(
                id=plan_id,
                project_id=project_id,
                status=plan_status,
                segments=[_make_segment(clip_id)],
                total_duration_seconds=2.0,
                reasoning="test plan",
            )
            if plan_status == EditPlanStatus.approved:
                plan.approved_at = datetime.utcnow()
            s.add(plan)
            s.commit()

    return project_id, plan_id


# ── GET /edit-plan ────────────────────────────────────────────────────────────


class TestGetEditPlan:
    def test_404_when_no_project(self, test_env):
        with TestClient(app) as client:
            resp = client.get(f"/api/projects/{uuid.uuid4()}/edit-plan")
        assert resp.status_code == 404

    def test_404_when_no_plan(self, test_env):
        project_id, _ = _seed_project(test_env, with_plan=False)
        with TestClient(app) as client:
            resp = client.get(f"/api/projects/{project_id}/edit-plan")
        assert resp.status_code == 404

    def test_returns_plan_when_exists(self, test_env):
        project_id, plan_id = _seed_project(test_env, with_plan=True)
        with TestClient(app) as client:
            resp = client.get(f"/api/projects/{project_id}/edit-plan")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == plan_id
        assert body["status"] == "draft"
        assert body["segments"] is not None


# ── POST /edit-plan/approve ───────────────────────────────────────────────────


class TestApproveEditPlan:
    def test_404_when_no_project(self, test_env):
        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{uuid.uuid4()}/edit-plan/approve", json={"approved": True})
        assert resp.status_code == 404

    def test_404_when_no_plan(self, test_env):
        project_id, _ = _seed_project(test_env, with_plan=False)
        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{project_id}/edit-plan/approve", json={"approved": True})
        assert resp.status_code == 404

    def test_approval_sets_status_and_approved_at(self, test_env):
        project_id, plan_id = _seed_project(test_env, with_plan=True)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/projects/{project_id}/edit-plan/approve",
                json={"approved": True},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["approved_at"] is not None

    def test_rejection_sets_status_without_approved_at(self, test_env):
        project_id, plan_id = _seed_project(test_env, with_plan=True)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/projects/{project_id}/edit-plan/approve",
                json={"approved": False},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["approved_at"] is None

    def test_409_when_not_draft(self, test_env):
        project_id, _ = _seed_project(test_env, with_plan=True, plan_status=EditPlanStatus.approved)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/projects/{project_id}/edit-plan/approve",
                json={"approved": True},
            )
        assert resp.status_code == 409
        assert "already" in resp.json()["detail"]


# ── POST /assemble ────────────────────────────────────────────────────────────


class TestAssembleStream:
    def test_404_when_no_project(self, test_env):
        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{uuid.uuid4()}/assemble")
        assert resp.status_code == 404

    def test_409_when_no_approved_plan(self, test_env):
        project_id, _ = _seed_project(test_env, with_plan=True, plan_status=EditPlanStatus.draft)
        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{project_id}/assemble")
        assert resp.status_code == 409

    def test_lock_emits_error_event(self, test_env):
        project_id, _ = _seed_project(test_env, with_plan=True, plan_status=EditPlanStatus.approved)
        from config import settings
        lock = pipeline_lock_path(settings.base_dir, project_id)
        lock.touch()
        try:
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/assemble")
            events = _parse_sse(resp.text)
            assert events[0]["stage"] == "error"
            assert "already running" in events[0]["message"]
        finally:
            lock.unlink(missing_ok=True)

    def test_happy_path_emits_done(self, test_env):
        project_id, _ = _seed_project(test_env, with_plan=True, plan_status=EditPlanStatus.approved)
        fake_output = test_env / "output.mp4"
        fake_output.write_bytes(b"fake")

        with patch("routes.assemble.assemble", return_value=fake_output):
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/assemble")

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert events[-1]["stage"] == "done"
        assert "output_path" in events[-1]

    def test_lock_released_after_success(self, test_env):
        project_id, _ = _seed_project(test_env, with_plan=True, plan_status=EditPlanStatus.approved)
        fake_output = test_env / "output.mp4"
        fake_output.write_bytes(b"fake")

        with patch("routes.assemble.assemble", return_value=fake_output):
            with TestClient(app) as client:
                client.post(f"/api/projects/{project_id}/assemble")

        from config import settings
        assert not pipeline_lock_path(settings.base_dir, project_id).exists()

    def test_lock_released_after_error(self, test_env):
        project_id, _ = _seed_project(test_env, with_plan=True, plan_status=EditPlanStatus.approved)

        with patch("routes.assemble.assemble", side_effect=Exception("boom")):
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/assemble")

        from config import settings
        assert not pipeline_lock_path(settings.base_dir, project_id).exists()
        events = _parse_sse(resp.text)
        assert any(e["stage"] == "error" for e in events)
