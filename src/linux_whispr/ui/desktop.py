"""Shared Qt application lifecycle for LinuxWhispr's desktop UI."""

from __future__ import annotations

import signal
import sys
import threading
from typing import Final

try:
    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtWidgets import QApplication
except ImportError as error:  # pragma: no cover - exercised on broken installations
    raise RuntimeError(
        "LinuxWhispr's desktop UI requires PySide6-Essentials. "
        "Reinstall LinuxWhispr with its core dependencies."
    ) from error


_APPLICATION_NAME: Final = "linux-whispr"
_app: QApplication | None = None
_quit_bridge: _QuitBridge | None = None


class _QuitBridge(QObject):
    """Queue shutdown requests made by worker threads onto Qt's GUI thread."""

    quit_requested = Signal()


def ensure_application() -> QApplication:
    """Return LinuxWhispr's sole QApplication, created on the main thread.

    Desktop objects must be created only after this function has returned.
    """
    global _app, _quit_bridge

    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("The Qt application must be created on the main thread.")

    existing = QApplication.instance()
    if existing is not None:
        if not isinstance(existing, QApplication):
            raise RuntimeError("LinuxWhispr requires a QApplication for its desktop UI.")
        app = existing
    else:
        app = QApplication(sys.argv[:1])

    app.setApplicationName(_APPLICATION_NAME)
    app.setDesktopFileName(_APPLICATION_NAME)
    app.setQuitOnLastWindowClosed(False)
    _app = app  # Keep a strong Python reference for the process lifetime.

    if _quit_bridge is None:
        _quit_bridge = _QuitBridge()
        _quit_bridge.quit_requested.connect(app.quit)

    return app


def run_desktop_loop() -> int:
    """Run Qt's main loop until SIGINT, SIGTERM, or an explicit quit request."""
    app = ensure_application()
    previous_handlers: dict[int, signal.Handlers] = {}

    def request_quit(_signum: int, _frame: object) -> None:
        quit_desktop_loop()

    # Qt's native event dispatcher can remain inside C++ indefinitely after
    # every window is hidden. A bounded Python callback gives CPython a chance
    # to dispatch SIGINT/SIGTERM handlers while that dispatcher is idle.
    signal_wakeup = QTimer()
    signal_wakeup.setInterval(100)
    signal_wakeup.timeout.connect(lambda: None)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, request_quit)

    signal_wakeup.start()
    try:
        return app.exec()
    finally:
        signal_wakeup.stop()
        signal_wakeup.timeout.disconnect()
        signal_wakeup.deleteLater()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def quit_desktop_loop() -> None:
    """Request a Qt main-loop exit without touching widgets from worker threads."""
    app = _app or QApplication.instance()
    if app is None:
        return
    if _quit_bridge is None:
        app.quit()
        return
    _quit_bridge.quit_requested.emit()
