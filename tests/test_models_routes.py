"""Focused API tests for backend-scoped model management."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from linux_whispr.config import AppConfig
from linux_whispr.stt.model_manager import ModelInfo
from linux_whispr.web.api import models_routes


class StubModelManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.deleted = True

    def list_models(self, *, backend: str) -> list[ModelInfo]:
        self.calls.append(("list", backend))
        return [
            ModelInfo(name="base", size_mb=142, downloaded=True, path=Path("/models/base")),
            ModelInfo(name="tiny", size_mb=75, downloaded=False),
        ]

    def download(self, name: str, *, backend: str) -> Path:
        self.calls.append(("download", backend))
        return Path(f"/models/{backend}/{name}")

    def delete(self, name: str, *, backend: str) -> bool:
        self.calls.append(("delete", backend))
        return self.deleted


def configure_routes(
    monkeypatch: pytest.MonkeyPatch, manager: StubModelManager, config: AppConfig
) -> None:
    monkeypatch.setattr(models_routes, "_get_model_manager", lambda: manager)
    monkeypatch.setattr(models_routes.AppConfig, "load", lambda: config)


@pytest.mark.asyncio
async def test_list_models_scopes_active_model_to_requested_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = StubModelManager()
    config = AppConfig()
    config.stt.backend = "whisper-cpp"
    config.stt.model = "base"
    configure_routes(monkeypatch, manager, config)

    cpp_response = await models_routes.list_models(backend="whisper-cpp")
    faster_response = await models_routes.list_models(backend="faster-whisper")

    assert cpp_response["backend"] == "whisper-cpp"
    assert cpp_response["active_model"] == "base"
    assert cpp_response["models"] == [
        {
            "name": "base",
            "size_mb": 142,
            "downloaded": True,
            "active": True,
            "backend": "whisper-cpp",
        },
        {
            "name": "tiny",
            "size_mb": 75,
            "downloaded": False,
            "active": False,
            "backend": "whisper-cpp",
        },
    ]
    assert faster_response["active_model"] is None
    assert all(not model["active"] for model in faster_response["models"])
    assert manager.calls == [("list", "whisper-cpp"), ("list", "faster-whisper")]


@pytest.mark.asyncio
async def test_download_runs_manager_in_threadpool_with_captured_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = StubModelManager()
    config = AppConfig()
    configure_routes(monkeypatch, manager, config)
    threadpool_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def fake_run_in_threadpool(function: object, *args: object, **kwargs: object) -> object:
        threadpool_calls.append((function, args, kwargs))
        return function(*args, **kwargs)  # type: ignore[operator]

    monkeypatch.setattr(models_routes, "run_in_threadpool", fake_run_in_threadpool)

    response = await models_routes.download_model("tiny", backend="whisper-cpp")

    assert response == {"status": "ok", "message": "Model 'tiny' downloaded"}
    assert manager.calls == [("download", "whisper-cpp")]
    assert threadpool_calls == [(manager.download, ("tiny",), {"backend": "whisper-cpp"})]


@pytest.mark.asyncio
async def test_delete_rejects_the_active_model_without_touching_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = StubModelManager()
    config = AppConfig()
    config.stt.backend = "whisper-cpp"
    config.stt.model = "base"
    configure_routes(monkeypatch, manager, config)

    with pytest.raises(HTTPException) as error:
        await models_routes.delete_model("base", backend="whisper-cpp")

    assert error.value.status_code == 409
    assert "active" in str(error.value.detail).lower()
    assert manager.calls == []


@pytest.mark.asyncio
async def test_delete_uses_backend_scope_for_nonactive_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = StubModelManager()
    config = AppConfig()
    config.stt.backend = "whisper-cpp"
    config.stt.model = "base"
    configure_routes(monkeypatch, manager, config)

    response = await models_routes.delete_model("base", backend="faster-whisper")

    assert response == {"status": "ok", "message": "Model 'base' deleted"}
    assert manager.calls == [("delete", "faster-whisper")]


@pytest.mark.asyncio
async def test_illegal_backend_is_a_clear_client_error() -> None:
    with pytest.raises(HTTPException) as error:
        await models_routes.list_models(backend="unknown")

    assert error.value.status_code == 400
    assert "backend" in str(error.value.detail).lower()


@pytest.mark.asyncio
async def test_illegal_model_is_a_clear_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = StubModelManager()
    config = AppConfig()
    configure_routes(monkeypatch, manager, config)

    def reject_unknown_model(name: str, *, backend: str) -> Path:
        raise ValueError(f"Unsupported model '{name}' for backend '{backend}'")

    monkeypatch.setattr(manager, "download", reject_unknown_model)

    with pytest.raises(HTTPException) as error:
        await models_routes.download_model("unknown", backend="whisper-cpp")

    assert error.value.status_code == 400
    assert "unsupported model" in str(error.value.detail).lower()
