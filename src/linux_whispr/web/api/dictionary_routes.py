"""Dictionary API routes."""

from __future__ import annotations

import ipaddress
import json
import secrets
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path, PurePath
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from linux_whispr.config import AppConfig

from linux_whispr.features.community_dictionary import (
    MAX_IMPORT_BYTES,
    CommunityDictionaryConflict,
    CommunityDictionaryError,
    dictionary_schema,
    parse_dictionary_document,
)
from linux_whispr.features.community_dictionary_import import (
    DictionarySourceError,
    fetch_dictionary_source,
    is_dictionary_source_input_error,
)
from linux_whispr.features.dictionary import CorrectionPair, Dictionary

router = APIRouter(tags=["dictionary"])

_PREVIEW_TTL_SECONDS = 10 * 60
_MAX_PENDING_PREVIEWS = 32
# JSON escapes may use six bytes for each decoded content byte (for example,
# control characters). Retain a small envelope allowance while bounding the
# stream separately from the decoded 1 MiB content limit.
_MAX_IMPORT_REQUEST_BYTES = MAX_IMPORT_BYTES * 6 + 8 * 1024
_MAX_CONFIRM_REQUEST_BYTES = 8 * 1024


class AddWordRequest(BaseModel):
    word: str
    source: str = "manual"
    category: str = "general"
    aliases: list[str] | None = None


class SetPackEnabledRequest(BaseModel):
    enabled: bool


@dataclass(frozen=True)
class _DictionaryTarget:
    """The application and storage target a preview is authorized to change."""

    application: object
    provider: object | None
    dictionary: Dictionary | None
    storage_path: str


@dataclass(frozen=True)
class _PendingPreview:
    document: dict[str, object]
    source: dict[str, object]
    revision: str
    pack_id: str | None
    target: _DictionaryTarget
    has_conflicts: bool
    expires_at: float


