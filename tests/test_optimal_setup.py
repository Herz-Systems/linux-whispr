"""Focused coverage for conservative local optimal-setup detection."""

from __future__ import annotations

import pytest

from linux_whispr.platform import optimal_setup


def _gpu(
    *,
    name: str = "AMD GPU",
    vendor: str = "amd",
    kind: str = "integrated",
    total_mb: int | None = 32 * 1024,
    available_mb: int | None = 30 * 1024,
    vendor_id: str | None = "1002",
    device_id: str | None = "1586",
    pci_slot: str | None = "0000:04:00.0",
) -> dict[str, object]:
    return {
        "name": name,
        "vendor": vendor,
        "kind": kind,
        "vram_total_mb": total_mb,
        "vram_available_mb": available_mb,
        "usable": False,
        "acceleration": None,
        "_vendor_id": vendor_id,
        "_device_id": device_id,
        "_pci_slot": pci_slot,
    }


def _vulkan_log(name: str = "AMD Radeon 8060S Graphics") -> str:
    return f"ggml_vulkan: Found 1 Vulkan devices:\nggml_vulkan: 0 = {name} | uma: 1"


def _vulkan_device(
    *,
    name: str = "AMD Radeon 8060S Graphics",
    kind: str = "integrated",
    vendor_id: str = "1002",
    device_id: str = "1586",
) -> list[dict[str, str]]:
    return [
        {
            "index": "0",
            "vendor_id": vendor_id,
            "device_id": device_id,
            "name": name,
            "kind": kind,
        }
    ]


def _configure(monkeypatch: pytest.MonkeyPatch, *, cpu_threads: int = 32, ram_mb: int | None = 62 * 1024, gpus: list[dict[str, object]] | None = None) -> None:
    monkeypatch.setattr(optimal_setup, "_cpu_threads", lambda: cpu_threads)
    monkeypatch.setattr(optimal_setup, "_memory_info", lambda: (94 * 1024, ram_mb))
    monkeypatch.setattr(optimal_setup, "_enumerate_sysfs_gpus", lambda: list(gpus or []))
    monkeypatch.setattr(optimal_setup, "_probe_cuda_capabilities", lambda: None)
    monkeypatch.setattr(optimal_setup, "_probe_nvidia_smi", lambda: None)
    monkeypatch.setattr(optimal_setup, "_probe_vulkan_runtime", lambda: None)
    monkeypatch.setattr(optimal_setup, "_probe_vulkaninfo", lambda: None)
    monkeypatch.setattr(
        optimal_setup,
        "_model_details",
        lambda backend, model: ({"tiny": 75, "base": 150, "small": 500, "large-v3-turbo": 1550}[model], model == "large-v3-turbo"),
    )


def test_detects_host_amd_vulkan_and_large_turbo(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, gpus=[_gpu()])
    monkeypatch.setattr(optimal_setup, "_probe_vulkan_runtime", _vulkan_log)
    monkeypatch.setattr(optimal_setup, "_probe_vulkaninfo", _vulkan_device)

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"] == {
        "backend": "whisper-cpp",
        "model": "large-v3-turbo",
        "device": "vulkan",
        "compute_type": "auto",
        "reason": "vulkan",
        "download_size_mb": 1550,
        "downloaded": True,
    }
    assert result["hardware"]["gpus"] == [
        {
            "name": "AMD Radeon 8060S Graphics",
            "vendor": "amd",
            "kind": "integrated",
            "vram_total_mb": 32 * 1024,
            "vram_available_mb": 30 * 1024,
            "usable": True,
            "acceleration": "vulkan",
        }
    ]
    assert result["warnings"] == []


@pytest.mark.parametrize(
    ("gpu_mb", "ram_mb", "expected_model"),
    [
        (6 * 1024, 8 * 1024, "large-v3-turbo"),
        (3 * 1024, 4 * 1024, "small"),
        (1536, 2 * 1024, "base"),
        (1024, 2 * 1024, "tiny"),
    ],
)
def test_gpu_model_fit_uses_separate_gpu_and_ram_budgets(
    monkeypatch: pytest.MonkeyPatch, gpu_mb: int, ram_mb: int, expected_model: str
) -> None:
    _configure(monkeypatch, ram_mb=ram_mb, gpus=[_gpu(available_mb=gpu_mb)])
    monkeypatch.setattr(optimal_setup, "_probe_vulkan_runtime", _vulkan_log)
    monkeypatch.setattr(optimal_setup, "_probe_vulkaninfo", _vulkan_device)

    assert optimal_setup.detect_optimal_setup()["recommendation"]["model"] == expected_model


