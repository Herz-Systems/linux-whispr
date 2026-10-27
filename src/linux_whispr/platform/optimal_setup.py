"""Conservative local hardware detection for the setup recommendation.

Detection intentionally only reads local operating-system state and runs bounded
capability probes.  It never downloads a model, changes configuration, or loads
an STT model.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from linux_whispr.stt.model_manager import (
    FASTER_WHISPER_BACKEND,
    WHISPER_CPP_BACKEND,
    ModelManager,
)

_MIB = 1024 * 1024
_PROBE_TIMEOUT_SECONDS = 5
_SOFTWARE_DEVICE_MARKERS = ("llvmpipe", "lavapipe", "software", "cpu", "swiftshader")
_VENDOR_IDS = {"1002": "amd", "10de": "nvidia", "8086": "intel"}


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_int(path: Path, *, base: int = 10) -> int | None:
    value = _read_text(path)
    if value is None:
        return None
    try:
        return int(value, base)
    except ValueError:
        return None


def _memory_info() -> tuple[int | None, int | None]:
    """Return total and available system RAM in MiB from procfs."""
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None

    values: dict[str, int] = {}
    for line in lines:
        key, separator, value = line.partition(":")
        if not separator:
            continue
        amount = value.strip().split(maxsplit=1)
        if not amount:
            continue
        try:
            values[key] = int(amount[0]) // 1024
        except ValueError:
            continue
    return values.get("MemTotal"), values.get("MemAvailable")


def _cpu_threads() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _vendor_from_id(value: str | None) -> str:
    if value is None:
        return "other"
    return _VENDOR_IDS.get(value.removeprefix("0x").lower(), "other")


def _pci_slot(device: Path) -> str | None:
    uevent = _read_text(device / "uevent")
    if uevent is None:
        return None
    for line in uevent.splitlines():
        if line.startswith("PCI_SLOT_NAME="):
            return line.partition("=")[2].lower()
    return None


def _enumerate_sysfs_gpus() -> list[dict[str, Any]]:
    """Discover physical DRM PCI GPUs and their real VRAM counters when exposed."""
    drm_dir = Path("/sys/class/drm")
    try:
        cards = sorted(drm_dir.glob("card[0-9]*"))
    except OSError:
        return []

    gpus: list[dict[str, Any]] = []
    seen_devices: set[Path] = set()
    for card in cards:
        device_link = card / "device"
        try:
            device = device_link.resolve(strict=True)
        except OSError:
            continue
        if device in seen_devices or not (device / "vendor").is_file():
            continue
        seen_devices.add(device)

        vendor_id = _read_text(device / "vendor")
        device_id = _read_text(device / "device")
        total_bytes = _read_int(device / "mem_info_vram_total")
        used_bytes = _read_int(device / "mem_info_vram_used")
        total_mb = total_bytes // _MIB if total_bytes is not None else None
        available_mb = None
        if total_bytes is not None and used_bytes is not None:
            available_mb = max(0, total_bytes - used_bytes) // _MIB

        gpus.append(
            {
                "name": f"{_vendor_from_id(vendor_id).upper()} GPU",
                "vendor": _vendor_from_id(vendor_id),
                "kind": "unknown",
                "vram_total_mb": total_mb,
                "vram_available_mb": available_mb,
                "usable": False,
                "acceleration": None,
                "_vendor_id": vendor_id.removeprefix("0x").lower() if vendor_id else None,
                "_device_id": device_id.removeprefix("0x").lower() if device_id else None,
                "_pci_slot": _pci_slot(device),
            }
        )
    return gpus


def _run_probe(arguments: list[str]) -> str | None:
    """Run one fixed local capability probe with a short wall-clock deadline."""
    try:
        completed = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            check=False,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return f"{completed.stdout}\n{completed.stderr}"


def _probe_cuda_capabilities() -> tuple[set[str], dict[str, str]] | None:
    """Probe CUDA logical device zero and its identity in one bounded child."""
    script = """
import ctypes
import ctypes.util
import ctranslate2
import json

