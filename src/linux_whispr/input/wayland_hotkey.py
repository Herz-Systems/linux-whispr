"""Wayland global hotkey listener using D-Bus GlobalShortcuts portal."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from linux_whispr.input.hotkey import _STARTUP_TIMEOUT_SECONDS, HotkeyListener

logger = logging.getLogger(__name__)

# XDG Desktop Portal GlobalShortcuts interface
PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PORTAL_IFACE = "org.freedesktop.portal.GlobalShortcuts"


class WaylandHotkeyListener(HotkeyListener):
    """Global hotkey listener using the XDG Desktop Portal GlobalShortcuts."""

    def __init__(self) -> None:
        super().__init__()
        self._bindings: list[tuple[str, Callable[[], None], str]] = []
        self._thread: threading.Thread | None = None
        self._running = False
        self._session_handle: str | None = None
        self._startup_loop: Any | None = None
        self._main_loop: Any | None = None

    def register(self, hotkey: str, callback: Callable[[], None], name: str = "") -> None:
        self._bindings.append((hotkey, callback, name or hotkey))
        logger.info("Registered Wayland hotkey: %s (%s)", hotkey, name)

    def start(self) -> None:
        if not self._bindings:
            raise RuntimeError("No Wayland hotkeys have been registered.")
        if self._running:
            self._wait_for_startup("Wayland")
            return

        self._running = True
        if not self._begin_startup():
            self._wait_for_startup("Wayland")
            return

        self._thread = threading.Thread(target=self._run, daemon=True, name="wayland-hotkey")
        self._thread.start()
        try:
            self._wait_for_startup("Wayland")
        except BaseException:
            self.stop()
            self._thread.join(timeout=0.5)
            raise

    def stop(self) -> None:
        self._running = False
        self._cancel_startup("Wayland")
        for loop in (self._startup_loop, self._main_loop):
            if loop is not None:
                loop.quit()
        self._close_session()

    def _run(self) -> None:
        try:
            self._listen_loop()
        except BaseException as error:
            logger.exception("Wayland hotkey listener failed")
            self._mark_startup_failed(error)
        finally:
            self._mark_startup_failed(
                RuntimeError("Wayland hotkey listener stopped before it became ready.")
            )
            self._running = False

    def _listen_loop(self) -> None:
        """Register shortcuts and run the portal signal loop."""
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            from gi.repository import GLib
        except ImportError as error:
            raise RuntimeError(
                "Wayland global hotkeys require dbus-python and PyGObject."
            ) from error

        DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        portal = bus.get_object(PORTAL_BUS, PORTAL_PATH)
        shortcuts_iface = dbus.Interface(portal, PORTAL_IFACE)

        session_request = shortcuts_iface.CreateSession(
            dbus.Dictionary(
                {
                    "handle_token": dbus.String("linux_whispr_session"),
                    "session_handle_token": dbus.String("linux_whispr"),
                },
                signature="sv",
            )
        )
        session_response = self._wait_for_response(
            bus, session_request, GLib, "create a GlobalShortcuts session"
        )
        session_handle = session_response.get("session_handle")
        if session_handle is None:
            raise RuntimeError("GlobalShortcuts portal did not return a session handle.")
        self._session_handle = str(session_handle)

        shortcuts = dbus.Array([], signature="(sa{sv})")
        callback_map: dict[str, Callable[[], None]] = {}
        for i, (hotkey, callback, name) in enumerate(self._bindings):
            shortcut_id = f"linux-whispr-{i}"
            shortcuts.append(
                dbus.Struct(
                    (
                        dbus.String(shortcut_id),
                        dbus.Dictionary(
                            {
                                "description": dbus.String(name),
                                "preferred_trigger": dbus.String(hotkey),
                            },
                            signature="sv",
                        ),
                    ),
                    signature="sa{sv}",
                )
            )
            callback_map[shortcut_id] = callback

        bind_request = shortcuts_iface.BindShortcuts(
            dbus.ObjectPath(self._session_handle),
            shortcuts,
            "",
            dbus.Dictionary(
                {"handle_token": dbus.String("linux_whispr_bind")},
                signature="sv",
            ),
        )
        self._wait_for_response(bus, bind_request, GLib, "bind GlobalShortcuts")

        def on_activated(
            session_handle: str, shortcut_id: str, timestamp: int, options: dict
        ) -> None:
            callback = callback_map.get(shortcut_id)
            if callback is None:
                return
            try:
                callback()
            except Exception:
                logger.exception("Error in hotkey callback for %s", shortcut_id)

        bus.add_signal_receiver(
            on_activated,
            signal_name="Activated",
            dbus_interface=PORTAL_IFACE,
        )
        if not self._mark_startup_ready():
            return

        logger.info("Wayland hotkey listener running")
        loop = GLib.MainLoop()
        self._main_loop = loop
        try:
            if self._running:
                loop.run()
        finally:
            self._main_loop = None
        logger.info("Wayland hotkey listener stopped")

    def _wait_for_response(
        self, bus: Any, request_path: object, glib: Any, operation: str
    ) -> dict[str, object]:
        """Wait for the portal request response rather than treating submission as success."""
        response: list[tuple[int, dict[str, object]]] = []
        loop = glib.MainLoop()

        def on_response(code: int, results: dict[str, object]) -> None:
            response.append((int(code), results))
            loop.quit()

        def on_timeout() -> bool:
            loop.quit()
            return False

        path = str(request_path)
        bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            path=path,
        )
        timeout_id = glib.timeout_add(
            int(_STARTUP_TIMEOUT_SECONDS * 1000), on_timeout
        )
        self._startup_loop = loop
        try:
            loop.run()
        finally:
            self._startup_loop = None
            bus.remove_signal_receiver(
                on_response,
                signal_name="Response",
                dbus_interface="org.freedesktop.portal.Request",
                path=path,
            )
            glib.source_remove(timeout_id)

        if not self._running:
            raise RuntimeError(f"Wayland listener stopped while trying to {operation}.")
        if not response:
            raise RuntimeError(
                f"GlobalShortcuts portal did not respond while trying to {operation}."
            )
        code, results = response[0]
        if code != 0:
            raise RuntimeError(f"GlobalShortcuts portal refused to {operation} (code {code}).")
        return results

    def _close_session(self) -> None:
        """Close the portal session when it was created successfully."""
        # Closing the D-Bus connection remains the portal's fallback cleanup path.
        self._session_handle = None
