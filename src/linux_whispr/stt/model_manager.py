"""Download, list, and delete backend-scoped Whisper models."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from linux_whispr.constants import (
    MODELS_DIR,
    SUPPORTED_WHISPER_CPP_MODELS,
    SUPPORTED_WHISPER_MODELS,
)

logger = logging.getLogger(__name__)

FASTER_WHISPER_BACKEND = "faster-whisper"
WHISPER_CPP_BACKEND = "whisper-cpp"
SUPPORTED_MODEL_BACKENDS = (FASTER_WHISPER_BACKEND, WHISPER_CPP_BACKEND)
WHISPER_CPP_REPOSITORY = "ggerganov/whisper.cpp"

# Approximate faster-whisper model sizes in MB (for display purposes).
MODEL_SIZES: dict[str, int] = {
    "tiny": 75,
    "base": 150,
    "small": 500,
    "medium": 1500,
    "large-v3": 3100,
    "large-v3-turbo": 1600,
    "distil-large-v3": 1500,
}

# Official ggerganov/whisper.cpp GGML artifact sizes, rounded up to MiB.
WHISPER_CPP_MODEL_SIZES: dict[str, int] = {
    "tiny": 75,
    "base": 142,
    "small": 466,
    "medium": 1463,
    "large-v3": 2952,
    "large-v3-turbo": 1550,
}


@dataclass
class ModelInfo:
    """Information about a Whisper model."""

    name: str
    size_mb: int
    downloaded: bool
    path: Path | None = None


class ModelManager:
    """Manages separately cached faster-whisper and whisper.cpp models."""

    def __init__(self, models_dir: Path | None = None) -> None:
        self._models_dir = models_dir or MODELS_DIR

    def list_models(self, *, backend: str = FASTER_WHISPER_BACKEND) -> list[ModelInfo]:
        """List supported models and download status for one backend."""
        model_sizes = self._model_sizes(backend)
        return [
            ModelInfo(
                name=name,
                size_mb=model_sizes[name],
                downloaded=(path := self.get_model_path(name, backend=backend)) is not None,
                path=path,
            )
            for name in self._supported_models(backend)
        ]

    def is_downloaded(self, model_name: str, *, backend: str = FASTER_WHISPER_BACKEND) -> bool:
        """Check whether a supported backend-specific artifact is available."""
        return self.get_model_path(model_name, backend=backend) is not None

    def get_model_path(
        self, model_name: str, *, backend: str = FASTER_WHISPER_BACKEND
    ) -> Path | None:
        """Return an existing usable artifact path, or ``None`` when absent."""
        self._validate_model(model_name, backend)

        if backend == WHISPER_CPP_BACKEND:
            path = self._whisper_cpp_path(model_name)
            return path if self._is_usable_file(path) else None

        for candidate in self._faster_whisper_candidates(model_name):
            if self._is_usable_directory(candidate):
                return candidate
        return None

    def download(
        self,
        model_name: str,
        progress_callback: Callable[[float], None] | None = None,
        *,
        backend: str = FASTER_WHISPER_BACKEND,
    ) -> Path:
        """Download a supported model and return its actual local artifact path."""
        self._validate_model(model_name, backend)
        existing = self.get_model_path(model_name, backend=backend)
        if existing is not None:
            return existing

        if backend == WHISPER_CPP_BACKEND:
            return self._download_whisper_cpp(model_name, progress_callback)
        return self._download_faster_whisper(model_name, progress_callback)

    def delete(self, model_name: str, *, backend: str = FASTER_WHISPER_BACKEND) -> bool:
        """Delete a backend-specific downloaded model, if present."""
        path = self.get_model_path(model_name, backend=backend)
        if path is None:
            logger.warning("Model '%s' not found for backend '%s'", model_name, backend)
            return False

        if backend == WHISPER_CPP_BACKEND:
            path.unlink()
        else:
            shutil.rmtree(path)

        logger.info("Deleted model '%s' for backend '%s' at %s", model_name, backend, path)
        return True

    def get_disk_usage(self) -> int:
        """Get total disk usage of all downloaded model formats in bytes."""
        if not self._models_dir.exists():
            return 0
        return sum(path.stat().st_size for path in self._models_dir.rglob("*") if path.is_file())

    def _download_faster_whisper(
        self, model_name: str, progress_callback: Callable[[float], None] | None
    ) -> Path:
        """Download a CTranslate2 faster-whisper model using its existing loader."""
        self._models_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading faster-whisper model '%s'...", model_name)

        try:
            from faster_whisper import WhisperModel

            model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                download_root=str(self._models_dir),
            )
            del model
        except Exception:
            logger.exception("Failed to download faster-whisper model '%s'", model_name)
            raise

        path = self.get_model_path(model_name, backend=FASTER_WHISPER_BACKEND)
        if path is None:
            raise RuntimeError(
                f"faster-whisper reported a successful download for '{model_name}', "
                "but no usable local model artifact was found"
            )
        if progress_callback is not None:
            progress_callback(1.0)
        return path

    def _download_whisper_cpp(
        self, model_name: str, progress_callback: Callable[[float], None] | None
    ) -> Path:
        """Download one official GGML artifact through Hugging Face's atomic cache."""
        model_dir = self._models_dir / WHISPER_CPP_BACKEND
        model_dir.mkdir(parents=True, exist_ok=True)
        filename = f"ggml-{model_name}.bin"
        logger.info("Downloading whisper.cpp model '%s'...", model_name)

        try:
            from huggingface_hub import hf_hub_download

            hf_hub_download(
                repo_id=WHISPER_CPP_REPOSITORY,
                filename=filename,
                local_dir=str(model_dir),
            )
        except Exception:
            logger.exception("Failed to download whisper.cpp model '%s'", model_name)
            raise

        path = self.get_model_path(model_name, backend=WHISPER_CPP_BACKEND)
        if path is None:
            raise RuntimeError(
                f"whisper.cpp download for '{model_name}' completed without a usable GGML file"
            )
        if progress_callback is not None:
            progress_callback(1.0)
        return path

    def _supported_models(self, backend: str) -> list[str]:
        self._validate_backend(backend)
        if backend == WHISPER_CPP_BACKEND:
            return SUPPORTED_WHISPER_CPP_MODELS
        return SUPPORTED_WHISPER_MODELS

    def _model_sizes(self, backend: str) -> dict[str, int]:
        self._validate_backend(backend)
        if backend == WHISPER_CPP_BACKEND:
            return WHISPER_CPP_MODEL_SIZES
        return MODEL_SIZES

    def _validate_model(self, model_name: str, backend: str) -> None:
        if model_name not in self._supported_models(backend):
            raise ValueError(f"Unsupported model '{model_name}' for backend '{backend}'")

    @staticmethod
    def _validate_backend(backend: str) -> None:
        if backend not in SUPPORTED_MODEL_BACKENDS:
            supported = ", ".join(SUPPORTED_MODEL_BACKENDS)
            raise ValueError(f"Unsupported model backend '{backend}'; expected one of: {supported}")

    def _whisper_cpp_path(self, model_name: str) -> Path:
        return self._models_dir / WHISPER_CPP_BACKEND / f"ggml-{model_name}.bin"

    def _faster_whisper_candidates(self, model_name: str) -> list[Path]:
        candidates = [
            self._models_dir / model_name,
            self._models_dir / f"faster-whisper-{model_name}",
        ]
        if self._models_dir.exists():
            candidates.extend(
                child
                for child in self._models_dir.iterdir()
                if child.is_dir() and child.name.endswith(f"faster-whisper-{model_name}")
            )
        return candidates

    @staticmethod
    def _is_usable_file(path: Path) -> bool:
        return path.is_file() and path.stat().st_size > 0

    @staticmethod
    def _is_usable_directory(path: Path) -> bool:
        return path.is_dir() and any(path.iterdir())
