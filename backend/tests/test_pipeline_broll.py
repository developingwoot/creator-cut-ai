"""Tests for pipeline/broll_overlay.py."""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from exceptions import FFmpegError
from models.clip import Clip, ClipStatus
from models.edit_plan import BRollPlacement, EditSegment
from pipeline.broll_overlay import _resolve_placements, apply_broll
from pipeline.proxy import generate_proxy


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_clip(proxy_path: Path | None = None) -> Clip:
    clip = Clip(
        id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        filename="test.mp4",
        original_path="/dev/null",
        proxy_path=str(proxy_path) if proxy_path else None,
        status=ClipStatus.proxied,
    )
    return clip


def _make_segment(clip_id: str, overlays: list[BRollPlacement] | None = None) -> EditSegment:
    return EditSegment(
        order=0,
        clip_id=clip_id,
        source_start=0.0,
        source_end=3.0,
        b_roll_overlays=overlays or [],
    )


def _make_placement(clip_id: str, start: float = 0.5, end: float = 1.5) -> BRollPlacement:
    return BRollPlacement(
        clip_id=clip_id,
        start_seconds=start,
        end_seconds=end,
        description="test overlay",
    )


# ── Unit tests for _resolve_placements ───────────────────────────────────────


class TestResolvePlacements:
    def test_empty_overlays(self):
        assert _resolve_placements([], {}) == []

    def test_unknown_clip_id_skipped(self):
        p = _make_placement("nonexistent-clip-id")
        result = _resolve_placements([p], {})
        assert result == []

    def test_missing_proxy_path_skipped(self, tmp_path: Path):
        clip = _make_clip(proxy_path=None)
        p = _make_placement(clip.id)
        result = _resolve_placements([p], {clip.id: clip})
        assert result == []

    def test_nonexistent_proxy_file_skipped(self, tmp_path: Path):
        clip = _make_clip(proxy_path=tmp_path / "ghost.mp4")
        p = _make_placement(clip.id)
        result = _resolve_placements([p], {clip.id: clip})
        assert result == []

    def test_zero_duration_placement_skipped(self, tmp_path: Path):
        proxy = tmp_path / "proxy.mp4"
        proxy.write_bytes(b"fake")
        clip = _make_clip(proxy_path=proxy)
        p = BRollPlacement(
            clip_id=clip.id, start_seconds=1.0, end_seconds=1.0, description="zero"
        )
        result = _resolve_placements([p], {clip.id: clip})
        assert result == []

    def test_valid_placement_included(self, tmp_path: Path):
        proxy = tmp_path / "proxy.mp4"
        proxy.write_bytes(b"fake")
        clip = _make_clip(proxy_path=proxy)
        p = _make_placement(clip.id)
        result = _resolve_placements([p], {clip.id: clip})
        assert len(result) == 1
        assert result[0].clip_id == clip.id


# ── Unit tests for apply_broll (no-op path) ───────────────────────────────────


class TestApplyBrollNoOp:
    def test_no_overlays_returns_input_unchanged(self, tmp_path: Path):
        aroll = tmp_path / "aroll.mp4"
        aroll.write_bytes(b"fake")
        clip = _make_clip()
        seg = _make_segment(clip.id, overlays=[])

        result = apply_broll(seg, {}, "proj-id", tmp_path, aroll)
        assert result == aroll

    def test_all_invalid_placements_returns_input_unchanged(self, tmp_path: Path):
        aroll = tmp_path / "aroll.mp4"
        aroll.write_bytes(b"fake")
        clip = _make_clip()  # no proxy
        p = _make_placement(clip.id)
        seg = _make_segment(clip.id, overlays=[p])

        result = apply_broll(seg, {clip.id: clip}, "proj-id", tmp_path, aroll)
        assert result == aroll

    def test_no_ffmpeg_call_when_no_valid_placements(self, tmp_path: Path):
        aroll = tmp_path / "aroll.mp4"
        aroll.write_bytes(b"fake")
        clip = _make_clip()  # no proxy
        seg = _make_segment(clip.id, overlays=[_make_placement(clip.id)])

        with patch("pipeline.broll_overlay._run_overlay") as mock_run:
            apply_broll(seg, {clip.id: clip}, "proj-id", tmp_path, aroll)
            mock_run.assert_not_called()


# ── Integration tests (real FFmpeg) ──────────────────────────────────────────


class TestApplyBrollIntegration:
    def test_single_overlay_produces_output(self, fixture_clip_path: Path, tmp_path: Path):
        project_id = str(uuid.uuid4())

        aroll_clip = _make_clip()
        aroll_clip.project_id = project_id
        aroll_clip.original_path = str(fixture_clip_path)
        aroll_proxy = generate_proxy(aroll_clip, project_id, tmp_path)

        broll_clip = _make_clip()
        broll_clip.project_id = project_id
        broll_clip.original_path = str(fixture_clip_path)
        broll_proxy = generate_proxy(broll_clip, project_id, tmp_path)
        broll_clip.proxy_path = str(broll_proxy)

        # Create a fake "input" (reuse the A-roll proxy as the segment input)
        aroll_input = tmp_path / "seg_0000.mp4"
        aroll_input.write_bytes(aroll_proxy.read_bytes())

        p = _make_placement(broll_clip.id, start=0.5, end=1.0)
        seg = _make_segment(aroll_clip.id, overlays=[p])

        result = apply_broll(seg, {broll_clip.id: broll_clip}, project_id, tmp_path, aroll_input)

        assert result != aroll_input
        assert result.exists()
        assert result.stat().st_size > 0

    def test_ffmpeg_error_raises_ffmpeg_error(self, tmp_path: Path):
        # Bad input file → FFmpeg will fail.
        bad_input = tmp_path / "bad.mp4"
        bad_input.write_bytes(b"not a video")

        broll_proxy = tmp_path / "broll.mp4"
        broll_proxy.write_bytes(b"not a video either")

        broll_clip = _make_clip(proxy_path=broll_proxy)
        p = _make_placement(broll_clip.id, start=0.0, end=1.0)
        seg = _make_segment(broll_clip.id, overlays=[p])

        with pytest.raises(FFmpegError):
            apply_broll(seg, {broll_clip.id: broll_clip}, "proj-id", tmp_path, bad_input)
