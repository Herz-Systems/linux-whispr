"""Settings window (GTK4 + libadwaita)."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from linux_whispr.config import AppConfig
    from linux_whispr.events import EventBus
    from linux_whispr.features.dictionary import Dictionary
    from linux_whispr.features.history import HistoryManager
    from linux_whispr.features.snippets import SnippetEngine
    from linux_whispr.stt.model_manager import ModelManager

logger = logging.getLogger(__name__)


class SettingsWindow:
    """GTK4 + libadwaita settings window.

    Sections (FR-9.3):
    - General: hotkey bindings, activation mode, auto-start
    - Audio: input device, silence detection, max duration
    - Transcription: STT backend, model selection, language, model management
    - AI Refinement: enable/disable, backend, API keys, custom prompts
    - Text Injection: method preference, clipboard preservation
    - Custom Dictionary: add/remove words and terms
    - Snippets: manage trigger → expansion mappings
    - History: browse/search/delete transcriptions
    - Appearance: overlay position, theme
    - Privacy: data retention, audio deletion
    """

    def __init__(
        self,
        config: AppConfig,
        event_bus: EventBus,
        dictionary: Dictionary | None = None,
        snippets: SnippetEngine | None = None,
        history: HistoryManager | None = None,
        model_manager: ModelManager | None = None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._dictionary = dictionary
        self._snippets = snippets
        self._history = history
        self._model_manager = model_manager
        self._window: object | None = None
        self._gtk_available = False
        self._ai_models_by_backend: dict[str, str] = {
            config.ai.backend: config.ai.model,
        }
        self._ollama_catalog_generation = 0
        self._ollama_catalog_loading = False
        self._ollama_model_updating = False
        self._ollama_ui: dict[str, object] | None = None

        try:
            import gi

            gi.require_version("Gtk", "4.0")
            gi.require_version("Adw", "1")
            self._gtk_available = True
        except (ImportError, ValueError):
            logger.warning("GTK4/libadwaita not available — settings UI disabled")

    def show(self) -> None:
        """Show the settings window."""
        if not self._gtk_available:
            logger.warning("Cannot show settings: GTK4 not available")
            return

        if self._window is not None:
            from gi.repository import GLib

            GLib.idle_add(self._window.present)
            return

        self._build_window()
        if self._window is not None:
            from gi.repository import GLib

            GLib.idle_add(self._window.present)

    def _build_window(self) -> None:
        """Build the settings window with all pages."""
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk

        self._window = Adw.PreferencesWindow(
            title="LinuxWhispr Settings",
            default_width=700,
            default_height=600,
        )
        self._window.connect("close-request", self._on_close)

        # General page
        self._window.add(self._build_general_page())

        # Audio page
        self._window.add(self._build_audio_page())

        # Transcription page
        self._window.add(self._build_transcription_page())

        # AI page
        self._window.add(self._build_ai_page())

        # Dictionary page
        self._window.add(self._build_dictionary_page())

        # History page
        self._window.add(self._build_history_page())

    def _build_general_page(self) -> object:
        """Build the General settings page."""
        from gi.repository import Adw, Gtk

        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")

        # Hotkeys group
        hotkey_group = Adw.PreferencesGroup(title="Hotkeys")

        dictation_row = Adw.EntryRow(title="Dictation Hotkey")
        dictation_row.set_text(self._config.hotkey.dictation)
        dictation_row.connect(
            "changed", lambda r: self._update_config("hotkey", "dictation", r.get_text())
        )
        hotkey_group.add(dictation_row)

        command_row = Adw.EntryRow(title="Command Mode Hotkey")
        command_row.set_text(self._config.hotkey.command)
        command_row.connect(
            "changed", lambda r: self._update_config("hotkey", "command", r.get_text())
        )
        hotkey_group.add(command_row)

        # Activation mode
        mode_row = Adw.ComboRow(title="Activation Mode", subtitle="How the dictation hotkey works")
        mode_model = Gtk.StringList.new(["Toggle", "Push-to-Talk"])
        mode_row.set_model(mode_model)
        mode_row.set_selected(0 if self._config.hotkey.mode == "toggle" else 1)
        mode_row.connect(
            "notify::selected",
            lambda r, _: self._update_config(
                "hotkey", "mode", "toggle" if r.get_selected() == 0 else "push-to-talk"
            ),
        )
        hotkey_group.add(mode_row)

        page.add(hotkey_group)

        # Startup group
        startup_group = Adw.PreferencesGroup(title="Startup")

        autostart_row = Adw.SwitchRow(
            title="Start on Login", subtitle="Launch LinuxWhispr automatically"
        )
        autostart_row.set_active(self._config.autostart)
        autostart_row.connect("notify::active", lambda r, _: self._toggle_autostart(r.get_active()))
        startup_group.add(autostart_row)

        page.add(startup_group)
        return page

    def _build_audio_page(self) -> object:
        """Build the Audio settings page."""
        from gi.repository import Adw, Gtk

        page = Adw.PreferencesPage(title="Audio", icon_name="audio-input-microphone-symbolic")

        group = Adw.PreferencesGroup(title="Recording")

        # Silence duration
        silence_row = Adw.SpinRow.new_with_range(0.5, 10.0, 0.1)
        silence_row.set_title("Silence Duration (seconds)")
        silence_row.set_subtitle("Auto-stop after this much silence")
        silence_row.set_value(self._config.audio.silence_duration)
        silence_row.connect(
            "notify::value",
            lambda r, _: self._update_config("audio", "silence_duration", r.get_value()),
        )
        group.add(silence_row)

        # VAD threshold
        threshold_row = Adw.SpinRow.new_with_range(0.1, 0.9, 0.05)
        threshold_row.set_title("VAD Sensitivity")
        threshold_row.set_subtitle("Lower = more sensitive to speech")
        threshold_row.set_value(self._config.audio.silence_threshold)
        threshold_row.connect(
            "notify::value",
            lambda r, _: self._update_config("audio", "silence_threshold", r.get_value()),
        )
        group.add(threshold_row)

        # Whisper mode
        whisper_row = Adw.SwitchRow(
            title="Whisper Mode", subtitle="Boost microphone gain for quiet environments"
        )
        whisper_row.set_active(self._config.audio.whisper_mode)
        whisper_row.connect(
            "notify::active",
            lambda r, _: self._update_config("audio", "whisper_mode", r.get_active()),
        )
        group.add(whisper_row)

        page.add(group)
        return page

    def _build_transcription_page(self) -> object:
        """Build the Transcription settings page."""
        from gi.repository import Adw, Gtk

        page = Adw.PreferencesPage(title="Transcription", icon_name="document-edit-symbolic")

        group = Adw.PreferencesGroup(title="Speech-to-Text Engine")

        # Backend selection
        backend_row = Adw.ComboRow(title="STT Backend")
        backend_values = ["faster-whisper", "whisper-cpp", "openai", "groq"]
        backend_row.set_model(
            Gtk.StringList.new(
                [
                    "faster-whisper (Local)",
                    "whisper.cpp (AMD / Vulkan)",
                    "OpenAI Whisper API",
                    "Groq Whisper API",
                ]
            )
        )
        try:
            backend_index = backend_values.index(self._config.stt.backend)
        except ValueError:
            backend_index = 0
        backend_row.set_selected(backend_index)
        group.add(backend_row)

        # Model and device choices depend on the selected local backend.
        from linux_whispr.constants import (
            SUPPORTED_WHISPER_CPP_MODELS,
            SUPPORTED_WHISPER_MODELS,
        )

        model_row = Adw.ComboRow(
            title="Whisper Model",
            subtitle="Larger models are more accurate but slower",
        )
        device_row = Adw.ComboRow(title="Compute Device")
        model_values: list[str] = []
        device_values: list[str] = []
        updating_transcription = False

        def selected_value(row: object, values: list[str]) -> str | None:
            selected = row.get_selected()  # type: ignore[union-attr]
            if 0 <= selected < len(values):
                return values[selected]
            return None

        def set_model_choices(backend: str) -> None:
            nonlocal model_values
            model_values = list(
                SUPPORTED_WHISPER_CPP_MODELS
                if backend == "whisper-cpp"
                else SUPPORTED_WHISPER_MODELS
            )
            model_row.set_model(Gtk.StringList.new(model_values))
            try:
                model_index = model_values.index(self._config.stt.model)
            except ValueError:
                model_index = 0
            model_row.set_selected(model_index)
            model_row.set_visible(backend in {"faster-whisper", "whisper-cpp"})

        def set_device_choices(backend: str) -> None:
            nonlocal device_values
            if backend == "whisper-cpp":
                device_values = ["vulkan", "cpu"]
                device_labels = ["Vulkan (AMD GPU)", "CPU"]
            else:
                device_values = ["auto", "cpu", "cuda"]
                device_labels = ["Auto", "CPU", "CUDA (GPU)"]
            device_row.set_model(Gtk.StringList.new(device_labels))
            try:
                device_index = device_values.index(self._config.stt.device)
            except ValueError:
                device_index = 0
            device_row.set_selected(device_index)
            device_row.set_visible(backend in {"faster-whisper", "whisper-cpp"})

        selected_backend = backend_values[backend_index]
        set_model_choices(selected_backend)
        set_device_choices(selected_backend)

        def on_backend_changed(row: object, _param: object) -> None:
            nonlocal updating_transcription
            backend = selected_value(row, backend_values)
            if backend is None or updating_transcription:
                return
            updating_transcription = True
            try:
                self._config.stt.backend = backend
                if backend == "whisper-cpp":
                    self._config.stt.device = "vulkan"
                    self._config.stt.compute_type = "auto"
                    if self._config.stt.model not in SUPPORTED_WHISPER_CPP_MODELS:
                        self._config.stt.model = "base"
                elif backend == "faster-whisper" and self._config.stt.device == "vulkan":
                    self._config.stt.device = "auto"
                set_model_choices(backend)
                set_device_choices(backend)
                self._config.save()
            finally:
                updating_transcription = False

        def on_model_changed(row: object, _param: object) -> None:
            if updating_transcription:
                return
            model = selected_value(row, model_values)
            if model is not None:
                self._update_config("stt", "model", model)

        def on_device_changed(row: object, _param: object) -> None:
            if updating_transcription:
                return
            device = selected_value(row, device_values)
            if device is not None:
                self._update_config("stt", "device", device)

        backend_row.connect("notify::selected", on_backend_changed)
        model_row.connect("notify::selected", on_model_changed)
        device_row.connect("notify::selected", on_device_changed)
        group.add(model_row)
        group.add(device_row)

        page.add(group)
        return page

    def _build_ai_page(self) -> object:
        """Build the AI Refinement settings page."""
        from gi.repository import Adw, Gtk

        page = Adw.PreferencesPage(title="AI Refinement", icon_name="starred-symbolic")

        group = Adw.PreferencesGroup(title="Text Refinement")

        # Gtk.Switch inside an ActionRow remains compatible with libadwaita 1.1.
        enable_row = Adw.ActionRow(
            title="Enable AI Refinement",
            subtitle="Clean up filler words, fix grammar, format by context",
        )
        enable_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        enable_switch.set_active(self._config.ai.enabled)
        enable_row.add_suffix(enable_switch)
        enable_row.set_activatable_widget(enable_switch)
        enable_switch.connect(
            "notify::active", lambda switch, _: self._update_config("ai", "enabled", switch.get_active())
        )
        group.add(enable_row)

        backend_values = ["none", "openai", "groq", "anthropic", "local", "ollama"]
        backend_row = Adw.ComboRow(title="LLM Backend")
        backend_row.set_model(
            Gtk.StringList.new(
                [
                    "None",
                    "OpenAI",
                    "Groq",
                    "Anthropic",
                    "Local (llama.cpp)",
                    "Local (Ollama)",
                ]
            )
        )
        try:
            backend_index = backend_values.index(self._config.ai.backend)
        except ValueError:
            backend_index = 0
        backend_row.set_selected(backend_index)
        group.add(backend_row)

        model_row = Adw.ActionRow(
            title="Model",
            subtitle="Choose the model for this backend",
        )
        model_entry = Gtk.Entry()
        model_entry.set_hexpand(True)
        model_entry.set_text(self._config.ai.model)
        model_row.add_suffix(model_entry)
        group.add(model_row)
        page.add(group)

        ollama_group = Adw.PreferencesGroup(
            title="Ollama Models",
            description="Uses only the local Ollama service at http://127.0.0.1:11434.",
        )
        ollama_status_row = Adw.ActionRow(
            title="Checking local Ollama service…",
            subtitle="Only installed text-completion models can be selected.",
        )
        ollama_group.add(ollama_status_row)

        ollama_model_row = Adw.ComboRow(
            title="Installed local text model",
            subtitle="Select an eligible model installed on this computer",
        )
        ollama_model_row.set_model(Gtk.StringList.new(["Checking installed models…"]))
        ollama_model_row.set_sensitive(False)
        ollama_group.add(ollama_model_row)

        refresh_row = Adw.ActionRow(
            title="Refresh installed models",
            subtitle="Checks the local Ollama service without downloading anything.",
        )
        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.set_valign(Gtk.Align.CENTER)
        refresh_row.add_suffix(refresh_button)
        refresh_row.set_activatable_widget(refresh_button)
        ollama_group.add(refresh_row)
        page.add(ollama_group)

        recommendations_group = Adw.PreferencesGroup(
            title="Recommended models",
            description="Recommendations are practical multilingual choices, not benchmark rankings.",
        )
        recommendations_status_row = Adw.ActionRow(
            title="Loading recommendations…",
            subtitle="Recommendations remain visible even when the local service is offline.",
        )
        recommendations_group.add(recommendations_status_row)
        recommended_rows: dict[str, object] = {}
        page.add(recommendations_group)

        # Gtk.Entry inside an ActionRow remains compatible with libadwaita 1.1.
        prompt_group = Adw.PreferencesGroup(title="Custom System Prompt")
        prompt_row = Adw.ActionRow(title="Override default refinement prompt")
        prompt_entry = Gtk.Entry()
        prompt_entry.set_hexpand(True)
        prompt_entry.set_text(self._config.ai.custom_prompt)
        prompt_row.add_suffix(prompt_entry)
        prompt_entry.connect(
            "changed",
            lambda entry: self._update_config("ai", "custom_prompt", entry.get_text()),
        )
        prompt_group.add(prompt_row)
        page.add(prompt_group)

        self._ollama_ui = {
            "group": ollama_group,
            "recommendations_group": recommendations_group,
            "status_row": ollama_status_row,
            "model_row": ollama_model_row,
            "refresh_button": refresh_button,
            "recommendations": recommended_rows,
            "recommendations_status_row": recommendations_status_row,
            "model_entry": model_entry,
            "model_action_row": model_row,
        }

        def selected_value(row: object, values: list[str]) -> str | None:
            selected = row.get_selected()  # type: ignore[union-attr]
            if 0 <= selected < len(values):
                return values[selected]
            return None

        def update_backend_visibility(backend: str) -> None:
            is_ollama = backend == "ollama"
            ollama_group.set_visible(is_ollama)
            recommendations_group.set_visible(is_ollama)
            model_row.set_visible(not is_ollama and backend != "none")

        def on_backend_changed(row: object, _param: object) -> None:
            backend = selected_value(row, backend_values)
            if backend is None or backend == self._config.ai.backend:
                return

            previous_backend = self._config.ai.backend
            self._ai_models_by_backend[previous_backend] = self._config.ai.model
            self._config.ai.backend = backend
            self._config.ai.model = self._ai_models_by_backend.get(backend, "")
            model_entry.set_text(self._config.ai.model)
            self._config.save()
            update_backend_visibility(backend)
            if backend == "ollama":
                self._refresh_ollama_model_catalog()

        def on_model_changed(entry: object) -> None:
            if self._config.ai.backend == "ollama":
                return
            model = entry.get_text()  # type: ignore[union-attr]
            self._ai_models_by_backend[self._config.ai.backend] = model
            self._update_config("ai", "model", model)

        def on_ollama_model_changed(row: object, _param: object) -> None:
            if self._ollama_model_updating or self._config.ai.backend != "ollama":
                return
            model_names = self._ollama_ui.get("model_names", []) if self._ollama_ui else []
            model = selected_value(row, model_names)  # type: ignore[arg-type]
            if model is not None:
                self._ai_models_by_backend["ollama"] = model
                self._update_config("ai", "model", model)

        backend_row.connect("notify::selected", on_backend_changed)
        model_entry.connect("changed", on_model_changed)
        ollama_model_row.connect("notify::selected", on_ollama_model_changed)
        refresh_button.connect("clicked", lambda _button: self._refresh_ollama_model_catalog())

        update_backend_visibility(self._config.ai.backend)
        if self._config.ai.backend == "ollama":
            self._refresh_ollama_model_catalog()
        return page

    def _refresh_ollama_model_catalog(self) -> None:
        """Discover installed Ollama models without blocking the GTK main loop."""
        if self._window is None or self._config.ai.backend != "ollama" or self._ollama_ui is None:
            return

        self._ollama_catalog_generation += 1
        generation = self._ollama_catalog_generation
        self._ollama_catalog_loading = True
        status_row = self._ollama_ui["status_row"]
        model_row = self._ollama_ui["model_row"]
        refresh_button = self._ollama_ui["refresh_button"]
        status_row.set_title("Checking local Ollama service…")  # type: ignore[union-attr]
        status_row.set_subtitle("Only installed text-completion models can be selected.")  # type: ignore[union-attr]
        model_row.set_sensitive(False)  # type: ignore[union-attr]
        refresh_button.set_sensitive(False)  # type: ignore[union-attr]

        from gi.repository import GLib

        def discover() -> None:
            catalog: dict[str, object] | None = None
            error: str | None = None
            try:
                from linux_whispr.ai.ollama import get_ollama_model_catalog

                catalog = get_ollama_model_catalog()
            except Exception as exc:
                logger.warning("Could not discover local Ollama models: %s", exc)
                error = str(exc)
            GLib.idle_add(self._apply_ollama_model_catalog, generation, catalog, error)

        threading.Thread(
            target=discover,
            name="linux-whispr-ollama-discovery",
            daemon=True,
        ).start()

    def _apply_ollama_model_catalog(
        self,
        generation: int,
        catalog: dict[str, object] | None,
        discovery_error: str | None,
    ) -> bool:
        """Apply a discovery result only while its owning settings view is current."""
        if (
            generation != self._ollama_catalog_generation
            or self._window is None
            or self._config.ai.backend != "ollama"
            or self._ollama_ui is None
        ):
            return False

        self._ollama_catalog_loading = False
        status_row = self._ollama_ui["status_row"]
        model_row = self._ollama_ui["model_row"]
        refresh_button = self._ollama_ui["refresh_button"]
        refresh_button.set_sensitive(True)  # type: ignore[union-attr]

        if catalog is None:
            status_row.set_title("Ollama is unavailable")  # type: ignore[union-attr]
            status_row.set_subtitle(discovery_error or "Could not contact the local Ollama service.")  # type: ignore[union-attr]
            self._set_ollama_model_choices([], False)
            return False

        available = catalog.get("available") is True
        error = catalog.get("error")
        warnings = catalog.get("warnings")
        models = catalog.get("models")
        model_records = models if isinstance(models, list) else []
        names = [
            record.get("name")
            for record in model_records
            if isinstance(record, dict) and isinstance(record.get("name"), str)
        ]
        names = [name for name in names if isinstance(name, str)]

        if not available:
            detail = error if isinstance(error, str) and error else "Could not contact the local Ollama service."
            status_row.set_title("Ollama is unavailable")  # type: ignore[union-attr]
            status_row.set_subtitle(detail)  # type: ignore[union-attr]
            self._set_ollama_model_choices([], False)
        elif not names:
            detail = "No eligible local text models are installed."
            if isinstance(warnings, list) and warnings:
                detail = f"{detail} {warnings[0]}"
            status_row.set_title("No eligible Ollama models found")  # type: ignore[union-attr]
            status_row.set_subtitle(detail)  # type: ignore[union-attr]
            self._set_ollama_model_choices([], False)
        else:
            detail = "Select an installed local text-completion model."
            if isinstance(warnings, list) and warnings:
                detail = f"{detail} {warnings[0]}"
            status_row.set_title("Local Ollama service is available")  # type: ignore[union-attr]
            status_row.set_subtitle(detail)  # type: ignore[union-attr]
            self._set_ollama_model_choices(names, True)

        recommendations = catalog.get("recommended")
        if isinstance(recommendations, list):
            self._update_ollama_recommendations(recommendations, names)
        return False

    def _set_ollama_model_choices(self, names: list[str], available: bool) -> None:
        """Render model choices without changing the configured model implicitly."""
        if self._ollama_ui is None:
            return

        from gi.repository import Gtk

        configured_model = self._config.ai.model
        values = list(names)
        labels = list(names)
        if configured_model and configured_model not in values:
            values.insert(0, configured_model)
            labels.insert(0, f"{configured_model} (configured, unavailable)")
        elif not configured_model and names:
            values.insert(0, "")
            labels.insert(0, "Select an installed model")
        if not labels:
            labels = ["No eligible installed models"]

        model_row = self._ollama_ui["model_row"]
        self._ollama_model_updating = True
        try:
            model_row.set_model(Gtk.StringList.new(labels))  # type: ignore[union-attr]
            if configured_model and configured_model in values:
                model_row.set_selected(values.index(configured_model))  # type: ignore[union-attr]
            else:
                model_row.set_selected(0)  # type: ignore[union-attr]
            model_row.set_sensitive(available and bool(names))  # type: ignore[union-attr]
            self._ollama_ui["model_names"] = values
        finally:
            self._ollama_model_updating = False

    def _update_ollama_recommendations(
        self,
        recommendations: list[object],
        installed_names: list[str],
    ) -> None:
        """Render the catalog's researched recommendations and local availability."""
        if self._ollama_ui is None:
            return
        rows = self._ollama_ui["recommendations"]
        group = self._ollama_ui["recommendations_group"]
        status_row = self._ollama_ui["recommendations_status_row"]
        if not isinstance(rows, dict):
            return

        status_row.set_visible(False)  # type: ignore[union-attr]
        for recommendation in recommendations:
            if not isinstance(recommendation, dict):
                continue
            name = recommendation.get("name")
            if not isinstance(name, str):
                continue
            row = rows.get(name)
            if row is None:
                from gi.repository import Adw

                row = Adw.ActionRow()
                set_subtitle_lines = getattr(row, "set_subtitle_lines", None)
                if callable(set_subtitle_lines):
                    set_subtitle_lines(0)
                group.add(row)  # type: ignore[union-attr]
                rows[name] = row
            description = recommendation.get("description")
            size_gb = recommendation.get("size_gb")
            source_url = recommendation.get("source_url")
            installed = recommendation.get("installed") is True or name in installed_names
            availability = (
                "Installed locally."
                if installed
                else f"Not installed. Install manually: ollama pull {name}"
            )
            size = f" Approx. {size_gb:g} GB download." if isinstance(size_gb, (int, float)) else ""
            source = f" Details: {source_url}" if isinstance(source_url, str) else ""
            row.set_title(f"{name} — {'Installed' if installed else 'Not installed'}")  # type: ignore[union-attr]
            row.set_subtitle(  # type: ignore[union-attr]
                f"{description if isinstance(description, str) else ''}{size} {availability}{source}"
            )

    def _build_dictionary_page(self) -> object:
        """Build the Dictionary & Snippets settings page."""
        from gi.repository import Adw, Gtk

        page = Adw.PreferencesPage(title="Dictionary", icon_name="accessories-dictionary-symbolic")

        # Custom words group
        dict_group = Adw.PreferencesGroup(
            title="Custom Words",
            description="Words added here improve recognition accuracy",
        )

        if self._dictionary is not None:
            for entry in self._dictionary.entries:
                row = Adw.ActionRow(title=entry.word, subtitle=f"{entry.source} · {entry.category}")
                dict_group.add(row)

        # Add word button
        add_row = Adw.EntryRow(title="Add new word")
        add_row.connect("apply", self._on_add_dictionary_word)
        dict_group.add(add_row)

        page.add(dict_group)

        # Snippets group
        snippet_group = Adw.PreferencesGroup(
            title="Voice Snippets",
            description="Trigger phrases that expand to longer text",
        )

        if self._snippets is not None:
            for snippet in self._snippets.snippets:
                row = Adw.ActionRow(title=snippet.trigger, subtitle=snippet.expansion)
                snippet_group.add(row)

        page.add(snippet_group)

        # Learned corrections group
        corrections_group = Adw.PreferencesGroup(
            title="Learned Corrections",
            description="Automatically learned from your edits",
        )

        if self._dictionary is not None:
            for corr in self._dictionary.corrections:
                row = Adw.ActionRow(
                    title=f"{corr.heard} → {corr.corrected}",
                    subtitle=f"Seen {corr.count} time(s)",
                )
                corrections_group.add(row)

        page.add(corrections_group)
        return page

    def _build_history_page(self) -> object:
        """Build the History settings page."""
        from gi.repository import Adw, Gtk

        page = Adw.PreferencesPage(title="History", icon_name="document-open-recent-symbolic")

        group = Adw.PreferencesGroup(title="Transcription History")

        # Retention
        retention_row = Adw.SpinRow.new_with_range(1, 365, 1)
        retention_row.set_title("Retention (days)")
        retention_row.set_subtitle("Auto-delete entries older than this")
        retention_row.set_value(self._config.history.retention_days)
        group.add(retention_row)

        # Show recent entries
        if self._history is not None:
            recent = self._history.get_recent(limit=10)
            for entry in recent:
                text_preview = entry.raw_text[:80] + ("..." if len(entry.raw_text) > 80 else "")
                row = Adw.ActionRow(
                    title=text_preview,
                    subtitle=f"{entry.timestamp[:16]} · {entry.word_count} words · {entry.app_context or 'unknown'}",
                )
                group.add(row)

        page.add(group)

        # Actions group
        actions_group = Adw.PreferencesGroup(title="Actions")

        clear_button = Gtk.Button(label="Clear All History")
        clear_button.add_css_class("destructive-action")
        clear_button.connect("clicked", self._on_clear_history)
        actions_group.add(clear_button)

        page.add(actions_group)
        return page

    def _update_config(self, section: str, key: str, value: object) -> None:
        """Update a config value and save."""
        sub = getattr(self._config, section)
        setattr(sub, key, value)
        self._config.save()
        logger.debug("Config updated: %s.%s = %s", section, key, value)

    def _toggle_autostart(self, enabled: bool) -> None:
        """Toggle autostart and update config."""
        from linux_whispr.platform.autostart import disable_autostart, enable_autostart

        if enabled:
            enable_autostart()
        else:
            disable_autostart()
        self._config.autostart = enabled
        self._config.save()

    def _on_add_dictionary_word(self, row: object) -> None:
        """Handle adding a new dictionary word."""
        word = row.get_text().strip()  # type: ignore[union-attr]
        if word and self._dictionary is not None:
            self._dictionary.add_word(word)
            self._dictionary.save()
            row.set_text("")  # type: ignore[union-attr]
            logger.info("Added dictionary word: %s", word)

    def _on_clear_history(self, button: object) -> None:
        """Handle clear all history button."""
        if self._history is not None:
            count = self._history.clear()
            logger.info("Cleared %d history entries", count)

    def _on_close(self, window: object) -> bool:
        """Handle close and invalidate outstanding background UI updates."""
        self._ollama_catalog_generation += 1
        self._ollama_catalog_loading = False
        self._ollama_ui = None
        self._window = None
        return False  # Allow default close behavior
