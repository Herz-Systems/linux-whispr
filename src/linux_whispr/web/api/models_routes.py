"""Backend-scoped model management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from linux_whispr.constants import SUPPORTED_WHISPER_CPP_MODELS, SUPPORTED_WHISPER_MODELS
from linux_whispr.stt.model_manager import ModelManager, SUPPORTED_MODEL_BACKENDS
from linux_whispr.web.api.config_routes import get_active_config

router = APIRouter(tags=["models"])


def _get_model_manager() -> ModelManager:
    return ModelManager()


def _validate_backend(backend: str) -> str:
    if backend not in SUPPORTED_MODEL_BACKENDS:
        supported = ", ".join(SUPPORTED_MODEL_BACKENDS)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model backend '{backend}'; expected one of: {supported}",
        )
    return backend


def _validate_model_name(name: str, backend: str) -> None:
    supported_models = (
        SUPPORTED_WHISPER_CPP_MODELS if backend == "whisper-cpp" else SUPPORTED_WHISPER_MODELS
    )
    if name not in supported_models:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model '{name}' for backend '{backend}'",
        )


@router.get("/models")
async def list_models(backend: str | None = None) -> dict:
    """List supported models for the requested or configured model backend."""
    config = get_active_config()
    backend = _validate_backend(backend if backend is not None else config.stt.backend)
    manager = _get_model_manager()
    models = manager.list_models(backend=backend)
    configured_model_is_available = any(model.name == config.stt.model for model in models)
    active_model = (
        config.stt.model
        if config.stt.backend == backend and configured_model_is_available
        else None
    )
    return {
        "backend": backend,
        "models": [
            {
                "name": model.name,
                "size_mb": model.size_mb,
                "downloaded": model.downloaded,
                "active": model.name == active_model,
                "backend": backend,
            }
            for model in models
        ],
        "active_model": active_model,
    }


@router.post("/models/{name}/download")
async def download_model(name: str, backend: str | None = None) -> dict:
    """Download one backend-specific model without blocking the event loop."""
    backend = _validate_backend(
        backend if backend is not None else get_active_config().stt.backend
    )
    _validate_model_name(name, backend)
    manager = _get_model_manager()
    try:
        await run_in_threadpool(manager.download, name, backend=backend)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        return {"status": "error", "message": f"Download failed: {error}"}
    return {"status": "ok", "message": f"Model '{name}' downloaded"}


@router.delete("/models/{name}")
async def delete_model(name: str, backend: str | None = None) -> dict:
    """Delete one non-active backend-specific model."""
    config = get_active_config()
    backend = _validate_backend(backend if backend is not None else config.stt.backend)
    _validate_model_name(name, backend)
    if config.stt.backend == backend and config.stt.model == name:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete active model '{name}' for backend '{backend}'",
        )

    manager = _get_model_manager()
    try:
        deleted = await run_in_threadpool(manager.delete, name, backend=backend)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if deleted:
        return {"status": "ok", "message": f"Model '{name}' deleted"}
    return {"status": "error", "message": f"Model '{name}' not found or not downloaded"}


@router.get("/models/disk-usage")
async def get_disk_usage() -> dict:
    """Get total disk usage of downloaded models."""
    manager = _get_model_manager()
    usage_bytes = manager.get_disk_usage()
    return {
        "bytes": usage_bytes,
        "mb": round(usage_bytes / (1024 * 1024), 1),
        "gb": round(usage_bytes / (1024 * 1024 * 1024), 2),
    }
