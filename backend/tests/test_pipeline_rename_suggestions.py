"""Tests for pipeline/rename_suggestions.py."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pipeline.rename_suggestions import suggest_renames


def _make_client(response_text: str) -> MagicMock:
    client = MagicMock()
    content_block = MagicMock()
    content_block.text = response_text
    msg = MagicMock()
    msg.content = [content_block]
    client.messages.create.return_value = msg
    return client


class TestSuggestRenames:
    def test_returns_three_suggestions(self):
        payload = json.dumps({"suggestions": ["Name A", "Name B", "Name C"]})
        client = _make_client(payload)
        result = suggest_renames("Hello world this is a test", "clip.mp4", client)
        assert result == ["Name A", "Name B", "Name C"]

    def test_degrades_gracefully_on_bad_json(self):
        client = _make_client("not json at all")
        result = suggest_renames("transcript text", "clip.mp4", client)
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]

    def test_degrades_gracefully_on_missing_key(self):
        client = _make_client(json.dumps({"wrong_key": ["a", "b", "c"]}))
        result = suggest_renames("transcript text", "clip.mp4", client)
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]

    def test_degrades_gracefully_on_wrong_count(self):
        client = _make_client(json.dumps({"suggestions": ["only one"]}))
        result = suggest_renames("transcript text", "clip.mp4", client)
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]

    def test_degrades_gracefully_on_api_error(self):
        client = MagicMock()
        client.messages.create.side_effect = Exception("API unavailable")
        result = suggest_renames("transcript text", "clip.mp4", client)
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]

    def test_empty_transcript_returns_filename_fallback(self):
        client = _make_client(json.dumps({"suggestions": ["a", "b", "c"]}))
        result = suggest_renames("", "clip.mp4", client)
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]
        client.messages.create.assert_not_called()

    def test_uses_cache_control_ephemeral(self):
        payload = json.dumps({"suggestions": ["A", "B", "C"]})
        client = _make_client(payload)
        suggest_renames("some text", "clip.mp4", client)

        call_kwargs = client.messages.create.call_args.kwargs
        system_blocks = call_kwargs["system"]
        assert any(
            b.get("cache_control", {}).get("type") == "ephemeral"
            for b in system_blocks
        )

    def test_uses_sonnet_model(self):
        payload = json.dumps({"suggestions": ["A", "B", "C"]})
        client = _make_client(payload)
        suggest_renames("some text", "clip.mp4", client)

        call_kwargs = client.messages.create.call_args.kwargs
        assert "sonnet" in call_kwargs["model"]
