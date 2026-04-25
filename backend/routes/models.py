from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from exceptions import OllamaUnreachableError
from pipeline import ollama_client
from pipeline.ollama_lifecycle import (
    detect_tier,
    get_missing_models,
    pull_with_progress,
    required_models,
)

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelStatusResponse(BaseModel):
    installed: list[str]
    required: list[str]
    missing: list[str]
    ollama_reachable: bool


class TierResponse(BaseModel):
    tier: Literal["default", "low_spec"]
    vlm: str
    llm: str
    whisper: str
    required: list[str]


class PullRequest(BaseModel):
    model: str


@router.get("/status", response_model=ModelStatusResponse)
async def get_model_status() -> ModelStatusResponse:
    """Return which required models are installed vs missing."""
    try:
        installed = await ollama_client.tags()
        tier_models = required_models()
        req = [tier_models["vlm"], tier_models["llm"]]
        missing = await get_missing_models(req)
        return ModelStatusResponse(
            installed=installed,
            required=req,
            missing=missing,
            ollama_reachable=True,
        )
    except OllamaUnreachableError:
        return ModelStatusResponse(
            installed=[],
            required=[],
            missing=[],
            ollama_reachable=False,
        )


@router.get("/tier", response_model=TierResponse)
async def get_tier() -> TierResponse:
    """Return the auto-detected model tier and the required model tags."""
    tier = detect_tier()
    models = required_models(tier)
    return TierResponse(
        tier=tier,
        vlm=models["vlm"],
        llm=models["llm"],
        whisper=models["whisper"],
        required=[models["vlm"], models["llm"]],
    )


@router.post("/pull")
async def pull_model(body: PullRequest) -> StreamingResponse:
    """Stream pull progress for a model as SSE events."""

    async def _sse_stream():
        try:
            async for event in pull_with_progress(body.model):
                data = json.dumps({
                    "model": event.model,
                    "status": event.status,
                    "completed": event.completed,
                    "total": event.total,
                })
                yield f"data: {data}\n\n"
                await asyncio.sleep(0)  # yield control to event loop

            # Final done event
            yield f"data: {json.dumps({'model': body.model, 'status': 'success', 'completed': 0, 'total': 0})}\n\n"
        except OllamaUnreachableError as exc:
            yield f"data: {json.dumps({'model': body.model, 'status': 'error', 'message': str(exc)})}\n\n"
        except Exception as exc:
            logger.error("pull stream error for {}: {}", body.model, exc)
            yield f"data: {json.dumps({'model': body.model, 'status': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        _sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
