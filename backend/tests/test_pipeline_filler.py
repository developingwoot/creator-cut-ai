"""Tests for pipeline/filler_removal.py."""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import ffmpeg
import pytest

from exceptions import ClipNotFoundError, FFmpegError
from models.clip import Clip, ClipAnalysis, ClipStatus, FillerSpan
from models.edit_plan import EditSegment
from pipeline.filler_removal import _active_spans, remove_fillers
from pipeline.proxy import generate_proxy


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_clip(proxy_path: Path | None = None, analysis: dict | None = None) -> Clip:
    project_id = str(uuid.uuid4())
    return Clip(
        id=str(uuid.uuid4()),
        project_id=project_id,
        filename="test.mp4",
        original_path="/dev/null",
        proxy_path=str(proxy_path) if proxy_path else None,
        duration_seconds=3.0,
        status=ClipStatus.proxied,
        analysis=analysis,
    )


def _make_segment(
    order: int = 0,
    source_start: float = 0.0,
    source_end: float = 3.0,
    clip_id: str | None = None,
) -> EditSegment:
    return EditSegment(
        order=order,
        clip_id=clip_id or str(uuid.uuid4()),
        source_start=source_start,
        source_end=source_end,
    )


def _analysis_with_fillers(spans: list[tuple[float, float, str]]) -> dict:
    return ClipAnalysis(
        quality_score=0.8,
        filler_spans=[FillerSpan(start=s, end=e, word=w) for s, e, w in spans],
        scene_mood="neutral",
        is_usable=True,
    ).model_dump()


def _clip_duration(path: Path) -> float:
    """Return duration of a video file in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


# ── Unit tests for _active_spans ─────────────────────────────────────────────


class TestActiveSpans:
    def test_no_analysis_returns_empty(self):
        clip = _make_clip(analysis=None)
        seg = _make_segment(source_start=0.0, source_end=3.0)
        assert _active_spans(seg, clip) == []

    def test_span_inside_window(self):
        clip = _make_clip(analysis=_analysis_with_fillers([(1.0, 1.5, "um")]))
        seg = _make_segment(source_start=0.0, source_end=3.0)
        spans = _active_spans(seg, clip)
        assert len(spans) == 1
        assert spans[0] == pytest.approx((1.0, 1.5))

    def test_span_converted_to_segment_relative(self):
        # Clip filler at absolute t=12.5–13.0; segment starts at 10.0
        clip = _make_clip(analysis=_analysis_with_fillers([(12.5, 13.0, "uh")]))
        seg = _make_segment(source_start=10.0, source_end=20.0)
        spans = _active_spans(seg, clip)
        assert len(spans) == 1
        assert spans[0] == pytest.approx((2.5, 3.0))

    def test_span_entirely_before_window_excluded(self):
        clip = _make_clip(analysis=_analysis_with_fillers([(0.5, 1.0, "like")]))
        seg = _make_segment(source_start=5.0, source_end=10.0)
        assert _active_spans(seg, clip) == []

    def test_span_entirely_after_window_excluded(self):
        clip = _make_clip(analysis=_analysis_with_fillers([(15.0, 16.0, "um")]))
        seg = _make_segment(source_start=5.0, source_end=10.0)
        assert _active_spans(seg, clip) == []

    def test_span_partially_overlapping_start_clamped(self):
        # Span starts before window; only the portion inside is kept.
        clip = _make_clip(analysis=_analysis_with_fillers([(4.0, 6.0, "um")]))
        seg = _make_segment(source_start=5.0, source_end=10.0)
        spans = _active_spans(seg, clip)
        assert len(spans) == 1
        assert spans[0][0] == pytest.approx(0.0)
        assert spans[0][1] == pytest.approx(1.0)

    def test_multiple_spans_mixed(self):
        clip = _make_clip(
            analysis=_analysis_with_fillers([
                (0.5, 1.0, "um"),   # inside
                (2.0, 2.5, "uh"),   # inside
                (5.0, 6.0, "like"), # outside
            ])
        )
        seg = _make_segment(source_start=0.0, source_end=3.0)
        spans = _active_spans(seg, clip)
        assert len(spans) == 2


# ── Integration tests (real FFmpeg) ──────────────────────────────────────────


class TestRemoveFillers:
    def test_no_fillers_trims_segment(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(analysis=None)
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)

        seg = _make_segment(
            clip_id=clip.id,
            source_start=0.0,
            source_end=2.0,
        )
        out = remove_fillers(seg, clip, clip.project_id, tmp_path)

        assert out.exists()
        duration = _clip_duration(out)
        # Allow 0.2s tolerance for codec alignment
        assert abs(duration - 2.0) < 0.2

    def test_output_shorter_when_fillers_removed(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(
            analysis=_analysis_with_fillers([(0.5, 1.0, "um"), (1.5, 2.0, "uh")])
        )
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)

        seg = _make_segment(clip_id=clip.id, source_start=0.0, source_end=3.0)
        out = remove_fillers(seg, clip, clip.project_id, tmp_path)

        assert out.exists()
        # 1 second of fillers removed from a 3-second segment
        assert _clip_duration(out) < 2.5

    def test_filler_outside_window_has_no_effect(self, fixture_clip_path: Path, tmp_path: Path):
        # Filler at t=5.0–5.5 is outside the segment [0, 2], so nothing is removed.
        clip = _make_clip(
            analysis=_analysis_with_fillers([(5.0, 5.5, "um")])
        )
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)

        seg = _make_segment(clip_id=clip.id, source_start=0.0, source_end=2.0)
        out = remove_fillers(seg, clip, clip.project_id, tmp_path)

        assert out.exists()
        assert abs(_clip_duration(out) - 2.0) < 0.2

    def test_missing_proxy_raises_clip_not_found(self, tmp_path: Path):
        clip = _make_clip(proxy_path=tmp_path / "nonexistent.mp4")
        clip.project_id = str(uuid.uuid4())
        seg = _make_segment(clip_id=clip.id)

        with pytest.raises(ClipNotFoundError):
            remove_fillers(seg, clip, clip.project_id, tmp_path)

    def test_ffmpeg_error_raises_ffmpeg_error(self, tmp_path: Path):
        # Point proxy at a corrupt (empty) file to trigger FFmpeg failure.
        bad_proxy = tmp_path / "bad.mp4"
        bad_proxy.write_bytes(b"not a video")

        clip = _make_clip(proxy_path=bad_proxy)
        clip.project_id = str(uuid.uuid4())
        seg = _make_segment(clip_id=clip.id)

        with pytest.raises(FFmpegError):
            remove_fillers(seg, clip, clip.project_id, tmp_path)

    def test_output_placed_in_segments_subdir(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(analysis=None)
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)

        seg = _make_segment(order=7, clip_id=clip.id, source_start=0.0, source_end=2.0)
        out = remove_fillers(seg, clip, clip.project_id, tmp_path)

        assert out.parent.name == "segments"
        assert out.name == "seg_0007.mp4"

    def test_idempotent(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(analysis=None)
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)
        seg = _make_segment(clip_id=clip.id, source_start=0.0, source_end=2.0)

        out1 = remove_fillers(seg, clip, clip.project_id, tmp_path)
        out2 = remove_fillers(seg, clip, clip.project_id, tmp_path)
        assert out1 == out2
        assert out2.exists()
