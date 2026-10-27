"""Main application orchestrator — wires all components together."""

from __future__ import annotations

import logging
import subprocess
import threading
from enum import Enum, auto
from typing import TYPE_CHECKING

from linux_whispr.ai.base import LLMBackend
from linux_whispr.audio.capture import AudioCapture
from linux_whispr.audio.vad import SileroVAD
from linux_whispr.config import AppConfig
from linux_whispr.events import EventBus, event_bus
from linux_whispr.features.adaptive import AdaptiveLearner
from linux_whispr.features.dictionary import Dictionary
from linux_whispr.features.history import HistoryManager
from linux_whispr.features.snippets import SnippetEngine
from linux_whispr.input.hotkey import create_hotkey_listener
from linux_whispr.output.clipboard import Clipboard
from linux_whispr.output.injector import TextInjector
from linux_whispr.platform.detect import PlatformInfo, detect_platform
from linux_whispr.stt.base import STTBackend
from linux_whispr.stt.faster_whisper import FasterWhisperBackend
from linux_whispr.stt.whisper_cpp import WhisperCppBackend
from linux_whispr.ui.overlay import Overlay

if TYPE_CHECKING:
    from linux_whispr.ui.tray import SystemTray

logger = logging.getLogger(__name__)


class AppState(Enum):
    """Application states."""

    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    ERROR = auto()


