"""Local-only Ollama client and AI refinement backend."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from linux_whispr.ai.base import LLMBackend, RefinementResult

logger = logging.getLogger(__name__)

OLLAMA_API_URL = "http://127.0.0.1:11434/api"
DEFAULT_DISCOVERY_TIMEOUT = 2.0
DEFAULT_GENERATION_TIMEOUT = 30.0
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_MAX_SHOW_WORKERS = 4


class _NoRedirect(HTTPRedirectHandler):
    """Reject redirects so loopback requests cannot leave the local daemon."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        raise HTTPError(
            req.full_url,
            code,
            "Ollama redirects are not permitted for local-only requests.",
            headers,
            fp,
        )


_LOCAL_OPENER = build_opener(ProxyHandler({}), _NoRedirect())


def _open_local(request: Request, timeout: float) -> Any:
    """Send one request without inheriting proxy environment configuration."""
    return _LOCAL_OPENER.open(request, timeout=timeout)

_RECOMMENDATIONS: tuple[tuple[str, str, float], ...] = (
    (
        "qwen3:8b",
        "Balanced multilingual refinement; recommended starting point.",
        5.2,
    ),
    (
        "qwen3.5:4b",
        "Smaller download for quick corrections on modest hardware.",
        3.3,
    ),
    (
        "qwen3:14b",
        "Larger multilingual model for more demanding edits.",
        9.3,
    ),
    (
        "gemma3:12b",
        "Multilingual alternative; larger download includes vision components.",
        8.2,
    ),
)


class OllamaError(RuntimeError):
    """Base error raised for an Ollama local API failure."""


class OllamaUnavailableError(OllamaError):
    """Raised when the local Ollama service cannot be contacted."""


class OllamaTimeoutError(OllamaError):
    """Raised when the local Ollama service exceeds the configured timeout."""


class OllamaResponseError(OllamaError):
    """Raised when Ollama returns an invalid or unsuccessful response."""


class OllamaModelUnavailableError(OllamaError):
    """Raised when a selected model is not an eligible local completion model."""


def _read_body(response: Any) -> bytes:
    """Read one bounded response body and reject oversized daemon output."""
    body = response.read(_MAX_RESPONSE_BYTES + 1)
    if not isinstance(body, bytes):
        raise OllamaResponseError("Ollama returned an invalid response body.")
    if len(body) > _MAX_RESPONSE_BYTES:
        raise OllamaResponseError(
            f"Ollama response exceeds the {_MAX_RESPONSE_BYTES // (1024 * 1024)} MiB limit."
        )
    return body


@dataclass(frozen=True)
class _LocalModel:
    name: str
    size: int
    parameter_size: str
    quantization_level: str
    capabilities: frozenset[str]
    can_disable_thinking: bool


def _is_remote_model(model: dict[str, Any]) -> bool:
    """Identify cloud-routed models from Ollama's explicit remote metadata."""
    return bool(model.get("remote_model") or model.get("remote_host"))


