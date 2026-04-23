from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

from exceptions import FFmpegError
from models.clip import Clip
from models.edit_plan import BRollPlacement, EditSegment


def apply_broll(
    segment: EditSegment,
    clips_by_id: dict[str, Clip],
    project_id: str,
    base_dir: Path,
    input_path: Path,
) -> Path:
    """Composite B-roll video over the A-roll segment during each BRollPlacement window.

    Timecodes in BRollPlacement are segment-relative (t=0 is when the segment starts).
    A-roll audio is always preserved unchanged; only the video track is composited.

    Returns input_path unchanged if there are no valid placements (no-op).
    Logs a warning and skips any placement whose source clip or proxy is missing.

    Raises FFmpegError (with stderr) if FFmpeg fails.
    """
    placements = _resolve_placements(segment.b_roll_overlays, clips_by_id)
    if not placements:
        return input_path

    out = input_path.parent / f"seg_{segment.order:04d}_broll.mp4"
    _run_overlay(input_path, placements, clips_by_id, out, segment.order)
    logger.info(
        "segment {} — {} B-roll overlay(s) applied → {}",
        segment.order,
        len(placements),
        out,
    )
    return out


# ── Internals ─────────────────────────────────────────────────────────────────


def _resolve_placements(
    overlays: list[BRollPlacement],
    clips_by_id: dict[str, Clip],
) -> list[BRollPlacement]:
    valid: list[BRollPlacement] = []
    for p in overlays:
        clip = clips_by_id.get(p.clip_id)
        if clip is None:
            logger.warning("B-roll clip {} not in project — skipping overlay", p.clip_id)
            continue
        if not clip.proxy_path or not Path(clip.proxy_path).exists():
            logger.warning("B-roll proxy missing for clip {} — skipping overlay", p.clip_id)
            continue
        if p.end_seconds <= p.start_seconds:
            logger.warning(
                "B-roll placement for clip {} has zero/negative duration — skipping",
                p.clip_id,
            )
            continue
        valid.append(p)
    return valid


def _run_overlay(
    input_path: Path,
    placements: list[BRollPlacement],
    clips_by_id: dict[str, Clip],
    out: Path,
    segment_order: int,
) -> None:
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    for p in placements:
        cmd += ["-i", str(clips_by_id[p.clip_id].proxy_path)]

    # For each B-roll input, trim it to the required overlay duration and reset its PTS.
    # Then chain overlay filters: [0:v] + [bv0] → [tmp0]; [tmp0] + [bv1] → [tmp1]; …
    filter_parts: list[str] = []
    for i, p in enumerate(placements):
        duration = p.end_seconds - p.start_seconds
        filter_parts.append(
            f"[{i + 1}:v]trim=start=0:duration={duration:.6f},setpts=PTS-STARTPTS[bv{i}]"
        )

    prev_label = "0:v"
    for i, p in enumerate(placements):
        out_label = "out" if i == len(placements) - 1 else f"tmp{i}"
        filter_parts.append(
            f"[{prev_label}][bv{i}]"
            f"overlay=enable='between(t,{p.start_seconds:.6f},{p.end_seconds:.6f})'"
            f"[{out_label}]"
        )
        prev_label = out_label

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[out]",
        "-map", "0:a",
        "-c:a", "copy",
        str(out),
    ]

    logger.info(
        "applying {} B-roll overlay(s) to segment {} → {}",
        len(placements),
        segment_order,
        out,
    )
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        out.unlink(missing_ok=True)
        raise FFmpegError(
            f"FFmpeg failed applying B-roll overlays to segment {segment_order}",
            stderr=stderr,
            stage="broll_overlay",
        )
