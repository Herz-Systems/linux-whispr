"""Ollama model discovery API route."""

from __future__ import annotations

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from linux_whispr.ai.ollama import get_ollama_model_catalog

router = APIRouter(tags=["ollama"])


@router.get("/ollama/models")
async def list_ollama_models() -> dict:
    """List verified local Ollama completion models and static recommendations."""
    return await run_in_threadpool(get_ollama_model_catalog)
