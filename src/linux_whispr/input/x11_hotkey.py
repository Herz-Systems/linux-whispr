"""X11 global hotkey listener using python-xlib XGrabKey."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from linux_whispr.input.hotkey import HotkeyListener

logger = logging.getLogger(__name__)

# Modifier masks for XGrabKey
_MODIFIER_MAP = {
    "ctrl": "ControlMask",
    "control": "ControlMask",
    "shift": "ShiftMask",
    "alt": "Mod1Mask",
    "super": "Mod4Mask",
    "meta": "Mod4Mask",
    "hyper": "Mod4Mask",
}


def _parse_hotkey(hotkey_str: str) -> tuple[list[str], str]:
    """Parse a hotkey string like '<Ctrl><Shift>h' or 'F12' into modifiers + key.

    Returns:
        Tuple of (modifier_names, key_name).
    """
    import re

    modifiers: list[str] = []
    remaining = hotkey_str

    # Extract <Modifier> patterns
    for match in re.finditer(r"<(\w+)>", hotkey_str):
        mod = match.group(1).lower()
        if mod in _MODIFIER_MAP:
            modifiers.append(mod)
        remaining = remaining.replace(match.group(0), "")

    key = remaining.strip()
    if not key:
        raise ValueError(f"No key found in hotkey string: {hotkey_str!r}")

    return modifiers, key


class X11HotkeyListener(HotkeyListener):
    """Global hotkey listener using X11 XGrabKey via python-xlib."""

    def __init__(self) -> None:
        super().__init__()
        self._bindings: list[tuple[str, Callable[[], None], str]] = []
        self._thread: threading.Thread | None = None
        self._running = False

    def register(self, hotkey: str, callback: Callable[[], None], name: str = "") -> None:
        self._bindings.append((hotkey, callback, name))
        logger.info("Registered X11 hotkey: %s (%s)", hotkey, name)

    def start(self) -> None:
        if not self._bindings:
            raise RuntimeError("No X11 hotkeys have been registered.")
        if self._running:
            self._wait_for_startup("X11")
            return

        self._running = True
        if not self._begin_startup():
            self._wait_for_startup("X11")
            return

        self._thread = threading.Thread(target=self._run, daemon=True, name="x11-hotkey")
        self._thread.start()
        try:
            self._wait_for_startup("X11")
        except BaseException:
            self.stop()
            self._thread.join(timeout=0.5)
            raise

    def stop(self) -> None:
        self._running = False
        self._cancel_startup("X11")

    def _run(self) -> None:
        try:
            self._listen_loop()
        except BaseException as error:
            logger.exception("X11 hotkey listener failed")
            self._mark_startup_failed(error)
        finally:
            self._mark_startup_failed(
                RuntimeError("X11 hotkey listener stopped before it became ready.")
            )
            self._running = False

    def _listen_loop(self) -> None:
        """Main X11 event loop for hotkey listening."""
        from Xlib import XK, X, display

        disp = display.Display()
        root = disp.screen().root
        grab_errors: list[BaseException] = []

        def record_grab_error(error: BaseException, _request: object) -> int:
            grab_errors.append(error)
            return 1

        def release_grabs(grab_specs: list[tuple[int, int, Callable[[], None]]]) -> None:
            for keycode, mod_mask, _ in grab_specs:
                for extra_mod in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                    root.ungrab_key(keycode, mod_mask | extra_mod)

        # Build keycode/modifier mappings for our bindings
        grab_specs: list[tuple[int, int, Callable[[], None]]] = []
        for hotkey_str, callback, name in self._bindings:
            modifiers, key_name = _parse_hotkey(hotkey_str)

            # Get keycode
            keysym = XK.string_to_keysym(key_name)
            if keysym == 0:
                # Try common aliases
                keysym = XK.string_to_keysym(key_name.capitalize())
            if keysym == 0:
                logger.error("Unknown key: %s", key_name)
                continue

            keycode = disp.keysym_to_keycode(keysym)
            if keycode == 0:
                logger.error("Cannot map key '%s' to keycode", key_name)
                continue

            # Build modifier mask
            mod_mask = 0
            for mod in modifiers:
                xlib_mod = _MODIFIER_MAP.get(mod)
                if xlib_mod == "ControlMask":
                    mod_mask |= X.ControlMask
                elif xlib_mod == "ShiftMask":
                    mod_mask |= X.ShiftMask
                elif xlib_mod == "Mod1Mask":
                    mod_mask |= X.Mod1Mask
                elif xlib_mod == "Mod4Mask":
                    mod_mask |= X.Mod4Mask

            # Grab the key on root window
            # We grab with and without NumLock (Mod2Mask) and CapsLock (LockMask)
            for extra_mod in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                root.grab_key(
                    keycode,
                    mod_mask | extra_mod,
                    True,
                    X.GrabModeAsync,
                    X.GrabModeAsync,
                    onerror=record_grab_error,
                )

            grab_specs.append((keycode, mod_mask, callback))
            logger.info("X11: grabbed keycode=%d, mod_mask=%d for '%s'", keycode, mod_mask, name)
        # Flush XGrabKey requests and collect asynchronous failures before readiness.
        disp.sync()
        if grab_errors:
            release_grabs(grab_specs)
            disp.close()
            raise RuntimeError(
                "X11 could not acquire the configured hotkey; it may already be in use."
            ) from grab_errors[0]
        if not grab_specs:
            disp.close()
            raise RuntimeError("X11 could not register any configured hotkeys.")
        if not self._mark_startup_ready():
            release_grabs(grab_specs)
            disp.close()
            self._running = False
            return

        logger.info("X11 hotkey listener running")
        while self._running:
            # Process pending events with a timeout
            while disp.pending_events() > 0 and self._running:
                event = disp.next_event()
                if event.type == X.KeyPress:
                    for keycode, mod_mask, callback in grab_specs:
                        # Mask out NumLock and CapsLock for comparison
                        clean_state = event.state & ~(X.Mod2Mask | X.LockMask)
                        if event.detail == keycode and clean_state == mod_mask:
                            try:
                                callback()
                            except Exception:
                                logger.exception("Error in hotkey callback")

            # Small sleep to avoid busy-waiting
            import time

            time.sleep(0.05)

        release_grabs(grab_specs)

        disp.close()
        logger.info("X11 hotkey listener stopped")
