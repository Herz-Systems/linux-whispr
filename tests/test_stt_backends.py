"""Tests for STT backend interfaces."""

from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from linux_whispr.stt.base import STTBackend, TranscriptionResult
from linux_whispr.stt.faster_whisper import FasterWhisperBackend
from linux_whispr.stt.whisper_cpp import WhisperCppBackend


class TestSTTBackendInterface:
    def test_transcription_result_defaults(self) -> None:
        result = TranscriptionResult(text="hello world")
        assert result.text == "hello world"
        assert result.language is None
        assert result.confidence == 0.0
        assert result.duration == 0.0

    def test_transcription_result_with_all_fields(self) -> None:
        result = TranscriptionResult(
            text="hello",
            language="en",
            confidence=0.95,
            duration=2.5,
        )
        assert result.language == "en"
        assert result.confidence == 0.95
        assert result.duration == 2.5


class TestFasterWhisperBackend:
    def test_initial_state(self) -> None:
        backend = FasterWhisperBackend(model_name="base")
        assert not backend.is_loaded

    def test_unload_when_not_loaded(self) -> None:
        backend = FasterWhisperBackend(model_name="base")
        backend.unload()  # Should not raise
        assert not backend.is_loaded

    def test_transcribe_without_load_raises(self) -> None:
        backend = FasterWhisperBackend(model_name="base")
        # Create minimal WAV
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(np.zeros(16000, dtype=np.int16).tobytes())

        try:
            backend.transcribe(buf.getvalue())
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "not loaded" in str(e).lower()


def _wav_bytes(
    samples: np.ndarray,
    *,
    sample_rate: int = 16_000,
    channels: int = 1,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples.astype("<i2").tobytes())
    return buffer.getvalue()


class _Segment:
    def __init__(self, text: str, probability: float) -> None:
        self.text = text
        self.probability = probability


class _CapturingWhisperCppModel:
    def __init__(self) -> None:
        self.calls: list[tuple[np.ndarray, dict[str, object]]] = []

    def transcribe(self, audio: np.ndarray, **kwargs: object) -> list[_Segment]:
        self.calls.append((audio, kwargs))
        return [_Segment(" first", 0.4), _Segment(" second", 0.8)]


class TestWhisperCppBackend:
    def test_initial_state_and_unload(self) -> None:
        backend = WhisperCppBackend(model_name="base")
        assert not backend.is_loaded
        backend.unload()
        assert not backend.is_loaded

    def test_rejects_invalid_device(self) -> None:
        with pytest.raises(ValueError, match="whisper.cpp device"):
            WhisperCppBackend(device="cuda")

    def test_transcribe_without_load_raises(self) -> None:
        backend = WhisperCppBackend(model_name="base")
        with pytest.raises(RuntimeError, match="not loaded"):
            backend.transcribe(_wav_bytes(np.zeros(1, dtype=np.int16)))

    def test_decodes_stereo_and_resamples_to_contiguous_mono_16khz(self) -> None:
        frame_count = 8_000
        left = np.full(frame_count, 16_384, dtype=np.int16)
        right = np.full(frame_count, -16_384, dtype=np.int16)
        stereo = np.column_stack((left, right)).reshape(-1)

        audio, duration = WhisperCppBackend._decode_wav(
            _wav_bytes(stereo, sample_rate=8_000, channels=2)
        )

        assert duration == 1.0
        assert audio.dtype == np.float32
        assert audio.flags.c_contiguous
        assert audio.shape == (16_000,)
        assert np.allclose(audio, 0.0)

    def test_rejects_empty_or_invalid_wav(self) -> None:
        with pytest.raises(ValueError, match="valid WAV"):
            WhisperCppBackend._decode_wav(b"not a WAV")

        with pytest.raises(ValueError, match="contains no frames"):
            WhisperCppBackend._decode_wav(_wav_bytes(np.array([], dtype=np.int16)))

    def test_clears_language_and_prompt_between_transcriptions(self) -> None:
        backend = WhisperCppBackend(model_name="base")
        model = _CapturingWhisperCppModel()
        backend._model = model
        audio = _wav_bytes(np.zeros(16_000, dtype=np.int16))

        first = backend.transcribe(audio, language="de", initial_prompt="Fachwort")
        second = backend.transcribe(audio, language="auto", initial_prompt=None)

        assert first.text == "first second"
        assert first.language == "de"
        assert first.confidence == pytest.approx(0.6)
        assert first.duration == 1.0
        assert model.calls[0][1] == {
            "language": "de",
            "initial_prompt": "Fachwort",
            "detect_language": False,
        }
        assert second.language is None
        assert model.calls[1][1] == {
            "language": "",
            "initial_prompt": "",
            "detect_language": False,
        }
