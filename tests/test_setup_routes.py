"""Tests for the read-only optimal setup detection route."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from linux_whispr.web.api import setup_routes


@pytest.mark.asyncio
async def test_detect_setup_runs_detection_in_threadpool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detection = {
        "hardware": {
            "cpu_threads": 8,
            "ram_total_mb": 16_384,
            "ram_available_mb": 8_192,
            "gpus": [],
        },
        "recommendation": {
            "backend": "faster-whisper",
            "model": "small",
            "device": "cpu",
            "compute_type": "int8",
            "reason": "cpu",
            "download_size_mb": 461,
            "downloaded": False,
        },
        "warnings": [],
    }
    calls: list[Callable[[], dict]] = []

    async def fake_run_in_threadpool(function: Callable[[], dict]) -> dict:
        calls.append(function)
        return function()

    monkeypatch.setattr(setup_routes, "detect_optimal_setup", lambda: detection)
    monkeypatch.setattr(setup_routes, "run_in_threadpool", fake_run_in_threadpool)

    assert await setup_routes.detect_setup() == {"status": "ok", **detection}
    assert calls == [setup_routes.detect_optimal_setup]
