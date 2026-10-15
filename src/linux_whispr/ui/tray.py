"""Qt-native system tray status indicator."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from PySide6.QtCore import QObject, QPoint, Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from linux_whispr.ui.desktop import ensure_application

if TYPE_CHECKING:
    from linux_whispr.events import EventBus

logger = logging.getLogger(__name__)


class _TrayBridge(QObject):
    """Deliver event-bus updates to the tray's Qt thread."""

    status_requested = Signal(str, str)


class SystemTray(QObject):
    """Expose LinuxWhispr's current dictation status through Qt's tray API."""

    _STATUS_LABELS: ClassVar[dict[str, str]] = {
        "starting": "Starting",
        "ready": "Ready",
        "recording": "Recording",
        "processing": "Processing",
        "problem": "Needs attention",
    }
    _STATUS_COLORS: ClassVar[dict[str, QColor]] = {
        "starting": QColor("#636674"),
        "ready": QColor("#26a65b"),
        "recording": QColor("#d22f2f"),
        "processing": QColor("#297ad6"),
        "problem": QColor("#e27019"),
    }

    def __init__(
        self,
        event_bus: EventBus,
        on_toggle_dictation: Callable[[], None] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._on_toggle_dictation = on_toggle_dictation
        self._on_open_settings = on_open_settings
        self._on_quit = on_quit
        self._icon: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._status_action: QAction | None = None
        self._toggle_action: QAction | None = None
        self._actions: list[QAction] = []
        self._images: dict[str, QIcon] = {}
        self._status = "starting"
        self._problem_detail: str | None = None
        self._subscriptions: list[tuple[str, Callable[..., None]]] = []
        self._bridge: _TrayBridge | None = None
        self._started = False
        self._stopped = False

    def setup(self) -> None:
        """Create the native tray item and subscribe to application events."""
        if self._icon is not None:
            return

        ensure_application()
        if not self._is_host_available():
            raise RuntimeError(
                "No system tray host is available. Start a desktop panel with a StatusNotifier "
                "area, or run LinuxWhispr with --no-tray."
            )

        self._icon = QSystemTrayIcon(self._image_for(self._status))
        self._icon.setToolTip(self._tooltip_for(self._status))
        self._menu = QMenu()
        self._build_menu()
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)

        self._bridge = _TrayBridge(self)
        self._bridge.status_requested.connect(
            self._apply_status, Qt.ConnectionType.QueuedConnection
        )
        self._subscribe("state.change", self._on_state_change)
        self._subscribe("app.error", self._on_app_error)
        self._subscribe("ai.error", self._on_ai_error)
        logger.info("Qt system tray icon created")

    def start(self) -> None:
        """Request registration with the desktop's native tray host."""
        if self._started:
            return
        if self._icon is None:
            raise RuntimeError("System tray has not been set up.")
        if not self._is_host_available():
            raise RuntimeError(
                "The system tray host disappeared before LinuxWhispr could register. "
                "Restore the desktop StatusNotifier area or use --no-tray."
            )
        self._stopped = False
        self._icon.show()
        self._started = True
        logger.info("Qt system tray registration requested")

    def stop(self) -> None:
        """Remove the native item and detach all event-bus callbacks."""
        if self._stopped:
            return
        self._stopped = True
        self._unsubscribe_all()
        if self._bridge is not None:
            self._bridge.status_requested.disconnect(self._apply_status)
            self._bridge.deleteLater()
            self._bridge = None
        if self._icon is not None:
            self._icon.hide()
            self._icon.setContextMenu(None)
            self._icon.deleteLater()
            self._icon = None
        if self._menu is not None:
            self._menu.deleteLater()
            self._menu = None
        self._actions.clear()
        self._status_action = None
        self._toggle_action = None
        self._started = False
        self._images.clear()
        logger.info("Qt system tray stopped")

    @staticmethod
    def _is_host_available() -> bool:
        """Check that Qt can register with the current desktop tray host."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _build_menu(self) -> None:
        assert self._menu is not None
        open_action = self._menu.addAction("Open Dashboard")
        open_action.triggered.connect(self._handle_open_settings)
        self._actions.append(open_action)

        self._status_action = self._menu.addAction(self._status_label())
        self._status_action.setEnabled(False)
        self._actions.append(self._status_action)
        self._menu.addSeparator()

        self._toggle_action = self._menu.addAction(self._dictation_label())
        self._toggle_action.triggered.connect(self._handle_toggle_dictation)
        self._actions.append(self._toggle_action)
        self._menu.addSeparator()

        quit_action = self._menu.addAction("Quit")
        quit_action.triggered.connect(self._handle_quit)
        self._actions.append(quit_action)
        self._update_menu()

    def _image_for(self, status: str) -> QIcon:
        """Return a cached, state-specific microphone icon painted by Qt."""
        icon = self._images.get(status)
        if icon is not None:
            return icon

        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("white"), 4))
        painter.setBrush(self._STATUS_COLORS[status])
        painter.drawEllipse(4, 4, 56, 56)

        painter.setBrush(QColor("white"))
        painter.setPen(QPen(QColor("white"), 4))
        painter.drawRoundedRect(24, 14, 16, 23, 8, 8)
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawArc(17, 25, 30, 23, 0, -180 * 16)
        painter.drawLine(32, 44, 32, 51)
        painter.drawLine(23, 52, 41, 52)

        painter.setBrush(QColor("#202020"))
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawEllipse(41, 4, 19, 19)
        painter.setPen(QPen(QColor("white"), 3))
        painter.setBrush(QColor("white"))
        if status == "ready":
            painter.drawLine(45, 14, 49, 18)
            painter.drawLine(49, 18, 57, 9)
        elif status == "recording":
            painter.drawEllipse(47, 10, 7, 7)
        elif status == "processing":
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawArc(45, 8, 12, 12, 30 * 16, 255 * 16)
            painter.setBrush(QColor("white"))
            painter.drawPolygon(QPolygon([QPoint(55, 8), QPoint(59, 10), QPoint(55, 13)]))
        elif status == "problem":
            painter.drawPolygon(QPolygon([QPoint(51, 7), QPoint(58, 20), QPoint(44, 20)]))
            painter.setPen(QPen(QColor("#323232"), 2))
            painter.drawLine(51, 11, 51, 16)
            painter.drawPoint(51, 18)
        else:
            painter.drawEllipse(47, 13, 2, 2)
            painter.drawEllipse(51, 13, 2, 2)
            painter.drawEllipse(55, 13, 2, 2)
        painter.end()

        icon = QIcon(pixmap)
        self._images[status] = icon
        return icon

    def _on_state_change(
        self, old_state: object = None, new_state: object = None, **kwargs: object
    ) -> None:
        state_name = getattr(new_state, "name", "")
        if state_name in {"RECORDING", "PROCESSING"}:
            self._request_status(
                "recording" if state_name == "RECORDING" else "processing", clear_problem=True
            )
        elif state_name == "ERROR":
            self._request_status("problem", problem_detail="Dictation needs attention")
        elif state_name == "IDLE":
            self._request_status("ready")

    def _on_app_error(self, message: str = "", **kwargs: object) -> None:
        self._request_status("problem", problem_detail="Dictation needs attention")

    def _on_ai_error(self, message: str = "", **kwargs: object) -> None:
        self._request_status("problem", problem_detail="AI refinement needs attention")

    def _request_status(
        self, status: str, *, clear_problem: bool = False, problem_detail: str = ""
    ) -> None:
        if self._stopped or self._bridge is None:
            return
        detail = "" if clear_problem else problem_detail
        self._bridge.status_requested.emit(status, detail)

    @Slot(str, str)
    def _apply_status(self, status: str, problem_detail: str) -> None:
        """Apply a worker event on Qt's main thread."""
        if self._stopped:
            return
        if status in {"recording", "processing"}:
            self._problem_detail = None
        elif problem_detail:
            self._problem_detail = problem_detail
        elif status == "ready" and self._problem_detail is not None:
            return

        self._status = status
        if self._icon is not None:
            self._icon.setIcon(self._image_for(status))
            self._icon.setToolTip(self._tooltip_for(status))
        self._update_menu()

    def _update_menu(self) -> None:
        if self._status_action is not None:
            self._status_action.setText(f"Status: {self._status_label()}")
        if self._toggle_action is not None:
            self._toggle_action.setText(self._dictation_label())
            self._toggle_action.setEnabled(self._status in {"ready", "recording", "problem"})

    def _tooltip_for(self, status: str) -> str:
        """Keep hover text generic: event payloads can contain dictated text."""
        return f"LinuxWhispr — {self._STATUS_LABELS[status]}"

    def _status_label(self) -> str:
        if self._status == "problem":
            return self._problem_detail or self._STATUS_LABELS[self._status]
        return self._STATUS_LABELS[self._status]

    def _dictation_label(self) -> str:
        return "Stop Dictation" if self._status == "recording" else "Start Dictation"

    def _subscribe(self, event: str, handler: Callable[..., None]) -> None:
        self._event_bus.on(event, handler)
        self._subscriptions.append((event, handler))

    def _unsubscribe_all(self) -> None:
        while self._subscriptions:
            event, handler = self._subscriptions.pop()
            self._event_bus.off(event, handler)

    @Slot()
    def _handle_toggle_dictation(self) -> None:
        if self._on_toggle_dictation is not None:
            self._on_toggle_dictation()

    @Slot()
    def _handle_open_settings(self) -> None:
        if self._on_open_settings is not None:
            self._on_open_settings()

    @Slot()
    def _handle_quit(self) -> None:
        if self._on_quit is not None:
            self._on_quit()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._handle_open_settings()
