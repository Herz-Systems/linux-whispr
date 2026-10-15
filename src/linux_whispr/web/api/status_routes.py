"""Status API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from linux_whispr.constants import VERSION

router = APIRouter(tags=["status"])


@router.get("/status")
async def get_status(request: Request) -> dict[str, object]:
    """Report whether this dashboard has an attached dictation runtime."""
    runtime: dict[str, bool | str] = {"available": False, "state": "unavailable"}
    provider = getattr(request.app.state, "runtime_status_provider", None)
    if callable(provider):
        try:
            reported_runtime = provider()
        except Exception:
            reported_runtime = None
        if (
            isinstance(reported_runtime, dict)
            and reported_runtime.get("available") is True
            and isinstance(reported_runtime.get("state"), str)
        ):
            runtime = {
                "available": True,
                "state": reported_runtime["state"],
            }

    return {
        "version": VERSION,
        "status": "running" if runtime["available"] else "unavailable",
        "app_name": "LinuxWhispr",
        "runtime": runtime,
    }