result = {
    "types": sorted(ctranslate2.get_supported_compute_types("cuda", device_index=0)),
    "identity": {},
}
try:
    libcuda = ctypes.CDLL(ctypes.util.find_library("cuda") or "libcuda.so.1")
    device = ctypes.c_int()
    if libcuda.cuInit(0) == 0 and libcuda.cuDeviceGet(ctypes.byref(device), 0) == 0:
        pci_bus_id = ctypes.create_string_buffer(32)
        if libcuda.cuDeviceGetPCIBusId(pci_bus_id, len(pci_bus_id), device) == 0:
            result["identity"]["pci_bus_id"] = pci_bus_id.value.decode().lower()
        get_uuid = getattr(libcuda, "cuDeviceGetUuid_v2", None)
        if get_uuid is not None:
            uuid = (ctypes.c_ubyte * 16)()
            if get_uuid(ctypes.byref(uuid), device) == 0:
                value = bytes(uuid).hex()
                result["identity"]["uuid"] = (
                    f"GPU-{value[:8]}-{value[8:12]}-{value[12:16]}-"
                    f"{value[16:20]}-{value[20:]}"
                )
except (AttributeError, OSError):
    pass
print(json.dumps(result))
"""
    output = _run_probe([sys.executable, "-c", script])
    if output is None:
        return None
    for line in reversed(output.splitlines()):
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        types = decoded.get("types") if isinstance(decoded, dict) else None
        identity = decoded.get("identity") if isinstance(decoded, dict) else None
        if (
            isinstance(types, list)
            and all(isinstance(item, str) for item in types)
            and isinstance(identity, dict)
            and all(
                key in {"pci_bus_id", "uuid"} and isinstance(value, str)
                for key, value in identity.items()
            )
        ):
            return set(types), {
                key: value.lower() for key, value in identity.items() if value
            }
    return None


def _parse_csv_records(output: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line in output.splitlines():
        values = [part.strip() for part in line.split(",")]
        if len(values) != 6:
            continue
        index, name, total, free, bus_id, uuid = values
        if not index.isdigit():
            continue
        records.append(
            {
                "index": index,
                "name": name,
                "total_mb": total,
                "free_mb": free,
                "pci_bus_id": _normalize_pci_bus_id(bus_id),
                "uuid": uuid.lower(),
            }
        )
    return records


def _normalize_pci_bus_id(value: str) -> str:
    """Normalize equivalent PCI domain spellings from CUDA, NVML, and sysfs."""
    parts = value.strip().lower().split(":")
    if len(parts) != 3:
        return value.strip().lower()
    try:
        return f"{int(parts[0], 16):04x}:{parts[1]}:{parts[2]}"
    except ValueError:
        return value.strip().lower()


def _probe_nvidia_smi() -> list[dict[str, str]] | None:
    if shutil.which("nvidia-smi") is None:
        return None
    output = _run_probe(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.free,pci.bus_id,uuid",
            "--format=csv,noheader,nounits",
        ]
    )
    return _parse_csv_records(output) if output is not None else None


def _visible_nvidia_gpu(
    records: list[dict[str, str]], cuda_identity: dict[str, str]
) -> dict[str, str] | None:
    """Match CUDA logical device zero to NVIDIA memory metadata by identity."""
    if not records or not cuda_identity:
        return None
    matches = records
    pci_bus_id = cuda_identity.get("pci_bus_id")
    if pci_bus_id:
        matches = [
            record
            for record in matches
            if record["pci_bus_id"] == _normalize_pci_bus_id(pci_bus_id)
        ]
    uuid = cuda_identity.get("uuid")
    if uuid:
        matches = [record for record in matches if record["uuid"] == uuid.lower()]
    return matches[0] if len(matches) == 1 else None


def _probe_vulkan_runtime() -> str | None:
    """Initialize pywhispercpp in a child and capture its Vulkan device-zero log."""
    script = (
        "import _pywhispercpp as native; "
        "assert callable(getattr(native, 'whisper_log_set', None)); "
        "native.whisper_print_system_info()"
    )
    return _run_probe([sys.executable, "-c", script])


def _native_vulkan_device_zero(output: str | None) -> str | None:
    if output is None or not re.search(r"ggml_vulkan:\s*Found\s+[1-9][0-9]*\s+Vulkan devices", output):
        return None
    match = re.search(r"ggml_vulkan:\s*0\s*=\s*([^\n|]+)", output, re.IGNORECASE)
    if match is None:
        return None
    name = match.group(1).strip()
    if (
        not name
        or re.search(r"ggml_vulkan:\s*Device type is CPU\b", output, re.IGNORECASE)
        or any(marker in name.casefold() for marker in _SOFTWARE_DEVICE_MARKERS)
    ):
        return None
    return name


def _probe_vulkaninfo() -> list[dict[str, str]] | None:
    """Read Vulkan physical device identities when the optional utility exists."""
    if shutil.which("vulkaninfo") is None:
        return None
    output = _run_probe(["vulkaninfo", "--summary"])
    if output is None:
        return None

    devices: list[dict[str, str]] = []
    sections = re.split(r"(?m)^GPU(\d+):\s*", output)
    for index in range(1, len(sections), 2):
        body = sections[index + 1]
        vendor = re.search(r"vendorID\s*=\s*0x([0-9a-fA-F]+)", body)
        device = re.search(r"deviceID\s*=\s*0x([0-9a-fA-F]+)", body)
        name = re.search(r"deviceName\s*=\s*(.+)", body)
        device_type = re.search(r"deviceType\s*=\s*(.+)", body)
        device_type_value = device_type.group(1).upper() if device_type else ""
        if vendor is None or device is None:
            continue
        devices.append(
            {
                "index": sections[index],
                "vendor_id": vendor.group(1).lower(),
                "device_id": device.group(1).lower(),
                "name": name.group(1).strip() if name else "",
                "device_type": device_type_value,
                "kind": (
                    "integrated"
                    if "INTEGRATED_GPU" in device_type_value
                    else "discrete"
                    if "DISCRETE_GPU" in device_type_value
                    else "unknown"
                ),
            }
        )
    return devices


def _find_sysfs_gpu(
    gpus: list[dict[str, Any]], *, vendor_id: str, device_id: str
) -> dict[str, Any] | None:
    matches = [
        gpu
        for gpu in gpus
        if gpu["_vendor_id"] == vendor_id and gpu["_device_id"] == device_id
    ]
    return matches[0] if len(matches) == 1 else None


def _normalized_device_name(name: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", name.casefold()))


def _unknown_vulkan_gpu(
    gpus: list[dict[str, Any]],
    native_name: str,
    devices: list[dict[str, str]],
) -> dict[str, Any]:
    """Represent a native Vulkan GPU whose physical memory cannot be identified."""
    vendor_ids = {device["vendor_id"] for device in devices}
    kinds = {device["kind"] for device in devices}
    gpu = {
        "name": native_name,
        "vendor": _vendor_from_id(next(iter(vendor_ids))) if len(vendor_ids) == 1 else "other",
        "kind": next(iter(kinds)) if len(kinds) == 1 else "unknown",
        "vram_total_mb": None,
        "vram_available_mb": None,
        "usable": False,
        "acceleration": None,
        "_vendor_id": next(iter(vendor_ids)) if len(vendor_ids) == 1 else None,
        "_device_id": None,
        "_pci_slot": None,
    }
    gpus.append(gpu)
    return gpu


def _match_vulkan_gpu(
    gpus: list[dict[str, Any]], native_name: str, vulkan_devices: list[dict[str, str]] | None
) -> dict[str, Any] | None:
    """Match the initialized native device name to one physical Vulkan identity."""
    if not vulkan_devices:
        return None
    native_identity = _normalized_device_name(native_name)
    matching_devices = [
        device
        for device in vulkan_devices
        if "CPU" not in device.get("device_type", "").upper()
        and not any(
            marker in device.get("name", "").casefold()
            for marker in _SOFTWARE_DEVICE_MARKERS
        )
        and (
            _normalized_device_name(device.get("name", "")) == native_identity
            or _normalized_device_name(device.get("name", "")) in native_identity
            or native_identity in _normalized_device_name(device.get("name", ""))
        )
    ]
    if not matching_devices:
        return None
    if len(matching_devices) != 1:
        return _unknown_vulkan_gpu(gpus, native_name, matching_devices)

    device = matching_devices[0]
    matched = _find_sysfs_gpu(
        gpus,
        vendor_id=device["vendor_id"],
        device_id=device["device_id"],
    )
    if matched is None:
        matched = {
            "name": device["name"] or native_name,
            "vendor": _vendor_from_id(device["vendor_id"]),
            "kind": device["kind"],
            "vram_total_mb": None,
            "vram_available_mb": None,
            "usable": False,
            "acceleration": None,
            "_vendor_id": device["vendor_id"],
            "_device_id": device["device_id"],
            "_pci_slot": None,
        }
        gpus.append(matched)
    else:
        matched["name"] = device["name"] or native_name
        matched["kind"] = device["kind"]
    return matched


def _unknown_cuda_gpu(
    gpus: list[dict[str, Any]], cuda_identity: dict[str, str]
) -> dict[str, Any]:
    """Represent usable CUDA device zero without assigning another GPU's memory."""
    gpu = {
        "name": "CUDA GPU",
        "vendor": "nvidia",
        "kind": "unknown",
        "vram_total_mb": None,
        "vram_available_mb": None,
        "usable": False,
        "acceleration": None,
        "_vendor_id": "10de",
        "_device_id": None,
        "_pci_slot": _normalize_pci_bus_id(cuda_identity.get("pci_bus_id", "")),
    }
    gpus.append(gpu)
    return gpu


