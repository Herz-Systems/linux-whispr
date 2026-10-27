"""Configuration API routes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from linux_whispr.config import AppConfig
from linux_whispr.constants import OLLAMA_KEEP_ALIVE_OPTIONS
from linux_whispr.platform.autostart import disable_autostart, enable_autostart

router = APIRouter(tags=["config"])


_config_path: Path | None = None


def set_config_path(path: Path | None) -> None:
    """Set the configuration file used by dashboard configuration APIs."""
    global _config_path
    _config_path = path


def get_active_config() -> AppConfig:
    """Load the configuration selected for the active dashboard."""
    if _config_path is None:
        return AppConfig.load()
    return AppConfig.load(_config_path)


def save_active_config(config: AppConfig) -> None:
    """Persist a dashboard configuration to its active file."""
    if _config_path is None:
        config.save()
    else:
        config.save(_config_path)


def _strip_none(d: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _strip_none(v)
        elif v is not None:
            result[k] = v
    return result


def _validate_update(data: dict[str, Any]) -> None:
    """Reject invalid preload settings before any configuration side effects."""
    if "preload_models" in data and not isinstance(data["preload_models"], bool):
        raise HTTPException(
            status_code=400, detail="preload_models must be a boolean"
        )

    ai = data.get("ai")
    if isinstance(ai, dict) and "keep_alive_minutes" in ai:
        keep_alive_minutes = ai["keep_alive_minutes"]
        if (
            not isinstance(keep_alive_minutes, int)
            or isinstance(keep_alive_minutes, bool)
            or keep_alive_minutes not in OLLAMA_KEEP_ALIVE_OPTIONS
        ):
            allowed = ", ".join(str(value) for value in OLLAMA_KEEP_ALIVE_OPTIONS)
            raise HTTPException(
                status_code=400,
                detail=f"ai.keep_alive_minutes must be one of: {allowed}",
            )


@router.get("/config")
async def get_config() -> dict:
    """Get the full application configuration."""
    config = get_active_config()
    return _strip_none(asdict(config))


@router.put("/config")
async def update_config(data: dict[str, Any]) -> dict:
    """Update configuration with partial data. Merges with existing config."""
    config = get_active_config()

    _validate_update(data)

    section_map = {
        "audio": config.audio,
        "stt": config.stt,
        "ai": config.ai,
        "hotkey": config.hotkey,
        "injection": config.injection,
        "history": config.history,
        "adaptive": config.adaptive,
        "web": config.web,
    }

    for section_name, section_obj in section_map.items():
        if section_name in data and isinstance(data[section_name], dict):
            for key, val in data[section_name].items():
                if hasattr(section_obj, key):
                    setattr(section_obj, key, val)

    autostart_changed = "autostart" in data and data["autostart"] != config.autostart

    if "preload_models" in data:
        config.preload_models = data["preload_models"]
    if autostart_changed:
        try:
            if data["autostart"]:
                enable_autostart()
            else:
                disable_autostart()
        except OSError as error:
            raise HTTPException(
                status_code=500, detail=f"Could not update desktop autostart: {error}"
            ) from error

    if "autostart" in data:
        config.autostart = data["autostart"]
    if "first_run" in data:
        config.first_run = data["first_run"]

    try:
        save_active_config(config)
    except OSError as error:
        raise HTTPException(
            status_code=500, detail=f"Could not save configuration: {error}"
        ) from error
    return {"status": "ok", "message": "Configuration saved"}


@router.post("/config/reset")
async def reset_config() -> dict:
    """Reset configuration to defaults."""
    try:
        disable_autostart()
    except OSError as error:
        raise HTTPException(
            status_code=500, detail=f"Could not disable desktop autostart: {error}"
        ) from error

    config = AppConfig()
    try:
        save_active_config(config)
    except OSError as error:
        raise HTTPException(
            status_code=500, detail=f"Could not reset configuration: {error}"
        ) from error
    return {"status": "ok", "message": "Configuration reset to defaults"}
