from __future__ import annotations

import re

_FILLER_UNIGRAMS: frozenset[str] = frozenset({
    "um", "uh", "like", "so", "basically", "literally",
    "right", "okay", "actually",
})

_FILLER_BIGRAMS: frozenset[tuple[str, str]] = frozenset({
    ("you", "know"),
    ("i", "mean"),
    ("kind", "of"),
    ("sort", "of"),
    ("you", "know", ),
})

_STRIP_PUNCT = re.compile(r"[^\w']")
_MIN_SPAN_DURATION = 0.05  # skip Whisper timing artifacts shorter than this


def _clean(word: str) -> str:
    return _STRIP_PUNCT.sub("", word).lower()


def detect_fillers_from_words(words: list[dict]) -> list[dict]:
    """Identify filler word spans from word-level Whisper output.

    Args:
        words: list of {"start": float, "end": float, "word": str}

    Returns list of {"start": float, "end": float, "word": str}.
    Matches both single-word and two-word fillers (e.g. "you know", "i mean").
    Skips spans shorter than 50ms (likely Whisper artifacts).
    """
    if not words:
        return []

    fillers: list[dict] = []
    i = 0

    while i < len(words):
        w0 = _clean(words[i]["word"])

        # Try bigram match first (greedy)
        if i + 1 < len(words):
            w1 = _clean(words[i + 1]["word"])
            if (w0, w1) in _FILLER_BIGRAMS:
                start = words[i]["start"]
                end = words[i + 1]["end"]
                if end - start >= _MIN_SPAN_DURATION:
                    fillers.append({"start": start, "end": end, "word": f"{w0} {w1}"})
                i += 2
                continue

        if w0 in _FILLER_UNIGRAMS:
            start = words[i]["start"]
            end = words[i]["end"]
            if end - start >= _MIN_SPAN_DURATION:
                fillers.append({"start": start, "end": end, "word": w0})

        i += 1

    return fillers
