from __future__ import annotations

import json
from pathlib import Path
from loguru import logger

from models.clip import Clip, ClipStatus
from storage.local import ensure_project_dirs, transcript_path

# Module-level model cache — loaded once per process, not once per clip.
_whisper_cache: dict[str, object] = {}


def _load_model(model_size: str):
    if model_size not in _whisper_cache:
        from faster_whisper import WhisperModel  # deferred import: slow to load
        logger.info("loading Whisper model '{}'", model_size)
        _whisper_cache[model_size] = WhisperModel(
            model_size, device="cpu", compute_type="int8"
        )
    return _whisper_cache[model_size]


def transcribe_clip(
    clip: Clip,
    project_id: str,
    base_dir: Path,
    whisper_model: str = "medium",
) -> dict:
    """Transcribe clip.proxy_path with local Whisper.

    Returns {"segments": [{"start": float, "end": float, "text": str}]}.
    Non-fatal: on any error logs TranscriptionError and returns {"segments": []}.
    The caller is responsible for persisting clip.transcript and clip.status.
    """
    ensure_project_dirs(base_dir, project_id)
    out = transcript_path(base_dir, project_id, clip.id)

    if out.exists() and out.stat().st_size > 0:
        logger.debug("transcript cache hit for clip {}", clip.id)
        return json.loads(out.read_text())

    if not clip.proxy_path:
        logger.warning("clip {} has no proxy_path — skipping transcription", clip.id)
        return {"segments": []}

    proxy = Path(clip.proxy_path)
    if not proxy.exists():
        logger.warning("proxy not found at {} — skipping transcription", proxy)
        return {"segments": []}

    clip.status = ClipStatus.transcribing
    logger.info("transcribing clip {} with Whisper '{}'", clip.id, whisper_model)

    try:
        model = _load_model(whisper_model)
        segments_iter, _ = model.transcribe(str(proxy), beam_size=5)
        segments = [
            {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
            for seg in segments_iter
        ]
        result = {"segments": segments}
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        logger.info("transcript written: {} ({} segments)", out, len(segments))
        return result
    except Exception as exc:
        # Non-fatal: log and continue — Pass 1 will still analyse frames.
        logger.warning(
            "transcription failed for clip {} — continuing without transcript: {}",
            clip.id,
            exc,
        )
        return {"segments": []}
