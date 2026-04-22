"""Tests for pipeline/proxy.py and pipeline/whisper_transcribe.py."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from exceptions import ProxyGenerationError
from models.clip import Clip, ClipStatus
from pipeline.proxy import generate_proxy
from pipeline.whisper_transcribe import transcribe_clip


def _make_clip(original_path: str | Path, proxy_path: str | Path | None = None) -> Clip:
    return Clip(
        id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        filename=Path(str(original_path)).name,
        original_path=str(original_path),
        proxy_path=str(proxy_path) if proxy_path else None,
    )


# ── Proxy tests ───────────────────────────────────────────────────────────────


class TestGenerateProxy:
    def test_creates_file(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(fixture_clip_path)
        out = generate_proxy(clip, clip.project_id, tmp_path)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_sets_proxying_status(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(fixture_clip_path)
        generate_proxy(clip, clip.project_id, tmp_path)
        # Status should have been set to proxying during generation.
        # After completion caller sets proxied — we only check it was touched.
        assert clip.status == ClipStatus.proxying

    def test_idempotent(self, fixture_clip_path: Path, tmp_path: Path):
        clip = _make_clip(fixture_clip_path)
        out1 = generate_proxy(clip, clip.project_id, tmp_path)
        mtime1 = out1.stat().st_mtime

        out2 = generate_proxy(clip, clip.project_id, tmp_path)
        assert out1 == out2
        assert out2.stat().st_mtime == mtime1  # not re-encoded

    def test_bad_input_raises(self, tmp_path: Path):
        clip = _make_clip("/nonexistent/path/clip.mp4")
        with pytest.raises(ProxyGenerationError):
            generate_proxy(clip, clip.project_id, tmp_path)

    def test_partial_output_cleaned_on_failure(self, tmp_path: Path):
        clip = _make_clip("/nonexistent/path/clip.mp4")
        try:
            generate_proxy(clip, clip.project_id, tmp_path)
        except ProxyGenerationError:
            pass
        from storage.local import proxy_path
        assert not proxy_path(tmp_path, clip.project_id, clip.id).exists()


# ── Transcription tests ───────────────────────────────────────────────────────


class TestTranscribeClip:
    def _make_proxy_clip(self, fixture_clip_path: Path, tmp_path: Path) -> Clip:
        """Generate a proxy for the fixture clip and return a Clip with proxy_path set."""
        clip = _make_clip(fixture_clip_path)
        proxy = generate_proxy(clip, clip.project_id, tmp_path)
        clip.proxy_path = str(proxy)
        return clip

    def test_returns_segments_dict(self, fixture_clip_path: Path, tmp_path: Path):
        clip = self._make_proxy_clip(fixture_clip_path, tmp_path)
        # Mock WhisperModel to avoid loading a real model in CI.
        fake_seg = MagicMock()
        fake_seg.start = 0.0
        fake_seg.end = 1.5
        fake_seg.text = "  hello world  "
        fake_info = MagicMock()

        with patch("pipeline.whisper_transcribe._load_model") as mock_load:
            mock_load.return_value.transcribe.return_value = ([fake_seg], fake_info)
            result = transcribe_clip(clip, clip.project_id, tmp_path)

        assert "segments" in result
        assert result["segments"][0]["text"] == "hello world"
        assert result["segments"][0]["start"] == 0.0

    def test_idempotent(self, fixture_clip_path: Path, tmp_path: Path):
        clip = self._make_proxy_clip(fixture_clip_path, tmp_path)
        fake_seg = MagicMock()
        fake_seg.start = 0.0
        fake_seg.end = 1.0
        fake_seg.text = "cached"
        fake_info = MagicMock()

        with patch("pipeline.whisper_transcribe._load_model") as mock_load:
            mock_load.return_value.transcribe.return_value = ([fake_seg], fake_info)
            result1 = transcribe_clip(clip, clip.project_id, tmp_path)

        # Second call should read from cache — _load_model not called again.
        with patch("pipeline.whisper_transcribe._load_model") as mock_load2:
            result2 = transcribe_clip(clip, clip.project_id, tmp_path)
            mock_load2.assert_not_called()

        assert result1 == result2

    def test_bad_proxy_path_nonfatal(self, tmp_path: Path):
        clip = _make_clip("/real/source.mp4", proxy_path="/nonexistent/proxy.mp4")
        result = transcribe_clip(clip, clip.project_id, tmp_path)
        assert result == {"segments": []}

    def test_no_proxy_path_nonfatal(self, tmp_path: Path):
        clip = _make_clip("/real/source.mp4")
        result = transcribe_clip(clip, clip.project_id, tmp_path)
        assert result == {"segments": []}

    def test_whisper_exception_nonfatal(self, fixture_clip_path: Path, tmp_path: Path):
        clip = self._make_proxy_clip(fixture_clip_path, tmp_path)
        with patch("pipeline.whisper_transcribe._load_model") as mock_load:
            mock_load.return_value.transcribe.side_effect = RuntimeError("boom")
            result = transcribe_clip(clip, clip.project_id, tmp_path)
        assert result == {"segments": []}

    def test_transcript_written_to_disk(self, fixture_clip_path: Path, tmp_path: Path):
        clip = self._make_proxy_clip(fixture_clip_path, tmp_path)
        fake_seg = MagicMock()
        fake_seg.start = 0.5
        fake_seg.end = 2.0
        fake_seg.text = "on disk"
        fake_info = MagicMock()

        with patch("pipeline.whisper_transcribe._load_model") as mock_load:
            mock_load.return_value.transcribe.return_value = ([fake_seg], fake_info)
            transcribe_clip(clip, clip.project_id, tmp_path)

        from storage.local import transcript_path
        saved = json.loads(transcript_path(tmp_path, clip.project_id, clip.id).read_text())
        assert saved["segments"][0]["text"] == "on disk"
