from __future__ import annotations

import re
import subprocess
from pathlib import Path

from loguru import logger

from exceptions import FFmpegError

_SILENCE_START_RE = re.compile(r"silence_start:\s*([\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([\d.]+)")


def detect_silence(
    proxy: Path,
    noise_threshold_db: float = -30.0,
    min_duration_seconds: float = 0.5,
) -> list[dict]:
    """Detect silence spans in a video file using FFmpeg's silencedetect filter.

    Returns [{"start": float, "end": float}, ...].
    Raises FFmpegError if FFmpeg exits with non-zero status.
    """
    if not proxy.exists():
        raise FileNotFoundError(f"Proxy not found: {proxy}")

    cmd = [
        "ffmpeg", "-i", str(proxy),
        "-af", f"silencedetect=noise={noise_threshold_db}dB:duration={min_duration_seconds}",
        "-f", "null", "-",
    ]

    logger.debug("running silencedetect on {}", proxy)
    result = subprocess.run(cmd, capture_output=True, text=True)

    # silencedetect writes to stderr regardless of exit code
    output = result.stderr

    if result.returncode != 0:
        raise FFmpegError(
            f"FFmpeg silencedetect failed on {proxy.name}",
            stderr=output,
            stage="silence_detection",
        )

    starts = [float(m.group(1)) for m in _SILENCE_START_RE.finditer(output)]
    ends = [float(m.group(1)) for m in _SILENCE_END_RE.finditer(output)]

    spans = [{"start": s, "end": e} for s, e in zip(starts, ends)]
    logger.info("silence detection: {} span(s) found in {}", len(spans), proxy.name)
    return spans
