from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

import httpx
import psutil
from loguru import logger

from config import settings
from exceptions import OllamaModelMissingError, OllamaUnreachableError
from pipeline import ollama_client

_RAM_TIER_THRESHOLD_GB = 16.0

# Default model sets per tier
_TIER_MODELS: dict[str, dict[str, str]] = {
    "default": {
        "vlm": "qwen2.5vl:7b",
        "llm": "qwen2.5:7b-instruct",
        "whisper": "medium",
    },
    "low_spec": {
        "vlm": "moondream:1.8b",
        "llm": "llama3.2:3b-instruct",
        "whisper": "small",
    },
}


@dataclass
class PullEvent:
    model: str
    status: str
    completed: int
    total: int


def detect_tier() -> Literal["default", "low_spec"]:
    """Return 'default' if ≥16 GB RAM is available, else 'low_spec'."""
    ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    tier: Literal["default", "low_spec"] = "default" if ram_gb >= _RAM_TIER_THRESHOLD_GB else "low_spec"
    logger.info("detected {:.1f} GB RAM → tier={}", ram_gb, tier)
    return tier


def required_models(tier: str | None = None) -> dict[str, str]:
    """Return the VLM and LLM model tags for the given tier (auto-detects if None)."""
    t = tier or detect_tier()
    return _TIER_MODELS.get(t, _TIER_MODELS["default"])


async def _probe_ollama() -> bool:
    """Return True if Ollama responds on its API endpoint."""
    try:
        r = await httpx.AsyncClient(timeout=5.0).get(f"{settings.ollama_host}/api/tags")
        return r.status_code == 200
    except Exception:
        return False


async def ensure_running() -> None:
    """Probe Ollama; attempt to spawn `ollama serve` if unreachable.

    Raises OllamaUnreachableError after the spawn attempt if still unreachable.
    This is a *soft* failure from validate_startup's perspective — the backend
    still starts and serves the setup screen; the frontend gates workflow entry.
    """
    if await _probe_ollama():
        logger.info("[OK] Ollama reachable at {}", settings.ollama_host)
        return

    logger.warning("[WARN] Ollama not reachable — attempting auto-spawn")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        logger.warning("[WARN] `ollama` binary not on PATH — install from https://ollama.com/download")
        raise OllamaUnreachableError(settings.ollama_host)

    # Poll for up to 5 seconds
    for _ in range(10):
        await asyncio.sleep(0.5)
        if await _probe_ollama():
            logger.info("[OK] Ollama spawned and reachable")
            return

    raise OllamaUnreachableError(settings.ollama_host)


async def get_missing_models(required: list[str]) -> list[str]:
    """Return model names from `required` that are not yet installed locally."""
    try:
        installed = await ollama_client.tags()
        installed_names = {m.split(":")[0] + ":" + (m.split(":")[1] if ":" in m else "latest") for m in installed}
        # Also match bare names without tag vs names with :latest
        installed_set = set(installed)
        missing = []
        for model in required:
            normalized = model if ":" in model else f"{model}:latest"
            if model not in installed_set and normalized not in installed_set:
                missing.append(model)
        return missing
    except OllamaUnreachableError:
        return required


async def pull_with_progress(model: str) -> AsyncIterator[PullEvent]:
    """Stream pull progress for a single model as PullEvent objects."""
    async for raw in ollama_client.pull(model):
        status = raw.get("status", "")
        completed = raw.get("completed", 0)
        total = raw.get("total", 0)
        yield PullEvent(model=model, status=status, completed=completed, total=total)