def test_unknown_gpu_budget_uses_base_only_with_known_safe_ram(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, ram_mb=4 * 1024, gpus=[_gpu(total_mb=None, available_mb=None)])
    monkeypatch.setattr(optimal_setup, "_probe_vulkan_runtime", _vulkan_log)
    monkeypatch.setattr(optimal_setup, "_probe_vulkaninfo", _vulkan_device)

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["model"] == "base"
    assert result["recommendation"]["device"] == "vulkan"
    assert "gpu_memory_unknown" in result["warnings"]


def test_uma_does_not_combine_vram_and_system_ram(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, ram_mb=4 * 1024, gpus=[_gpu(available_mb=32 * 1024)])
    monkeypatch.setattr(optimal_setup, "_probe_vulkan_runtime", _vulkan_log)
    monkeypatch.setattr(optimal_setup, "_probe_vulkaninfo", _vulkan_device)

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["model"] == "small"

def test_native_vulkan_remapping_uses_the_initialized_gpu_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    large_gpu = _gpu(
        name="AMD large",
        available_mb=8 * 1024,
        device_id="1111",
        pci_slot="0000:01:00.0",
    )
    low_memory_gpu = _gpu(
        name="AMD low memory",
        available_mb=1024,
        device_id="2222",
        pci_slot="0000:02:00.0",
    )
    _configure(monkeypatch, ram_mb=16 * 1024, gpus=[large_gpu, low_memory_gpu])
    monkeypatch.setattr(
        optimal_setup, "_probe_vulkan_runtime", lambda: _vulkan_log("AMD low memory")
    )
    monkeypatch.setattr(
        optimal_setup,
        "_probe_vulkaninfo",
        lambda: [
            {
                "index": "0",
                "vendor_id": "1002",
                "device_id": "1111",
                "name": "AMD large",
                "kind": "discrete",
                "device_type": "VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU",
            },
            {
                "index": "1",
                "vendor_id": "1002",
                "device_id": "2222",
                "name": "AMD low memory",
                "kind": "discrete",
                "device_type": "VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU",
            },
        ],
    )

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["device"] == "vulkan"
    assert result["recommendation"]["model"] == "tiny"
    assert result["hardware"]["gpus"][0]["usable"] is False
    assert result["hardware"]["gpus"][1]["usable"] is True


def test_ambiguous_vulkan_sysfs_identity_does_not_take_another_gpu_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(
        monkeypatch,
        ram_mb=4 * 1024,
        gpus=[
            _gpu(name="AMD first", available_mb=8 * 1024),
            _gpu(name="AMD second", available_mb=8 * 1024),
        ],
    )
    monkeypatch.setattr(
        optimal_setup, "_probe_vulkan_runtime", lambda: _vulkan_log("AMD selected")
    )
    monkeypatch.setattr(
        optimal_setup,
        "_probe_vulkaninfo",
        lambda: [
            {
                "index": "1",
                "vendor_id": "1002",
                "device_id": "1586",
                "name": "AMD selected",
                "kind": "integrated",
                "device_type": "VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU",
            }
        ],
    )

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["device"] == "vulkan"
    assert result["recommendation"]["model"] == "base"
    assert "gpu_memory_unknown" in result["warnings"]
    assert result["hardware"]["gpus"][-1]["vram_available_mb"] is None




def test_software_vulkan_device_is_not_recommended(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, gpus=[_gpu()])
    monkeypatch.setattr(optimal_setup, "_probe_vulkan_runtime", lambda: _vulkan_log("llvmpipe (LLVM 19.1.0)"))

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["device"] == "cpu"
    assert "vulkan_unavailable" in result["warnings"]
    assert "amd_runtime_missing" not in result["warnings"]

def test_swiftshader_cpu_vulkan_device_is_not_matched_to_an_amd_gpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, gpus=[_gpu()])
    monkeypatch.setattr(
        optimal_setup,
        "_probe_vulkan_runtime",
        lambda: _vulkan_log("SwiftShader Device (Subzero)"),
    )
    monkeypatch.setattr(
        optimal_setup,
        "_probe_vulkaninfo",
        lambda: [
            {
                "index": "1",
                "vendor_id": "1002",
                "device_id": "1586",
                "name": "SwiftShader Device (Subzero)",
                "kind": "unknown",
                "device_type": "VK_PHYSICAL_DEVICE_TYPE_CPU",
            }
        ],
    )

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["device"] == "cpu"
    assert result["hardware"]["gpus"][0]["usable"] is False
    assert "vulkan_unavailable" in result["warnings"]


