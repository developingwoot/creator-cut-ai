from __future__ import annotations

from pathlib import Path

import ffmpeg
from loguru import logger

from exceptions import ClipNotFoundError, FFmpegError
from models.clip import Clip, ClipAnalysis
from models.edit_plan import EditSegment
from storage.local import outputs_dir, proxy_path


def remove_fillers(
    segment: EditSegment,
    clip: Clip,
    project_id: str,
    base_dir: Path,
) -> Path:
    """Trim filler spans from a proxy clip for one EditSegment.

    Writes a processed segment MP4 to outputs/{project_id}/segments/.
    Even if there are no filler spans, the segment is trimmed to
    [source_start, source_end] and written — giving assembly a consistent
    set of pre-trimmed segment files to concatenate.

    Raises ClipNotFoundError if the proxy is missing.
    Raises FFmpegError (with stderr) if transcoding fails.
    """
    proxy = Path(clip.proxy_path) if clip.proxy_path else proxy_path(base_dir, project_id, clip.id)
    if not proxy.exists():
        raise ClipNotFoundError(clip.id, str(proxy))

    seg_dir = outputs_dir(base_dir, project_id) / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    out = seg_dir / f"seg_{segment.order:04d}.mp4"

    spans = _active_spans(segment, clip)
    logger.info(
        "segment {} — {} filler span(s) to remove, source [{:.3f}, {:.3f}]",
        segment.order,
        len(spans),
        segment.source_start,
        segment.source_end,
    )
    _encode_segment(proxy, segment.source_start, segment.source_end, spans, out, segment.order)
    logger.info("segment {} written → {}", segment.order, out)
    return out


# ── Internals ─────────────────────────────────────────────────────────────────


def _active_spans(segment: EditSegment, clip: Clip) -> list[tuple[float, float]]:
    """Return filler spans (segment-relative timestamps) that fall within [source_start, source_end]."""
    if not clip.analysis:
        return []

    analysis = ClipAnalysis.model_validate(clip.analysis)
    seg_duration = segment.source_end - segment.source_start
    spans: list[tuple[float, float]] = []

    for span in analysis.filler_spans:
        rel_start = max(0.0, span.start - segment.source_start)
        rel_end = min(seg_duration, span.end - segment.source_start)
        if rel_end > rel_start:
            spans.append((rel_start, rel_end))

    return spans


def _encode_segment(
    proxy: Path,
    source_start: float,
    source_end: float,
    filler_spans: list[tuple[float, float]],
    out: Path,
    segment_order: int,
) -> None:
    # Using ss/to as input options performs a fast seek before the filter chain.
    # After the seek, the filter's `t` variable is reset to 0, so filler span
    # timestamps must be relative to source_start (done in _active_spans).
    inp = ffmpeg.input(str(proxy), ss=source_start, to=source_end)

    shared_opts = dict(
        vcodec="libx264",
        crf=23,
        preset="fast",
        acodec="aac",
        audio_bitrate="128k",
    )

    if filler_spans:
        not_clauses = [f"not(between(t,{s:.6f},{e:.6f}))" for s, e in filler_spans]
        select_expr = "*".join(not_clauses)
        out_node = inp.output(
            str(out),
            vf=f"select='{select_expr}',setpts=N/FRAME_RATE/TB",
            af=f"aselect='{select_expr}',asetpts=N/SR/TB",
            vsync="vfr",
            **shared_opts,
        )
    else:
        out_node = inp.output(str(out), **shared_opts)

    try:
        out_node.overwrite_output().run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        out.unlink(missing_ok=True)
        raise FFmpegError(
            f"FFmpeg failed on segment {segment_order}",
            stderr=stderr,
            stage="filler_removal",
        ) from exc
