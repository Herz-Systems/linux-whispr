"""Consumer-boundary tests for local Ollama refinement and catalog discovery."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any
from urllib.error import URLError

import pytest
from typing_extensions import Self

from linux_whispr.ai import ollama
from linux_whispr.ai.refinement import RefinementPipeline
from linux_whispr.events import EventBus
from linux_whispr.web.api import ollama_routes


class JsonResponse:
    """Minimal context-managed urllib response carrying a real JSON API payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        return self._payload if amount < 0 else self._payload[:amount]


class ScriptedOllama:
    """Protocol-level local Ollama fixture that records every HTTP request."""

    def __init__(
        self,
        tags: list[dict[str, Any]],
        shows: dict[str, dict[str, Any]],
        chat_response: (
            dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]] | None
        ) = None,
    ) -> None:
        self._tags = tags
        self._shows = shows
        self._chat_response = chat_response or {
            "message": {
                "role": "assistant",
                "content": "Corrected dictation",
                "thinking": "hidden",
            },
            "prompt_eval_count": 7,
            "eval_count": 5,
        }
        self.calls: list[tuple[str, str, dict[str, Any] | None, float]] = []

    def __call__(self, request: Any, timeout: float) -> JsonResponse:
        payload = json.loads(request.data.decode("utf-8")) if request.data else None
        path = request.full_url.removeprefix(ollama.OLLAMA_API_URL)
        self.calls.append((request.get_method(), path, payload, timeout))
        if path == "/tags":
            return JsonResponse({"models": self._tags})
        if path == "/show" and payload is not None:
            return JsonResponse(self._shows[payload["model"]])
        if path == "/chat":
            response = self._chat_response
            if callable(response):
                assert payload is not None
                response = response(payload)
            return JsonResponse(response)
        raise AssertionError(f"Unexpected Ollama request: {path}")


def local_summary(name: str = "qwen3:8b") -> dict[str, Any]:
    return {"name": name, "size": 5_200_000_000}


def local_show(*, thinking: bool = False) -> dict[str, Any]:
    capabilities = ["completion"] + (["thinking"] if thinking else [])
    response: dict[str, Any] = {
        "capabilities": capabilities,
        "details": {"parameter_size": "8.2B", "quantization_level": "Q4_K_M"},
    }
    if thinking:
        response["thinking"] = {"values": [True, False]}
    return response


def test_backend_validates_local_model_and_uses_nonstream_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScriptedOllama([local_summary()], {"qwen3:8b": local_show(thinking=True)})
    monkeypatch.setattr(ollama, "_open_local", service)

    result = ollama.OllamaBackend(model="qwen3:8b").generate("System instruction", "Raw words")

    assert result.text == "Corrected dictation"
    assert result.model == "qwen3:8b"
    assert result.tokens_used == 12
    assert [path for _, path, _, _ in service.calls] == ["/tags", "/show", "/chat"]
    chat_payload = service.calls[-1][2]
    assert chat_payload == {
        "model": "qwen3:8b",
        "messages": [
            {"role": "system", "content": "System instruction"},
            {"role": "user", "content": "Raw words"},
        ],
        "stream": False,
        "keep_alive": "15m",
        "options": {"temperature": 0.3, "num_ctx": 8192, "num_predict": 2048},
        "think": False,
    }


@pytest.mark.parametrize("keep_alive_minutes", [True, 15.0, 10])
def test_backend_rejects_invalid_residency_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
    keep_alive_minutes: object,
) -> None:
    requests: list[object] = []

    def unexpected_request(*args: object, **kwargs: object) -> JsonResponse:
        requests.append((args, kwargs))
        raise AssertionError("The backend must reject invalid residency before networking.")

    monkeypatch.setattr(ollama, "_open_local", unexpected_request)

    with pytest.raises(ValueError, match="keep_alive_minutes"):
        ollama.OllamaBackend(
            model="qwen3:8b", keep_alive_minutes=keep_alive_minutes  # type: ignore[arg-type]
        )

    assert requests == []


def test_backend_preloads_empty_chat_with_the_generation_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def chat_response(payload: dict[str, Any]) -> dict[str, Any]:
        if payload["messages"] == []:
            return {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "load",
                "eval_count": 0,
            }
        return {
            "message": {"role": "assistant", "content": "Corrected dictation"},
            "prompt_eval_count": 7,
            "eval_count": 5,
        }

    service = ScriptedOllama(
        [local_summary()], {"qwen3:8b": local_show(thinking=True)}, chat_response
    )
    monkeypatch.setattr(ollama, "_open_local", service)
    backend = ollama.OllamaBackend(model="qwen3:8b", keep_alive_minutes=30)

    backend.preload()
    assert backend.generate("System instruction", "Raw words").text == "Corrected dictation"

    preload_payload = service.calls[2][2]
    generate_payload = service.calls[5][2]
    assert preload_payload is not None
    assert generate_payload is not None
    assert preload_payload["messages"] == []
    assert {
        key: preload_payload[key]
        for key in ("model", "stream", "keep_alive", "options", "think")
    } == {
        key: generate_payload[key]
        for key in ("model", "stream", "keep_alive", "options", "think")
    }


