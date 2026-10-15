"""Fallback hotkey listener using pynput (works on X11 and some Wayland setups)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from linux_whispr.input.hotkey import _STARTUP_TIMEOUT_SECONDS, HotkeyListener

logger = logging.getLogger(__name__)


def _parse_hotkey_to_pynput(hotkey_str: str) -> set[object]:
    """Parse a hotkey string into pynput key objects."""
    import re

    from pynput.keyboard import Key, KeyCode

    keys: set[object] = set()
    remaining = hotkey_str

    # Extract <Modifier> patterns
    modifier_map = {
        "ctrl": Key.ctrl_l,
        "control": Key.ctrl_l,
        "shift": Key.shift_l,
        "alt": Key.alt_l,
        "super": Key.cmd,
        "meta": Key.cmd,
    }

    for match in re.finditer(r"<(\w+)>", hotkey_str):
        mod = match.group(1).lower()
        if mod in modifier_map:
            keys.add(modifier_map[mod])
        remaining = remaining.replace(match.group(0), "")

    key_name = remaining.strip().lower()
    if key_name:
        # Try as a special key first (F1-F12, etc.)
        try:
            keys.add(getattr(Key, key_name.lower()))
        except AttributeError:
            # Regular character key
            if len(key_name) == 1:
                keys.add(KeyCode.from_char(key_name))
            else:
                logger.error("Unknown key: %s", key_name)

    return keys


class PynputHotkeyListener(HotkeyListener):
    """Fallback hotkey listener using pynput."""

    def __init__(self) -> None:
        super().__init__()
        self._bindings: list[tuple[set[object], Callable[[], None]]] = []
        self._listener: Any | None = None
        self._current_keys: set[object] = set()
        self._running = False

    def register(self, hotkey: str, callback: Callable[[], None], name: str = "") -> None:
        keys = _parse_hotkey_to_pynput(hotkey)
        if keys:
            self._bindings.append((keys, callback))
            logger.info("Registered pynput hotkey: %s (%s) -> %s", hotkey, name, keys)

    def start(self) -> None:
        if not self._bindings:
            raise RuntimeError("No pynput hotkeys have been registered.")
        if self._running:
            self._wait_for_startup("pynput")
            return

        self._running = True
        if not self._begin_startup():
            self._wait_for_startup("pynput")
            return

        try:
            from pynput.keyboard import Listener

            self._listener = Listener(on_press=self._on_press, on_release=self._on_release)
            self._listener.start()
            deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                # pynput sets _ready only after its platform listener has initialized.
                if getattr(self._listener, "_ready", False):
                    if self._mark_startup_ready():
                        logger.info("pynput hotkey listener running")
                        return
                    break
                if not self._listener.is_alive():
                    self._listener.join(timeout=0)
                    raise RuntimeError("pynput listener exited before becoming ready.")
                if not self._running:
                    raise RuntimeError("pynput listener was stopped before it became ready.")
                time.sleep(0.01)
            else:
                raise RuntimeError(
                    f"pynput listener did not become ready within {_STARTUP_TIMEOUT_SECONDS:g} seconds."
                )
            raise RuntimeError("pynput listener was stopped before it became ready.")
        except BaseException as error:
            self._running = False
            self._mark_startup_failed(error)
            if self._listener is not None:
                self._listener.stop()
                self._listener.join(timeout=0.5)
            raise RuntimeError("pynput hotkey listener failed to start.") from error

    def stop(self) -> None:
        self._running = False
        self._cancel_startup("pynput")
        if self._listener is not None:
            self._listener.stop()
            logger.info("pynput hotkey listener stopped")

    def _on_press(self, key: object) -> None:
        self._current_keys.add(key)
        for combo, callback in self._bindings:
            if combo.issubset(self._current_keys):
                try:
                    callback()
                except Exception:
                    logger.exception("Error in hotkey callback")

    def _on_release(self, key: object) -> None:
        self._current_keys.discard(key)
