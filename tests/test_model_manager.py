"""Focused tests for backend-scoped model storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from linux_whispr.constants import SUPPORTED_WHISPER_CPP_MODELS, SUPPORTED_WHISPER_MODELS
from linux_whispr.stt.model_manager import ModelManager


def test_list_models_keeps_backends_and_artifacts_separate(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    faster_model = models_dir / "faster-whisper-base"
    faster_model.mkdir(parents=True)
    (faster_model / "model.bin").write_bytes(b"faster")
    cpp_model = models_dir / "whisper-cpp" / "ggml-base.bin"
    cpp_model.parent.mkdir(parents=True)
    cpp_model.write_bytes(b"cpp")

    manager = ModelManager(models_dir)

    faster = {model.name: model for model in manager.list_models()}
    cpp = {model.name: model for model in manager.list_models(backend="whisper-cpp")}

    assert set(faster) == set(SUPPORTED_WHISPER_MODELS)
    assert set(cpp) == set(SUPPORTED_WHISPER_CPP_MODELS)
    assert faster["base"].path == faster_model
    assert cpp["base"].path == cpp_model
    assert manager.get_model_path("base") == faster_model
    assert manager.get_model_path("base", backend="whisper-cpp") == cpp_model
    assert manager.get_disk_usage() == len(b"faster") + len(b"cpp")


def test_delete_whisper_cpp_model_leaves_faster_whisper_model(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    faster_model = models_dir / "base"
    faster_model.mkdir(parents=True)
    (faster_model / "model.bin").write_bytes(b"faster")
    cpp_model = models_dir / "whisper-cpp" / "ggml-base.bin"
    cpp_model.parent.mkdir(parents=True)
    cpp_model.write_bytes(b"cpp")

    manager = ModelManager(models_dir)

    assert manager.delete("base", backend="whisper-cpp")
    assert not cpp_model.exists()
    assert faster_model.exists()
    assert manager.is_downloaded("base")
    assert not manager.is_downloaded("base", backend="whisper-cpp")


@pytest.mark.parametrize(
    ("method", "args", "kwargs"),
    [
        ("list_models", (), {"backend": "invalid"}),
        ("is_downloaded", ("../base",), {}),
        ("get_model_path", ("distil-large-v3",), {"backend": "whisper-cpp"}),
        ("download", ("../base",), {}),
        ("delete", ("base",), {"backend": "invalid"}),
    ],
)
def test_model_manager_rejects_unknown_backends_and_names(
    tmp_path: Path,
    method: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> None:
    manager = ModelManager(tmp_path)

    with pytest.raises(ValueError):
        getattr(manager, method)(*args, **kwargs)


