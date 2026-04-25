"""Tests for pipeline/pass2_edit_planning.py."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from exceptions import InvalidOllamaResponseError, PipelineError
from models.clip import Clip, ClipAnalysis, ClipStatus
from models.edit_plan import EditPlan, EditPlanStatus
from models.project import StoryBrief
from pipeline.pass2_edit_planning import (
    _build_user_message,
    _load_sfx_ids,
    run_pass2,
)


# ── Fixtures / helpers ────────────────────────────────────────────────────────


def _make_clip(clip_id: str | None = None, duration: float = 60.0) -> Clip:
    return Clip(
        id=clip_id or str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        filename="test.mp4",
        original_path="/footage/test.mp4",
        duration_seconds=duration,
        status=ClipStatus.analyzed,
    )


def _make_analysis(quality: float = 0.8) -> ClipAnalysis:
    return ClipAnalysis(
        quality_score=quality,
        key_moments=[{"start": 1.0, "end": 5.0, "description": "good moment"}],
        filler_spans=[],
        b_roll_tags=["outdoor"],
        scene_mood="calm",
        is_usable=True,
        notes="",
    )


def _make_brief(**kwargs) -> StoryBrief:
    defaults = dict(
        title="My Video",
        story_summary="A test video about testing.",
        target_duration_seconds=300,
        tone="informational",
        key_moments=["intro", "conclusion"],
        b_roll_preferences=["outdoor"],
    )
    return StoryBrief(**{**defaults, **kwargs})


def _valid_plan_dict(clip_id: str) -> dict:
    return {
        "segments": [
            {
                "order": 0,
                "clip_id": clip_id,
                "source_start": 1.0,
                "source_end": 5.0,
                "is_broll": False,
                "narration_note": "Opening hook",
                "b_roll_overlays": [],
                "sound_cues": [],
            }
        ],
        "total_duration_seconds": 4.0,
        "reasoning": "Started with the strongest moment.",
    }


def _patch_ollama(response_text: str):
    """Patch ollama_client.generate to always return response_text."""
    return patch(
        "pipeline.pass2_edit_planning.ollama_client.generate",
        new=AsyncMock(return_value=response_text),
    )


# ── _load_sfx_ids ─────────────────────────────────────────────────────────────


class TestLoadSfxIds:
    def test_returns_filenames_from_manifest(self):
        ids = _load_sfx_ids()
        assert isinstance(ids, list)
        if ids:
            assert all(isinstance(s, str) for s in ids)

    def test_missing_manifest_returns_empty_list(self, tmp_path):
        with patch("pipeline.pass2_edit_planning._SFX_MANIFEST", tmp_path / "nonexistent.json"):
            result = _load_sfx_ids()
        assert result == []

    def test_malformed_manifest_returns_empty_list(self, tmp_path):
        bad = tmp_path / "manifest.json"
        bad.write_text("not json")
        with patch("pipeline.pass2_edit_planning._SFX_MANIFEST", bad):
            result = _load_sfx_ids()
        assert result == []


# ── _build_user_message ───────────────────────────────────────────────────────


class TestBuildUserMessage:
    def _pair(self):
        clip = _make_clip()
        return clip, _make_analysis()

    def test_contains_brief_title(self):
        brief = _make_brief(title="Unique Title XYZ")
        msg = _build_user_message(brief, [self._pair()], [], None)
        assert "Unique Title XYZ" in msg

    def test_contains_clip_id(self):
        clip, analysis = self._pair()
        msg = _build_user_message(_make_brief(), [(clip, analysis)], [], None)
        assert clip.id in msg

    def test_no_rejection_block_when_none(self):
        msg = _build_user_message(_make_brief(), [self._pair()], [], None)
        assert "rejected" not in msg

    def test_rejection_block_injected(self):
        msg = _build_user_message(_make_brief(), [self._pair()], [], "too many cuts")
        assert "rejected" in msg
        assert "too many cuts" in msg

    def test_sfx_ids_listed(self):
        msg = _build_user_message(_make_brief(), [self._pair()], ["whoosh.wav", "impact.wav"], None)
        assert "whoosh.wav" in msg
        assert "impact.wav" in msg

    def test_no_sfx_shows_none_available(self):
        msg = _build_user_message(_make_brief(), [self._pair()], [], None)
        assert "(none available)" in msg

    def test_target_duration_formatted(self):
        brief = _make_brief(target_duration_seconds=125)
        msg = _build_user_message(brief, [self._pair()], [], None)
        assert "2m 5s" in msg

    def test_empty_key_moments_shows_none_specified(self):
        brief = _make_brief(key_moments=[])
        msg = _build_user_message(brief, [self._pair()], [], None)
        assert "None specified" in msg


# ── run_pass2 ─────────────────────────────────────────────────────────────────


class TestRunPass2:
    def _pair(self, quality: float = 0.8, duration: float = 60.0):
        clip = _make_clip(duration=duration)
        return clip, _make_analysis(quality=quality)

    def test_returns_edit_plan(self, tmp_path):
        clip, analysis = self._pair()
        # Patch ollama twice: draft call + self-critique call
        with _patch_ollama(json.dumps(_valid_plan_dict(clip.id))):
            result = asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        assert isinstance(result, EditPlan)

    def test_status_is_draft(self, tmp_path):
        clip, analysis = self._pair()
        with _patch_ollama(json.dumps(_valid_plan_dict(clip.id))):
            result = asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        assert result.status == EditPlanStatus.draft

    def test_segments_stored(self, tmp_path):
        clip, analysis = self._pair()
        with _patch_ollama(json.dumps(_valid_plan_dict(clip.id))):
            result = asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        assert isinstance(result.segments, list)
        assert len(result.segments) == 1

    def test_total_duration_set(self, tmp_path):
        clip, analysis = self._pair()
        with _patch_ollama(json.dumps(_valid_plan_dict(clip.id))):
            result = asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        assert result.total_duration_seconds == pytest.approx(4.0)

    def test_reasoning_stored(self, tmp_path):
        clip, analysis = self._pair()
        with _patch_ollama(json.dumps(_valid_plan_dict(clip.id))):
            result = asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        assert result.reasoning == "Started with the strongest moment."

    def test_project_id_set(self, tmp_path):
        clip, analysis = self._pair()
        project_id = str(uuid.uuid4())
        with _patch_ollama(json.dumps(_valid_plan_dict(clip.id))):
            result = asyncio.run(run_pass2([(clip, analysis)], _make_brief(), project_id, tmp_path))
        assert result.project_id == project_id

    def test_empty_clip_analyses_raises(self, tmp_path):
        with _patch_ollama("{}"):
            with pytest.raises(PipelineError):
                asyncio.run(run_pass2([], _make_brief(), str(uuid.uuid4()), tmp_path))

    def test_bad_json_retries_and_raises(self, tmp_path):
        clip, analysis = self._pair()
        mock = AsyncMock(return_value="not json at all")
        with patch("pipeline.pass2_edit_planning.ollama_client.generate", mock):
            with pytest.raises(InvalidOllamaResponseError):
                asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        # 3 retries for draft + self-critique falls back, so mock call count ≥ 3
        assert mock.call_count >= 3

    def test_bad_schema_retries_and_raises(self, tmp_path):
        clip, analysis = self._pair()
        with _patch_ollama(json.dumps({"reasoning": "oops"})):
            with pytest.raises(InvalidOllamaResponseError):
                asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))

    def test_rejection_feedback_in_user_message(self, tmp_path):
        clip, analysis = self._pair()
        mock = AsyncMock(return_value=json.dumps(_valid_plan_dict(clip.id)))
        with patch("pipeline.pass2_edit_planning.ollama_client.generate", mock):
            asyncio.run(
                run_pass2(
                    [(clip, analysis)],
                    _make_brief(),
                    clip.project_id,
                    tmp_path,
                    rejection_feedback="pacing is too slow",
                )
            )
        # The first generate call should include the rejection feedback
        first_call_prompt = mock.call_args_list[0].kwargs.get("prompt") or mock.call_args_list[0].args[1]
        assert "pacing is too slow" in first_call_prompt

    def test_no_rejection_feedback_absent(self, tmp_path):
        clip, analysis = self._pair()
        mock = AsyncMock(return_value=json.dumps(_valid_plan_dict(clip.id)))
        with patch("pipeline.pass2_edit_planning.ollama_client.generate", mock):
            asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        first_call_prompt = mock.call_args_list[0].kwargs.get("prompt") or mock.call_args_list[0].args[1]
        assert "rejected" not in first_call_prompt

    def test_self_critique_called(self, tmp_path):
        """run_pass2 makes at least 2 Ollama calls: draft + critique."""
        clip, analysis = self._pair()
        mock = AsyncMock(return_value=json.dumps(_valid_plan_dict(clip.id)))
        with patch("pipeline.pass2_edit_planning.ollama_client.generate", mock):
            asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        assert mock.call_count >= 2

    def test_uses_configured_llm_model(self, tmp_path):
        clip, analysis = self._pair()
        mock = AsyncMock(return_value=json.dumps(_valid_plan_dict(clip.id)))
        with patch("pipeline.pass2_edit_planning.ollama_client.generate", mock):
            asyncio.run(run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path))
        from config import settings
        called_model = mock.call_args_list[0].kwargs.get("model") or mock.call_args_list[0].args[0]
        assert called_model == settings.ollama_llm_model