class LinuxWhispr:
    """Main application class that orchestrates the dictation pipeline.

    Pipeline: Hotkey → Record → VAD auto-stop → STT → Snippets → (AI refinement) →
    Dictionary corrections → Inject → History
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        enable_tray: bool = True,
    ) -> None:
        self._config = config or AppConfig.load()
        self._event_bus: EventBus = event_bus
        self._state = AppState.IDLE
        self._tray_enabled = enable_tray
        self._platform: PlatformInfo | None = None

        # Core components (initialized in setup())
        self._audio: AudioCapture | None = None
        self._vad: SileroVAD | None = None
        self._stt: STTBackend | None = None
        self._injector: TextInjector | None = None
        self._clipboard: Clipboard | None = None
        self._hotkey_listener: object | None = None

        # Feature components
        self._dictionary: Dictionary | None = None
        self._snippets: SnippetEngine | None = None
        self._history: HistoryManager | None = None
        self._adaptive: AdaptiveLearner | None = None

        # UI components
        self._overlay: Overlay | None = None
        self._tray: SystemTray | None = None

        # AI refinement
        self._refinement: object | None = None
        self._llm_backend: LLMBackend | None = None

        # Web dashboard
        self._web_server: object | None = None
        self._web_thread: threading.Thread | None = None
        self._web_stopping = False

        # VAD monitoring
        self._vad_thread: threading.Thread | None = None
        self._vad_active = False

        # STT lifecycle is serialized so launch warmup, transcription, and
        # shutdown share exactly one model instance.
        self._stt_lock = threading.RLock()
        self._warmup_stop = threading.Event()
        self._warmup_thread: threading.Thread | None = None
        self._models_preparing = False

        # Track last transcription for history
        self._last_raw_text: str = ""
        self._last_duration: float = 0.0
        self._last_language: str | None = None

    @property
    def state(self) -> AppState:
        return self._state

    def setup(self) -> None:
        """Initialize all components."""
        from linux_whispr.ui.desktop import ensure_application

        ensure_application()
        logger.info("Setting up LinuxWhispr...")

        # Detect platform
        self._platform = detect_platform()

        # Initialize clipboard (used by injector, adaptive learner, etc.)
        self._clipboard = Clipboard(self._platform)

        # Initialize audio capture
        self._audio = AudioCapture(
            event_bus=self._event_bus,
            sample_rate=self._config.audio.sample_rate,
            device=self._config.audio.device,
        )

        # Initialize VAD
        self._vad = SileroVAD(
            threshold=self._config.audio.silence_threshold,
            silence_duration=self._config.audio.silence_duration,
        )
        self._vad.load()

        # Initialize STT
        self._stt = self._create_stt_backend()

        # Initialize text injector
        self._injector = TextInjector(
            event_bus=self._event_bus,
            platform=self._platform,
            preserve_clipboard=self._config.injection.preserve_clipboard,
            restore_delay=self._config.injection.clipboard_restore_delay,
            method=self._config.injection.method,
        )

        # Initialize features
        self._dictionary = Dictionary()
        self._dictionary.load()

        self._snippets = SnippetEngine()
        self._snippets.load()

        self._history = HistoryManager()
        self._history.open()

        self._adaptive = AdaptiveLearner(
            event_bus=self._event_bus,
            dictionary=self._dictionary,
            clipboard=self._clipboard,
            watch_window=self._config.adaptive.watch_window,
            poll_interval=2.0,
        )
        self._adaptive.enabled = self._config.adaptive.enabled

        # Initialize AI refinement (if configured)
        self._setup_ai_refinement()

        # Initialize overlay
        self._overlay = Overlay(self._event_bus)
        self._overlay.setup()

        # Initialize the system tray unless explicitly disabled by the CLI.
        if self._tray_enabled:
            self._setup_tray()

        # Register event handlers
        self._event_bus.on("audio.ready", self._on_audio_ready)

        # Prepare global hotkeys. Listening begins in start(), alongside the dashboard.
        self._setup_hotkeys()

        logger.info("LinuxWhispr setup complete")

    def _create_stt_backend(self) -> STTBackend:
        """Create the STT backend based on config."""
        backend = self._config.stt.backend

        if backend == "faster-whisper":
            return FasterWhisperBackend(
                model_name=self._config.stt.model,
                device=self._config.stt.device,
                compute_type=self._config.stt.compute_type,
            )
        elif backend == "whisper-cpp":
            return WhisperCppBackend(
                model_name=self._config.stt.model,
                device=self._config.stt.device,
            )
        elif backend == "openai":
            from linux_whispr.stt.openai_api import OpenAIWhisperBackend

            # API key should come from secretstorage or env var
            import os

            api_key = os.environ.get("OPENAI_API_KEY", "")
            return OpenAIWhisperBackend(api_key=api_key)
        elif backend == "groq":
            from linux_whispr.stt.groq_api import GroqWhisperBackend

            import os

            api_key = os.environ.get("GROQ_API_KEY", "")
            return GroqWhisperBackend(api_key=api_key)
        else:
            logger.warning("Unknown STT backend '%s', falling back to faster-whisper", backend)
            return FasterWhisperBackend(model_name=self._config.stt.model)

    def _setup_ai_refinement(self) -> None:
        """Setup AI refinement pipeline if enabled."""
        if not self._config.ai.enabled or self._config.ai.backend == "none":
            return

        from linux_whispr.ai.refinement import RefinementPipeline

        llm_backend = self._create_llm_backend()
        if llm_backend is not None:
            self._llm_backend = llm_backend
            self._refinement = RefinementPipeline(
                event_bus=self._event_bus,
                backend=llm_backend,
                enabled=True,
                custom_prompt=self._config.ai.custom_prompt,
            )
            logger.info("AI refinement enabled (backend=%s)", self._config.ai.backend)

    def _create_llm_backend(self) -> LLMBackend | None:
        """Create the LLM backend for AI refinement based on config."""
        import os

        backend = self._config.ai.backend

        if backend == "openai":
            from linux_whispr.ai.openai_llm import OpenAILLMBackend

            api_key = os.environ.get("OPENAI_API_KEY", "")
            model = self._config.ai.model or "gpt-4o-mini"
            return OpenAILLMBackend(api_key=api_key, model=model)
        elif backend == "groq":
            from linux_whispr.ai.groq_llm import GroqLLMBackend

            api_key = os.environ.get("GROQ_API_KEY", "")
            model = self._config.ai.model or "llama-3.1-8b-instant"
            return GroqLLMBackend(api_key=api_key, model=model)
        elif backend == "anthropic":
            from linux_whispr.ai.anthropic_llm import AnthropicLLMBackend

            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            model = self._config.ai.model or "claude-3-haiku-20240307"
            return AnthropicLLMBackend(api_key=api_key, model=model)
        elif backend == "local":
            from linux_whispr.ai.local_llm import LocalLLMBackend

            model_path = self._config.ai.model
            if model_path:
                return LocalLLMBackend(model_path=model_path)
            logger.warning("Local LLM backend requires a model path in config")
        elif backend == "ollama":
            from linux_whispr.ai.ollama import OllamaBackend

            return OllamaBackend(
                model=self._config.ai.model,
                keep_alive_minutes=self._config.ai.keep_alive_minutes,
            )
        else:
            logger.warning("Unknown AI backend: %s", backend)

        return None

    def _start_model_warmup(self) -> None:
        """Start one cached-only preparation worker after interactive startup."""
        if not self._config.preload_models or self._warmup_stop.is_set():
            return

        from linux_whispr.ai.ollama import OllamaBackend

        has_local_stt = isinstance(self._stt, (FasterWhisperBackend, WhisperCppBackend))
        has_ollama = self._config.ai.enabled and isinstance(self._llm_backend, OllamaBackend)
        if not has_local_stt and not has_ollama:
            return

        if self._warmup_thread is not None and self._warmup_thread.is_alive():
            return

        self._models_preparing = True
        self._warmup_thread = threading.Thread(
            target=self._warm_models,
            daemon=True,
            name="model-warmup",
        )
        self._warmup_thread.start()

    def _warm_models(self) -> None:
        """Load only already cached local models without delaying dictation."""
        try:
            stt = self._stt
            if isinstance(stt, (FasterWhisperBackend, WhisperCppBackend)):
                try:
                    with self._stt_lock:
                        if not self._warmup_stop.is_set() and not stt.is_loaded:
                            stt.load(local_files_only=True)
                except Exception:
                    logger.info("Cached local STT warmup skipped", exc_info=True)

            if self._warmup_stop.is_set():
                return

            from linux_whispr.ai.ollama import OllamaBackend

            llm_backend = self._llm_backend
            if (
                not self._warmup_stop.is_set()
                and self._config.ai.enabled
                and isinstance(llm_backend, OllamaBackend)
            ):
                try:
                    llm_backend.preload(cancel_event=self._warmup_stop)
                except Exception:
                    logger.info("Ollama model warmup skipped", exc_info=True)
        finally:
            self._models_preparing = False

    def _start_web_dashboard(self) -> None:
        """Start the dashboard and wait until it accepts connections."""
        try:
            import uvicorn

            from linux_whispr.web.server import app as web_app
            from linux_whispr.web.server import (
                set_dictionary_provider,
                set_runtime_status_provider,
            )
        except ImportError as error:
            raise RuntimeError(
                "The dashboard dependencies are unavailable. Reinstall LinuxWhispr "
                "with its required web dependencies."
            ) from error

        port = self._config.web.port
        if self._is_port_in_use(port):
            raise RuntimeError(
                f"Dashboard startup failed: http://127.0.0.1:{port} is already in use."
            )

        set_runtime_status_provider(self._runtime_status)
        set_dictionary_provider(self._live_dictionary, self._live_promotion_threshold)
        config = uvicorn.Config(web_app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        start_error: list[BaseException] = []
        stopped = threading.Event()

        def _run_server() -> None:
            try:
                server.run()
            except BaseException as error:
                start_error.append(error)
            finally:
                stopped.set()
                if server.started and not self._web_stopping:
                    logger.critical(
                        "Dashboard stopped unexpectedly; shutting down LinuxWhispr."
                    )
                    self._request_quit()

        self._web_stopping = False
        self._web_server = server
        self._web_thread = threading.Thread(target=_run_server, name="web-dashboard")
        self._web_thread.start()

        import time

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if server.started:
                logger.info("Web dashboard available at http://127.0.0.1:%d", port)
                if self._config.web.auto_open:
                    self._open_web_dashboard(port)
                return
            if stopped.wait(timeout=0.1):
                break

        self._stop_web_dashboard()
        if start_error:
            raise RuntimeError("Dashboard startup failed.") from start_error[0]
        raise RuntimeError(
            f"Dashboard startup failed: http://127.0.0.1:{port} did not become ready."
        )

    @staticmethod
    def _open_web_dashboard(port: int) -> None:
        """Open the ready dashboard when the user has opted in."""
        import webbrowser

        url = f"http://127.0.0.1:{port}"
        try:
            webbrowser.open(url)
        except Exception:
            logger.warning("Could not open the web dashboard at %s", url, exc_info=True)

    def _runtime_status(self) -> dict[str, bool | str]:
        """Expose the active dictation runtime to the dashboard status endpoint."""
        return {
            "available": True,
            "state": self._state.name.lower(),
            "models_preparing": self._models_preparing,
        }

    def _live_dictionary(self) -> Dictionary:
        """Expose the single active dictionary object to dashboard mutations."""
        if self._dictionary is None:
            raise RuntimeError("Dictionary is unavailable before application setup.")
        return self._dictionary

    def _live_promotion_threshold(self) -> int:
        """Expose the policy currently used for runtime dictionary corrections."""
        return self._config.adaptive.promotion_threshold

    def _stop_web_dashboard(self) -> None:
        """Stop and join the dashboard server started with this application."""
        self._web_stopping = True
        server = self._web_server
        thread = self._web_thread
        self._web_server = None
        self._web_thread = None
        if server is not None:
            server.should_exit = True  # type: ignore[union-attr]
        if thread is not None:
            thread.join()

        from linux_whispr.web.server import (
            set_dictionary_provider,
            set_runtime_status_provider,
        )

        set_runtime_status_provider(None)
        set_dictionary_provider(None)

    @staticmethod
    def _is_port_in_use(port: int) -> bool:
        """Check if a TCP port is already bound on localhost."""
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def _setup_tray(self) -> None:
        """Initialize the native system tray icon."""
        from linux_whispr.ui.tray import SystemTray

        self._tray = SystemTray(
            event_bus=self._event_bus,
            on_toggle_dictation=self._on_dictation_hotkey,
            on_open_settings=lambda: self._open_web_dashboard(self._config.web.port),
            on_quit=self._request_quit,
        )
        try:
            self._tray.setup()
        except Exception:
            logger.exception("System tray initialization failed")
            raise

    def _setup_hotkeys(self) -> None:
        """Register global hotkeys."""
        assert self._platform is not None

        listener = create_hotkey_listener(self._platform)
        listener.register(
            self._config.hotkey.dictation,
            self._on_dictation_hotkey,
            name="dictation",
        )
        self._hotkey_listener = listener

    def start(self) -> None:
        """Start dictation input and the required dashboard."""
        if self._hotkey_listener is not None:
            self._hotkey_listener.start()  # type: ignore[union-attr]

        if self._tray is not None:
            try:
                self._tray.start()
            except Exception:
                logger.exception("System tray failed to start")
                raise

        self._start_web_dashboard()
        self._set_state(AppState.IDLE)
        self._start_model_warmup()
        logger.info("LinuxWhispr started — press %s to dictate", self._config.hotkey.dictation)

    def stop(self) -> None:
        """Stop the application and every component it started."""
        self._warmup_stop.set()
        self._models_preparing = False
        self._stop_web_dashboard()

        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()  # type: ignore[union-attr]

        if self._audio is not None and self._audio.is_recording:
            self._audio.stop()

        if self._stt is not None:
            with self._stt_lock:
                if self._stt.is_loaded:
                    self._stt.unload()

        if self._history is not None:
            self._history.close()

        if self._tray is not None:
            self._tray.stop()

        if self._overlay is not None:
            self._overlay.destroy()

        self._event_bus.clear()
        logger.info("LinuxWhispr stopped")

    def _request_quit(self) -> None:
        """Request clean shutdown through the Qt main loop."""
        from linux_whispr.ui.desktop import quit_desktop_loop

        quit_desktop_loop()

    # --- Hotkey callbacks ---

    def _on_dictation_hotkey(self) -> None:
        """Handle dictation hotkey press (toggle mode)."""
        if self._state in (AppState.IDLE, AppState.ERROR):
            self._start_recording()
        elif self._state == AppState.RECORDING:
            self._stop_recording()
        else:
            logger.debug("Ignoring hotkey in state %s", self._state)

    def _start_recording(self) -> None:
        """Start audio recording."""
        assert self._audio is not None
        assert self._vad is not None

        try:
            self._vad.reset()
            self._audio.start()
        except Exception:
            logger.exception("Could not start microphone recording")
            self._event_bus.emit(
                "app.error",
                message="Could not start recording. Check the microphone and audio settings.",
            )
            self._set_state(AppState.ERROR)
            return

        self._set_state(AppState.RECORDING)
        self._event_bus.emit("hotkey.dictation.start")

        # Start VAD monitoring thread
        self._vad_active = True
        self._vad_thread = threading.Thread(target=self._vad_monitor, daemon=True)
        self._vad_thread.start()

        logger.info("Recording started")

    def _stop_recording(self) -> None:
        """Stop audio recording and process."""
        assert self._audio is not None

        self._vad_active = False
        self._set_state(AppState.PROCESSING)
        self._event_bus.emit("hotkey.dictation.stop")

        # Stop recording returns WAV bytes and emits audio.ready
        try:
            wav_bytes = self._audio.stop()
        except Exception:
            logger.exception("Could not stop microphone recording")
            self._event_bus.emit(
                "app.error",
                message="Could not finish recording. Check the microphone and audio settings.",
            )
            self._set_state(AppState.ERROR)
            return

        if wav_bytes is None:
            logger.warning("No audio captured")
            self._set_state(AppState.IDLE)

    def _on_audio_ready(self, wav_bytes: bytes, duration: float) -> None:
        """Handle audio ready event — run full STT + refinement pipeline."""
        if self._warmup_stop.is_set():
            return
        if self._state != AppState.PROCESSING:
            self._set_state(AppState.PROCESSING)

        # Run in a thread to avoid blocking the event bus
        threading.Thread(
            target=self._process_audio,
            args=(wav_bytes, duration),
            daemon=True,
            name="stt-pipeline",
        ).start()

    def _process_audio(self, wav_bytes: bytes, duration: float) -> None:
        """Full processing pipeline: STT → snippets → AI refinement → inject → history."""
        assert self._stt is not None
        assert self._injector is not None

        try:
            with self._stt_lock:
                if self._warmup_stop.is_set():
                    return
                # Load STT model if not loaded
                if not self._stt.is_loaded:
                    logger.info("Loading STT model (first use)...")
                    self._event_bus.emit("stt.started")
                    self._stt.load()

                # Transcribe
                self._event_bus.emit("stt.started")
                result = self._stt.transcribe(
                    wav_bytes,
                    language=self._config.stt.language,
                    initial_prompt=self._get_dictionary_prompt(),
                )
        except Exception:
            logger.exception("Transcription failed")
            self._event_bus.emit(
                "app.error",
                message="Transcription failed. Check the speech model and audio settings.",
            )
            self._set_state(AppState.ERROR)
            from linux_whispr.platform.notifications import notify

            notify(
                "Transcription Failed",
                "Check the speech model and audio settings.",
                urgency="critical",
            )
            return

        if self._warmup_stop.is_set():
            return

        if not result.text.strip():
            logger.info("Empty transcription, skipping injection")
            self._set_state(AppState.IDLE)
            return

        self._event_bus.emit("stt.complete", text=result.text, language=result.language)
        raw_text = result.text.strip()
        self._last_raw_text = raw_text
        self._last_duration = duration
        self._last_language = result.language
        logger.info("Transcribed: %s", raw_text[:100])

        # Snippet expansion (FR-11)
        final_text = raw_text
        refined_text: str | None = None
        success = False

        def save_history() -> None:
            """Persist this dictation while the lifecycle guard is held."""
            if self._history is None:
                return

            try:
                app_context = self._get_active_window_name()
                self._history.add(
                    raw_text=raw_text,
                    refined_text=refined_text,
                    duration=duration,
                    app_context=app_context,
                    language=result.language,
                )
            except Exception:
                logger.exception("Failed to save transcription to history")
                self._event_bus.emit(
                    "app.error",
                    message="Could not save dictation history. Check storage permissions.",
                )

        try:
            if self._snippets is not None:
                final_text = self._snippets.expand(final_text)
                if final_text != raw_text:
                    logger.info("Snippet expanded: %s", final_text[:100])

            # AI refinement (FR-4)
            if self._refinement is not None:
                app_name = self._get_active_window_name()
                dict_context = self._get_correction_context()
                from linux_whispr.ai.refinement import RefinementPipeline

                assert isinstance(self._refinement, RefinementPipeline)
                configured_stt_language = self._config.stt.language
                refinement_language = (
                    configured_stt_language
                    if configured_stt_language
                    and configured_stt_language.casefold() != "auto"
                    else result.language
                )
                refined = self._refinement.refine(
                    raw_text=final_text,
                    app_name=app_name,
                    dictionary_context=dict_context,
                    language=refinement_language,
                )
                if refined != final_text:
                    final_text = refined
                    logger.info("Refined: %s", final_text[:100])

            if self._dictionary is not None:
                corrected = self._dictionary.apply_corrections(
                    final_text,
                    promotion_threshold=self._config.adaptive.promotion_threshold,
                )
                if corrected != final_text:
                    final_text = corrected
                    logger.info("Dictionary corrections applied: %s", final_text[:100])

            # Store the actual injected text while preserving the transcription as raw text.
            refined_text = final_text if final_text != raw_text else None
        except Exception:
            with self._stt_lock:
                if self._warmup_stop.is_set():
                    return
                logger.exception("Post-transcription pipeline failed")
                self._event_bus.emit(
                    "app.error",
                    message="Post-processing failed. Dictation was not injected.",
                )
                save_history()
        else:
            # The lifecycle guard admits the final effects as one unit. It is
            # deliberately acquired only after all refinement work, which may
            # perform AI HTTP, has completed.
            with self._stt_lock:
                if self._warmup_stop.is_set():
                    return

                try:
                    # Inject text (FR-6)
                    success = self._injector.inject(final_text)
                    if success:
                        logger.info("Text injected (%d chars)", len(final_text))
                    else:
                        logger.error("Text injection failed")
                        self._event_bus.emit(
                            "app.error",
                            message=(
                                "Text injection failed. Check input permissions and the active application."
                            ),
                        )
                except Exception:
                    logger.exception("Post-transcription pipeline failed")
                    self._event_bus.emit(
                        "app.error",
                        message="Post-processing failed. Dictation was not injected.",
                    )
                finally:
                    # Save to history (FR-12) — always persist, even if injection failed.
                    save_history()

        # Start adaptive learning watch (FR-14)
        if self._adaptive is not None and success:
            try:
                self._adaptive.start_watching(final_text)
            except Exception:
                logger.exception("Failed to start adaptive learning")
                self._event_bus.emit(
                    "app.error",
                    message="Adaptive learning could not start. Dictation was still processed.",
                )

        self._set_state(AppState.IDLE)

    def _get_active_window_name(self) -> str | None:
        """Get the name of the currently active window."""
        assert self._platform is not None
        from linux_whispr.platform.detect import DisplayServer

        try:
            if self._platform.display_server == DisplayServer.X11:
                result = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            # Wayland: could use D-Bus or compositor IPC
            # For now, return None on Wayland
        except Exception:
            logger.debug("Failed to get active window name", exc_info=True)
        return None

    def _get_dictionary_prompt(self) -> str | None:
        """Build the initial_prompt from the custom dictionary (FR-10)."""
        if self._dictionary is not None:
            return self._dictionary.build_initial_prompt(
                promotion_threshold=self._config.adaptive.promotion_threshold
            )
        return None

    def _get_correction_context(self) -> str:
        """Build preferred-spelling context for optional AI refinement."""
        if self._dictionary is None:
            return ""
        return self._dictionary.build_ai_context(
            promotion_threshold=self._config.adaptive.promotion_threshold
        )

    def _vad_monitor(self) -> None:
        """Monitor VAD in a separate thread to auto-stop on silence."""
        import time

        assert self._audio is not None
        assert self._vad is not None

        while self._vad_active and self._audio.is_recording:
            # Get latest audio frames for VAD processing
            if self._audio._frames:
                latest = self._audio._frames[-1]
                flat = latest.flatten() if latest.ndim > 1 else latest
                self._vad.is_speech(flat)

                if self._vad.should_stop():
                    logger.info("VAD: silence detected, auto-stopping")
                    self._event_bus.emit("audio.silence")
                    self._stop_recording()
                    return

            time.sleep(0.1)

    def _set_state(self, new_state: AppState) -> None:
        """Update application state and emit event."""
        old_state = self._state
        self._state = new_state
        self._event_bus.emit("state.change", old_state=old_state, new_state=new_state)
        logger.debug("State: %s → %s", old_state.name, new_state.name)
