from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from models.clip import Clip, ClipStatus
from pipeline.whisper_transcribe import _load_model
from storage.local import ensure_project_dirs, transcript_path

_WORD_CACHE_KEY_SUFFIX = "_words"


def transcribe_clip_with_words(
    clip: Clip,
    project_id: str,
    base_dir: Path,
    whisper_model: str = "medium",
) -> dict:
    """Transcribe clip.proxy_path with word-level timestamps.

    Returns {"segments": [{start, end, text}], "words": [{start, end, word}]}.
    Non-fatal: on any error returns {"segments": [], "words": []}.
    The caller is responsible for persisting clip.transcript and clip.status.

    Shares the model cache from whisper_transcribe to avoid double-loading.
    """
    ensure_project_dirs(base_dir, project_id)
    out = transcript_path(base_dir, project_id, clip.id)

    if out.exists() and out.stat().st_size > 0:
        cached = json.loads(out.read_text())
        if "words" in cached:
            logger.debug("word-transcript cache hit for clip {}", clip.id)
            return cached

    if not clip.proxy_path:
        logger.warning("clip {} has no proxy_path — skipping transcription", clip.id)
        return {"segments": [], "words": []}

    proxy = Path(clip.proxy_path)
    if not proxy.exists():
        logger.warning("proxy not found at {} — skipping transcription", proxy)
        return {"segments": [], "words": []}

    clip.status = ClipStatus.transcribing
    logger.info("word-transcribing clip {} with Whisper '{}'", clip.id, whisper_model)

    try:
        model = _load_model(whisper_model)
        segments_iter, _ = model.transcribe(str(proxy), beam_size=5, word_timestamps=True)

        segments: list[dict] = []
        words: list[dict] = []

        for seg in segments_iter:
            segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
            if seg.words:
                for w in seg.words:
                    words.append({"start": w.start, "end": w.end, "word": w.word})

        result = {"segments": segments, "words": words}
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        logger.info(
            "word transcript written: {} ({} segments, {} words)",
            out, len(segments), len(words),
        )
        return result

    except Exception as exc:
        logger.warning(
            "word transcription failed for clip {} — continuing without transcript: {}",
            clip.id, exc,
        )
        return {"segments": [], "words": []}
