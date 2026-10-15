"""Focused regression tests for the native dictation activity overlay."""

from __future__ import annotations

import math
import threading
from enum import Enum, auto

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from linux_whispr.events import EventBus
from linux_whispr.ui.overlay import Overlay, OverlayState


class _ApplicationState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    ERROR = auto()


@pytest.fixture
def overlay(qt_app: object, event_bus: EventBus) -> Overlay:
    instance = Overlay(event_bus)
    instance.setup()
    yield instance
    instance.destroy()
    qt_app.processEvents()  # type: ignore[attr-defined]


def _emit_state(event_bus: EventBus, state: _ApplicationState) -> None:
    event_bus.emit("state.change", old_state=None, new_state=state)


def _flush(qt_app: object) -> None:
    qt_app.processEvents()  # type: ignore[attr-defined]


def test_initial_idle_confirms_readiness_on_the_active_screen(
    qt_app: object, event_bus: EventBus, overlay: Overlay
) -> None:
    _emit_state(event_bus, _ApplicationState.IDLE)
    _flush(qt_app)

    assert overlay._state is OverlayState.IDLE
    assert overlay._window is not None
    assert overlay._window.isVisible()
    assert overlay._window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert overlay._window.focusPolicy() is Qt.FocusPolicy.NoFocus

    screen = QGuiApplication.screenAt(overlay._window.frameGeometry().center())
    assert screen is not None
    assert screen.availableGeometry().contains(overlay._window.frameGeometry())


def test_error_latches_before_injection_completion(
    qt_app: object, event_bus: EventBus, overlay: Overlay
) -> None:
    _emit_state(event_bus, _ApplicationState.RECORDING)
    event_bus.emit("app.error", message="microphone unavailable")
    event_bus.emit("inject.complete", text="ignored")
    _flush(qt_app)

    assert overlay._state is OverlayState.ERROR
    assert overlay._error_attempt == overlay._attempt
    assert overlay._window is not None
    assert overlay._window.isVisible()


def test_stale_completion_timer_cannot_hide_a_new_recording(
    qt_app: object, event_bus: EventBus, overlay: Overlay
) -> None:
    _emit_state(event_bus, _ApplicationState.RECORDING)
    event_bus.emit("inject.complete", text="first attempt")
    _flush(qt_app)

    stale_token = overlay._scheduled_token
    stale_attempt = overlay._scheduled_attempt
    stale_state = overlay._scheduled_state
    assert stale_state is OverlayState.DONE

    _emit_state(event_bus, _ApplicationState.RECORDING)
    _flush(qt_app)
    overlay._hide_if_current(stale_token, stale_state, stale_attempt)

    assert overlay._state is OverlayState.RECORDING
    assert overlay._window is not None
    assert overlay._window.isVisible()


def test_background_event_bus_notifications_are_queued_to_the_gui_thread(
    qt_app: object, event_bus: EventBus, overlay: Overlay
) -> None:
    worker = threading.Thread(
        target=_emit_state, args=(event_bus, _ApplicationState.RECORDING)
    )
    worker.start()
    worker.join()

    assert overlay._state is OverlayState.HIDDEN
    _flush(qt_app)
    assert overlay._state is OverlayState.RECORDING


def test_audio_levels_are_clamped_and_smoothed_for_recording_artwork(
    qt_app: object, event_bus: EventBus, overlay: Overlay
) -> None:
    _emit_state(event_bus, _ApplicationState.RECORDING)
    event_bus.emit("audio.level", level=2.0)
    _flush(qt_app)

    assert 0.0 < overlay._audio_level < 1.0
    previous_level = overlay._audio_level
    event_bus.emit("audio.level", level=math.nan)
    _flush(qt_app)

    assert 0.0 <= overlay._audio_level < previous_level
    assert overlay._window is not None
    assert overlay._window._audio_level == overlay._audio_level
