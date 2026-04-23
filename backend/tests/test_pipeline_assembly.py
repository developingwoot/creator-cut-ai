"""Tests for pipeline/assembly.py."""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from exceptions import AssemblyError, ClipNotFoundError
from models.clip import Clip, ClipStatus
from models.edit_plan import EditPlan, EditPlanStatus, EditSegment
from pipeline.assembly import assemble
from pipeline.proxy import generate_proxy


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_clip(proxy_path: Path | None = None) -> Clip:
    clip_id = str(uuid.uuid4())
    return Clip(
        id=clip_id,
        project_id=str(uuid.uuid4()),
        filename="test.mp4",
        original_path="/dev/null",
        proxy_path=str(proxy_path) if proxy_path else None,
        duration_seconds=3.0,
        status=ClipStatus.proxied,
    )


def _make_segment(clip_id: str, order: int = 0, start: float = 0.0, end: float = 2.5) -> EditSegment:
    return EditSegment(order=order, clip_id=clip_id, source_start=start, source_end=end)


def _make_plan(segments: list[EditSegment]) -> EditPlan:
    return EditPlan(
        id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        status=EditPlanStatus.approved,
        segments=[s.model_dump() for s in segments],
        total_duration_seconds=sum(s.source_end - s.source_start for s in segments),
    )


def _clip_duration(path: Path) -> float:
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


# ── Unit tests ────────────────────────────────────────────────────────────────


class TestAssembleValidation:
    def test_empty_segments_raises(self, tmp_path):
        plan = _make_plan([])
        plan.segments = []
        with pytest.raises(AssemblyError, match="no segments"):
            assemble(plan, {}, "proj", tmp_path)

    def test_none_segments_raises(self, tmp_path):
        plan = _make_plan([])
        plan.segments = None
        with pytest.raises(AssemblyError, match="no segments"):
            assemble(plan, {}, "proj", tmp_path)

    def test_missing_clip_raises(self, tmp_path):
        clip_id = str(uuid.uuid4())
        plan = _make_plan([_make_segment(clip_id)])
        with pytest.raises(ClipNotFoundError):
            assemble(plan, {}, "proj", tmp_path)

    def test_segments_sorted_by_order(self, tmp_path):
        """Out-of-order segments in the plan are sorted before processing."""
        clip_a = _make_clip()
        clip_b = _make_clip()
        seg_first = _make_segment(clip_a.id, order=0, start=0.0, end=1.0)
        seg_second = _make_segment(clip_b.id, order=1, start=0.0, end=1.0)
        # Deliberately put second before first in the plan JSON
        plan = _make_plan([seg_second, seg_first])

        processed: list[str] = []

        def fake_remove_fillers(segment, clip, project_id, base_dir):
            processed.append(clip.id)
            out = base_dir / f"seg_{segment.order:04d}.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.touch()
            return out

        def fake_apply_broll(segment, clips_by_id, project_id, base_dir, input_path):
            return input_path

        def fake_concat(segment_files, out):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.touch()

        clips_by_id = {clip_a.id: clip_a, clip_b.id: clip_b}
        with (
            patch("pipeline.assembly.remove_fillers", side_effect=fake_remove_fillers),
            patch("pipeline.assembly.apply_broll", side_effect=fake_apply_broll),
            patch("pipeline.assembly._concat", side_effect=fake_concat),
        ):
            assemble(plan, clips_by_id, "proj", tmp_path)

        assert processed == [clip_a.id, clip_b.id], "Segments must be processed in order"


# ── Integration tests ─────────────────────────────────────────────────────────


class TestAssembleIntegration:
    def test_single_segment_produces_output(self, fixture_clip_path, tmp_path):
        """A single segment assembles into output.mp4."""
        project_id = str(uuid.uuid4())
        clip = _make_clip()
        clip.original_path = str(fixture_clip_path)

        proxy = generate_proxy(clip, project_id, tmp_path)
        clip.proxy_path = str(proxy)

        seg = _make_segment(clip.id, order=0, start=0.0, end=2.5)
        plan = _make_plan([seg])

        out = assemble(plan, {clip.id: clip}, project_id, tmp_path)

        assert out.exists(), "output.mp4 must exist"
        assert out.stat().st_size > 0

    def test_two_segments_concat(self, fixture_clip_path, tmp_path):
        """Two segments from the same proxy are concatenated correctly."""
        project_id = str(uuid.uuid4())
        clip = _make_clip()
        clip.original_path = str(fixture_clip_path)

        proxy = generate_proxy(clip, project_id, tmp_path)
        clip.proxy_path = str(proxy)

        seg0 = _make_segment(clip.id, order=0, start=0.0, end=1.0)
        seg1 = _make_segment(clip.id, order=1, start=1.0, end=2.0)
        plan = _make_plan([seg0, seg1])

        out = assemble(plan, {clip.id: clip}, project_id, tmp_path)

        assert out.exists()
        duration = _clip_duration(out)
        # Each segment is 1s; allow 10% tolerance for codec frame alignment
        assert 1.5 <= duration <= 2.5, f"Expected ~2s, got {duration:.2f}s"