def test_backend_preload_cancellation_before_validation_avoids_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScriptedOllama([local_summary()], {"qwen3:8b": local_show()})
    monkeypatch.setattr(ollama, "_open_local", service)
    cancel_event = threading.Event()
    cancel_event.set()

    ollama.OllamaBackend(model="qwen3:8b").preload(cancel_event=cancel_event)

    assert service.calls == []


def test_backend_preload_cancellation_after_validation_avoids_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScriptedOllama([local_summary()], {"qwen3:8b": local_show()})
    monkeypatch.setattr(ollama, "_open_local", service)
    backend = ollama.OllamaBackend(model="qwen3:8b")
    cancel_event = threading.Event()
    validate_model = backend._client.validate_model

    def cancel_after_validation(name: str) -> Any:
        model = validate_model(name)
        cancel_event.set()
        return model

    monkeypatch.setattr(backend._client, "validate_model", cancel_after_validation)

    backend.preload(cancel_event=cancel_event)

    assert [path for _, path, _, _ in service.calls] == ["/tags", "/show"]


def test_backend_preload_refuses_missing_or_cloud_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = ScriptedOllama([], {})
    monkeypatch.setattr(ollama, "_open_local", missing)

    with pytest.raises(ollama.OllamaModelUnavailableError, match="not installed"):
        ollama.OllamaBackend(model="qwen3:8b").preload()

    assert [path for _, path, _, _ in missing.calls] == ["/tags"]

    cloud = ScriptedOllama(
        [local_summary()],
        {"qwen3:8b": {"remote_host": "https://ollama.com"}},
    )
    monkeypatch.setattr(ollama, "_open_local", cloud)

    with pytest.raises(ollama.OllamaModelUnavailableError, match="cloud-routed"):
        ollama.OllamaBackend(model="qwen3:8b").preload()

    assert [path for _, path, _, _ in cloud.calls] == ["/tags", "/show"]


def test_backend_rejects_malformed_or_remote_preload_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = ScriptedOllama(
        [local_summary()],
        {"qwen3:8b": local_show()},
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
        },
    )
    monkeypatch.setattr(ollama, "_open_local", malformed)

    with pytest.raises(ollama.OllamaResponseError, match="invalid model preload"):
        ollama.OllamaBackend(model="qwen3:8b").preload()

    remote = ScriptedOllama(
        [local_summary()],
        {"qwen3:8b": local_show()},
        {
            "remote_host": "https://ollama.com",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "load",
        },
    )
    monkeypatch.setattr(ollama, "_open_local", remote)

    with pytest.raises(ollama.OllamaModelUnavailableError, match="routed remotely"):
        ollama.OllamaBackend(model="qwen3:8b").preload()


