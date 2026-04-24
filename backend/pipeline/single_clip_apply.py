from __future__ import annotations

from pathlib import Path

from loguru import logger

from exceptions import ClipNotFoundError, SingleClipNotProcessedError
from models.clip import Clip, SingleClipAnalysis
from pipeline.filler_removal import _encode_segment
from storage.local import outputs_dir, proxy_path, single_clip_output_path


def apply_single_clip_edits(
    clip: Clip,
    project_id: str,
    base_dir: Path,
    remove_fillers: bool,
    remove_silence: bool,
) -> Path:
    """Apply filler and/or silence removal to the full clip in one FFmpeg pass.

    Reads filler_spans and silence_spans from clip.analysis (SingleClipAnalysis).
    Writes the result to outputs/{project_id}/{clip_id}_edited.mp4.

    Raises ClipNotFoundError if the proxy is missing.
    Raises SingleClipNotProcessedError if clip.analysis is absent.
    Raises FFmpegError (with stderr) if transcoding fails.
    """
    if not clip.analysis:
        raise SingleClipNotProcessedError(clip.id)

    proxy = Path(clip.proxy_path) if clip.proxy_path else proxy_path(base_dir, project_id, clip.id)
    if not proxy.exists():
        raise ClipNotFoundError(clip.id, str(proxy))

    analysis = SingleClipAnalysis.model_validate(clip.analysis)
    duration = clip.duration_seconds or 0.0

    spans: list[tuple[float, float]] = []
    if remove_fillers:
        spans += [(s.start, s.end) for s in analysis.filler_spans]
    if remove_silence:
        spans += [(s.start, s.end) for s in analysis.silence_spans]

    merged = _merge_spans(spans)

    outputs_dir(base_dir, project_id).mkdir(parents=True, exist_ok=True)
    out = single_clip_output_path(base_dir, project_id, clip.id)

    logger.info(
        "applying {} span(s) to clip {} (remove_fillers={}, remove_silence={})",
        len(merged), clip.id, remove_fillers, remove_silence,
    )
    _encode_segment(proxy, 0.0, duration, merged, out, segment_order=0)
    logger.info("single-clip edit written → {}", out)
    return out


def _merge_spans(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sort and merge overlapping or adjacent time spans."""
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: s[0])
    merged: list[tuple[float, float]] = [sorted_spans[0]]
    for start, end in sorted_spans[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged
