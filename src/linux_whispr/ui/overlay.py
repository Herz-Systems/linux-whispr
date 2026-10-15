"""Qt floating activity indicator for dictation lifecycle feedback."""

from __future__ import annotations

import math
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from linux_whispr.ui.desktop import ensure_application

if TYPE_CHECKING:
    from linux_whispr.events import EventBus


class OverlayState(Enum):
    """Visual states exposed by the recording activity overlay."""

    HIDDEN = auto()
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    DONE = auto()
    ERROR = auto()
    COMMAND = auto()


_PILL_WIDTH = 228
_PILL_HEIGHT = 42
_CORNER_RADIUS = 21
_BOTTOM_MARGIN = 48
_READY_VISIBLE_MS = 1_400
_DONE_VISIBLE_MS = 1_200
_ERROR_VISIBLE_MS = 3_500

_STATE_COLORS: dict[OverlayState, QColor] = {
    OverlayState.IDLE: QColor(91, 190, 122),
    OverlayState.RECORDING: QColor(238, 79, 81),
    OverlayState.PROCESSING: QColor(96, 143, 239),
    OverlayState.DONE: QColor(79, 199, 120),
    OverlayState.ERROR: QColor(241, 149, 69),
    OverlayState.COMMAND: QColor(151, 119, 239),
}

_STATE_LABELS: dict[OverlayState, str] = {
    OverlayState.IDLE: "Ready",
    OverlayState.RECORDING: "Recording",
    OverlayState.PROCESSING: "Processing…",
    OverlayState.DONE: "Done",
    OverlayState.ERROR: "Needs attention",
    OverlayState.COMMAND: "Listening…",
}


class _PillWidget(QWidget):
    """Non-interactive translucent capsule, deliberately drawn without themes."""

    def __init__(self) -> None:
        super().__init__()
        self._state = OverlayState.HIDDEN
        self._audio_level = 0.0
        self._phase = 0

        self.setFixedSize(_PILL_WIDTH, _PILL_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )

    def set_visual(self, state: OverlayState, audio_level: float, phase: int) -> None:
        """Accept the current model values and request one inexpensive repaint."""
        self._state = state
        self._audio_level = audio_level
        self._phase = phase
        self.update()

    def paintEvent(self, _event: object) -> None:
        """Paint the compact state pill and only state-derived activity artwork."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 21, 26, 224))
        painter.drawRoundedRect(QRectF(self.rect()), _CORNER_RADIUS, _CORNER_RADIUS)

        state = self._state
        color = _STATE_COLORS.get(state, QColor(154, 158, 171))
        center_x, center_y = 27.0, self.height() / 2.0

        if state == OverlayState.RECORDING:
            self._paint_audio_bars(painter, color, center_x, center_y)
        elif state == OverlayState.PROCESSING:
            self._paint_spinner(painter, color, center_x, center_y)
        elif state == OverlayState.DONE:
            self._paint_check(painter, color, center_x, center_y)
        else:
            painter.setBrush(color)
            painter.drawEllipse(QRectF(center_x - 5, center_y - 5, 10, 10))

        label = _STATE_LABELS.get(state, "")
        painter.setPen(QColor(239, 240, 244, 235))
        painter.drawText(
            QRectF(52, 0, self.width() - 62, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label,
        )

    def _paint_audio_bars(
        self, painter: QPainter, color: QColor, center_x: float, center_y: float
    ) -> None:
        """Draw bars from the latest measured input level, not a synthetic pulse."""
        level = self._audio_level
        baseline = 4.0
        for index, multiplier in enumerate((0.52, 0.82, 1.0, 0.70, 0.46)):
            height = baseline + level * 17.0 * multiplier
            x = center_x - 10.0 + index * 5.0
            bar_color = QColor(color)
            bar_color.setAlpha(135 + int(level * 120))
            painter.setBrush(bar_color)
            painter.drawRoundedRect(QRectF(x, center_y - height / 2, 3, height), 1.5, 1.5)

    def _paint_spinner(
        self, painter: QPainter, color: QColor, center_x: float, center_y: float
    ) -> None:
        """Paint a processing spinner; its phase advances only while processing."""
        for index in range(8):
            angle = (self._phase * 0.24) + index * (math.tau / 8)
            alpha = 65 + int(190 * (index + 1) / 8)
            dot_color = QColor(color)
            dot_color.setAlpha(alpha)
            painter.setBrush(dot_color)
            x = center_x + math.cos(angle) * 7.0
            y = center_y + math.sin(angle) * 7.0
            painter.drawEllipse(QRectF(x - 2, y - 2, 4, 4))

    @staticmethod
    def _paint_check(
        painter: QPainter, color: QColor, center_x: float, center_y: float
    ) -> None:
        pen = QPen(color, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(center_x - 6), int(center_y), int(center_x - 1), int(center_y + 5))
        painter.drawLine(
            int(center_x - 1), int(center_y + 5), int(center_x + 8), int(center_y - 5)
        )


class _OverlayBridge(QObject):
    """Queue event-bus notifications into the QApplication's GUI thread."""

    application_state = Signal(object)
    audio_level = Signal(object)
    completed = Signal()
    failed = Signal()
    command_started = Signal()
    show_requested = Signal()
    hide_requested = Signal()
    destroy_requested = Signal()


class Overlay(QObject):
    """Show transient, non-activating dictation feedback above the desktop."""

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._state = OverlayState.HIDDEN
        self._window: _PillWidget | None = None
        self._bridge: _OverlayBridge | None = None
        self._animation_timer: QTimer | None = None
        self._hide_timer: QTimer | None = None
        self._scheduled_state: OverlayState | None = None
        self._scheduled_attempt = 0
        self._scheduled_token = 0
        self._audio_level = 0.0
        self._animation_phase = 0
        self._attempt = 0
        self._error_attempt: int | None = None
        self._transition_token = 0
        self._seen_application_state = False
        self._subscriptions: list[tuple[str, object]] = []
        self._destroyed = False

    def setup(self) -> None:
        """Create the Qt window in the main thread and attach event subscriptions."""
        if self._destroyed or self._window is not None:
            return

        ensure_application()
        self._bridge = _OverlayBridge()
        self._bridge.application_state.connect(self._apply_application_state)
        self._bridge.audio_level.connect(self._apply_audio_level)
        self._bridge.completed.connect(self._apply_done)
        self._bridge.failed.connect(self._apply_error)
        self._bridge.command_started.connect(self._apply_command_started)
        self._bridge.show_requested.connect(self._show_window)
        self._bridge.hide_requested.connect(self._hide_window)
        self._bridge.destroy_requested.connect(self._destroy_window)

        self._window = _PillWidget()
        self._animation_timer = QTimer(self._window)
        self._animation_timer.setInterval(33)
        self._animation_timer.timeout.connect(self._advance_animation)
        self._hide_timer = QTimer(self._window)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timeout)
        self._register_events()

    def _register_events(self) -> None:
        self._subscribe("state.change", self._on_state_change)
        self._subscribe("audio.level", self._on_audio_level)
        self._subscribe("inject.complete", self._on_done)
        self._subscribe("inject.error", self._on_error)
        self._subscribe("app.error", self._on_error)
        self._subscribe("ai.error", self._on_error)
        self._subscribe("hotkey.command.start", self._on_command_start)

    def _subscribe(self, event: str, handler: object) -> None:
        self._event_bus.on(event, handler)  # type: ignore[arg-type]
        self._subscriptions.append((event, handler))

    def _unsubscribe_all(self) -> None:
        for event, handler in self._subscriptions:
            self._event_bus.off(event, handler)  # type: ignore[arg-type]
        self._subscriptions.clear()

    # Event-bus callbacks do no GUI work, so they are safe on capture/STT threads.
    def _on_state_change(self, new_state: object = None, **_kwargs: object) -> None:
        if self._bridge is not None and not self._destroyed:
            self._bridge.application_state.emit(new_state)

    def _on_audio_level(self, level: object = 0.0, **_kwargs: object) -> None:
        if self._bridge is not None and not self._destroyed:
            self._bridge.audio_level.emit(level)

    def _on_done(self, **_kwargs: object) -> None:
        if self._bridge is not None and not self._destroyed:
            self._bridge.completed.emit()

    def _on_error(self, **_kwargs: object) -> None:
        if self._bridge is not None and not self._destroyed:
            self._bridge.failed.emit()

    def _on_command_start(self, **_kwargs: object) -> None:
        if self._bridge is not None and not self._destroyed:
            self._bridge.command_started.emit()

    @Slot(object)
    def _apply_application_state(self, application_state: object) -> None:
        if self._destroyed:
            return
        state_name = getattr(application_state, "name", str(application_state)).upper()
        initial_state = not self._seen_application_state
        self._seen_application_state = True

        if state_name == "RECORDING":
            self._attempt += 1
            self._error_attempt = None
            self._set_visual(OverlayState.RECORDING)
        elif state_name == "PROCESSING":
            self._set_visual(OverlayState.PROCESSING)
        elif state_name == "ERROR":
            self._apply_error()
        elif state_name == "IDLE":
            if initial_state:
                self._set_visual(OverlayState.IDLE)
                self._schedule_hide(OverlayState.IDLE, _READY_VISIBLE_MS)
            elif self._state not in (OverlayState.DONE, OverlayState.ERROR):
                self._set_visual(OverlayState.HIDDEN)

    @Slot(object)
    def _apply_audio_level(self, raw_level: object) -> None:
        if self._destroyed:
            return
        try:
            level = float(raw_level)
        except (TypeError, ValueError):
            level = 0.0
        if not math.isfinite(level):
            level = 0.0
        level = max(0.0, min(1.0, level))
        self._audio_level += (level - self._audio_level) * 0.35
        self._redraw()

    @Slot()
    def _apply_done(self) -> None:
        if self._destroyed or self._error_attempt == self._attempt:
            return
        self._set_visual(OverlayState.DONE)
        self._schedule_hide(OverlayState.DONE, _DONE_VISIBLE_MS)

    @Slot()
    def _apply_error(self) -> None:
        if self._destroyed:
            return
        self._error_attempt = self._attempt
        self._set_visual(OverlayState.ERROR)
        self._schedule_hide(OverlayState.ERROR, _ERROR_VISIBLE_MS)

    @Slot()
    def _apply_command_started(self) -> None:
        if not self._destroyed and self._state not in (OverlayState.ERROR, OverlayState.RECORDING):
            self._set_visual(OverlayState.COMMAND)

    def _set_visual(self, state: OverlayState) -> None:
        self._cancel_scheduled_hide()
        self._state = state
        if state in (OverlayState.RECORDING, OverlayState.PROCESSING):
            assert self._animation_timer is not None
            if not self._animation_timer.isActive():
                self._animation_timer.start()
        elif self._animation_timer is not None:
            self._animation_timer.stop()

        if state == OverlayState.HIDDEN:
            self._hide_window()
            return
        self._show_window()
        self._redraw()

    def _schedule_hide(self, expected_state: OverlayState, milliseconds: int) -> None:
        assert self._hide_timer is not None
        self._transition_token += 1
        self._scheduled_token = self._transition_token
        self._scheduled_state = expected_state
        self._scheduled_attempt = self._attempt
        self._hide_timer.stop()
        self._hide_timer.start(milliseconds)

    def _cancel_scheduled_hide(self) -> None:
        self._transition_token += 1
        if self._hide_timer is not None:
            self._hide_timer.stop()

    def _hide_if_current(
        self, token: int, expected_state: OverlayState, attempt: int
    ) -> None:
        if (
            not self._destroyed
            and token == self._transition_token
            and self._state == expected_state
            and self._attempt == attempt
        ):
            self._set_visual(OverlayState.HIDDEN)

    @Slot()
    def _on_hide_timeout(self) -> None:
        if self._scheduled_state is not None:
            self._hide_if_current(
                self._scheduled_token, self._scheduled_state, self._scheduled_attempt
            )

    @Slot()
    def _advance_animation(self) -> None:
        if self._state not in (OverlayState.RECORDING, OverlayState.PROCESSING):
            assert self._animation_timer is not None
            self._animation_timer.stop()
            return
        self._animation_phase += 1
        self._redraw()

    def _redraw(self) -> None:
        if self._window is not None:
            self._window.set_visual(self._state, self._audio_level, self._animation_phase)

    @Slot()
    def _show_window(self) -> None:
        if self._destroyed or self._window is None:
            return
        self._position_on_active_screen()
        self._window.show()
        self._redraw()

    def _position_on_active_screen(self) -> None:
        assert self._window is not None
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self._window.move(
            available.x() + (available.width() - self._window.width()) // 2,
            available.y() + available.height() - self._window.height() - _BOTTOM_MARGIN,
        )

    @Slot()
    def _hide_window(self) -> None:
        if self._window is not None:
            self._window.hide()

    def show(self) -> None:
        """Queue a non-activating show request without changing the visual state."""
        if self._bridge is not None and not self._destroyed:
            self._bridge.show_requested.emit()

    def hide(self) -> None:
        """Queue a hide request without retaining a focusable window."""
        if self._bridge is not None and not self._destroyed:
            self._bridge.hide_requested.emit()

    def destroy(self) -> None:
        """Unsubscribe and queue teardown so shutdown leaves no native window behind."""
        if self._destroyed:
            return
        self._destroyed = True
        self._unsubscribe_all()
        if self._bridge is not None:
            self._bridge.destroy_requested.emit()

    @Slot()
    def _destroy_window(self) -> None:
        if self._animation_timer is not None:
            self._animation_timer.stop()
        if self._hide_timer is not None:
            self._hide_timer.stop()
        if self._window is not None:
            self._window.close()
            self._window.deleteLater()
            self._window = None