def _apply_nvidia_smi(gpus: list[dict[str, Any]], record: dict[str, str]) -> dict[str, Any]:
    matched = next(
        (
            gpu
            for gpu in gpus
            if _normalize_pci_bus_id(gpu["_pci_slot"] or "") == record["pci_bus_id"]
        ),
        None,
    )
    if matched is None:
        matched = {
            "name": record["name"],
            "vendor": "nvidia",
            "kind": "discrete",
            "vram_total_mb": None,
            "vram_available_mb": None,
            "usable": False,
            "acceleration": None,
            "_vendor_id": "10de",
            "_device_id": None,
            "_pci_slot": record["pci_bus_id"],
        }
        gpus.append(matched)
    matched["name"] = record["name"] or matched["name"]
    matched["kind"] = "discrete"
    try:
        matched["vram_total_mb"] = int(record["total_mb"])
    except ValueError:
        pass
    try:
        matched["vram_available_mb"] = int(record["free_mb"])
    except ValueError:
        pass
    return matched


def _model_details(backend: str, model: str) -> tuple[int, bool]:
    try:
        info = next(item for item in ModelManager().list_models(backend=backend) if item.name == model)
    except (OSError, StopIteration):
        return 0, False
    return info.size_mb, info.downloaded


def _choose_gpu_model(gpu_memory_mb: int | None, ram_mb: int | None) -> str | None:
    if ram_mb is None:
        return None
    if gpu_memory_mb is None:
        return "base" if ram_mb >= 2 * 1024 else None
    if gpu_memory_mb >= 6 * 1024 and ram_mb >= 8 * 1024:
        return "large-v3-turbo"
    if gpu_memory_mb >= 3 * 1024 and ram_mb >= 4 * 1024:
        return "small"
    if gpu_memory_mb >= 1536 and ram_mb >= 2 * 1024:
        return "base"
    return "tiny" if ram_mb >= 1024 else None


