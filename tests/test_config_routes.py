"""Tests for dashboard configuration path handling."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from linux_whispr import config as config_module
from linux_whispr.config import AppConfig
from linux_whispr.platform import autostart
from linux_whispr.stt.model_manager import ModelInfo
from linux_whispr.web import server
from linux_whispr.web.api import config_routes, models_routes, status_routes


class StubModelManager:
    def list_models(self, *, backend: str) -> list[ModelInfo]:
        return [
            ModelInfo(name="base", size_mb=142, downloaded=True, path=Path("/models/base")),
            ModelInfo(name="tiny", size_mb=75, downloaded=False),
        ]


@pytest.mark.asyncio
async def test_dashboard_config_routes_persist_to_selected_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_path = tmp_path / "default.toml"
    selected_path = tmp_path / "selected.toml"
    monkeypatch.setattr(config_module, "CONFIG_FILE", default_path)

    config = AppConfig()
    config.hotkey.dictation = "F8"
    config.save(selected_path)

    server.set_config_path(selected_path)
    assert server.app.state.config_path == selected_path
    try:
        response = await config_routes.update_config(
            {"stt": {"model": "small"}, "first_run": False}
        )
        active_config = await config_routes.get_config()
    finally:
        server.set_config_path(None)

    persisted = AppConfig.load(selected_path)
    assert response == {"status": "ok", "message": "Configuration saved"}
    assert persisted.stt.model == "small"
    assert persisted.hotkey.dictation == "F8"
    assert persisted.first_run is False
    assert active_config["stt"]["model"] == "small"
    assert not default_path.exists()


@pytest.mark.asyncio
async def test_dashboard_startup_preferences_persist_and_manage_autostart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_path = tmp_path / "selected.toml"
    autostart_dir = tmp_path / "xdg" / "autostart"
    launcher_path = tmp_path / "bin path" / "linux-whispr"
    monkeypatch.setattr(autostart, "AUTOSTART_DIR", autostart_dir)
    monkeypatch.setenv("LINUX_WHISPR_LAUNCHER", str(launcher_path))

    config = AppConfig()
    config.web.port = 7_777
    config.save(selected_path)

    server.set_config_path(selected_path)
    try:
        response = await config_routes.update_config({"web": {"auto_open": False}})
        saved_preferences = AppConfig.load(selected_path)
        entry_absent_before_enable = not (
            autostart_dir / autostart.DESKTOP_ENTRY_NAME
        ).exists()
        enabled_response = await config_routes.update_config({"autostart": True})
        entry_path = autostart_dir / autostart.DESKTOP_ENTRY_NAME
        initial_entry_content = entry_path.read_text()
        entry_path.write_text("custom entry")
        await config_routes.update_config(await config_routes.get_config())
        entry_after_full_save = entry_path.read_text()
        disabled_response = await config_routes.update_config({"autostart": False})
        await config_routes.update_config({"autostart": True})
        reset_response = await config_routes.reset_config()
    finally:
        server.set_config_path(None)

    persisted = AppConfig.load(selected_path)
    assert response == {"status": "ok", "message": "Configuration saved"}
    assert saved_preferences.web.auto_open is False
    assert saved_preferences.web.port == 7_777
    assert saved_preferences.autostart is False
    assert entry_absent_before_enable
    assert enabled_response == {"status": "ok", "message": "Configuration saved"}
    assert f'Exec="{launcher_path}"' in initial_entry_content
    assert entry_after_full_save == "custom entry"
    assert disabled_response == {"status": "ok", "message": "Configuration saved"}
    assert reset_response == {"status": "ok", "message": "Configuration reset to defaults"}
    assert not (autostart_dir / autostart.DESKTOP_ENTRY_NAME).exists()
    assert persisted.web.auto_open is True
    assert persisted.web.port == AppConfig().web.port
    assert persisted.autostart is False


@pytest.mark.asyncio
async def test_autostart_failure_does_not_persist_claimed_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_path = tmp_path / "selected.toml"
    config = AppConfig()
    config.web.auto_open = False
    config.save(selected_path)

    autostart_dir = tmp_path / "xdg" / "autostart"
    autostart_dir.parent.mkdir()
    autostart_dir.write_text("not a directory")
    monkeypatch.setattr(autostart, "AUTOSTART_DIR", autostart_dir)

    server.set_config_path(selected_path)
    try:
        with pytest.raises(HTTPException) as error:
            await config_routes.update_config({"autostart": True})
    finally:
        server.set_config_path(None)

    persisted = AppConfig.load(selected_path)
    assert error.value.status_code == 500
    assert "desktop autostart" in error.value.detail
    assert persisted.autostart is False
    assert persisted.web.auto_open is False


@pytest.mark.asyncio
async def test_preload_settings_partial_updates_and_reset_use_selected_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_path = tmp_path / "selected.toml"
    config = AppConfig()
    config.stt.model = "small"
    config.audio.silence_duration = 2.0
    monkeypatch.setattr(config_routes, "disable_autostart", lambda: None)
    config.save(selected_path)

    server.set_config_path(selected_path)
    try:
        response = await config_routes.update_config(
            {"preload_models": False, "ai": {"keep_alive_minutes": 30}}
        )
        updated = AppConfig.load(selected_path)
        reset_response = await config_routes.reset_config()
        reset = AppConfig.load(selected_path)
    finally:
        server.set_config_path(None)

    assert response == {"status": "ok", "message": "Configuration saved"}
    assert updated.preload_models is False
    assert updated.ai.keep_alive_minutes == 30
    assert updated.stt.model == "small"
    assert updated.audio.silence_duration == 2.0
    assert reset_response == {"status": "ok", "message": "Configuration reset to defaults"}
    assert reset.preload_models is AppConfig().preload_models
    assert reset.ai.keep_alive_minutes == AppConfig().ai.keep_alive_minutes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "update",
    [
        {"preload_models": "false"},
        {"ai": {"keep_alive_minutes": 10}},
    ],
)
async def test_invalid_preload_settings_do_not_save(
    tmp_path: Path, update: dict[str, object]
) -> None:
    selected_path = tmp_path / "selected.toml"
    config = AppConfig()
    config.stt.model = "small"
    config.audio.silence_duration = 2.0
    config.save(selected_path)

    server.set_config_path(selected_path)
    try:
        with pytest.raises(HTTPException) as error:
            await config_routes.update_config(update)
    finally:
        server.set_config_path(None)

    persisted = AppConfig.load(selected_path)
    assert error.value.status_code == 400
    assert persisted.stt.model == "small"
    assert persisted.audio.silence_duration == 2.0


@pytest.mark.asyncio
async def test_status_exposes_model_preparation_without_changing_runtime_state() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                runtime_status_provider=lambda: {
                    "available": True,
                    "state": "idle",
                    "models_preparing": True,
                }
            )
        )
    )

    response = await status_routes.get_status(request)

    assert response["runtime"] == {
        "available": True,
        "state": "idle",
        "models_preparing": True,
    }


@pytest.mark.asyncio
async def test_models_uses_selected_config_for_active_model_and_default_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_path = tmp_path / "selected.toml"
    config = AppConfig()
    config.stt.backend = "whisper-cpp"
    config.stt.model = "base"
    config.save(selected_path)
    monkeypatch.setattr(models_routes, "_get_model_manager", StubModelManager)

    server.set_config_path(selected_path)
    try:
        response = await models_routes.list_models()
    finally:
        server.set_config_path(None)

    assert response["backend"] == "whisper-cpp"
    assert response["active_model"] == "base"
    assert response["models"][0]["active"] is True