class _PreviewRegistry:
    """Bounded, one-use storage for the exact preview a user reviewed."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pending: OrderedDict[str, _PendingPreview] = OrderedDict()

    def create(
        self,
        *,
        document: dict[str, object],
        source: dict[str, object],
        revision: str,
        pack_id: str | None,
        target: _DictionaryTarget,
        has_conflicts: bool,
    ) -> str:
        now = time.monotonic()
        with self._lock:
            self._discard_expired(now)
            if len(self._pending) >= _MAX_PENDING_PREVIEWS:
                self._pending.popitem(last=False)
            token = secrets.token_urlsafe(32)
            while token in self._pending:
                token = secrets.token_urlsafe(32)
            self._pending[token] = _PendingPreview(
                document=deepcopy(document),
                source=deepcopy(source),
                revision=revision,
                pack_id=pack_id,
                target=target,
                has_conflicts=has_conflicts,
                expires_at=now + _PREVIEW_TTL_SECONDS,
            )
            return token

    def consume(self, token: str, *, acknowledge_conflicts: bool) -> _PendingPreview:
        now = time.monotonic()
        with self._lock:
            self._discard_expired(now)
            preview = self._pending.get(token)
            if preview is None:
                raise CommunityDictionaryConflict(
                    "This import preview has expired or was already confirmed."
                )
            if preview.has_conflicts and not acknowledge_conflicts:
                raise CommunityDictionaryConflict(
                    "Acknowledge the listed dictionary conflicts before confirming."
                )
            # Pop while locked so only a single concurrent confirmation reaches
            # persistence, even if the dictionary provider is shared.
            return self._pending.pop(token)

    def _discard_expired(self, now: float) -> None:
        expired = [token for token, preview in self._pending.items() if preview.expires_at <= now]
        for token in expired:
            self._pending.pop(token, None)


_preview_registry = _PreviewRegistry()
_dictionary_mutation_lock = threading.RLock()


def _get_dictionary(request: Request) -> Dictionary:
    provider = getattr(request.app.state, "dictionary_provider", None)
    if provider is not None:
        if not callable(provider):
            raise RuntimeError("Configured dictionary provider is not callable.")
        dictionary = provider()
        if not isinstance(dictionary, Dictionary):
            raise RuntimeError("Configured dictionary provider returned an invalid value.")
        return dictionary

    dictionary = Dictionary()
    dictionary.load()
    return dictionary


def _promotion_threshold(request: Request) -> int:
    """Return the policy used by the active dictionary correction runtime."""
    dictionary_provider = getattr(request.app.state, "dictionary_provider", None)
    provider = getattr(request.app.state, "dictionary_promotion_threshold_provider", None)
    if provider is not None:
        if not callable(provider):
            raise RuntimeError("Configured promotion threshold provider is not callable.")
        return provider()
    if dictionary_provider is not None:
        return 2
    return AppConfig.load().adaptive.promotion_threshold


def _dictionary_target(request: Request, dictionary: Dictionary) -> _DictionaryTarget:
    """Capture a non-public identity for the active dictionary storage target."""
    provider = getattr(request.app.state, "dictionary_provider", None)
    path = getattr(dictionary, "_path", None)
    if not isinstance(path, Path):
        raise RuntimeError("Configured dictionary has no persistent storage path.")
    return _DictionaryTarget(
        application=request.app,
        provider=provider,
        # A live provider must return the same instance that produced the
        # review; standalone requests intentionally reconstruct from disk.
        dictionary=dictionary if provider is not None else None,
        storage_path=str(path.expanduser().resolve()),
    )


def _add_personal_word(request: Request, req: AddWordRequest) -> None:
    with _dictionary_mutation_lock:
        _get_dictionary(request).add_word(
            req.word, source=req.source, category=req.category, aliases=req.aliases
        )


def _remove_personal_word(request: Request, word: str) -> bool:
    with _dictionary_mutation_lock:
        return _get_dictionary(request).remove_word(word)


def _remove_personal_correction(request: Request, index: int) -> CorrectionPair | None:
    with _dictionary_mutation_lock:
        return _get_dictionary(request).remove_correction(index)


def _set_dictionary_pack_enabled(request: Request, pack_id: str, enabled: bool) -> None:
    with _dictionary_mutation_lock:
        _get_dictionary(request).set_pack_enabled(pack_id, enabled)


def _confirm_community_pack(request: Request, token: str, acknowledge_conflicts: bool) -> str:
    with _dictionary_mutation_lock:
        pending = _preview_registry.consume(token, acknowledge_conflicts=acknowledge_conflicts)
        # Standalone requests each construct a fresh Dictionary. Resolving it
        # under this lock forces a latest-disk snapshot before Core compares the
        # reviewed revision and persists the update.
        dictionary = _get_dictionary(request)
        target = _dictionary_target(request, dictionary)
        if (
            pending.target.application is not target.application
            or pending.target.provider is not target.provider
            or pending.target.dictionary is not target.dictionary
            or pending.target.storage_path != target.storage_path
        ):
            raise CommunityDictionaryConflict(
                "This import preview no longer targets the active dictionary."
            )
        return dictionary.install_community_pack(
            pending.document,
            source=pending.source,
            expected_revision=pending.revision,
            pack_id=pending.pack_id,
            promotion_threshold=_promotion_threshold(request),
        )


def _remove_community_pack(request: Request, pack_id: str) -> bool:
    with _dictionary_mutation_lock:
        dictionary = _get_dictionary(request)
        if dictionary.community_pack_metadata(pack_id) is None:
            return False
        return dictionary.remove_community_pack(pack_id)


def _public_source(source: object) -> dict[str, str]:
    """Return only presentation-safe provenance, never a local source path."""
    if not isinstance(source, dict):
        return {"kind": "file", "filename": ""}
    kind = source.get("kind")
    filename = source.get("filename")
    result = {
        "kind": kind if kind in {"file", "url"} else "file",
        "filename": _safe_filename(filename) if isinstance(filename, str) else "",
    }
    if result["kind"] == "url" and isinstance(source.get("url"), str):
        result["url"] = source["url"]
    return result


def _pack_response(dictionary: Dictionary) -> list[dict[str, object]]:
    packs: list[dict[str, object]] = []
    for pack in dictionary.pack_catalog():
        response: dict[str, object] = {
            "id": pack.id,
            "name": pack.name,
            "description": pack.description,
            "enabled": dictionary.is_pack_enabled(pack.id),
            "term_count": len(pack.terms),
            "alias_count": sum(len(term.aliases) for term in pack.terms),
            "terms": [{"word": term.word, "aliases": list(term.aliases)} for term in pack.terms],
            "sources": [{"title": title, "url": url} for title, url in pack.sources],
            "kind": "bundled",
        }
        metadata = dictionary.community_pack_metadata(pack.id)
        if metadata is not None:
            document = metadata.get("document")
            response["kind"] = "community"
            response["document_id"] = document.get("id") if isinstance(document, dict) else None
            response["license"] = document.get("license") if isinstance(document, dict) else None
            response["author"] = document.get("author") if isinstance(document, dict) else None
            response["source"] = _public_source(metadata.get("source"))
            response["content_hash"] = metadata.get("content_hash")
        packs.append(response)
    return packs


def _safe_filename(filename: str) -> str:
    """Retain a display filename while dropping both POSIX and Windows paths."""
    return PurePath(filename.replace("\\", "/")).name


def _validate_filename(value: object, *, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="filename must be a string.")
    filename = _safe_filename(value.strip())
    if (
        not filename
        or filename in {".", ".."}
        or len(filename) > 255
        or any(ord(character) < 32 for character in filename)
    ):
        raise HTTPException(status_code=400, detail="filename must be a safe filename.")
    return filename


def _validate_pack_id(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 128
    ):
        raise HTTPException(status_code=400, detail="pack_id must be a non-empty string.")
    return value


def _validate_remote_url_input(url: str) -> None:
    """Reject malformed or non-public URL syntax before starting a fetch."""
    if len(url) > 2_048 or url != url.strip() or any(ord(character) < 32 for character in url):
        raise HTTPException(status_code=400, detail="The dictionary URL is invalid.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise HTTPException(
            status_code=400, detail="The dictionary URL has an invalid port."
        ) from error
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Only public HTTPS URLs are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(status_code=400, detail="Dictionary URLs must not include credentials.")
    if port not in (None, 443):
        raise HTTPException(status_code=400, detail="Dictionary URLs must use HTTPS port 443.")
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return
    raise HTTPException(
        status_code=400,
        detail="Dictionary URLs must use a public hostname, not an IP address.",
    )


def _require_same_origin_json(request: Request) -> None:
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().casefold() != "application/json":
        raise HTTPException(status_code=400, detail="Content-Type must be application/json.")

    supplied_origin = request.headers.get("origin") or request.headers.get("referer")
    if not supplied_origin:
        raise HTTPException(status_code=400, detail="A same-origin request is required.")
    try:
        origin = urlsplit(supplied_origin)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="A same-origin request is required.") from error
    request_url = request.url
    if (
        origin.scheme not in {"http", "https"}
        or origin.scheme != request_url.scheme
        or origin.netloc != request_url.netloc
    ):
        raise HTTPException(status_code=400, detail="A same-origin request is required.")


async def _read_json_object(request: Request, *, maximum_bytes: int) -> dict[str, object]:
    """Validate origin and bound untrusted JSON before parsing it."""
    _require_same_origin_json(request)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.") from error
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.")
        if declared_length > maximum_bytes:
            raise HTTPException(status_code=413, detail="Request body is too large.")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > maximum_bytes:
            raise HTTPException(status_code=413, detail="Request body is too large.")
        body.extend(chunk)
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="Request body must be JSON.") from error
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object.")
    return decoded


def _require_exact_fields(data: dict[str, object], allowed: set[str]) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported request field: {sorted(unknown)[0]}.",
        )


def _remote_error(error: DictionarySourceError) -> HTTPException:
    detail = str(error) or "The remote dictionary source could not be retrieved."
    if is_dictionary_source_input_error(error):
        return HTTPException(status_code=400, detail=detail)
    status_code = 504 if "timed out" in detail.casefold() or "timeout" in detail.casefold() else 502
    return HTTPException(status_code=status_code, detail=detail)


async def _make_preview(
    request: Request,
    dictionary: Dictionary,
    *,
    target: _DictionaryTarget,
    content: str,
    filename: str,
    source: dict[str, object],
    pack_id: str | None,
) -> dict[str, object]:
    try:
        document, _ = await run_in_threadpool(parse_dictionary_document, content, filename)
        preview = await run_in_threadpool(
            dictionary.preview_community_pack,
            document,
            source=source,
            pack_id=pack_id,
            promotion_threshold=_promotion_threshold(request),
        )
    except CommunityDictionaryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CommunityDictionaryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    revision = preview.get("revision")
    if not isinstance(revision, str):
        raise HTTPException(status_code=400, detail="Dictionary preview could not be created.")
    conflicts = preview.get("conflicts")
    token = _preview_registry.create(
        document=document,
        source=source,
        revision=revision,
        pack_id=pack_id,
        target=target,
        has_conflicts=isinstance(conflicts, list) and bool(conflicts),
    )
    return {"status": "ok", "kind": "preview", "token": token, "preview": preview}


@router.get("/dictionary")
async def get_dictionary(request: Request) -> dict[str, object]:
    """Get personal dictionary data and the bundled plus community pack catalog."""
    dictionary = _get_dictionary(request)
    return {
        "entries": [asdict(entry) for entry in dictionary.entries],
        "corrections": [asdict(correction) for correction in dictionary.corrections],
        "packs": _pack_response(dictionary),
    }


@router.get("/dictionary/schema")
async def get_dictionary_schema() -> dict[str, object]:
    """Publish the accepted versioned community dictionary schema."""
    return dictionary_schema()


@router.post("/dictionary/words")
async def add_word(req: AddWordRequest, request: Request) -> dict[str, str]:
    """Add a personal word or update aliases for an existing personal word."""
    await run_in_threadpool(_add_personal_word, request, req)
    return {"status": "ok", "message": f"Word '{req.word}' added"}


@router.delete("/dictionary/words/{word}")
async def remove_word(word: str, request: Request) -> dict[str, str]:
    """Remove a personal dictionary word."""
    removed = await run_in_threadpool(_remove_personal_word, request, word)
    if removed:
        return {"status": "ok", "message": f"Word '{word}' removed"}
    return {"status": "error", "message": f"Word '{word}' not found"}


@router.delete("/dictionary/corrections/{index}")
async def remove_correction(index: int, request: Request) -> dict[str, str]:
    """Remove a correction by index."""
    removed = await run_in_threadpool(_remove_personal_correction, request, index)
    if removed is not None:
        return {
            "status": "ok",
            "message": f"Correction '{removed.heard} → {removed.corrected}' removed",
        }
    return {"status": "error", "message": "Invalid correction index"}


@router.put("/dictionary/packs/{pack_id}")
async def set_pack_enabled(
    pack_id: str, req: SetPackEnabledRequest, request: Request
) -> dict[str, str]:
    """Persist a pack selection without changing personal dictionary data."""
    try:
        await run_in_threadpool(_set_dictionary_pack_enabled, request, pack_id, req.enabled)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail=f"Unknown dictionary pack '{pack_id}'."
        ) from error
    return {"status": "ok"}


@router.post("/dictionary/import/preview")
async def preview_dictionary_import(request: Request) -> dict[str, object]:
    """Parse and review a local dictionary document or public HTTPS source."""
    data = await _read_json_object(request, maximum_bytes=_MAX_IMPORT_REQUEST_BYTES)
    _require_exact_fields(data, {"content", "filename", "url", "pack_id"})
    has_content = "content" in data
    has_url = "url" in data
    if has_content == has_url:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of content or url.",
        )
    pack_id = _validate_pack_id(data.get("pack_id"))
    dictionary = _get_dictionary(request)
    target = _dictionary_target(request, dictionary)

    if has_content:
        content = data["content"]
        if not isinstance(content, str):
            raise HTTPException(status_code=400, detail="content must be a string.")
        filename = _validate_filename(data.get("filename"), required=True)
        assert filename is not None
        try:
            content.encode("utf-8", "strict")
        except UnicodeEncodeError as error:
            raise HTTPException(
                status_code=400, detail="content must be valid UTF-8 text."
            ) from error
        if len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="Dictionary content exceeds 1 MiB.")
        return await _make_preview(
            request,
            dictionary,
            target=target,
            content=content,
            filename=filename,
            source={"kind": "file", "filename": filename},
            pack_id=pack_id,
        )

    url = data["url"]
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=400, detail="url must be a non-empty string.")
    _validate_remote_url_input(url)
    filename = _validate_filename(data.get("filename"), required=False)
    try:
        result = await run_in_threadpool(fetch_dictionary_source, url, filename)
    except DictionarySourceError as error:
        raise _remote_error(error) from error
    if result.get("kind") == "selection":
        return {
            "status": "ok",
            "kind": "selection",
            "source_url": result["source_url"],
            "files": result["files"],
        }
    if result.get("kind") != "file":
        raise HTTPException(status_code=502, detail="The remote dictionary response was invalid.")
    return await _make_preview(
        request,
        dictionary,
        target=target,
        content=result["content"],
        filename=result["filename"],
        source=result["source"],
        pack_id=pack_id,
    )


@router.post("/dictionary/packs/{pack_id}/check-update")
async def check_dictionary_pack_update(pack_id: str, request: Request) -> dict[str, object]:
    """Fetch a community URL source and return a reviewed update preview."""
    _require_same_origin_json(request)
    dictionary = _get_dictionary(request)
    target = _dictionary_target(request, dictionary)
    metadata = dictionary.community_pack_metadata(pack_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Community dictionary pack was not found.")
    source = metadata.get("source")
    if not isinstance(source, dict) or source.get("kind") != "url":
        raise HTTPException(
            status_code=400,
            detail="This dictionary was imported from a file; choose a replacement file.",
        )
    url = source.get("url")
    filename = source.get("filename")
    if not isinstance(url, str) or not isinstance(filename, str):
        raise HTTPException(status_code=400, detail="This dictionary source is invalid.")
    try:
        result = await run_in_threadpool(fetch_dictionary_source, url, filename)
    except DictionarySourceError as error:
        raise _remote_error(error) from error
    if result.get("kind") == "selection":
        return {
            "status": "ok",
            "kind": "selection",
            "source_url": result["source_url"],
            "files": result["files"],
        }
    if result.get("kind") != "file":
        raise HTTPException(status_code=502, detail="The remote dictionary response was invalid.")
    return await _make_preview(
        request,
        dictionary,
        target=target,
        content=result["content"],
        filename=result["filename"],
        source=result["source"],
        pack_id=pack_id,
    )


@router.post("/dictionary/import/confirm")
async def confirm_dictionary_import(request: Request) -> dict[str, str]:
    """Persist one exact, still-current preview without fetching it again."""
    data = await _read_json_object(request, maximum_bytes=_MAX_CONFIRM_REQUEST_BYTES)
    _require_exact_fields(data, {"token", "acknowledge_conflicts"})
    token = data.get("token")
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=400, detail="token must be a non-empty string.")
    acknowledge_conflicts = data.get("acknowledge_conflicts", False)
    if not isinstance(acknowledge_conflicts, bool):
        raise HTTPException(status_code=400, detail="acknowledge_conflicts must be a boolean.")
    try:
        pack_id = await run_in_threadpool(
            _confirm_community_pack,
            request,
            token,
            acknowledge_conflicts,
        )
    except CommunityDictionaryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CommunityDictionaryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(
            status_code=500, detail="The community dictionary could not be saved."
        ) from error
    return {"status": "ok", "pack_id": pack_id}


@router.delete("/dictionary/packs/{pack_id}")
async def delete_community_dictionary_pack(pack_id: str, request: Request) -> dict[str, str]:
    """Remove one persisted community pack while preserving bundled packs."""
    _require_same_origin_json(request)
    try:
        removed = await run_in_threadpool(_remove_community_pack, request, pack_id)
    except OSError as error:
        raise HTTPException(
            status_code=500, detail="The community dictionary could not be removed."
        ) from error
    if not removed:
        raise HTTPException(status_code=404, detail="Community dictionary pack was not found.")
    return {"status": "ok"}