def _error_detail(raw: bytes) -> str:
    """Extract Ollama's JSON error without trusting malformed response data."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace").strip()
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return ""


class OllamaClient:
    """Small native HTTP client fixed to the loopback-only Ollama API."""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def _request_json(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{OLLAMA_API_URL}{path}",
            data=data,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with _open_local(request, timeout=self._timeout) as response:
                raw = _read_body(response)
        except HTTPError as error:
            detail = _error_detail(_read_body(error))
            message = f"Ollama request failed with HTTP {error.code}"
            if detail:
                message = f"{message}: {detail}"
            raise OllamaResponseError(message) from error
        except TimeoutError as error:
            raise OllamaTimeoutError(
                f"Ollama did not respond within {self._timeout:g}s; confirm the local service is running."
            ) from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise OllamaTimeoutError(
                    f"Ollama did not respond within {self._timeout:g}s; confirm the local service is running."
                ) from error
            reason = str(error.reason).strip()
            raise OllamaUnavailableError(
                f"Ollama is unavailable at {OLLAMA_API_URL}; start the local Ollama service"
                + (f" ({reason})." if reason else ".")
            ) from error
        except OSError as error:
            raise OllamaUnavailableError(
                f"Ollama is unavailable at {OLLAMA_API_URL}; start the local Ollama service ({error})."
            ) from error

        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OllamaResponseError("Ollama returned invalid JSON.") from error
        if not isinstance(decoded, dict):
            raise OllamaResponseError("Ollama returned an invalid response object.")
        if isinstance(decoded.get("error"), str):
            raise OllamaResponseError(f"Ollama request failed: {decoded['error']}")
        return decoded

    def _tags(self) -> list[dict[str, Any]]:
        response = self._request_json("/tags")
        models = response.get("models")
        if not isinstance(models, list):
            raise OllamaResponseError("Ollama returned an invalid model catalog.")
        return [model for model in models if isinstance(model, dict)]

    def _show(self, name: str) -> dict[str, Any]:
        return self._request_json("/show", {"model": name})

    def _inspect_model(self, summary: dict[str, Any]) -> _LocalModel:
        name = summary.get("name")
        if not isinstance(name, str) or not name:
            raise OllamaResponseError("Ollama returned a model without a valid name.")
        if _is_remote_model(summary):
            raise OllamaModelUnavailableError(
                f"Model '{name}' is cloud-routed and cannot be used for local refinement."
            )

        show = self._show(name)
        if _is_remote_model(show):
            raise OllamaModelUnavailableError(
                f"Model '{name}' is cloud-routed and cannot be used for local refinement."
            )
        capabilities_value = show.get("capabilities")
        if not isinstance(capabilities_value, list) or not all(
            isinstance(capability, str) for capability in capabilities_value
        ):
            raise OllamaResponseError(f"Ollama returned invalid capabilities for model '{name}'.")
        capabilities = frozenset(capabilities_value)
        if "completion" not in capabilities:
            raise OllamaModelUnavailableError(
                f"Model '{name}' cannot generate text completions; select an installed chat model."
            )

        size = summary.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise OllamaResponseError(f"Ollama returned an invalid size for model '{name}'.")
        details = show.get("details")
        if not isinstance(details, dict):
            raise OllamaResponseError(f"Ollama returned invalid metadata for model '{name}'.")
        parameter_size = details.get("parameter_size", "")
        quantization_level = details.get("quantization_level", "")
        if not isinstance(parameter_size, str) or not isinstance(quantization_level, str):
            raise OllamaResponseError(f"Ollama returned invalid metadata for model '{name}'.")

        thinking = show.get("thinking")
        if "thinking" not in capabilities:
            can_disable_thinking = False
        elif thinking is None:
            can_disable_thinking = True
        elif isinstance(thinking, dict):
            values = thinking.get("values")
            can_disable_thinking = isinstance(values, list) and False in values
        else:
            can_disable_thinking = False
        return _LocalModel(
            name=name,
            size=size,
            parameter_size=parameter_size,
            quantization_level=quantization_level,
            capabilities=capabilities,
            can_disable_thinking=can_disable_thinking,
        )

    def validate_model(self, name: str) -> _LocalModel:
        """Freshly verify a configured model is installed, local, and completion-capable."""
        if not name:
            raise OllamaModelUnavailableError("Select an installed Ollama model before enabling refinement.")
        for summary in self._tags():
            if summary.get("name") == name:
                return self._inspect_model(summary)
        raise OllamaModelUnavailableError(
            f"Model '{name}' is not installed locally; install it with 'ollama pull {name}'."
        )

    def catalog(self) -> tuple[list[_LocalModel], list[str]]:
        """Return verified local completion models and any per-model discovery warnings."""
        summaries = self._tags()
        if not summaries:
            return [], []

        def inspect(summary: dict[str, Any]) -> tuple[_LocalModel | None, str | None]:
            name = summary.get("name")
            label = name if isinstance(name, str) and name else "unnamed model"
            try:
                return self._inspect_model(summary), None
            except OllamaModelUnavailableError:
                return None, None
            except OllamaError as error:
                return None, f"Skipped {label}: {error}"

        worker_count = min(_MAX_SHOW_WORKERS, len(summaries))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            inspected = list(executor.map(inspect, summaries))
        models = [model for model, _ in inspected if model is not None]
        warnings = [warning for _, warning in inspected if warning is not None]
        return models, warnings

    def chat(
        self,
        model: _LocalModel,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 8192, "num_predict": 2048},
        }
        if model.can_disable_thinking:
            payload["think"] = False
        return self._request_json("/chat", payload)


def _recommendations(installed_names: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": description,
            "size_gb": size_gb,
            "source_url": f"https://ollama.com/library/{name}",
            "installed": name in installed_names,
        }
        for name, description, size_gb in _RECOMMENDATIONS
    ]


def get_ollama_model_catalog(
    *, timeout: float = DEFAULT_DISCOVERY_TIMEOUT
) -> dict[str, bool | str | None | list[str] | list[dict[str, Any]]]:
    """Discover verified local completion models without downloading or contacting remote hosts."""
    client = OllamaClient(timeout=timeout)
    try:
        models, warnings = client.catalog()
    except OllamaError as error:
        return {
            "available": False,
            "models": [],
            "recommended": _recommendations(set()),
            "error": str(error),
            "warnings": [],
        }

    model_rows = [
        {
            "name": model.name,
            "size": model.size,
            "parameter_size": model.parameter_size,
            "quantization_level": model.quantization_level,
        }
        for model in models
    ]
    return {
        "available": True,
        "models": model_rows,
        "recommended": _recommendations({model.name for model in models}),
        "error": None,
        "warnings": warnings,
    }


class OllamaBackend(LLMBackend):
    """LLM backend that uses an installed local Ollama completion model only."""

    def __init__(self, model: str, timeout: float = DEFAULT_GENERATION_TIMEOUT) -> None:
        self._model = model
        self._client = OllamaClient(timeout=timeout)

    def is_available(self) -> bool:
        try:
            self._client.validate_model(self._model)
        except OllamaError as error:
            logger.warning("Ollama model is not available: %s", error)
            return False
        return True

    def generate(self, system_prompt: str, user_prompt: str) -> RefinementResult:
        model = self._client.validate_model(self._model)
        response = self._client.chat(model, system_prompt, user_prompt)
        if _is_remote_model(response):
            raise OllamaModelUnavailableError(
                f"Model '{model.name}' was routed remotely and cannot be used for local refinement."
            )
        message = response.get("message")
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise OllamaResponseError("Ollama returned a chat response without text content.")
        tokens = 0
        for field in ("prompt_eval_count", "eval_count"):
            value = response.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                tokens += value
        return RefinementResult(text=text, model=model.name, tokens_used=tokens)


__all__ = [
    "OllamaBackend",
    "OllamaError",
    "OllamaModelUnavailableError",
    "OllamaResponseError",
    "OllamaTimeoutError",
    "OllamaUnavailableError",
    "get_ollama_model_catalog",
]
