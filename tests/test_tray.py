"""Focused tests for the Qt-native desktop tray."""

from __future__ import annotations

from enum import Enum, auto

import pytest

from linux_whispr.events import EventBus
from linux_whispr.ui.tray import SystemTray


class _State(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    ERROR = auto()


@pytest.fixture
def tray(monkeypatch: pytest.MonkeyPatch, qt_app: object) -> SystemTray:
    monkeypatch.setattr(SystemTray, "_is_host_available", staticmethod(lambda: True))
    indicator = SystemTray(EventBus())
    indicator.setup()
    yield indicator
    indicator.stop()


def _process_events(qt_app: object) -> None:
    qt_app.processEvents()  # type: ignore[union-attr]


class TestSystemTray:
    def test_state_icons_and_error_latch_are_generic(self, tray: SystemTray, qt_app: object) -> None:
        icon = tray._icon
        assert icon is not None
        assert icon.toolTip() == "LinuxWhispr — Starting"
        starting_icon = icon.icon().cacheKey()

        tray._event_bus.emit("state.change", new_state=_State.IDLE)
        _process_events(qt_app)
        ready_icon = icon.icon().cacheKey()
        assert icon.toolTip() == "LinuxWhispr — Ready"
        assert ready_icon != starting_icon

        tray._event_bus.emit("state.change", new_state=_State.RECORDING)
        _process_events(qt_app)
        recording_icon = icon.icon().cacheKey()
        assert icon.toolTip() == "LinuxWhispr — Recording"

        tray._event_bus.emit("state.change", new_state=_State.PROCESSING)
        _process_events(qt_app)
        assert icon.toolTip() == "LinuxWhispr — Processing"
        assert icon.icon().cacheKey() not in {starting_icon, ready_icon, recording_icon}

        tray._event_bus.emit("ai.error", message="dictated text must never be shown")
        _process_events(qt_app)
        assert icon.toolTip() == "LinuxWhispr — Needs attention"
        assert "dictated text" not in icon.toolTip()

        tray._event_bus.emit("state.change", new_state=_State.IDLE)
        _process_events(qt_app)
        assert icon.toolTip() == "LinuxWhispr — Needs attention"

        tray._event_bus.emit("state.change", new_state=_State.RECORDING)
        _process_events(qt_app)
        assert icon.toolTip() == "LinuxWhispr — Recording"


    def test_problem_state_allows_manual_restart(self, tray: SystemTray, qt_app: object) -> None:
        tray._event_bus.emit("app.error", message="microphone text")
        _process_events(qt_app)
        assert tray._toggle_action is not None
        assert tray._toggle_action.text() == "Start Dictation"
        assert tray._toggle_action.isEnabled()

    def test_late_events_do_not_mutate_stopped_tray(self, tray: SystemTray, qt_app: object) -> None:
        tray._event_bus.emit("state.change", new_state=_State.IDLE)
        _process_events(qt_app)

        tray.stop()
        tray._event_bus.emit("state.change", new_state=_State.RECORDING)
        tray._event_bus.emit("app.error", message="late worker event")
        _process_events(qt_app)

        assert tray._status == "ready"
        assert tray._icon is None
        assert tray._toggle_action is None

    def test_missing_host_fails_with_actionable_guidance(
        self, monkeypatch: pytest.MonkeyPatch, qt_app: object
    ) -> None:
        monkeypatch.setattr(SystemTray, "_is_host_available", staticmethod(lambda: False))
        with pytest.raises(RuntimeError, match="--no-tray"):
            SystemTray(EventBus()).setup()
