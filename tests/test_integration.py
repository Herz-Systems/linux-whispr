"""Integration tests — verify module imports and wiring."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestModuleImports:
    """Verify all modules can be imported without errors."""

    @pytest.mark.parametrize(
        "module",
        [
            "linux_whispr",
            "linux_whispr.constants",
            "linux_whispr.config",
            "linux_whispr.events",
            "linux_whispr.platform.detect",
            "linux_whispr.platform.notifications",
            "linux_whispr.platform.autostart",
            "linux_whispr.stt.base",
            "linux_whispr.stt.faster_whisper",
            "linux_whispr.stt.model_manager",
            "linux_whispr.stt.whisper_cpp",
            "linux_whispr.stt.openai_api",
            "linux_whispr.stt.groq_api",
            "linux_whispr.ai.base",
            "linux_whispr.ai.refinement",
            "linux_whispr.ai.command",
            "linux_whispr.ai.openai_llm",
            "linux_whispr.ai.groq_llm",
            "linux_whispr.ai.anthropic_llm",
            "linux_whispr.ai.local_llm",
            "linux_whispr.ai.prompts.refinement",
            "linux_whispr.ai.prompts.command",
            "linux_whispr.features.dictionary",
            "linux_whispr.features.snippets",
            "linux_whispr.features.history",
            "linux_whispr.features.adaptive",
            "linux_whispr.output.clipboard",
            "linux_whispr.output.injector",
            "linux_whispr.output.xdotool",
            "linux_whispr.output.wtype",
            "linux_whispr.output.ydotool",
            "linux_whispr.input.hotkey",
            "linux_whispr.ui.overlay",
            "linux_whispr.ui.tray",
            "linux_whispr.ui.settings",
            "linux_whispr.ui.wizard",
        ],
    )
    def test_import(self, module: str) -> None:
        """Each module should import without error."""
        try:
            importlib.import_module(module)
        except OSError as e:
            if "PortAudio" in str(e):
                pytest.skip("PortAudio not available")
            raise


class TestConstants:
    def test_supported_models_list(self) -> None:
        from linux_whispr.constants import SUPPORTED_WHISPER_MODELS

        assert len(SUPPORTED_WHISPER_MODELS) >= 5
        assert "base" in SUPPORTED_WHISPER_MODELS
        assert "large-v3-turbo" in SUPPORTED_WHISPER_MODELS

    def test_xdg_paths_are_absolute(self) -> None:
        from linux_whispr.constants import CACHE_DIR, CONFIG_DIR, DATA_DIR

        assert CONFIG_DIR.is_absolute()
        assert DATA_DIR.is_absolute()
        assert CACHE_DIR.is_absolute()


class TestConfigIntegration:
    def test_default_config_round_trip(self, tmp_path: object) -> None:
        from pathlib import Path

        from linux_whispr.config import AppConfig

        p = Path(str(tmp_path)) / "test.toml"
        cfg = AppConfig()
        cfg.save(p)

        loaded = AppConfig.load(p)
        assert loaded.stt.backend == cfg.stt.backend
        assert loaded.hotkey.dictation == cfg.hotkey.dictation
        assert loaded.audio.silence_duration == cfg.audio.silence_duration


class TestEventBusIntegration:
    def test_full_pipeline_event_flow(self) -> None:
        from linux_whispr.events import EventBus

        bus = EventBus()
        trace: list[str] = []

        bus.on("hotkey.dictation.start", lambda **kw: trace.append("start"))
        bus.on("stt.started", lambda **kw: trace.append("stt"))
        bus.on("stt.complete", lambda **kw: trace.append("done"))
        bus.on("inject.complete", lambda **kw: trace.append("inject"))
        bus.on("state.change", lambda **kw: trace.append(f"state:{kw.get('new_state')}"))

        # Simulate the full pipeline
        bus.emit("hotkey.dictation.start")
        bus.emit("stt.started")
        bus.emit("stt.complete", text="hello world", language="en")
        bus.emit("inject.complete", text="hello world")
        bus.emit("state.change", old_state="PROCESSING", new_state="IDLE")

        assert trace == ["start", "stt", "done", "inject", "state:IDLE"]
        bus.clear()


class TestModelManager:
    def test_list_models(self) -> None:
        from linux_whispr.stt.model_manager import ModelManager

        mm = ModelManager()
        models = mm.list_models()
        assert len(models) >= 5
        names = [m.name for m in models]
        assert "base" in names

    def test_unsupported_model_raises(self) -> None:
        from linux_whispr.stt.model_manager import ModelManager

        mm = ModelManager()
        with pytest.raises(ValueError, match="Unsupported"):
            mm.download("nonexistent-model-xyz")


class TestSTTFactory:
    def test_creates_whisper_cpp_backend(self) -> None:
        from linux_whispr.app import LinuxWhispr
        from linux_whispr.config import AppConfig
        from linux_whispr.stt.whisper_cpp import WhisperCppBackend

        config = AppConfig()
        config.stt.backend = "whisper-cpp"
        config.stt.model = "small"
        config.stt.device = "vulkan"

        backend = LinuxWhispr(config)._create_stt_backend()
        assert isinstance(backend, WhisperCppBackend)
        assert backend._model_name == "small"


class TestDictationStateFailures:
    def test_error_state_hotkey_starts_explicit_retry(self) -> None:
        from linux_whispr.app import AppState, LinuxWhispr

        app = LinuxWhispr()
        app._state = AppState.ERROR
        app._start_recording = MagicMock()

        app._on_dictation_hotkey()

        app._start_recording.assert_called_once()

    def test_microphone_start_failure_emits_error_and_sets_error_state(self) -> None:
        from linux_whispr.app import AppState, LinuxWhispr
        from linux_whispr.events import EventBus

        bus = EventBus()
        errors: list[str] = []
        bus.on("app.error", lambda message: errors.append(message))
        app = LinuxWhispr()
        app._event_bus = bus
        app._audio = MagicMock()
        app._audio.start.side_effect = RuntimeError("microphone unavailable")
        app._vad = MagicMock()

        app._start_recording()

        assert app.state == AppState.ERROR
        assert errors == [
            "Could not start recording. Check the microphone and audio settings."
        ]

    def test_audio_ready_transitions_to_processing(self) -> None:
        from linux_whispr.app import AppState, LinuxWhispr

        app = LinuxWhispr()
        app._state = AppState.RECORDING

        with patch("linux_whispr.app.threading.Thread") as thread:
            app._on_audio_ready(b"wav", 1.0)

        assert app.state == AppState.PROCESSING
        thread.return_value.start.assert_called_once()

    def test_model_load_failure_emits_error_and_sets_error_state(self) -> None:
        from linux_whispr.app import AppState, LinuxWhispr
        from linux_whispr.events import EventBus

        bus = EventBus()
        errors: list[str] = []
        bus.on("app.error", lambda message: errors.append(message))
        app = LinuxWhispr()
        app._event_bus = bus
        app._stt = MagicMock()
        app._stt.is_loaded = False
        app._stt.load.side_effect = RuntimeError("model unavailable")
        app._injector = MagicMock()

        with patch("linux_whispr.platform.notifications.notify"):
            app._process_audio(b"wav", 1.0)

        assert app.state == AppState.ERROR
        assert errors == [
            "Transcription failed. Check the speech model and audio settings."
        ]

    def test_injection_failure_emits_error_and_returns_to_idle(self) -> None:
        from types import SimpleNamespace

        from linux_whispr.app import AppState, LinuxWhispr
        from linux_whispr.events import EventBus

        bus = EventBus()
        errors: list[str] = []
        bus.on("app.error", lambda message: errors.append(message))
        app = LinuxWhispr()
        app._event_bus = bus
        app._state = AppState.PROCESSING
        app._stt = MagicMock()
        app._stt.is_loaded = True
        app._stt.transcribe.return_value = SimpleNamespace(text="hello", language="en")
        app._injector = MagicMock()
        app._injector.inject.return_value = False

        app._process_audio(b"wav", 1.0)

        assert app.state == AppState.IDLE
        assert errors == [
            "Text injection failed. Check input permissions and the active application."
        ]

    def test_start_emits_idle_only_after_hotkey_and_dashboard_are_ready(self) -> None:
        from linux_whispr.app import AppState, LinuxWhispr
        from linux_whispr.events import EventBus

        bus = EventBus()
        states: list[AppState] = []
        bus.on("state.change", lambda new_state, **kwargs: states.append(new_state))
        app = LinuxWhispr()
        app._event_bus = bus
        app._hotkey_listener = MagicMock()
        app._tray = MagicMock()

        with patch.object(app, "_start_web_dashboard") as start_dashboard:
            app.start()

        app._hotkey_listener.start.assert_called_once()
        app._tray.start.assert_called_once()
        start_dashboard.assert_called_once()
        assert states == [AppState.IDLE]


class TestDictionaryCorrectionPipeline:
    def test_pack_alias_is_corrected_before_injection_without_ai(
        self, tmp_path: Path
    ) -> None:
        from types import SimpleNamespace

        from linux_whispr.app import AppState, LinuxWhispr
        from linux_whispr.events import EventBus
        from linux_whispr.features.dictionary import Dictionary

        dictionary = Dictionary(tmp_path / "dict.json")
        dictionary.set_pack_enabled("coding", True)
        app = LinuxWhispr()
        app._event_bus = EventBus()
        app._state = AppState.PROCESSING
        app._dictionary = dictionary
        app._snippets = None
        app._refinement = None
        app._adaptive = None
        app._history = MagicMock()
        app._stt = MagicMock()
        app._stt.is_loaded = True
        app._stt.transcribe.return_value = SimpleNamespace(
            text="type script", language="en"
        )
        app._injector = MagicMock()
        app._injector.inject.return_value = True

        with patch.object(app, "_get_active_window_name", return_value=None):
            app._process_audio(b"wav", 1.0)

        app._injector.inject.assert_called_once_with("TypeScript")
        app._history.add.assert_called_once_with(
            raw_text="type script",
            refined_text="TypeScript",
            duration=1.0,
            app_context=None,
            language="en",
        )
