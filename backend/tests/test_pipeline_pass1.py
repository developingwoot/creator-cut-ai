"""Tests for pipeline/pass1_clip_analysis.py."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from exceptions import ClaudeAPIError, FrameExtractionError, InvalidClaudeResponseError
from models.clip import Clip, ClipAnalysis, ClipStatus
from pipeline.pass1_clip_analysis import (
    _downsample,
    _transcript_text,
    analyse_clip,
    extract_frames,
)
from pipeline.proxy import generate_proxy


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_clip(original_path: str | Path, proxy_path: str | Path | None = None) -> Clip:
    return Clip(
        id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        filename=Path(str(original_path)).name,
        original_path=str(original_path),
        proxy_path=str(proxy_path) if proxy_path else None,
    )


def _valid_analysis_dict() -> dict:
    return {
        "quality_score": 0.8,
        "key_moments": [{"start": 0.5, "end": 1.5, "description": "test moment"}],
        "filler_spans": [],
        "b_roll_tags": ["outdoor"],
        "scene_mood": "calm",
        "is_usable": True,
        "notes": "",
    }


def _make_client(response_text: str) -> MagicMock:
    """Return a mock Anthropic client whose messages.create returns response_text."""
    content_block = MagicMock()
    content_block.text = response_text

    mock_response = MagicMock()
    mock_response.content = [content_block]

    client = MagicMock()
    client.messages.create.return_value = mock_response
    return client


def _proxy_clip(fixture_clip_path: Path, tmp_path: Path) -> Clip:
    clip = _make_clip(fixture_clip_path)
    proxy = generate_proxy(clip, clip.project_id, tmp_path)
    clip.proxy_path = str(proxy)
    clip.duration_seconds = 3.0
    return clip


# ── _downsample ───────────────────────────────────────────────────────────────


class TestDownsample:
    def test_fewer_than_max_unchanged(self, tmp_path):
        paths = [tmp_path / f"f{i}.jpg" for i in range(5)]
        assert _downsample(paths, 12) == paths

    def test_caps_at_max(self, tmp_path):
        paths = [tmp_path / f"f{i}.jpg" for i in range(20)]
        result = _downsample(paths, 12)
        assert len(result) == 12

    def test_includes_first_and_last(self, tmp_path):
        paths = [tmp_path / f"f{i}.jpg" for i in range(20)]
        result = _downsample(paths, 12)
        assert result[0] == paths[0]
        assert result[-1] == paths[-1]

    def test_empty_input(self, tmp_path):
        assert _downsample([], 12) == []


# ── _transcript_text ──────────────────────────────────────────────────────────


class TestTranscriptText:
    def test_none_returns_placeholder(self):
        assert _transcript_text(None) == "(no transcript available)"

    def test_empty_segments_returns_placeholder(self):
        assert _transcript_text({"segments": []}) == "(no transcript available)"

    def test_joins_segment_text(self):
        t = {"segments": [{"start": 0, "end": 1, "text": " hello "}, {"start": 1, "end": 2, "text": " world "}]}
        assert _transcript_text(t) == "hello world"


# ── extract_frames ────────────────────────────────────────────────────────────


class TestExtractFrames:
    def test_returns_list_of_paths(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        proxy = Path(clip.proxy_path)
        out_dir = tmp_path / "frames"
        frames = extract_frames(proxy, out_dir)
        assert isinstance(frames, list)
        assert all(p.suffix == ".jpg" for p in frames)

    def test_files_exist_on_disk(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        proxy = Path(clip.proxy_path)
        out_dir = tmp_path / "frames"
        frames = extract_frames(proxy, out_dir)
        assert all(p.exists() for p in frames)

    def test_never_exceeds_max_frames(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        proxy = Path(clip.proxy_path)
        out_dir = tmp_path / "frames"
        frames = extract_frames(proxy, out_dir, max_frames=2)
        assert len(frames) <= 2

    def test_bad_proxy_raises_frame_extraction_error(self, tmp_path: Path):
        with pytest.raises(FrameExtractionError):
            extract_frames(Path("/nonexistent/proxy.mp4"), tmp_path / "frames")

    def test_creates_output_directory(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        proxy = Path(clip.proxy_path)
        out_dir = tmp_path / "deep" / "nested" / "frames"
        assert not out_dir.exists()
        extract_frames(proxy, out_dir)
        assert out_dir.exists()


# ── analyse_clip ──────────────────────────────────────────────────────────────


class TestAnalyseClip:
    def test_returns_clip_analysis(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        client = _make_client(json.dumps(_valid_analysis_dict()))
        result = analyse_clip(clip, clip.project_id, tmp_path, client=client)
        assert isinstance(result, ClipAnalysis)
        assert result.quality_score == pytest.approx(0.8)
        assert result.scene_mood == "calm"

    def test_sets_status_to_analyzed(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        client = _make_client(json.dumps(_valid_analysis_dict()))
        analyse_clip(clip, clip.project_id, tmp_path, client=client)
        assert clip.status == ClipStatus.analyzed

    def test_missing_proxy_raises(self, tmp_path: Path):
        clip = _make_clip("/source.mp4")  # no proxy_path set
        client = _make_client(json.dumps(_valid_analysis_dict()))
        with pytest.raises(FrameExtractionError):
            analyse_clip(clip, clip.project_id, tmp_path, client=client)

    def test_nonexistent_proxy_raises(self, tmp_path: Path):
        clip = _make_clip("/source.mp4", proxy_path="/nonexistent/proxy.mp4")
        client = _make_client(json.dumps(_valid_analysis_dict()))
        with pytest.raises(FrameExtractionError):
            analyse_clip(clip, clip.project_id, tmp_path, client=client)

    def test_bad_json_retries_and_raises(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        client = _make_client("this is not json")
        with pytest.raises(InvalidClaudeResponseError) as exc_info:
            analyse_clip(clip, clip.project_id, tmp_path, client=client)
        # Should have attempted _MAX_RETRIES + 1 = 3 times total.
        assert client.messages.create.call_count == 3

    def test_bad_schema_retries_and_raises(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        # Valid JSON but wrong schema (missing required fields).
        client = _make_client(json.dumps({"wrong": "schema"}))
        with pytest.raises(InvalidClaudeResponseError):
            analyse_clip(clip, clip.project_id, tmp_path, client=client)

    def test_api_error_retries_and_raises(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        client = MagicMock()
        client.messages.create.side_effect = anthropic.APIError(
            message="rate limited", request=MagicMock(), body=None
        )
        with pytest.raises(ClaudeAPIError):
            analyse_clip(clip, clip.project_id, tmp_path, client=client)
        assert client.messages.create.call_count == 3

    def test_quality_score_clamped(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        bad_score = dict(_valid_analysis_dict(), quality_score=99.0)
        client = _make_client(json.dumps(bad_score))
        result = analyse_clip(clip, clip.project_id, tmp_path, client=client)
        assert result.quality_score == pytest.approx(1.0)

    def test_claude_called_with_cached_system_prompt(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        client = _make_client(json.dumps(_valid_analysis_dict()))
        analyse_clip(clip, clip.project_id, tmp_path, client=client)

        call_kwargs = client.messages.create.call_args
        system = call_kwargs.kwargs["system"]
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_frames_written_to_correct_subdir(self, fixture_clip_path: Path, tmp_path: Path):
        from storage.local import frames_subdir
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        client = _make_client(json.dumps(_valid_analysis_dict()))
        analyse_clip(clip, clip.project_id, tmp_path, client=client)
        expected_dir = frames_subdir(tmp_path, clip.project_id, clip.id)
        assert expected_dir.exists()
        assert any(expected_dir.iterdir())


# ── run_pass1 (async) ─────────────────────────────────────────────────────────


class TestRunPass1:
    def test_concurrent_analysis(self, fixture_clip_path: Path, tmp_path: Path):
        import asyncio
        from pipeline.pass1_clip_analysis import run_pass1

        clips = [_proxy_clip(fixture_clip_path, tmp_path) for _ in range(2)]
        # Give each clip its own frames subdir by using different project dirs.
        for i, clip in enumerate(clips):
            clip.project_id = str(uuid.uuid4())

        client = _make_client(json.dumps(_valid_analysis_dict()))

        async def _run():
            return await run_pass1(clips, clips[0].project_id, tmp_path, client=client)

        results = asyncio.run(_run())
        assert len(results) == 2
        assert all(analysis is not None for _, analysis in results)

    def test_failed_clip_does_not_block_others(self, fixture_clip_path: Path, tmp_path: Path):
        import asyncio
        from pipeline.pass1_clip_analysis import run_pass1

        good_clip = _proxy_clip(fixture_clip_path, tmp_path)
        bad_clip = _make_clip("/source.mp4")  # no proxy — will fail

        client = _make_client(json.dumps(_valid_analysis_dict()))

        async def _run():
            return await run_pass1([good_clip, bad_clip], good_clip.project_id, tmp_path, client=client)

        results = asyncio.run(_run())
        assert len(results) == 2
        analyses = {clip.id: a for clip, a in results}
        assert analyses[good_clip.id] is not None
        assert analyses[bad_clip.id] is None
        assert bad_clip.status == ClipStatus.failed