def test_backend_revalidates_local_routing_after_preload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def chat_response(payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["messages"] == []
        return {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "load",
        }

    service = ScriptedOllama(
        [local_summary()], {"qwen3:8b": local_show()}, chat_response
    )
    monkeypatch.setattr(ollama, "_open_local", service)
    backend = ollama.OllamaBackend(model="qwen3:8b")

    backend.preload()
    service._tags = [{**local_summary(), "remote_host": "https://ollama.com"}]

    with pytest.raises(ollama.OllamaModelUnavailableError, match="cloud-routed"):
        backend.generate("", "Private dictation")

    assert service.calls[-1][1] == "/tags"
    assert not any(
        path == "/chat" and payload is not None and "Private dictation" in json.dumps(payload)
        for _, path, payload, _ in service.calls
    )


def test_backend_omits_thinking_control_when_model_does_not_advertise_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScriptedOllama([local_summary()], {"qwen3:8b": local_show()})
    monkeypatch.setattr(ollama, "_open_local", service)

    ollama.OllamaBackend(model="qwen3:8b").generate("", "Raw words")

    assert "think" not in service.calls[-1][2]


def test_backend_rejects_empty_completion_text(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ScriptedOllama(
        [local_summary()],
        {"qwen3:8b": local_show()},
        {"message": {"role": "assistant", "content": "   "}},
    )
    monkeypatch.setattr(ollama, "_open_local", service)

    with pytest.raises(ollama.OllamaResponseError, match="without text content"):
        ollama.OllamaBackend(model="qwen3:8b").generate("", "Raw words")


def test_backend_rejects_remote_generation_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScriptedOllama(
        [local_summary()],
        {"qwen3:8b": local_show()},
        {
            "remote_host": "https://ollama.com",
            "message": {"role": "assistant", "content": "Never expose this"},
        },
    )
    monkeypatch.setattr(ollama, "_open_local", service)

    with pytest.raises(ollama.OllamaModelUnavailableError, match="routed remotely"):
        ollama.OllamaBackend(model="qwen3:8b").generate("", "Private dictation")


def test_backend_rejects_cloud_routed_model_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScriptedOllama(
        [{**local_summary(), "remote_host": "https://ollama.com", "remote_model": "cloud"}],
        {},
    )
    monkeypatch.setattr(ollama, "_open_local", service)

    with pytest.raises(ollama.OllamaModelUnavailableError, match="cloud-routed"):
        ollama.OllamaBackend(model="qwen3:8b").generate("", "Private dictation")

    assert [path for _, path, _, _ in service.calls] == ["/tags"]


def test_pipeline_rechecks_local_routing_before_each_refinement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScriptedOllama([local_summary()], {"qwen3:8b": local_show()})
    monkeypatch.setattr(ollama, "_open_local", service)
    errors: list[str] = []
    bus = EventBus()
    bus.on("ai.error", lambda message: errors.append(message))
    pipeline = RefinementPipeline(
        event_bus=bus,
        backend=ollama.OllamaBackend(model="qwen3:8b"),
        enabled=True,
    )

    assert pipeline.refine("First dictation") == "Corrected dictation"
    service._tags = [{**local_summary(), "remote_host": "https://ollama.com"}]

    assert pipeline.refine("Private dictation") == "Private dictation"
    assert errors == ["AI refinement is unavailable. Check the configured AI service."]
    assert service.calls[-1][1] == "/tags"
    assert not any(
        path == "/chat" and payload is not None and "Private dictation" in json.dumps(payload)
        for _, path, payload, _ in service.calls
    )


def test_catalog_keeps_only_verified_local_completion_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScriptedOllama(
        [
            local_summary("qwen3:8b"),
            local_summary("embedding-only"),
            {**local_summary("cloud-alias"), "remote_model": "some-cloud-model"},
            local_summary("bad-metadata"),
        ],
        {
            "qwen3:8b": local_show(),
            "embedding-only": {
                "capabilities": ["embedding"],
                "details": {"parameter_size": "1B", "quantization_level": "Q8_0"},
            },
            "bad-metadata": {"capabilities": ["completion"]},
        },
    )
    monkeypatch.setattr(ollama, "_open_local", service)

    catalog = ollama.get_ollama_model_catalog()

    assert catalog["available"] is True
    assert catalog["models"] == [
        {
            "name": "qwen3:8b",
            "size": 5_200_000_000,
            "parameter_size": "8.2B",
            "quantization_level": "Q4_K_M",
        }
    ]
    assert catalog["recommended"] == [
        {
            "name": "qwen3:8b",
            "description": "Balanced multilingual refinement; recommended starting point.",
            "size_gb": 5.2,
            "source_url": "https://ollama.com/library/qwen3:8b",
            "installed": True,
        },
        {
            "name": "qwen3.5:4b",
            "description": "Smaller download for quick corrections on modest hardware.",
            "size_gb": 3.3,
            "source_url": "https://ollama.com/library/qwen3.5:4b",
            "installed": False,
        },
        {
            "name": "qwen3:14b",
            "description": "Larger multilingual model for more demanding edits.",
            "size_gb": 9.3,
            "source_url": "https://ollama.com/library/qwen3:14b",
            "installed": False,
        },
        {
            "name": "gemma3:12b",
            "description": "Multilingual alternative; larger download includes vision components.",
            "size_gb": 8.2,
            "source_url": "https://ollama.com/library/gemma3:12b",
            "installed": False,
        },
    ]
    assert catalog["error"] is None
    assert catalog["warnings"] == [
        "Skipped bad-metadata: Ollama returned invalid metadata for model 'bad-metadata'."
    ]
    assert {path for _, path, _, _ in service.calls} == {"/tags", "/show"}


def test_catalog_preserves_recommendations_when_local_service_is_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_: object, **__: object) -> JsonResponse:
        raise URLError("Connection refused")

    monkeypatch.setattr(ollama, "_open_local", unavailable)

    catalog = ollama.get_ollama_model_catalog()

    assert catalog["available"] is False
    assert catalog["models"] == []
    assert catalog["error"] is not None
    assert [item["name"] for item in catalog["recommended"]] == [
        "qwen3:8b",
        "qwen3.5:4b",
        "qwen3:14b",
        "gemma3:12b",
    ]
    assert all(not item["installed"] for item in catalog["recommended"])


@pytest.mark.asyncio
async def test_catalog_route_runs_blocking_discovery_in_threadpool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "available": True,
        "models": [],
        "recommended": [],
        "error": None,
        "warnings": [],
    }
    calls: list[object] = []

    def discover() -> dict[str, Any]:
        return expected

    async def fake_threadpool(function: object, *args: object, **kwargs: object) -> object:
        calls.append(function)
        return function(*args, **kwargs)  # type: ignore[operator]

    monkeypatch.setattr(ollama_routes, "get_ollama_model_catalog", discover)
    monkeypatch.setattr(ollama_routes, "run_in_threadpool", fake_threadpool)

    assert await ollama_routes.list_ollama_models() == expected
    assert calls == [discover]
