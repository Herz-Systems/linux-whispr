"""Global hotkey listener — dispatches to X11 or Wayland implementation."""

from __future__ import annotations

import abc
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from linux_whispr.platform.detect import PlatformInfo

logger = logging.getLogger(__name__)

_STARTUP_TIMEOUT_SECONDS = 5.0


class HotkeyListener(abc.ABC):
    """Abstract base class for global hotkey listeners."""

    def __init__(self) -> None:
        self._startup_complete = threading.Event()
        self._startup_error: BaseException | None = None
        self._startup_in_progress = False
        self._startup_lock = threading.Lock()

    def _begin_startup(self) -> bool:
        """Begin a startup handshake, returning false when one is already active."""
        with self._startup_lock:
            if self._startup_in_progress:
                return False
            self._startup_complete.clear()
            self._startup_error = None
            self._startup_in_progress = True
            return True

    def _mark_startup_ready(self) -> bool:
        """Report that the backend has registered its hotkeys."""
        with self._startup_lock:
            if not self._startup_in_progress:
                return False
            self._startup_in_progress = False
            self._startup_complete.set()
            return True

    def _mark_startup_failed(self, error: BaseException) -> None:
        """Report a startup failure to the thread waiting in start()."""
        with self._startup_lock:
            if not self._startup_in_progress:
                return
            self._startup_error = error
            self._startup_in_progress = False
            self._startup_complete.set()

    def _cancel_startup(self, backend: str) -> None:
        """Unblock start() when stop() is called before the backend is ready."""
        self._mark_startup_failed(
            RuntimeError(f"{backend} hotkey listener was stopped before it became ready.")
        )

    def _wait_for_startup(self, backend: str) -> None:
        """Wait a bounded amount of time for backend registration to complete."""
        if not self._startup_complete.wait(_STARTUP_TIMEOUT_SECONDS):
            raise RuntimeError(
                f"{backend} hotkey listener did not become ready within "
                f"{_STARTUP_TIMEOUT_SECONDS:g} seconds."
            )

        with self._startup_lock:
            error = self._startup_error
        if error is not None:
            raise RuntimeError(f"{backend} hotkey listener failed to start.") from error

    @abc.abstractmethod
    def register(self, hotkey: str, callback: Callable[[], None], name: str = "") -> None:
        """Register a global hotkey.

        Args:
            hotkey: Hotkey string (e.g., "F12", "<Ctrl><Shift>h").
            callback: Function to call when the hotkey is pressed.
            name: Human-readable name for the hotkey binding.
        """
        ...

    @abc.abstractmethod
    def start(self) -> None:
        """Start listening and return only after global hotkeys are ready."""
        ...

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop listening for hotkeys."""
        ...


def create_hotkey_listener(platform: PlatformInfo) -> HotkeyListener:
    """Factory: create the appropriate hotkey listener for the platform."""
    from linux_whispr.platform.detect import DisplayServer

    if platform.display_server == DisplayServer.WAYLAND:
        try:
            from linux_whispr.input.wayland_hotkey import WaylandHotkeyListener

            logger.info("Using Wayland D-Bus GlobalShortcuts portal for hotkeys")
            return WaylandHotkeyListener()
        except ImportError:
            logger.warning("Wayland hotkey support unavailable, trying X11 fallback")

    if platform.display_server in (DisplayServer.X11, DisplayServer.WAYLAND):
        # On Wayland we can still try X11 via XWayland
        try:
            from linux_whispr.input.x11_hotkey import X11HotkeyListener

            logger.info("Using X11 XGrabKey for hotkeys")
            return X11HotkeyListener()
        except ImportError:
            logger.error("X11 hotkey support unavailable (python-xlib not installed)")

    # Last resort: pynput (works on both but may need permissions)
    try:
        from linux_whispr.input.pynput_hotkey import PynputHotkeyListener

        logger.info("Using pynput for hotkeys (fallback)")
        return PynputHotkeyListener()
    except ImportError:
        pass

    raise RuntimeError(
        "No hotkey backend available. Install python-xlib (X11) or ensure "
        "D-Bus GlobalShortcuts portal is available (Wayland)."
    )
