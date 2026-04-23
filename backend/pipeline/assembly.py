from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from loguru import logger

from exceptions import AssemblyError, ClipNotFoundError
from models.clip import Clip
from models.edit_plan import EditPlan, EditSegment
from pipeline.broll_overlay import apply_broll
from pipeline.filler_removal import remove_fillers
from storage.local import output_path, outputs_dir


def assemble(
    plan: EditPlan,
    clips_by_id: dict[str, Clip],
    project_id: str,
    base_dir: Path,
) -> Path:
    """Concatenate all approved edit segments into a final output.mp4.

    Runs each segment through filler removal then B-roll overlay, then
    concatenates the results with the FFmpeg concat demuxer.

    Returns the path to the assembled output file.
    Raises AssemblyError if FFmpeg concat fails.
    Raises ClipNotFoundError if a segment references an unknown clip.
    """
    raw_segments: list = plan.segments or []
    if not raw_segments:
        raise AssemblyError("Edit plan has no segments — nothing to assemble", stage="assembly")

    segments = sorted(
        [EditSegment.model_validate(s) for s in raw_segments],
        key=lambda s: s.order,
    )

    segments_dir = outputs_dir(base_dir, project_id) / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    segment_files: list[Path] = []
    for segment in segments:
        clip = clips_by_id.get(segment.clip_id)
        if clip is None:
            raise ClipNotFoundError(
                clip_id=segment.clip_id,
                expected_path="<unknown — clip not in clips_by_id>",
            )

        logger.info("Assembly: processing segment {} (clip {})", segment.order, segment.clip_id)
        seg_path = remove_fillers(segment, clip, project_id, base_dir)
        final_path = apply_broll(segment, clips_by_id, project_id, base_dir, seg_path)
        segment_files.append(final_path)

    out = output_path(base_dir, project_id)
    _concat(segment_files, out)
    logger.info("Assembly complete: {}", out)
    return out


# ── Internal helpers ──────────────────────────────────────────────────────────


def _concat(segment_files: list[Path], out: Path) -> None:
    """Write a concat list file and run FFmpeg to merge all segments."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        list_path = Path(f.name)
        for seg in segment_files:
            f.write(f"file '{seg.resolve()}'\n")

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssemblyError(
                f"FFmpeg concat failed (exit {result.returncode})\n"
                f"FFmpeg output:\n{result.stderr}",
                stage="assembly",
            )
    finally:
        list_path.unlink(missing_ok=True)
