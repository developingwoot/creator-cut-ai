"""Tests for pipeline/filler_detection.py."""
from __future__ import annotations

import pytest

from pipeline.filler_detection import detect_fillers_from_words


def _w(word: str, start: float, end: float) -> dict:
    return {"word": word, "start": start, "end": end}


class TestDetectFillersFromWords:
    def test_empty_input_returns_empty(self):
        assert detect_fillers_from_words([]) == []

    def test_detects_um(self):
        words = [_w("um", 1.0, 1.3), _w("hello", 1.4, 1.8)]
        result = detect_fillers_from_words(words)
        assert len(result) == 1
        assert result[0]["word"] == "um"
        assert result[0]["start"] == pytest.approx(1.0)
        assert result[0]["end"] == pytest.approx(1.3)

    def test_detects_uh(self):
        words = [_w("uh", 0.5, 0.9)]
        result = detect_fillers_from_words(words)
        assert len(result) == 1
        assert result[0]["word"] == "uh"

    def test_detects_like(self):
        words = [_w("like", 2.0, 2.4)]
        result = detect_fillers_from_words(words)
        assert len(result) == 1

    def test_detects_bigram_you_know(self):
        words = [_w("you", 1.0, 1.2), _w("know", 1.2, 1.5), _w("what", 1.6, 1.8)]
        result = detect_fillers_from_words(words)
        assert len(result) == 1
        assert result[0]["word"] == "you know"
        assert result[0]["start"] == pytest.approx(1.0)
        assert result[0]["end"] == pytest.approx(1.5)

    def test_detects_bigram_i_mean(self):
        words = [_w("i", 0.0, 0.1), _w("mean", 0.1, 0.3)]
        result = detect_fillers_from_words(words)
        assert len(result) == 1
        assert result[0]["word"] == "i mean"

    def test_skips_short_artifact_spans(self):
        # Word duration < 50ms should be skipped
        words = [_w("um", 1.0, 1.03)]
        assert detect_fillers_from_words(words) == []

    def test_strips_punctuation_before_matching(self):
        words = [_w("um,", 1.0, 1.3)]
        result = detect_fillers_from_words(words)
        assert len(result) == 1

    def test_case_insensitive_matching(self):
        words = [_w("Um", 0.5, 0.8), _w("UH", 1.0, 1.3)]
        result = detect_fillers_from_words(words)
        assert len(result) == 2

    def test_non_filler_word_not_detected(self):
        words = [_w("hello", 0.0, 0.5), _w("world", 0.6, 1.0)]
        assert detect_fillers_from_words(words) == []

    def test_bigram_preferred_over_unigram(self):
        # "you know" should match as bigram, not "you" if "you" were a filler
        words = [_w("you", 0.0, 0.2), _w("know", 0.2, 0.5)]
        result = detect_fillers_from_words(words)
        assert len(result) == 1
        assert result[0]["word"] == "you know"

    def test_multiple_fillers_in_sequence(self):
        words = [_w("um", 0.0, 0.3), _w("the", 0.4, 0.6), _w("uh", 0.7, 1.0)]
        result = detect_fillers_from_words(words)
        assert len(result) == 2

    def test_returns_correct_span_fields(self):
        words = [_w("basically", 2.0, 2.6)]
        result = detect_fillers_from_words(words)
        assert result[0].keys() == {"start", "end", "word"}
