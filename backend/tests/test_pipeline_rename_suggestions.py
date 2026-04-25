"""Tests for pipeline/rename_suggestions.py."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from pipeline.rename_suggestions import suggest_renames


def _patch_ollama(response_text: str):
    return patch(
        "pipeline.rename_suggestions.ollama_client.generate",
        new=AsyncMock(return_value=response_text),
    )


class TestSuggestRenames:
    def test_returns_three_suggestions(self):
        payload = json.dumps({"suggestions": ["Name A", "Name B", "Name C"]})
        with _patch_ollama(payload):
            result = asyncio.run(suggest_renames("Hello world this is a test", "clip.mp4"))
        assert result == ["Name A", "Name B", "Name C"]

    def test_degrades_gracefully_on_bad_json(self):
        with _patch_ollama("not json at all"):
            result = asyncio.run(suggest_renames("transcript text", "clip.mp4"))
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]

    def test_degrades_gracefully_on_missing_key(self):
        with _patch_ollama(json.dumps({"wrong_key": ["a", "b", "c"]})):
            result = asyncio.run(suggest_renames("transcript text", "clip.mp4"))
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]

    def test_degrades_gracefully_on_wrong_count(self):
        with _patch_ollama(json.dumps({"suggestions": ["only one"]})):
            result = asyncio.run(suggest_renames("transcript text", "clip.mp4"))
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]

    def test_degrades_gracefully_on_api_error(self):
        mock = AsyncMock(side_effect=Exception("Ollama unavailable"))
        with patch("pipeline.rename_suggestions.ollama_client.generate", mock):
            result = asyncio.run(suggest_renames("transcript text", "clip.mp4"))
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]

    def test_empty_transcript_returns_filename_fallback(self):
        mock = AsyncMock(return_value=json.dumps({"suggestions": ["a", "b", "c"]}))
        with patch("pipeline.rename_suggestions.ollama_client.generate", mock):
            result = asyncio.run(suggest_renames("", "clip.mp4"))
        assert result == ["clip.mp4", "clip.mp4", "clip.mp4"]
        mock.assert_not_called()

    def test_uses_configured_llm_model(self):
        payload = json.dumps({"suggestions": ["A", "B", "C"]})
        mock = AsyncMock(return_value=payload)
        with patch("pipeline.rename_suggestions.ollama_client.generate", mock):
            asyncio.run(suggest_renames("some text", "clip.mp4"))
        from config import settings
        called_model = mock.call_args.kwargs.get("model") or mock.call_args.args[0]
        assert called_model == settings.ollama_llm_model

    def test_suggestions_under_60_chars(self):
        suggestions = ["Short Name", "Another Good Name", "Third Valid Option"]
        payload = json.dumps({"suggestions": suggestions})
        with _patch_ollama(payload):
            result = asyncio.run(suggest_renames("some transcript text here", "clip.mp4"))
        assert all(len(s) <= 60 for s in result)
