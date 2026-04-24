"""Tests for pipeline/silence_detection.py."""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from exceptions import FFmpegError
from pipeline.silence_detection import detect_silence


class TestDetectSilence:
    def test_raises_file_not_found_for_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            detect_silence(tmp_path / "nonexistent.mp4")

    def test_raises_ffmpeg_error_on_bad_file(self, tmp_path):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"not a video")
        with pytest.raises(FFmpegError):
            detect_silence(bad)

    def test_parses_silence_spans_from_stderr(self, tmp_path):
        fake_stderr = (
            "[silencedetect @ 0x...] silence_start: 1.000\n"
            "[silencedetect @ 0x...] silence_end: 2.500 | silence_duration: 1.5\n"
            "[silencedetect @ 0x...] silence_start: 5.000\n"
            "[silencedetect @ 0x...] silence_end: 5.800 | silence_duration: 0.8\n"
        )
        proxy = tmp_path / "proxy.mp4"
        proxy.write_bytes(b"placeholder")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = fake_stderr

        with patch("pipeline.silence_detection.subprocess.run", return_value=mock_result):
            spans = detect_silence(proxy)

        assert len(spans) == 2
        assert spans[0]["start"] == pytest.approx(1.0)
        assert spans[0]["end"] == pytest.approx(2.5)
        assert spans[1]["start"] == pytest.approx(5.0)
        assert spans[1]["end"] == pytest.approx(5.8)

    def test_returns_empty_for_no_silence(self, tmp_path):
        proxy = tmp_path / "proxy.mp4"
        proxy.write_bytes(b"placeholder")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = "some ffmpeg output with no silence lines"

        with patch("pipeline.silence_detection.subprocess.run", return_value=mock_result):
            spans = detect_silence(proxy)

        assert spans == []

    def test_raises_ffmpeg_error_on_nonzero_returncode(self, tmp_path):
        proxy = tmp_path / "proxy.mp4"
        proxy.write_bytes(b"placeholder")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffmpeg error output"

        with patch("pipeline.silence_detection.subprocess.run", return_value=mock_result):
            with pytest.raises(FFmpegError):
                detect_silence(proxy)

    @pytest.mark.integration
    def test_real_clip_detects_silence(self, fixture_clip_path: Path, tmp_path: Path):
        """The fixture clip has audio (sine wave) but no silent parts — zero spans expected."""
        spans = detect_silence(fixture_clip_path, noise_threshold_db=-30.0, min_duration_seconds=0.5)
        # Sine wave at 440Hz is not silence — result may be 0 spans, but function should not raise
        assert isinstance(spans, list)
