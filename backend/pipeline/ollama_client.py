from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from loguru import logger

from config import settings
from exceptions import OllamaUnreachableError

_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
_MAX_RETRIES = 2

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=settings.ollama_host, timeout=_TIMEOUT)
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None


async def tags() -> list[str]:
    """Return locally installed model names."""
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            r = await get_client().get("/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except httpx.ConnectError as exc:
            if attempt > _MAX_RETRIES:
                raise OllamaUnreachableError(settings.ollama_host) from exc
            logger.warning("ollama tags attempt {}: connection error, retrying", attempt)
    return []


async def pull(model: str) -> AsyncIterator[dict[str, Any]]:
    """Stream pull progress events from Ollama (NDJSON) as dicts."""
    try:
        async with get_client().stream(
            "POST", "/api/pull", json={"name": model}
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        pass
    except httpx.ConnectError as exc:
        raise OllamaUnreachableError(settings.ollama_host) from exc


async def generate(
    model: str,
    prompt: str,
    images: list[str] | None = None,
    fmt: str | None = "json",
    options: dict[str, Any] | None = None,
) -> str:
    """Run a single /api/generate call (non-streaming). Returns the response text."""
    payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
    if images:
        payload["images"] = images
    if fmt:
        payload["format"] = fmt
    if options:
        payload["options"] = options

    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            r = await get_client().post("/api/generate", json=payload)
            r.raise_for_status()
            return r.json()["response"]
        except httpx.ConnectError as exc:
            if attempt > _MAX_RETRIES:
                raise OllamaUnreachableError(settings.ollama_host) from exc
            logger.warning("ollama generate attempt {}: connection error, retrying", attempt)
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unexpected Ollama response format: {exc}") from exc
    return ""  # unreachable


async def chat(
    model: str,
    messages: list[dict[str, Any]],
    fmt: str | None = "json",
    options: dict[str, Any] | None = None,
) -> str:
    """Run a single /api/chat call (non-streaming). Returns the assistant message content."""
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    if fmt:
        payload["format"] = fmt
    if options:
        payload["options"] = options

    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            r = await get_client().post("/api/chat", json=payload)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except httpx.ConnectError as exc:
            if attempt > _MAX_RETRIES:
                raise OllamaUnreachableError(settings.ollama_host) from exc
            logger.warning("ollama chat attempt {}: connection error, retrying", attempt)
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unexpected Ollama response format: {exc}") from exc
    return ""  # unreachable