def _choose_cpu_model(cpu_threads: int, ram_mb: int | None) -> str:
    if ram_mb is None:
        return "tiny"
    if cpu_threads >= 8 and ram_mb >= 4 * 1024:
        return "small"
    if cpu_threads >= 4 and ram_mb >= 2 * 1024:
        return "base"
    return "tiny"


def _public_gpu(gpu: dict[str, Any]) -> dict[str, Any]:
    return {key: gpu[key] for key in ("name", "vendor", "kind", "vram_total_mb", "vram_available_mb", "usable", "acceleration")}


def detect_optimal_setup() -> dict[str, Any]:
    """Detect locally usable acceleration and return a conservative model recommendation."""
    cpu_threads = _cpu_threads()
    ram_total_mb, ram_available_mb = _memory_info()
    gpus = _enumerate_sysfs_gpus()
    warnings: list[str] = []

    if ram_available_mb is None:
        warnings.append("ram_unknown")
    elif ram_available_mb < 1024:
        warnings.append("low_memory")

    cuda_capabilities = _probe_cuda_capabilities()
    cuda_types, cuda_identity = cuda_capabilities or (None, {})
    nvidia_records = _probe_nvidia_smi() or []
    cuda_record = _visible_nvidia_gpu(nvidia_records, cuda_identity)
    cuda_gpu: dict[str, Any] | None = None
    if cuda_types:
        supported_types = ("float16", "int8", "float32")
        cuda_compute_type = next((item for item in supported_types if item in cuda_types), None)
        if cuda_compute_type is not None:
            cuda_gpu = (
                _apply_nvidia_smi(gpus, cuda_record)
                if cuda_record is not None
                else _unknown_cuda_gpu(gpus, cuda_identity)
            )
    else:
        cuda_compute_type = None
    has_nvidia = any(gpu["vendor"] == "nvidia" for gpu in gpus) or bool(nvidia_records)
    if has_nvidia and cuda_gpu is None:
        warnings.append("cuda_unavailable")

    vulkan_runtime_output = _probe_vulkan_runtime()
    native_vulkan_name = _native_vulkan_device_zero(vulkan_runtime_output)
    vulkan_gpu = _match_vulkan_gpu(gpus, native_vulkan_name, _probe_vulkaninfo()) if native_vulkan_name else None
    has_amd = any(gpu["vendor"] == "amd" for gpu in gpus)
    has_vulkan_candidate = any(gpu["vendor"] in {"amd", "intel", "nvidia"} for gpu in gpus)
    if has_amd and vulkan_runtime_output is None:
        warnings.append("amd_runtime_missing")
    if has_vulkan_candidate and vulkan_gpu is None and cuda_gpu is None:
        warnings.append("vulkan_unavailable")
    if any(
        gpu is not None and gpu["vram_available_mb"] is None
        for gpu in (cuda_gpu, vulkan_gpu)
    ):
        warnings.append("gpu_memory_unknown")


    selected_gpu: dict[str, Any] | None = None
    backend = FASTER_WHISPER_BACKEND
    device = "cpu"
    compute_type = "int8"
    reason = "cpu"
    model: str | None = None

    if cuda_gpu is not None:
        candidate = _choose_gpu_model(cuda_gpu["vram_available_mb"], ram_available_mb)
        if candidate is not None:
            selected_gpu = cuda_gpu
            backend = FASTER_WHISPER_BACKEND
            device = "cuda"
            compute_type = cuda_compute_type or "int8"
            reason = "cuda"
            model = candidate
    if model is None and vulkan_gpu is not None:
        candidate = _choose_gpu_model(vulkan_gpu["vram_available_mb"], ram_available_mb)
        if candidate is not None:
            selected_gpu = vulkan_gpu
            backend = WHISPER_CPP_BACKEND
            device = "vulkan"
            compute_type = "auto"
            reason = "vulkan"
            model = candidate

    if selected_gpu is None:
        model = _choose_cpu_model(cpu_threads, ram_available_mb)
    else:
        selected_gpu["usable"] = True
        selected_gpu["acceleration"] = device
        if selected_gpu["vram_available_mb"] is None and "gpu_memory_unknown" not in warnings:
            warnings.append("gpu_memory_unknown")

    assert model is not None

    download_size_mb, downloaded = _model_details(backend, model)
    return {
        "hardware": {
            "cpu_threads": cpu_threads,
            "ram_total_mb": ram_total_mb,
            "ram_available_mb": ram_available_mb,
            "gpus": [_public_gpu(gpu) for gpu in gpus],
        },
        "recommendation": {
            "backend": backend,
            "model": model,
            "device": device,
            "compute_type": compute_type,
            "reason": reason,
            "download_size_mb": download_size_mb,
            "downloaded": downloaded,
        },
        "warnings": warnings,
    }
