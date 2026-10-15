"""whisper.cpp local STT backend with explicit Vulkan verification."""

from __future__ import annotations

import io
import logging
import re
import threading
import wave
from pathlib import Path
from typing import Any

import numpy as np

from linux_whispr.constants import DEFAULT_WHISPER_MODEL
from linux_whispr.stt.base import STTBackend, TranscriptionResult

logger = logging.getLogger(__name__)

# pywhispercpp exposes one process-global native log callback. Model construction
# is therefore serialized so a concurrent initialization cannot steal its output.
_NATIVE_LOG_LOCK = threading.RLock()
_VULKAN_INIT = re.compile(
    r"whisper_backend_init_gpu:\s+using\s+[^\n]*vulkan[^\n]*backend", re.IGNORECASE
)


def _forward_native_log(level: int, text: str) -> None:
    """Forward whisper.cpp's process-global native log to this module logger."""
    log_level = {
        0: logging.NOTSET,
        1: logging.DEBUG,
        2: logging.INFO,
        3: logging.WARNING,
        4: logging.ERROR,
    }.get(level, logging.INFO)
    logger.log(log_level, text.rstrip())


class WhisperCppBackend(STTBackend):
    """STT backend using a source-built pywhispercpp Vulkan runtime."""

    def __init__(
        self,
        model_name: str = DEFAULT_WHISPER_MODEL,
        device: str = "vulkan",
    ) -> None:
        if device not in {"auto", "cpu", "vulkan"}:
            raise ValueError("whisper.cpp device must be 'auto', 'cpu', or 'vulkan'")

        self._model_name = model_name
        self._device = device
        self._model: Any | None = None

    def load(self) -> None:
        """Load a cached GGML model and prove requested Vulkan initialization."""
        if self._model is not None:
            return

        Model, native = self._import_runtime()
        model_path = self._download_model()
        gpu_requested = self._device in {"auto", "vulkan"}
        init_messages: list[str] = []

        def capture_native_log(_level: int, text: str) -> None:
            init_messages.append(text)
            _forward_native_log(_level, text)

        context_params = {"use_gpu": gpu_requested, "gpu_device": 0}
        with _NATIVE_LOG_LOCK:
            native.whisper_log_set(capture_native_log)
            try:
                model = Model(
                    str(model_path),
                    context_params=context_params,
                    print_progress=False,
                    print_realtime=False,
                    language="",
                    initial_prompt="",
                    redirect_whispercpp_logs_to=False,
                )
            finally:
                # The binding only offers a setter, not a getter. Restore our normal
                # forwarding callback instead of leaving capture state installed.
                native.whisper_log_set(_forward_native_log)

        if gpu_requested and not _VULKAN_INIT.search("".join(init_messages)):
            raise RuntimeError(
                "whisper.cpp did not initialize a Vulkan GPU backend. Install the AMD "
                "extra from source with GGML_VULKAN=1 and a working Mesa Vulkan driver, "
                "then select CPU explicitly if GPU acceleration is unavailable."
            )

        self._model = model
        logger.info("whisper.cpp model loaded (device=%s)", self._device)

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe PCM WAV bytes as contiguous 16 kHz mono float32 samples."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        audio, duration = self._decode_wav(audio_bytes)
        effective_language = "" if language in (None, "auto") else language
        # pywhispercpp mutates persistent decode params. Always pass both fields,
        # including empty automatic language and an empty prompt, so a prior call
        # cannot leak into this request.
        segments = self._model.transcribe(
            audio,
            language=effective_language,
            initial_prompt=initial_prompt or "",
            detect_language=False,
        )

        text_parts: list[str] = []
        probabilities: list[float] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                text_parts.append(text)
            probability = getattr(segment, "probability", float("nan"))
            if np.isfinite(probability):
                probabilities.append(float(probability))

        return TranscriptionResult(
            text=" ".join(text_parts),
            language=effective_language or None,
            confidence=float(np.mean(probabilities)) if probabilities else 0.0,
            duration=duration,
        )

    def unload(self) -> None:
        """Release the persistent Python model reference."""
        self._model = None
        logger.info("whisper.cpp model unloaded")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @staticmethod
    def _import_runtime() -> tuple[type[Any], Any]:
        try:
            from pywhispercpp.model import Model
            import _pywhispercpp as native
        except ImportError as exc:
            raise RuntimeError(
                "whisper.cpp support requires the optional AMD dependency. Install with "
                "`uv sync --extra amd` (or `uv run --extra amd linux-whispr`)."
            ) from exc

        if not callable(getattr(native, "whisper_log_set", None)):
            raise RuntimeError("pywhispercpp==1.5.1 with native logging support is required")
        return Model, native

    def _download_model(self) -> Path:
        from linux_whispr.stt.model_manager import ModelManager

        return ModelManager().download(self._model_name, backend="whisper-cpp")

    @staticmethod
    def _decode_wav(audio_bytes: bytes) -> tuple[np.ndarray, float]:
        """Decode uncompressed PCM WAV bytes, downmixing and resampling to 16 kHz."""
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
                if wav_file.getcomptype() != "NONE":
                    raise ValueError("WAV audio must use uncompressed PCM")
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                sample_rate = wav_file.getframerate()
                frame_count = wav_file.getnframes()
                raw = wav_file.readframes(frame_count)
        except (wave.Error, EOFError) as exc:
            raise ValueError("audio_bytes must contain a valid WAV file") from exc

        if channels < 1:
            raise ValueError("WAV audio must contain at least one channel")
        if sample_rate <= 0:
            raise ValueError("WAV audio must have a positive sample rate")
        if frame_count == 0:
            raise ValueError("WAV audio contains no frames")

        samples = WhisperCppBackend._pcm_to_float32(raw, sample_width)
        if samples.size != frame_count * channels:
            raise ValueError("WAV audio frame data is truncated")
        samples = samples.reshape(frame_count, channels)
        mono = np.mean(samples, axis=1, dtype=np.float32)

        if sample_rate != 16_000:
            target_frames = max(1, round(frame_count * 16_000 / sample_rate))
            positions = np.arange(target_frames, dtype=np.float64) * sample_rate / 16_000
            mono = np.interp(positions, np.arange(frame_count), mono).astype(np.float32)

        return np.ascontiguousarray(mono, dtype=np.float32), frame_count / sample_rate

    @staticmethod
    def _pcm_to_float32(raw: bytes, sample_width: int) -> np.ndarray:
        """Convert little-endian signed PCM samples to normalized float32."""
        if sample_width == 1:
            return (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        if sample_width == 2:
            return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if sample_width == 3:
            bytes_array = np.frombuffer(raw, dtype=np.uint8)
            if bytes_array.size % 3:
                raise ValueError("WAV audio has incomplete 24-bit samples")
            expanded = np.zeros((bytes_array.size // 3, 4), dtype=np.uint8)
            expanded[:, :3] = bytes_array.reshape(-1, 3)
            expanded[:, 3] = np.where(expanded[:, 2] & 0x80, 0xFF, 0)
            return expanded.view("<i4").reshape(-1).astype(np.float32) / 8_388_608.0
        if sample_width == 4:
            return np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2_147_483_648.0
        raise ValueError("WAV audio must use 8-, 16-, 24-, or 32-bit PCM samples")
