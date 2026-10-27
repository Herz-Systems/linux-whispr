"""Runtime model warmup lifecycle tests."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from linux_whispr.app import LinuxWhispr
from linux_whispr.config import AppConfig
from linux_whispr.stt.base import TranscriptionResult
from linux_whispr.stt.faster_whisper import FasterWhisperBackend


def _local_app() -> tuple[LinuxWhispr, FasterWhisperBackend]:
    config = AppConfig()
    config.preload_models = True
    app = LinuxWhispr(config, enable_tray=False)
    stt = FasterWhisperBackend(model_name="base")
    app._stt = stt
    app._injector = MagicMock()
    return app, stt


def test_first_dictation_reuses_warmup_model_single_flight() -> None:
    app, stt = _local_app()
    warmup_entered = threading.Event()
    release_load = threading.Event()
    load_calls: list[bool] = []

    def load(*, local_files_only: bool = False) -> None:
        load_calls.append(local_files_only)
        warmup_entered.set()
        assert release_load.wait(timeout=1)
        stt._model = object()

    stt.load = load  # type: ignore[method-assign]
    stt.transcribe = MagicMock(  # type: ignore[method-assign]
        return_value=TranscriptionResult(text="")
    )

    app._start_model_warmup()
    assert warmup_entered.wait(timeout=1)

    foreground = threading.Thread(target=app._process_audio, args=(b"wav", 1.0))
    foreground.start()
    release_load.set()
    foreground.join(timeout=1)
    assert not foreground.is_alive()
    assert app._warmup_thread is not None
    app._warmup_thread.join(timeout=1)

    assert load_calls == [True]
    stt.transcribe.assert_called_once()


def test_stop_waits_for_active_warmup_load_before_unloading() -> None:
    app, stt = _local_app()
    load_started = threading.Event()
    release_load = threading.Event()
    stop_reached_dashboard = threading.Event()
    unloaded = threading.Event()

    def load(*, local_files_only: bool = False) -> None:
        assert local_files_only
        load_started.set()
        assert release_load.wait(timeout=1)
        stt._model = object()

    def unload() -> None:
        unloaded.set()
        stt._model = None

    stt.load = load  # type: ignore[method-assign]
    stt.unload = unload  # type: ignore[method-assign]
    app._stop_web_dashboard = stop_reached_dashboard.set  # type: ignore[method-assign]
    app._start_model_warmup()
    assert load_started.wait(timeout=1)

    stopping = threading.Thread(target=app.stop)
    stopping.start()
    assert stop_reached_dashboard.wait(timeout=1)
    assert not unloaded.is_set()

    release_load.set()
    stopping.join(timeout=1)
    assert not stopping.is_alive()
    assert unloaded.is_set()


def test_stop_waits_for_active_transcription_before_unloading() -> None:
    app, stt = _local_app()
    stt._model = object()
    transcription_started = threading.Event()
    release_transcription = threading.Event()
    stop_reached_dashboard = threading.Event()
    unloaded = threading.Event()

    def transcribe(*_args: object, **_kwargs: object) -> TranscriptionResult:
        transcription_started.set()
        assert release_transcription.wait(timeout=1)
        return TranscriptionResult(text="")

    def unload() -> None:
        unloaded.set()
        stt._model = None

    stt.transcribe = transcribe  # type: ignore[method-assign]
    stt.unload = unload  # type: ignore[method-assign]
    app._stop_web_dashboard = stop_reached_dashboard.set  # type: ignore[method-assign]

    processing = threading.Thread(
        target=app._process_audio,
        args=(b"wav", 1.0),
    )
    processing.start()
    assert transcription_started.wait(timeout=1)

    stopping = threading.Thread(target=app.stop)
    stopping.start()
    assert stop_reached_dashboard.wait(timeout=1)
    assert not unloaded.is_set()

    release_transcription.set()
    processing.join(timeout=1)
    stopping.join(timeout=1)
    assert not processing.is_alive()
    assert not stopping.is_alive()
    assert unloaded.is_set()


def test_stop_does_not_wait_for_ollama_warmup_request() -> None:
    from linux_whispr.ai.ollama import OllamaBackend

    config = AppConfig()
    config.preload_models = True
    config.ai.enabled = True
    config.ai.backend = "ollama"
    app = LinuxWhispr(config, enable_tray=False)
    backend = OllamaBackend(model="cached-model")
    preload_started = threading.Event()
    release_preload = threading.Event()

    def preload(*, cancel_event: threading.Event | None = None) -> None:
        assert cancel_event is app._warmup_stop
        preload_started.set()
        assert release_preload.wait(timeout=1)

    backend.preload = preload  # type: ignore[method-assign]
    app._llm_backend = backend
    app._stop_web_dashboard = MagicMock()  # type: ignore[method-assign]
    app._start_model_warmup()
    assert preload_started.wait(timeout=1)

    app.stop()

    assert not app._models_preparing
    release_preload.set()
    assert app._warmup_thread is not None
    app._warmup_thread.join(timeout=1)


def test_stop_prevents_queued_warmup_and_audio_processing() -> None:
    app, stt = _local_app()
    load = MagicMock()
    stt.load = load  # type: ignore[method-assign]
    app._stop_web_dashboard = MagicMock()  # type: ignore[method-assign]

    app.stop()
    app._start_model_warmup()
    app._on_audio_ready(b"wav", 1.0)

    load.assert_not_called()
    assert app._warmup_thread is None


def test_stop_discards_nonempty_refinement_before_final_effects() -> None:
    from linux_whispr.ai.base import RefinementResult
    from linux_whispr.ai.refinement import RefinementPipeline

    app, stt = _local_app()
    stt._model = object()
    stt.transcribe = MagicMock(  # type: ignore[method-assign]
        return_value=TranscriptionResult(text="Hallo Welt", language="de")
    )
    app._history = MagicMock()
    app._stop_web_dashboard = MagicMock()  # type: ignore[method-assign]
    app._get_active_window_name = MagicMock(return_value=None)  # type: ignore[method-assign]
    errors: list[str] = []
    app._event_bus.on("app.error", lambda message: errors.append(message))

    refinement_started = threading.Event()
    release_refinement = threading.Event()
    backend = MagicMock()

    def generate(*_args: object, **_kwargs: object) -> RefinementResult:
        refinement_started.set()
        assert release_refinement.wait(timeout=1)
        return RefinementResult(text="Hallo Welt", model="qwen3:8b")

    backend.generate.side_effect = generate
    app._refinement = RefinementPipeline(app._event_bus, backend=backend, enabled=True)

    processing = threading.Thread(target=app._process_audio, args=(b"wav", 1.0))
    processing.start()
    assert refinement_started.wait(timeout=1)

    app.stop()
    release_refinement.set()
    processing.join(timeout=1)

    assert not processing.is_alive()
    app._injector.inject.assert_not_called()
    app._history.add.assert_not_called()
    assert errors == []


def test_stop_waits_for_admitted_history_write_before_closing() -> None:
    app, stt = _local_app()
    stt._model = object()
    stt.transcribe = MagicMock(  # type: ignore[method-assign]
        return_value=TranscriptionResult(text="Hallo Welt", language="de")
    )
    app._history = MagicMock()
    history_started = threading.Event()
    release_history = threading.Event()
    history_closed = threading.Event()
    stop_reached_dashboard = threading.Event()

    def add(**_kwargs: object) -> None:
        history_started.set()
        assert release_history.wait(timeout=1)

    app._history.add.side_effect = add
    app._history.close.side_effect = history_closed.set
    app._stop_web_dashboard = stop_reached_dashboard.set  # type: ignore[method-assign]
    app._get_active_window_name = MagicMock(return_value=None)  # type: ignore[method-assign]

    processing = threading.Thread(target=app._process_audio, args=(b"wav", 1.0))
    processing.start()
    assert history_started.wait(timeout=1)

    stopping = threading.Thread(target=app.stop)
    stopping.start()
    assert stop_reached_dashboard.wait(timeout=1)
    assert not history_closed.is_set()

    release_history.set()
    processing.join(timeout=1)
    stopping.join(timeout=1)

    assert not processing.is_alive()
    assert not stopping.is_alive()
    assert history_closed.is_set()


def test_failed_cached_warmup_keeps_first_use_retry_available() -> None:
    app, stt = _local_app()
    load_calls: list[bool] = []

    def load(*, local_files_only: bool = False) -> None:
        load_calls.append(local_files_only)
        if local_files_only:
            raise RuntimeError("cache disappeared")
        stt._model = object()

    stt.load = load  # type: ignore[method-assign]
    stt.transcribe = MagicMock(  # type: ignore[method-assign]
        return_value=TranscriptionResult(text="")
    )

    app._models_preparing = True
    app._warm_models()
    app._process_audio(b"wav", 1.0)

    assert load_calls == [True, False]
    assert not app._models_preparing
    stt.transcribe.assert_called_once()
