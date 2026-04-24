"""Tests for pipeline/single_clip_apply.py."""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from exceptions import ClipNotFoundError, SingleClipNotProcessedError
from models.clip import Clip, ClipStatus, FillerSpan, SingleClipAnalysis, SilenceSpan
from pipeline.proxy import generate_proxy
from pipeline.single_clip_apply import _merge_spans, apply_single_clip_edits


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _analysis(
    filler_spans: list[tuple[float, float]] = (),
    silence_spans: list[tuple[float, float]] = (),
) -> dict:
    return SingleClipAnalysis(
        filler_spans=[FillerSpan(start=s, end=e, word="um") for s, e in filler_spans],
        silence_spans=[SilenceSpan(start=s, end=e) for s, e in silence_spans],
        rename_suggestions=["A", "B", "C"],
        full_transcript_text="test",
    ).model_dump()


def _make_clip(proxy_path: Path | None = None, analysis: dict | None = None) -> Clip:
    project_id = str(uuid.uuid4())
    return Clip(
        id=str(uuid.uuid4()),
        project_id=project_id,
        filename="test.mp4",
        original_path="/dev/null",
        proxy_path=str(proxy_path) if proxy_path else None,
        duration_seconds=3.0,
        status=ClipStatus.sc_ready,
        analysis=analysis,
    )


def _duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


# ── Unit tests for _merge_spans ───────────────────────────────────────────────


class TestMergeSpans:
    def test_empty_returns_empty(self):
        assert _merge_spans([]) == []

    def test_single_span_unchanged(self):
        assert _merge_spans([(1.0, 2.0)]) == [(1.0, 2.0)]

    def test_non_overlapping_preserved(self):
        result = _merge_spans([(0.0, 1.0), (2.0, 3.0)])
        assert result == [(0.0, 1.0), (2.0, 3.0)]

    def test_overlapping_merged(self):
        result = _merge_spans([(0.0, 1.5), (1.0, 2.0)])
        assert result == [(0.0, 2.0)]

    def test_adjacent_merged(self):
        result = _merge_spans([(0.0, 1.0), (1.0, 2.0)])
        assert result == [(0.0, 2.0)]

    def test_unsorted_input_sorted_first(self):
        result = _merge_spans([(2.0, 3.0), (0.0, 1.0)])
        assert result == [(0.0, 1.0), (2.0, 3.0)]

    def test_multiple_overlapping_merged_to_one(self):
        result = _merge_spans([(0.0, 1.0), (0.5, 1.5), (1.2, 2.0)])
        assert result == [(0.0, 2.0)]

    def test_filler_and_silence_combined(self):
        result = _merge_spans([(1.0, 1.5), (3.0, 3.8), (1.3, 1.8)])
        assert result == [(1.0, 1.8), (3.0, 3.8)]


# ── Integration tests (real FFmpeg) ──────────────────────────────────────────


class TestApplySingleClipEdits:
    def test_no_edits_produces_output(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(analysis=_analysis())
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)

        out = apply_single_clip_edits(clip, clip.project_id, tmp_path, False, False)
        assert out.exists()

    def test_filler_removal_shortens_clip(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(analysis=_analysis(filler_spans=[(0.5, 1.0), (1.5, 2.0)]))
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)
        clip.duration_seconds = _duration(proxy)

        out = apply_single_clip_edits(clip, clip.project_id, tmp_path, remove_fillers=True, remove_silence=False)
        assert out.exists()
        assert _duration(out) < clip.duration_seconds - 0.5

    def test_silence_removal_shortens_clip(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(analysis=_analysis(silence_spans=[(0.5, 1.0)]))
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)
        clip.duration_seconds = _duration(proxy)

        out = apply_single_clip_edits(clip, clip.project_id, tmp_path, remove_fillers=False, remove_silence=True)
        assert out.exists()
        assert _duration(out) < clip.duration_seconds - 0.3

    def test_missing_proxy_raises_clip_not_found(self, tmp_path: Path):
        clip = _make_clip(
            proxy_path=tmp_path / "nonexistent.mp4",
            analysis=_analysis(),
        )
        clip.project_id = str(uuid.uuid4())
        with pytest.raises(ClipNotFoundError):
            apply_single_clip_edits(clip, clip.project_id, tmp_path, False, False)

    def test_missing_analysis_raises_not_processed(self, tmp_path: Path):
        clip = _make_clip(analysis=None)
        clip.proxy_path = str(tmp_path / "fake.mp4")
        clip.project_id = str(uuid.uuid4())
        with pytest.raises(SingleClipNotProcessedError):
            apply_single_clip_edits(clip, clip.project_id, tmp_path, False, False)

    def test_output_in_correct_directory(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(analysis=_analysis())
        clip.original_path = str(fixture_clip_path)
        clip.project_id = str(uuid.uuid4())

        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)

        out = apply_single_clip_edits(clip, clip.project_id, tmp_path, False, False)
        assert out.parent.name == "outputs"
        assert clip.id in out.name