def test_native_vulkan_cpu_warning_rejects_the_selected_device() -> None:
    assert optimal_setup._native_vulkan_device_zero(
        _vulkan_log() + "\nggml_vulkan: Device type is CPU"
    ) is None


def test_missing_amd_runtime_degrades_to_cpu_with_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, gpus=[_gpu()])

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["reason"] == "cpu"
    assert "amd_runtime_missing" in result["warnings"]
    assert "vulkan_unavailable" in result["warnings"]


@pytest.mark.parametrize(
    ("threads", "ram_mb", "expected"),
    [
        (8, 4 * 1024, "small"),
        (4, 2 * 1024, "base"),
        (2, 16 * 1024, "tiny"),
        (16, None, "tiny"),
    ],
)
def test_cpu_model_tiers_are_conservative(
    monkeypatch: pytest.MonkeyPatch, threads: int, ram_mb: int | None, expected: str
) -> None:
    _configure(monkeypatch, cpu_threads=threads, ram_mb=ram_mb)

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"] == {
        "backend": "faster-whisper",
        "model": expected,
        "device": "cpu",
        "compute_type": "int8",
        "reason": "cpu",
        "download_size_mb": {"tiny": 75, "base": 150, "small": 500}[expected],
        "downloaded": False,
    }
    if ram_mb is None:
        assert "ram_unknown" in result["warnings"]


def test_cuda_uses_logical_zero_identity_not_nvml_order(monkeypatch: pytest.MonkeyPatch) -> None:
    nvidia_zero = _gpu(
        name="NVIDIA small",
        vendor="nvidia",
        kind="discrete",
        total_mb=1024,
        available_mb=1024,
        vendor_id="10de",
        device_id="1111",
        pci_slot="0000:01:00.0",
    )
    nvidia_one = _gpu(
        name="NVIDIA large",
        vendor="nvidia",
        kind="discrete",
        total_mb=8 * 1024,
        available_mb=8 * 1024,
        vendor_id="10de",
        device_id="2222",
        pci_slot="0000:02:00.0",
    )
    _configure(monkeypatch, ram_mb=16 * 1024, gpus=[nvidia_zero, nvidia_one])
    monkeypatch.setattr(
        optimal_setup,
        "_probe_cuda_capabilities",
        lambda: ({"float16", "int8"}, {"pci_bus_id": "0000:01:00.0", "uuid": "gpu-small"}),
    )
    monkeypatch.setattr(
        optimal_setup,
        "_probe_nvidia_smi",
        lambda: [
            {"index": "0", "name": "NVIDIA large", "total_mb": "8192", "free_mb": "8192", "pci_bus_id": "0000:02:00.0", "uuid": "gpu-large"},
            {"index": "1", "name": "NVIDIA small", "total_mb": "1024", "free_mb": "1024", "pci_bus_id": "0000:01:00.0", "uuid": "gpu-small"},
        ],
    )

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["backend"] == "faster-whisper"
    assert result["recommendation"]["device"] == "cuda"
    assert result["recommendation"]["compute_type"] == "float16"
    assert result["recommendation"]["model"] == "tiny"
    assert result["hardware"]["gpus"][0]["usable"] is True
    assert result["hardware"]["gpus"][1]["usable"] is False


def test_unmatched_cuda_identity_uses_unknown_memory_not_nvml_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, ram_mb=4 * 1024, gpus=[_gpu(vendor="nvidia", vendor_id="10de")])
    monkeypatch.setattr(
        optimal_setup,
        "_probe_cuda_capabilities",
        lambda: ({"float16"}, {"pci_bus_id": "0000:02:00.0"}),
    )
    monkeypatch.setattr(
        optimal_setup,
        "_probe_nvidia_smi",
        lambda: [
            {
                "index": "0",
                "name": "NVIDIA large",
                "total_mb": "8192",
                "free_mb": "8192",
                "pci_bus_id": "0000:01:00.0",
                "uuid": "gpu-large",
            }
        ],
    )

    result = optimal_setup.detect_optimal_setup()

    assert result["recommendation"]["device"] == "cuda"
    assert result["recommendation"]["model"] == "base"
    assert "gpu_memory_unknown" in result["warnings"]
