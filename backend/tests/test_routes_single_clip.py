"""Tests for routes/single_clip.py — single-clip workflow SSE endpoints."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from main import app
from models.clip import Clip, ClipStatus, FillerSpan, SingleClipAnalysis, SilenceSpan
from models.project import Project, ProjectStatus
import storage.database as db_mod
from storage.local import db_path, ensure_project_dirs


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_sse(text: str) -> list[dict]:
    return [
        json.loads(line[6:])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


# ── Test DB fixture ───────────────────────────────────────────────────────────


@pytest.fixture()
def test_env(tmp_path, monkeypatch):
    original_engine = db_mod._engine
    db_mod._engine = None

    from config import settings
    monkeypatch.setattr(settings, "base_dir", tmp_path)

    from storage.database import create_tables
    create_tables(db_path(tmp_path))

    yield tmp_path

    db_mod._engine = original_engine


def _seed_project(base_dir: Path, n_clips: int = 1, with_analysis: bool = False) -> tuple[str, list[str]]:
    engine = db_mod._engine
    project_id = str(uuid.uuid4())
    clip_ids = [str(uuid.uuid4()) for _ in range(n_clips)]
    ensure_project_dirs(base_dir, project_id)

    analysis = None
    status = ClipStatus.uploaded
    if with_analysis:
        status = ClipStatus.sc_ready
        analysis = SingleClipAnalysis(
            filler_spans=[FillerSpan(start=0.5, end=0.8, word="um")],
            silence_spans=[SilenceSpan(start=2.0, end=2.5)],
            rename_suggestions=["Name A", "Name B", "Name C"],
            full_transcript_text="hello world",
        ).model_dump()

    with Session(engine) as s:
        s.add(Project(id=project_id, name="Test", status=ProjectStatus.created))
        for i, cid in enumerate(clip_ids):
            s.add(Clip(
                id=cid,
                project_id=project_id,
                filename=f"clip_{i}.mp4",
                original_path="/dev/null",
                duration_seconds=3.0,
                order=i,
                status=status,
                analysis=analysis,
            ))
        s.commit()
    return project_id, clip_ids


# ── Process endpoint — validation ─────────────────────────────────────────────


class TestProcessValidation:
    def test_404_project_not_found(self, test_env):
        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{uuid.uuid4()}/single-clip/process")
        assert resp.status_code == 404

    def test_422_no_clips(self, test_env):
        project_id = str(uuid.uuid4())
        ensure_project_dirs(test_env, project_id)
        with Session(db_mod._engine) as s:
            s.add(Project(id=project_id, name="Empty", status=ProjectStatus.created))
            s.commit()

        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{project_id}/single-clip/process")
        assert resp.status_code == 422

    def test_422_multiple_clips(self, test_env):
        project_id, _ = _seed_project(test_env, n_clips=2)
        with TestClient(app) as client:
            resp = client.post(f"/api/projects/{project_id}/single-clip/process")
        assert resp.status_code == 422


# ── Process endpoint — SSE stream ─────────────────────────────────────────────


class TestProcessStream:
    def test_happy_path_emits_all_stages(self, test_env):
        project_id, clip_ids = _seed_project(test_env, n_clips=1)
        fake_proxy = test_env / "fake_proxy.mp4"
        fake_proxy.write_bytes(b"fake")

        transcript = {"segments": [{"start": 0.0, "end": 2.0, "text": "hello"}], "words": []}

        with (
            patch("routes.single_clip.generate_proxy", return_value=fake_proxy),
            patch("routes.single_clip.transcribe_clip_with_words", return_value=transcript),
            patch("routes.single_clip.detect_fillers_from_words", return_value=[]),
            patch("routes.single_clip.detect_silence", return_value=[]),
            patch("routes.single_clip.suggest_renames", new=AsyncMock(return_value=["A", "B", "C"])),
        ):
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/single-clip/process")

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        stages = [e["stage"] for e in events]
        assert "proxying" in stages
        assert "transcribing" in stages
        assert "detecting" in stages
        assert "suggesting" in stages
        assert stages[-1] == "done"

    def test_done_event_carries_expected_keys(self, test_env):
        project_id, _ = _seed_project(test_env, n_clips=1)
        fake_proxy = test_env / "fake.mp4"
        fake_proxy.write_bytes(b"fake")

        transcript = {"segments": [{"start": 0.0, "end": 1.0, "text": "hi"}], "words": []}
        filler = [{"start": 0.1, "end": 0.3, "word": "um"}]

        with (
            patch("routes.single_clip.generate_proxy", return_value=fake_proxy),
            patch("routes.single_clip.transcribe_clip_with_words", return_value=transcript),
            patch("routes.single_clip.detect_fillers_from_words", return_value=filler),
            patch("routes.single_clip.detect_silence", return_value=[]),
            patch("routes.single_clip.suggest_renames", new=AsyncMock(return_value=["A", "B", "C"])),
        ):
            with TestClient(app) as client:
                resp = client.post(f"/api/projects/{project_id}/single-clip/process")

        done = next(e for e in _parse_sse(resp.text) if e["stage"] == "done")
        assert "transcript" in done
        assert "filler_spans" in done
        assert "silence_spans" in done
        assert "rename_suggestions" in done
        assert done["rename_suggestions"] == ["A", "B", "C"]
        assert len(done["filler_spans"]) == 1

    def test_lock_released_after_success(self, test_env):
        project_id, _ = _seed_project(test_env, n_clips=1)
        fake_proxy = test_env / "fake.mp4"
        fake_proxy.write_bytes(b"fake")

        transcript = {"segments": [], "words": []}
        with (
            patch("routes.single_clip.generate_proxy", return_value=fake_proxy),
            patch("routes.single_clip.transcribe_clip_with_words", return_value=transcript),
            patch("routes.single_clip.detect_fillers_from_words", return_value=[]),
            patch("routes.single_clip.detect_silence", return_value=[]),
            patch("routes.single_clip.suggest_renames", new=AsyncMock(return_value=["A", "B", "C"])),
        ):
            with TestClient(app) as client:
                client.post(f"/api/projects/{project_id}/single-clip/process")

        from storage.local import pipeline_lock_path
        assert not pipeline_lock_path(test_env, project_id).exists()


# ── Apply endpoint — validation ───────────────────────────────────────────────


class TestApplyValidation:
    def test_404_project_not_found(self, test_env):
        with TestClient(app) as client:
            resp = client.post(
                f"/api/projects/{uuid.uuid4()}/single-clip/apply",
                json={"remove_fillers": True},
            )
        assert resp.status_code == 404

    def test_422_when_not_processed(self, test_env):
        project_id, _ = _seed_project(test_env, n_clips=1, with_analysis=False)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/projects/{project_id}/single-clip/apply",
                json={"remove_fillers": True},
            )
        assert resp.status_code == 422

    def test_422_unsafe_filename(self, test_env):
        project_id, _ = _seed_project(test_env, n_clips=1, with_analysis=True)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/projects/{project_id}/single-clip/apply",
                json={"chosen_filename": "../../../etc/passwd"},
            )
        assert resp.status_code == 422


# ── Apply endpoint — SSE stream ───────────────────────────────────────────────


class TestApplyStream:
    def test_happy_path_emits_done_with_output_path(self, test_env):
        project_id, clip_ids = _seed_project(test_env, n_clips=1, with_analysis=True)
        fake_output = test_env / "output.mp4"
        fake_output.write_bytes(b"fake output")

        with patch(
            "routes.single_clip.apply_single_clip_edits",
            return_value=fake_output,
        ):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/projects/{project_id}/single-clip/apply",
                    json={"remove_fillers": True, "remove_silence": False},
                )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        stages = [e["stage"] for e in events]
        assert "applying" in stages
        assert stages[-1] == "done"
        done = events[-1]
        assert "output_path" in done

    def test_chosen_filename_renames_output(self, test_env):
        project_id, _ = _seed_project(test_env, n_clips=1, with_analysis=True)
        fake_output = test_env / "original_edited.mp4"
        fake_output.write_bytes(b"fake")

        with patch(
            "routes.single_clip.apply_single_clip_edits",
            return_value=fake_output,
        ):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/projects/{project_id}/single-clip/apply",
                    json={"remove_fillers": False, "chosen_filename": "my custom name"},
                )

        done = next(e for e in _parse_sse(resp.text) if e["stage"] == "done")
        assert "my custom name.mp4" in done["output_path"]

    def test_lock_released_after_apply(self, test_env):
        project_id, _ = _seed_project(test_env, n_clips=1, with_analysis=True)
        fake_output = test_env / "out.mp4"
        fake_output.write_bytes(b"fake")

        with patch("routes.single_clip.apply_single_clip_edits", return_value=fake_output):
            with TestClient(app) as client:
                client.post(
                    f"/api/projects/{project_id}/single-clip/apply",
                    json={"remove_fillers": False},
                )

        from storage.local import pipeline_lock_path
        assert not pipeline_lock_path(test_env, project_id).exists()
