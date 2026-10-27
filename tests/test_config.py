"""Tests for configuration loading and saving."""

from __future__ import annotations

from pathlib import Path

from linux_whispr.config import AppConfig


class TestAppConfig:
    def test_default_config(self) -> None:
        config = AppConfig()
        assert config.stt.backend == "faster-whisper"
        assert config.stt.model == "base"
        assert config.hotkey.dictation == "F12"
        assert config.hotkey.mode == "toggle"
        assert config.ai.enabled is False
        assert config.first_run is True

    def test_save_and_load(self, tmp_path: Path) -> None:
        config = AppConfig()
        config.stt.model = "large-v3-turbo"
        config.hotkey.dictation = "F8"
        config.first_run = False

        config_path = tmp_path / "config.toml"
        config.save(config_path)

        loaded = AppConfig.load(config_path)
        assert loaded.stt.model == "large-v3-turbo"
        assert loaded.hotkey.dictation == "F8"
        assert loaded.first_run is False

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        config = AppConfig.load(tmp_path / "nonexistent.toml")
        assert config.stt.backend == "faster-whisper"
        assert config.first_run is True

    def test_load_legacy_config_without_first_run_marker_is_not_first_run(self, tmp_path: Path) -> None:
        config_path = tmp_path / "legacy.toml"
        config_path.write_text('[stt]\nmodel = "small"\n')

        loaded = AppConfig.load(config_path)

        assert loaded.stt.model == "small"
        assert loaded.first_run is False

    def test_load_explicit_first_run_marker_is_preserved(self, tmp_path: Path) -> None:
        config_path = tmp_path / "new.toml"
        config_path.write_text("first_run = true\n")

        assert AppConfig.load(config_path).first_run is True

    def test_partial_config_preserves_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "partial.toml"
        config_path.write_text('[stt]\nmodel = "small"\n')

        loaded = AppConfig.load(config_path)
        assert loaded.stt.model == "small"
        assert loaded.stt.backend == "faster-whisper"  # default preserved
        assert loaded.hotkey.dictation == "F12"  # default preserved

    def test_whisper_cpp_settings_round_trip(self, tmp_path: Path) -> None:
        config = AppConfig()
        config.stt.backend = "whisper-cpp"
        config.stt.model = "small"
        config.stt.device = "vulkan"
        config.stt.compute_type = "auto"

        config_path = tmp_path / "config.toml"
        config.save(config_path)

        loaded = AppConfig.load(config_path)
        assert loaded.stt.backend == "whisper-cpp"
        assert loaded.stt.model == "small"
        assert loaded.stt.device == "vulkan"
        assert loaded.stt.compute_type == "auto"

    def test_preload_settings_round_trip_without_changing_audio_or_model(
        self, tmp_path: Path
    ) -> None:
        config = AppConfig()
        config.stt.model = "large-v3-turbo"
        config.audio.silence_duration = 2.0
        config.preload_models = False
        config.ai.keep_alive_minutes = 30

        config_path = tmp_path / "config.toml"
        config.save(config_path)

        loaded = AppConfig.load(config_path)

        assert loaded.preload_models is False
        assert loaded.ai.keep_alive_minutes == 30
        assert loaded.stt.model == "large-v3-turbo"
        assert loaded.audio.silence_duration == 2.0

    def test_invalid_preload_values_keep_defaults_and_other_toml_settings(
        self, tmp_path: Path
    ) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            'preload_models = "yes"\n'
            "[audio]\n"
            "silence_duration = 2.0\n"
            "[stt]\n"
            'model = "small"\n'
            "[ai]\n"
            "keep_alive_minutes = 10\n"
        )

        loaded = AppConfig.load(config_path)

        assert loaded.preload_models is AppConfig().preload_models
        assert loaded.ai.keep_alive_minutes == AppConfig().ai.keep_alive_minutes
        assert loaded.stt.model == "small"
        assert loaded.audio.silence_duration == 2.0
