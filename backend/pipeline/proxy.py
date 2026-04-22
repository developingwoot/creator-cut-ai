from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import ffmpeg
from loguru import logger

from exceptions import ProxyGenerationError
from models.clip import Clip, ClipStatus
from storage.local import ensure_project_dirs, proxy_path, proxies_dir


def generate_proxy(
    clip: Clip,
    project_id: str,
    base_dir: Path,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Transcode clip.original_path to a 1280×720 H.264 proxy.

    Returns the Path to the proxy file. The caller is responsible for
    persisting clip.proxy_path and clip.status to the database.

    Raises ProxyGenerationError (with FFmpeg stderr) on transcode failure.
    """
    ensure_project_dirs(base_dir, project_id)
    out = proxy_path(base_dir, project_id, clip.id)

    if out.exists() and out.stat().st_size > 0:
        logger.debug("proxy already exists, skipping transcode: {}", out)
        return out

    clip.status = ClipStatus.proxying
    logger.info("generating proxy for clip {} → {}", clip.id, out)

    try:
        (
            ffmpeg
            .input(str(clip.original_path))
            .output(
                str(out),
                vf="scale=1280:720:force_original_aspect_ratio=decrease",
                vcodec="libx264",
                crf=23,
                preset="fast",
                acodec="aac",
                audio_bitrate="128k",
                movflags="+faststart",
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        # Clean up partial output so idempotency check doesn't skip a broken file.
        if out.exists():
            out.unlink(missing_ok=True)
        raise ProxyGenerationError(
            f"FFmpeg failed generating proxy for clip {clip.id}",
            stderr=stderr,
            clip_id=clip.id,
        ) from exc

    logger.info("proxy ready: {}", out)
    return out
