"""Tests for pipeline/pass1_clip_analysis.py."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from exceptions import FrameExtractionError, InvalidOllamaResponseError
from models.clip import Clip, ClipAnalysis, ClipStatus
from pipeline.pass1_clip_analysis import (
    _downsample,
    _transcript_text,
    analyse_clip,
    extract_frames,
    run_pass1,
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


def _proxy_clip(fixture_clip_path: Path, tmp_path: Path) -> Clip:
    clip = _make_clip(fixture_clip_path)
    proxy = generate_proxy(clip, clip.project_id, tmp_path)
    clip.proxy_path = str(proxy)
    clip.duration_seconds = 3.0
    return clip


def _patch_ollama(response_text: str):
    """Patch ollama_client.generate to return response_text."""
    return patch(
        "pipeline.pass1_clip_analysis.ollama_client.generate",
        new=AsyncMock(return_value=response_text),
    )


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
        frames = extract_frames(Path(clip.proxy_path), tmp_path / "frames")
        assert isinstance(frames, list)
        assert all(p.suffix == ".jpg" for p in frames)

    def test_files_exist_on_disk(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        frames = extract_frames(Path(clip.proxy_path), tmp_path / "frames")
        assert all(p.exists() for p in frames)

    def test_never_exceeds_max_frames(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        frames = extract_frames(Path(clip.proxy_path), tmp_path / "frames", max_frames=2)
        assert len(frames) <= 2

    def test_bad_proxy_raises_frame_extraction_error(self, tmp_path: Path):
        with pytest.raises(FrameExtractionError):
            extract_frames(Path("/nonexistent/proxy.mp4"), tmp_path / "frames")

    def test_creates_output_directory(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        out_dir = tmp_path / "deep" / "nested" / "frames"
        assert not out_dir.exists()
        extract_frames(Path(clip.proxy_path), out_dir)
        assert out_dir.exists()


# ── analyse_clip ──────────────────────────────────────────────────────────────


class TestAnalyseClip:
    def test_returns_clip_analysis(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        with _patch_ollama(json.dumps(_valid_analysis_dict())):
            result = asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))
        assert isinstance(result, ClipAnalysis)
        assert result.quality_score == pytest.approx(0.8)
        assert result.scene_mood == "calm"

    def test_sets_status_to_analyzed(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        with _patch_ollama(json.dumps(_valid_analysis_dict())):
            asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))
        assert clip.status == ClipStatus.analyzed

    def test_missing_proxy_raises(self, tmp_path: Path):
        clip = _make_clip("/source.mp4")
        with _patch_ollama(json.dumps(_valid_analysis_dict())):
            with pytest.raises(FrameExtractionError):
                asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))

    def test_nonexistent_proxy_raises(self, tmp_path: Path):
        clip = _make_clip("/source.mp4", proxy_path="/nonexistent/proxy.mp4")
        with _patch_ollama(json.dumps(_valid_analysis_dict())):
            with pytest.raises(FrameExtractionError):
                asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))

    def test_bad_json_retries_and_raises(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        mock = AsyncMock(return_value="this is not json")
        with patch("pipeline.pass1_clip_analysis.ollama_client.generate", mock):
            with pytest.raises(InvalidOllamaResponseError):
                asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))
        assert mock.call_count == 3  # _MAX_RETRIES + 1

    def test_bad_schema_retries_and_raises(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        with _patch_ollama(json.dumps({"wrong": "schema"})):
            with pytest.raises(InvalidOllamaResponseError):
                asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))

    def test_quality_score_clamped(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        bad_score = dict(_valid_analysis_dict(), quality_score=99.0)
        with _patch_ollama(json.dumps(bad_score)):
            result = asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))
        assert result.quality_score == pytest.approx(1.0)

    def test_frames_written_to_correct_subdir(self, fixture_clip_path: Path, tmp_path: Path):
        from storage.local import frames_subdir
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        with _patch_ollama(json.dumps(_valid_analysis_dict())):
            asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))
        expected_dir = frames_subdir(tmp_path, clip.project_id, clip.id)
        assert expected_dir.exists()
        assert any(expected_dir.iterdir())

    def test_ollama_called_with_images(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _proxy_clip(fixture_clip_path, tmp_path)
        mock = AsyncMock(return_value=json.dumps(_valid_analysis_dict()))
        with patch("pipeline.pass1_clip_analysis.ollama_client.generate", mock):
            asyncio.run(analyse_clip(clip, clip.project_id, tmp_path))
        call_kwargs = mock.call_args
        assert call_kwargs.kwargs.get("images") or (len(call_kwargs.args) > 2 and call_kwargs.args[2])


# ── run_pass1 (async) ─────────────────────────────────────────────────────────


class TestRunPass1:
    def test_concurrent_analysis(self, fixture_clip_path: Path, tmp_path: Path):
        clips = [_proxy_clip(fixture_clip_path, tmp_path) for _ in range(2)]
        for clip in clips:
            clip.project_id = str(uuid.uuid4())

        with _patch_ollama(json.dumps(_valid_analysis_dict())):
            results = asyncio.run(run_pass1(clips, clips[0].project_id, tmp_path))

        assert len(results) == 2
        assert all(analysis is not None for _, analysis in results)

    def test_failed_clip_does_not_block_others(self, fixture_clip_path: Path, tmp_path: Path):
        good_clip = _proxy_clip(fixture_clip_path, tmp_path)
        bad_clip = _make_clip("/source.mp4")  # no proxy — will fail

        with _patch_ollama(json.dumps(_valid_analysis_dict())):
            results = asyncio.run(run_pass1([good_clip, bad_clip], good_clip.project_id, tmp_path))

        assert len(results) == 2
        analyses = {clip.id: a for clip, a in results}
        assert analyses[good_clip.id] is not None
        assert analyses[bad_clip.id] is None
        assert bad_clip.status == ClipStatus.failed
