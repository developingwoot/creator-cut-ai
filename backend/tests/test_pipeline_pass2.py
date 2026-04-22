"""Tests for pipeline/pass2_edit_planning.py."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from exceptions import ClaudeAPIError, InvalidClaudeResponseError, PipelineError
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


def _make_client(response_text: str) -> MagicMock:
    content_block = MagicMock()
    content_block.text = response_text

    mock_response = MagicMock()
    mock_response.content = [content_block]

    client = MagicMock()
    client.messages.create.return_value = mock_response
    return client


# ── _load_sfx_ids ─────────────────────────────────────────────────────────────


class TestLoadSfxIds:
    def test_returns_filenames_from_manifest(self):
        ids = _load_sfx_ids()
        assert isinstance(ids, list)
        # Manifest has at least one entry if the file exists.
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
    def _pair(self) -> tuple[Clip, ClipAnalysis]:
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
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        result = run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert isinstance(result, EditPlan)

    def test_status_is_draft(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        result = run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert result.status == EditPlanStatus.draft

    def test_segments_stored(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        result = run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert isinstance(result.segments, list)
        assert len(result.segments) == 1

    def test_total_duration_set(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        result = run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert result.total_duration_seconds == pytest.approx(4.0)

    def test_reasoning_stored(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        result = run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert result.reasoning == "Started with the strongest moment."

    def test_project_id_set(self, tmp_path):
        clip, analysis = self._pair()
        project_id = str(uuid.uuid4())
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        result = run_pass2([(clip, analysis)], _make_brief(), project_id, tmp_path, client=client)
        assert result.project_id == project_id

    def test_empty_clip_analyses_raises(self, tmp_path):
        with pytest.raises(PipelineError):
            run_pass2([], _make_brief(), str(uuid.uuid4()), tmp_path, client=MagicMock())

    def test_bad_json_retries_and_raises(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client("not json at all")
        with pytest.raises(InvalidClaudeResponseError):
            run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert client.messages.create.call_count == 3

    def test_bad_schema_retries_and_raises(self, tmp_path):
        clip, analysis = self._pair()
        # Valid JSON but wrong shape — missing segments.
        client = _make_client(json.dumps({"reasoning": "oops"}))
        with pytest.raises(InvalidClaudeResponseError):
            run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)

    def test_segment_validation_failure_retries(self, tmp_path):
        clip, analysis = self._pair()
        # source_end <= source_start violates EditSegment validator.
        bad_plan = {
            "segments": [
                {
                    "order": 0,
                    "clip_id": clip.id,
                    "source_start": 10.0,
                    "source_end": 5.0,  # before source_start
                    "is_broll": False,
                    "narration_note": "",
                    "b_roll_overlays": [],
                    "sound_cues": [],
                }
            ],
            "total_duration_seconds": 0.0,
            "reasoning": "",
        }
        client = _make_client(json.dumps(bad_plan))
        with pytest.raises(InvalidClaudeResponseError):
            run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert client.messages.create.call_count == 3

    def test_api_error_retries_and_raises(self, tmp_path):
        clip, analysis = self._pair()
        client = MagicMock()
        client.messages.create.side_effect = anthropic.APIError(
            message="server error", request=MagicMock(), body=None
        )
        with pytest.raises(ClaudeAPIError):
            run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert client.messages.create.call_count == 3

    def test_cached_system_prompt(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        system = client.messages.create.call_args.kwargs["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_uses_opus_model(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        assert client.messages.create.call_args.kwargs["model"] == "claude-opus-4-7"

    def test_rejection_feedback_in_user_message(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        run_pass2(
            [(clip, analysis)],
            _make_brief(),
            clip.project_id,
            tmp_path,
            client=client,
            rejection_feedback="pacing is too slow",
        )
        user_content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "pacing is too slow" in user_content

    def test_no_rejection_feedback_not_in_message(self, tmp_path):
        clip, analysis = self._pair()
        client = _make_client(json.dumps(_valid_plan_dict(clip.id)))
        run_pass2([(clip, analysis)], _make_brief(), clip.project_id, tmp_path, client=client)
        user_content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "rejected" not in user_content
