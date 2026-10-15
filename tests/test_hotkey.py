"""Tests for hotkey parsing and listener factory."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from types import ModuleType, SimpleNamespace

import pytest

from linux_whispr.input.hotkey import HotkeyListener
from linux_whispr.input.x11_hotkey import _parse_hotkey
from linux_whispr.platform.detect import Desktop, DisplayServer, PlatformInfo


class TestHotkeyParsing:
    def test_simple_key(self) -> None:
        modifiers, key = _parse_hotkey("F12")
        assert modifiers == []
        assert key == "F12"

    def test_ctrl_shift_key(self) -> None:
        modifiers, key = _parse_hotkey("<Ctrl><Shift>h")
        assert "ctrl" in modifiers
        assert "shift" in modifiers
        assert key == "h"

    def test_single_modifier(self) -> None:
        modifiers, key = _parse_hotkey("<Alt>d")
        assert modifiers == ["alt"]
        assert key == "d"

    def test_super_key(self) -> None:
        modifiers, key = _parse_hotkey("<Super>h")
        assert modifiers == ["super"]
        assert key == "h"

    def test_no_key_raises(self) -> None:
        with pytest.raises(ValueError, match="No key found"):
            _parse_hotkey("<Ctrl><Shift>")


class TestHotkeyListenerFactory:
    def test_factory_with_x11_tries_x11_listener(self) -> None:
        from linux_whispr.input.hotkey import create_hotkey_listener

        platform = PlatformInfo(
            display_server=DisplayServer.X11,
            desktop=Desktop.I3,
            has_xdotool=True,
            has_wtype=False,
            has_ydotool=False,
            has_xclip=True,
            has_xsel=False,
            has_wl_clipboard=False,
        )

        # This will try to import X11 or pynput listener
        # If neither available, it raises RuntimeError
        try:
            listener = create_hotkey_listener(platform)
            assert listener is not None
        except (RuntimeError, ImportError):
            # Expected if neither python-xlib nor pynput is installed
            pass


class TestHotkeyStartup:
    @staticmethod
    def _register(listener: HotkeyListener) -> None:
        listener.register("F12", lambda: None)

    def test_x11_start_waits_for_registered_hotkey(self) -> None:
        from linux_whispr.input.x11_hotkey import X11HotkeyListener

        listener = X11HotkeyListener()
        self._register(listener)
        setup_started = threading.Event()
        allow_ready = threading.Event()
        returned = threading.Event()
        failures: list[BaseException] = []

        def listen_loop() -> None:
            setup_started.set()
            allow_ready.wait()
            if listener._mark_startup_ready():
                while listener._running:
                    threading.Event().wait(0.01)

        listener._listen_loop = listen_loop  # type: ignore[method-assign]

        def start() -> None:
            try:
                listener.start()
            except RuntimeError as error:
                failures.append(error)
            finally:
                returned.set()

        thread = threading.Thread(target=start)
        thread.start()
        assert setup_started.wait(1)
        assert not returned.is_set()

        allow_ready.set()
        assert returned.wait(1)
        listener.stop()
        assert listener._thread is not None
        listener._thread.join(1)
        assert not listener._thread.is_alive()
        thread.join(1)
        assert failures == []

    def test_x11_start_surfaces_background_initialization_failure(self) -> None:
        from linux_whispr.input.x11_hotkey import X11HotkeyListener

        listener = X11HotkeyListener()
        self._register(listener)

        def listen_loop() -> None:
            raise OSError("cannot open display")

        listener._listen_loop = listen_loop  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="X11 hotkey listener failed to start") as error:
            listener.start()

        assert isinstance(error.value.__cause__, OSError)
        assert not listener._running
        assert listener._thread is not None
        assert not listener._thread.is_alive()

    def test_x11_start_rejects_asynchronous_grab_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from linux_whispr.input.x11_hotkey import X11HotkeyListener

        handlers: list[Callable[[BaseException, object], int]] = []

        class FakeRoot:
            def __init__(self) -> None:
                self.released: list[tuple[int, int]] = []

            def grab_key(
                self, *args: object, onerror: Callable[[BaseException, object], int]
            ) -> None:
                handlers.append(onerror)

            def ungrab_key(self, keycode: int, modifiers: int) -> None:
                self.released.append((keycode, modifiers))

        class FakeDisplay:
            def __init__(self) -> None:
                self.root = FakeRoot()
                self.closed = False

            def screen(self) -> object:
                return SimpleNamespace(root=self.root)

            def keysym_to_keycode(self, keysym: int) -> int:
                return 42

            def sync(self) -> None:
                for handler in handlers:
                    handler(RuntimeError("BadAccess"), object())

            def close(self) -> None:
                self.closed = True

        fake_display = FakeDisplay()
        xlib = ModuleType("Xlib")
        xlib.X = SimpleNamespace(
            ControlMask=1,
            ShiftMask=2,
            Mod1Mask=4,
            Mod4Mask=8,
            Mod2Mask=16,
            LockMask=32,
            GrabModeAsync=1,
        )
        xlib.XK = SimpleNamespace(string_to_keysym=lambda _: 1)
        xlib.display = SimpleNamespace(Display=lambda: fake_display)
        monkeypatch.setitem(sys.modules, "Xlib", xlib)

        listener = X11HotkeyListener()
        self._register(listener)

        with pytest.raises(RuntimeError, match="X11 hotkey listener failed to start") as error:
            listener.start()

        assert error.value.__cause__ is not None
        assert "could not acquire" in str(error.value.__cause__)
        assert fake_display.closed
        assert len(fake_display.root.released) == 4

    def test_x11_stop_unblocks_startup(self) -> None:
        from linux_whispr.input.x11_hotkey import X11HotkeyListener

        listener = X11HotkeyListener()
        self._register(listener)
        setup_started = threading.Event()
        returned = threading.Event()
        failures: list[BaseException] = []

        def listen_loop() -> None:
            setup_started.set()
            while listener._running:
                threading.Event().wait(0.01)

        listener._listen_loop = listen_loop  # type: ignore[method-assign]

        def start() -> None:
            try:
                listener.start()
            except RuntimeError as error:
                failures.append(error)
            finally:
                returned.set()

        thread = threading.Thread(target=start)
        thread.start()
        assert setup_started.wait(1)

        listener.stop()
        assert returned.wait(1)
        assert len(failures) == 1
        assert isinstance(failures[0], RuntimeError)
        assert listener._thread is not None
        listener._thread.join(1)
        assert not listener._thread.is_alive()
        thread.join(1)
        assert not thread.is_alive()

    def test_pynput_start_waits_for_listener_ready_marker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from linux_whispr.input.pynput_hotkey import PynputHotkeyListener

        listener = PynputHotkeyListener()
        listener._bindings.append(({object()}, lambda: None))
        constructed = threading.Event()

        class FakeListener:
            def __init__(self, **kwargs: object) -> None:
                self._ready = False
                self._alive = True
                fake_listener.append(self)
                constructed.set()

            def start(self) -> None:
                return None

            def is_alive(self) -> bool:
                return self._alive

            def stop(self) -> None:
                self._alive = False

            def join(self, timeout: float | None = None) -> None:
                return None
        fake_listener: list[FakeListener] = []

        pynput = ModuleType("pynput")
        pynput_keyboard = ModuleType("pynput.keyboard")
        pynput_keyboard.Listener = FakeListener  # type: ignore[attr-defined]
        pynput.keyboard = pynput_keyboard  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "pynput", pynput)
        monkeypatch.setitem(sys.modules, "pynput.keyboard", pynput_keyboard)

        returned = threading.Event()
        failures: list[BaseException] = []

        def start() -> None:
            try:
                listener.start()
            except RuntimeError as error:
                failures.append(error)
            finally:
                returned.set()

        thread = threading.Thread(target=start)
        thread.start()
        assert constructed.wait(1)
        assert not returned.is_set()

        fake_listener[0]._ready = True
        assert returned.wait(1)
        listener.stop()
        thread.join(1)
        assert failures == []
