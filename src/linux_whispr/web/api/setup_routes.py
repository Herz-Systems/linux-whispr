"""Optimal setup detection API route."""

from __future__ import annotations

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from linux_whispr.platform.optimal_setup import detect_optimal_setup

router = APIRouter(tags=["setup"])


@router.get("/setup/detect")
async def detect_setup() -> dict:
    """Detect local hardware and recommend a supported dictation setup."""
    detected = await run_in_threadpool(detect_optimal_setup)
    return {
        "status": "ok",
        "hardware": detected["hardware"],
        "recommendation": detected["recommendation"],
        "warnings": detected["warnings"],
    }
