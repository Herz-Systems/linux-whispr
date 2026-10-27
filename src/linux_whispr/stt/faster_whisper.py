"""faster-whisper local STT backend (CTranslate2)."""

from __future__ import annotations

import io
import logging
import wave
from pathlib import Path

from linux_whispr.constants import DEFAULT_WHISPER_MODEL, MODELS_DIR
from linux_whispr.stt.base import STTBackend, TranscriptionResult

logger = logging.getLogger(__name__)


_REQUIRED_MODEL_FILES = ("config.json", "model.bin", "tokenizer.json")


def _has_complete_local_model(path: Path) -> bool:
    """Return whether a directory can load without native fallback downloads."""
    return (
        path.is_dir()
        and all(
            (artifact := path / name).is_file() and artifact.stat().st_size > 0
            for name in _REQUIRED_MODEL_FILES
        )
        and any(
            artifact.is_file() and artifact.stat().st_size > 0
            for artifact in path.glob("vocabulary.*")
        )
    )


def _resolve_cached_model_path(model_name: str, cached_path: Path) -> Path:
    """Resolve a Hugging Face cache root to its locally referenced snapshot."""
    if _has_complete_local_model(cached_path):
        return cached_path

    if not (cached_path / "snapshots").is_dir():
        raise RuntimeError(
            f"faster-whisper model '{model_name}' is not completely cached locally"
        )

    from faster_whisper.utils import download_model

    try:
        resolved_path = Path(
            download_model(
                model_name,
                cache_dir=str(MODELS_DIR),
                local_files_only=True,
            )
        )
    except Exception as error:
        raise RuntimeError(
            f"faster-whisper model '{model_name}' is not completely cached locally"
        ) from error

    if not _has_complete_local_model(resolved_path):
        raise RuntimeError(
            f"faster-whisper model '{model_name}' is not completely cached locally"
        )
    return resolved_path


class FasterWhisperBackend(STTBackend):
    """STT backend using faster-whisper (CTranslate2-optimized Whisper)."""

    def __init__(
        self,
        model_name: str = DEFAULT_WHISPER_MODEL,
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._model: object | None = None

    def load(self, *, local_files_only: bool = False) -> None:
        """Load the Whisper model, optionally from an existing local cache only."""

        # Resolve device
        device = self._device
        if device == "auto":
            device = self._detect_device()

        # Resolve compute type
        compute_type = self._compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        model_source: str = self._model_name
        kwargs: dict[str, object] = {"download_root": str(MODELS_DIR)}
        if local_files_only:
            from linux_whispr.stt.model_manager import ModelManager

            cached_path = ModelManager().get_model_path(
                self._model_name, backend="faster-whisper"
            )
            if cached_path is None or not cached_path.is_dir():
                raise RuntimeError(
                    f"faster-whisper model '{self._model_name}' is not cached locally"
                )
            # A Hugging Face cache root is not itself a CTranslate2 model
            # directory. Resolve its active cached revision before giving the
            # path to faster-whisper, which otherwise skips its resolver.
            model_source = str(_resolve_cached_model_path(self._model_name, cached_path))
            kwargs["local_files_only"] = True

        from faster_whisper import WhisperModel

        logger.info(
            "Loading faster-whisper model '%s' (device=%s, compute_type=%s)",
            self._model_name,
            device,
            compute_type,
        )

        self._model = WhisperModel(
            model_source,
            device=device,
            compute_type=compute_type,
            **kwargs,
        )
        logger.info("faster-whisper model loaded")

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe WAV audio to text."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Decode WAV to numpy array ourselves to bypass PyAV (avoids
        # UnicodeDecodeError when system locale is not UTF-8).
        import numpy as np

        audio_file = io.BytesIO(audio_bytes)
        with wave.open(audio_file, "rb") as wf:
            duration = wf.getnframes() / wf.getframerate()
            raw = wf.readframes(wf.getnframes())
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()

        # Convert raw PCM to float32 in [-1, 1]
        if sample_width == 2:
            audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 4:
            audio_np = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            audio_np = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

        # Resample to 16kHz if needed (faster-whisper expects 16000)
        if sample_rate != 16000:
            target_len = int(len(audio_np) * 16000 / sample_rate)
            audio_np = np.interp(
                np.linspace(0, len(audio_np), target_len, endpoint=False),
                np.arange(len(audio_np)),
                audio_np,
            ).astype(np.float32)

        logger.info(
            "Transcribing %.1fs of audio (language=%s, prompt=%s)",
            duration,
            language or "auto",
            "yes" if initial_prompt else "no",
        )

        # Treat "auto" as None so faster-whisper auto-detects language
        effective_language = None if language in (None, "auto") else language

        segments, info = self._model.transcribe(  # type: ignore[union-attr]
            audio_np,
            language=effective_language,
            initial_prompt=initial_prompt,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
            ),
        )

        # Collect all segment texts
        text_parts: list[str] = []
        for segment in segments:
            text_parts.append(segment.text)

        text = "".join(text_parts).strip()

        logger.info(
            "Transcription complete: lang=%s, prob=%.2f, text_len=%d",
            info.language,
            info.language_probability,
            len(text),
        )

        return TranscriptionResult(
            text=text,
            language=info.language,
            confidence=info.language_probability,
            duration=duration,
        )

    def unload(self) -> None:
        """Unload the model."""
        self._model = None
        logger.info("faster-whisper model unloaded")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @staticmethod
    def _detect_device() -> str:
        """Auto-detect the best device (CUDA or CPU)."""
        try:
            import torch

            if torch.cuda.is_available():
                logger.info("CUDA detected, using GPU")
                return "cuda"
        except ImportError:
            pass

        # Check for ctranslate2 CUDA support without torch
        try:
            import ctranslate2

            if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
                logger.info("CTranslate2 CUDA support detected, using GPU")
                return "cuda"
        except (ImportError, RuntimeError):
            pass

        logger.info("No GPU detected, using CPU")
        return "cpu"
