"""Focused API contract tests for community dictionary imports."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from linux_whispr.features.community_dictionary import CommunityDictionaryConflict
from linux_whispr.features.community_dictionary_import import DictionarySourceError
from linux_whispr.features.dictionary import Dictionary
from linux_whispr.features.dictionary_packs import DictionaryPack, PackTerm
from linux_whispr.web.api import dictionary_routes



_DEFAULT_APPLICATION = SimpleNamespace(
    state=SimpleNamespace(dictionary_provider=None)
)

def _request(
    payload: dict[str, object],
    *,
    method: str = "POST",
    application: object = _DEFAULT_APPLICATION,
) -> Request:
    """Build a same-origin JSON request without starting an ASGI server."""
    body = json.dumps(payload).encode("utf-8")
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": "http",
            "path": "/api/dictionary/import/preview",
            "raw_path": b"/api/dictionary/import/preview",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"origin", b"http://testserver"),
            ],
            "server": ("testserver", 80),
            "app": application,
            "client": ("testclient", 50000),
        },
        receive,
    )


async def _direct_threadpool(
    function: Callable[..., object], *args: object, **kwargs: object
) -> object:
    return function(*args, **kwargs)


class StubDictionary:
    def __init__(
        self,
        *,
        conflicts: list[dict[str, str]] | None = None,
        path: Path = Path("/tmp/linux-whispr-test-dictionary.json"),
    ) -> None:
        self._path = path
        self.conflicts = conflicts or []
        self.preview_calls: list[tuple[dict[str, object], dict[str, object], str | None]] = []
        self.preview_thresholds: list[int] = []
        self.install_calls: list[tuple[dict[str, object], dict[str, object], str, str | None]] = []
        self.install_thresholds: list[int] = []
        self.policy_sensitive_revision = False
        self.metadata: dict[str, object] | None = None
        self.install_error: Exception | None = None

    def preview_community_pack(
        self,
        document: dict[str, object],
        *,
        source: dict[str, object],
        pack_id: str | None = None,
        promotion_threshold: int = 2,
    ) -> dict[str, object]:
        self.preview_calls.append((document, source, pack_id))
        self.preview_thresholds.append(promotion_threshold)
        revision = (
            f"reviewed-revision-{promotion_threshold}"
            if self.policy_sensitive_revision
            else "reviewed-revision"
        )
        return {
            "revision": revision,
            "pack_id": pack_id,
            "document": document,
            "source": source,
            "term_count": 1,
            "alias_count": 1,
            "duplicates": 0,
            "conflicts": self.conflicts,
            "changes": {"added": [], "removed": [], "changed": []},
            "unchanged": False,
        }

    def install_community_pack(
        self,
        document: dict[str, object],
        *,
        source: dict[str, object],
        expected_revision: str,
        pack_id: str | None = None,
        promotion_threshold: int = 2,
    ) -> str:
        self.install_thresholds.append(promotion_threshold)
        if (
            self.policy_sensitive_revision
            and expected_revision != f"reviewed-revision-{promotion_threshold}"
        ):
            raise CommunityDictionaryConflict("Community dictionary preview is stale.")
        if self.install_error is not None:
            raise self.install_error
        self.install_calls.append((document, source, expected_revision, pack_id))
        return pack_id or "community-installed"

    def community_pack_metadata(self, pack_id: str) -> dict[str, object] | None:
        return self.metadata

    def remove_community_pack(self, pack_id: str) -> bool:
        return self.metadata is not None


@pytest.fixture(autouse=True)
def isolate_preview_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dictionary_routes, "_preview_registry", dictionary_routes._PreviewRegistry())
    monkeypatch.setattr(dictionary_routes, "run_in_threadpool", _direct_threadpool)


def _native_document() -> dict[str, object]:
    return {
        "format": "linux-whispr-dictionary",
        "schema_version": 1,
        "id": "community-ai",
        "name": "AI Terms",
        "entries": [{"word": "ChatGPT", "aliases": ["JetGPT"]}],
    }


@pytest.mark.asyncio
async def test_standalone_file_preview_confirms_against_fresh_dictionary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_dictionary = StubDictionary()
    current_dictionary = StubDictionary()
    dictionaries = iter((preview_dictionary, current_dictionary))
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: next(dictionaries))

    preview = await dictionary_routes.preview_dictionary_import(
        _request({"content": json.dumps(_native_document()), "filename": "terms.json"})
    )
    response = await dictionary_routes.confirm_dictionary_import(
        _request({"token": preview["token"]})
    )

    assert preview["status"] == "ok"
    assert preview["kind"] == "preview"
    assert response == {"status": "ok", "pack_id": "community-installed"}
    assert current_dictionary.install_calls == [
        (
            _native_document(),
            {"kind": "file", "filename": "terms.json"},
            "reviewed-revision",
            None,
        )
    ]


@pytest.mark.asyncio
async def test_standalone_preview_loads_the_configured_promotion_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)
    monkeypatch.setattr(
        dictionary_routes.AppConfig,
        "load",
        classmethod(
            lambda cls: SimpleNamespace(
                adaptive=SimpleNamespace(promotion_threshold=3)
            )
        ),
    )

    await dictionary_routes.preview_dictionary_import(
        _request({"content": json.dumps(_native_document()), "filename": "terms.json"})
    )

    assert dictionary.preview_thresholds == [3]


@pytest.mark.asyncio
async def test_live_provider_without_policy_uses_default_promotion_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    application = SimpleNamespace(
        state=SimpleNamespace(dictionary_provider=lambda: dictionary)
    )
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)

    preview = await dictionary_routes.preview_dictionary_import(
        _request(
            {"content": json.dumps(_native_document()), "filename": "terms.json"},
            application=application,
        )
    )
    await dictionary_routes.confirm_dictionary_import(
        _request({"token": preview["token"]}, application=application)
    )

    assert dictionary.preview_thresholds == [2]
    assert dictionary.install_thresholds == [2]



@pytest.mark.asyncio
async def test_live_policy_exposes_currently_promoted_adaptive_conflicts(
    tmp_path: Path,
) -> None:
    dictionary = Dictionary(tmp_path / "dictionary.json")
    dictionary.add_correction("JetGPT", "Personal spelling")
    application = SimpleNamespace(
        state=SimpleNamespace(
            dictionary_provider=lambda: dictionary,
            dictionary_promotion_threshold_provider=lambda: 1,
        )
    )

    response = await dictionary_routes.preview_dictionary_import(
        _request(
            {"content": json.dumps(_native_document()), "filename": "terms.json"},
            application=application,
        )
    )

    assert response["preview"]["conflicts"] == [
        {
            "alias": "JetGPT",
            "existing": "Personal spelling",
            "incoming": "ChatGPT",
            "scope": "adaptive",
        }
    ]

@pytest.mark.asyncio
async def test_changed_live_policy_rejects_community_import_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    dictionary.policy_sensitive_revision = True
    policy = {"promotion_threshold": 3}
    application = SimpleNamespace(
        state=SimpleNamespace(
            dictionary_provider=lambda: dictionary,
            dictionary_promotion_threshold_provider=lambda: policy["promotion_threshold"],
        )
    )
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)

    preview = await dictionary_routes.preview_dictionary_import(
        _request(
            {"content": json.dumps(_native_document()), "filename": "terms.json"},
            application=application,
        )
    )
    policy["promotion_threshold"] = 4

    with pytest.raises(HTTPException) as stale:
        await dictionary_routes.confirm_dictionary_import(
            _request({"token": preview["token"]}, application=application)
        )

    assert stale.value.status_code == 409
    assert dictionary.preview_thresholds == [3]
    assert dictionary.install_thresholds == [4]


@pytest.mark.asyncio
async def test_preview_token_is_bound_to_app_provider_and_dictionary_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary_a = StubDictionary(path=Path("/tmp/community-a.json"))
    dictionary_b = StubDictionary(path=Path("/tmp/community-b.json"))
    provider_a = lambda: dictionary_a
    replacement_provider = lambda: dictionary_a
    replacement_target_provider = lambda: dictionary_b
    application = SimpleNamespace(
        state=SimpleNamespace(dictionary_provider=provider_a)
    )
    other_application = SimpleNamespace(
        state=SimpleNamespace(dictionary_provider=provider_a)
    )
    monkeypatch.setattr(
        dictionary_routes,
        "_get_dictionary",
        lambda request: request.app.state.dictionary_provider(),
    )

    replacement_preview = await dictionary_routes.preview_dictionary_import(
        _request(
            {"content": json.dumps(_native_document()), "filename": "terms.json"},
            application=application,
        )
    )
    application.state.dictionary_provider = replacement_provider
    with pytest.raises(HTTPException) as replaced_provider:
        await dictionary_routes.confirm_dictionary_import(
            _request(
                {"token": replacement_preview["token"]},
                application=application,
            )
        )

    application.state.dictionary_provider = provider_a
    different_target_preview = await dictionary_routes.preview_dictionary_import(
        _request(
            {"content": json.dumps(_native_document()), "filename": "terms.json"},
            application=application,
        )
    )
    application.state.dictionary_provider = replacement_target_provider
    with pytest.raises(HTTPException) as different_target:
        await dictionary_routes.confirm_dictionary_import(
            _request(
                {"token": different_target_preview["token"]},
                application=application,
            )
        )

    application.state.dictionary_provider = provider_a
    other_app_preview = await dictionary_routes.preview_dictionary_import(
        _request(
            {"content": json.dumps(_native_document()), "filename": "terms.json"},
            application=application,
        )
    )
    with pytest.raises(HTTPException) as other_app:
        await dictionary_routes.confirm_dictionary_import(
            _request(
                {"token": other_app_preview["token"]},
                application=other_application,
            )
        )

    assert replaced_provider.value.status_code == 409
    assert different_target.value.status_code == 409
    assert other_app.value.status_code == 409
    assert dictionary_a.install_calls == []
    assert dictionary_b.install_calls == []


@pytest.mark.asyncio
async def test_preview_returns_gist_selection_without_parsing_or_creating_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)
    monkeypatch.setattr(
        dictionary_routes,
        "fetch_dictionary_source",
        lambda url, filename=None: {
            "kind": "selection",
            "source_url": "https://gist.github.com/example/abcdef",
            "files": [{"name": "ai.json", "size": 91}],
        },
    )

    response = await dictionary_routes.preview_dictionary_import(
        _request({"url": "https://gist.github.com/example/abcdef"})
    )

    assert response == {
        "status": "ok",
        "kind": "selection",
        "source_url": "https://gist.github.com/example/abcdef",
        "files": [{"name": "ai.json", "size": 91}],
    }
    assert dictionary.preview_calls == []


@pytest.mark.asyncio
async def test_conflicting_preview_requires_acknowledgement_without_losing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary(conflicts=[{"alias": "JetGPT"}])
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)
    preview = await dictionary_routes.preview_dictionary_import(
        _request({"content": json.dumps(_native_document()), "filename": "terms.json"})
    )

    with pytest.raises(HTTPException) as error:
        await dictionary_routes.confirm_dictionary_import(_request({"token": preview["token"]}))

    confirmed = await dictionary_routes.confirm_dictionary_import(
        _request({"token": preview["token"], "acknowledge_conflicts": True})
    )

    assert error.value.status_code == 409
    assert confirmed == {"status": "ok", "pack_id": "community-installed"}
    assert len(dictionary.install_calls) == 1


@pytest.mark.asyncio
async def test_concurrent_confirmation_consumes_preview_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)
    preview = await dictionary_routes.preview_dictionary_import(
        _request({"content": json.dumps(_native_document()), "filename": "terms.json"})
    )

    async def confirm() -> int:
        try:
            await dictionary_routes.confirm_dictionary_import(_request({"token": preview["token"]}))
        except HTTPException as error:
            return error.status_code
        return 200

    statuses = await asyncio.gather(confirm(), confirm())

    assert sorted(statuses) == [200, 409]
    assert len(dictionary.install_calls) == 1


@pytest.mark.asyncio
async def test_confirm_surfaces_stale_revision_and_cannot_reuse_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    dictionary.install_error = CommunityDictionaryConflict("Dictionary changed since preview.")
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)
    preview = await dictionary_routes.preview_dictionary_import(
        _request({"content": json.dumps(_native_document()), "filename": "terms.json"})
    )

    with pytest.raises(HTTPException) as stale:
        await dictionary_routes.confirm_dictionary_import(_request({"token": preview["token"]}))
    with pytest.raises(HTTPException) as reused:
        await dictionary_routes.confirm_dictionary_import(_request({"token": preview["token"]}))

    assert stale.value.status_code == 409
    assert reused.value.status_code == 409


@pytest.mark.asyncio
async def test_check_update_previews_then_applies_real_pack_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dictionary = Dictionary(tmp_path / "dictionary.json")
    application = SimpleNamespace(
        state=SimpleNamespace(dictionary_provider=lambda: dictionary)
    )
    source = {
        "kind": "url",
        "url": "https://example.com/terms.json",
        "filename": "terms.json",
    }
    original = {
        "format": "linux-whispr-dictionary",
        "schema_version": 1,
        "id": "community-ai",
        "name": "AI Terms",
        "entries": [
            {"word": "Changed term", "aliases": ["old pronunciation"]},
            {"word": "Removed term", "aliases": ["removed pronunciation"]},
            {"word": "Unchanged term", "aliases": ["same pronunciation"]},
        ],
    }
    original_preview = dictionary.preview_community_pack(original, source=source)
    target_pack_id = dictionary.install_community_pack(
        original, source=source, expected_revision=original_preview["revision"]
    )
    other_document = {
        "format": "linux-whispr-dictionary",
        "schema_version": 1,
        "id": "community-other",
        "name": "Other Terms",
        "entries": [{"word": "Other term", "aliases": ["other pronunciation"]}],
    }
    other_preview = dictionary.preview_community_pack(other_document, source=source)
    other_pack_id = dictionary.install_community_pack(
        other_document, source=source, expected_revision=other_preview["revision"]
    )
    dictionary.set_pack_enabled(target_pack_id, False)
    replacement = {
        "format": "linux-whispr-dictionary",
        "schema_version": 1,
        "id": "community-ai",
        "name": "AI Terms",
        "entries": [
            {"word": "Changed term", "aliases": ["new pronunciation"]},
            {"word": "Unchanged term", "aliases": ["same pronunciation"]},
            {"word": "Added term", "aliases": ["added pronunciation"]},
        ],
    }
    monkeypatch.setattr(
        dictionary_routes,
        "fetch_dictionary_source",
        lambda _url, _filename=None: {
            "kind": "file",
            "content": json.dumps(replacement),
            "filename": "terms.json",
            "source": source,
        },
    )

    preview = await dictionary_routes.check_dictionary_pack_update(
        target_pack_id, _request({}, method="POST", application=application)
    )

    assert preview["preview"]["changes"] == {
        "added": [{"word": "Added term", "aliases": ["added pronunciation"]}],
        "removed": [{"word": "Removed term", "aliases": ["removed pronunciation"]}],
        "changed": [
            {
                "before": {
                    "word": "Changed term",
                    "aliases": ["old pronunciation"],
                },
                "after": {
                    "word": "Changed term",
                    "aliases": ["new pronunciation"],
                },
            }
        ],
    }
    assert dictionary.community_pack_metadata(target_pack_id)["document"] == original
    assert next(
        pack for pack in dictionary.pack_catalog() if pack.id == target_pack_id
    ).terms == (
        PackTerm("Changed term", ("old pronunciation",)),
        PackTerm("Removed term", ("removed pronunciation",)),
        PackTerm("Unchanged term", ("same pronunciation",)),
    )
    assert not dictionary.is_pack_enabled(target_pack_id)

    confirmed = await dictionary_routes.confirm_dictionary_import(
        _request(
            {"token": preview["token"]},
            method="POST",
            application=application,
        )
    )

    assert confirmed == {"status": "ok", "pack_id": target_pack_id}
    assert not dictionary.is_pack_enabled(target_pack_id)
    assert next(
        pack for pack in dictionary.pack_catalog() if pack.id == target_pack_id
    ).terms == (
        PackTerm("Changed term", ("new pronunciation",)),
        PackTerm("Unchanged term", ("same pronunciation",)),
        PackTerm("Added term", ("added pronunciation",)),
    )
    assert dictionary.community_pack_metadata(other_pack_id)["document"] == other_document


@pytest.mark.asyncio
async def test_preview_rejects_cross_origin_and_oversized_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)
    request = _request({"content": "{}", "filename": "terms.json"})
    request.scope["headers"] = [
        (b"content-type", b"application/json"),
        (b"origin", b"https://attacker.invalid"),
    ]

    with pytest.raises(HTTPException) as cross_origin:
        await dictionary_routes.preview_dictionary_import(request)

    oversized = _request({"content": "{}", "filename": "terms.json"})
    oversized.scope["headers"] = [
        (b"content-type", b"application/json"),
        (b"origin", b"http://testserver"),
        (
            b"content-length",
            str(dictionary_routes._MAX_IMPORT_REQUEST_BYTES + 1).encode("ascii"),
        ),
    ]
    with pytest.raises(HTTPException) as too_large:
        await dictionary_routes.preview_dictionary_import(oversized)

    malformed_origin = _request({"content": "{}", "filename": "terms.json"})
    malformed_origin.scope["headers"] = [
        (b"content-type", b"application/json"),
        (b"origin", b"http://["),
    ]
    with pytest.raises(HTTPException) as malformed:
        await dictionary_routes.preview_dictionary_import(malformed_origin)

    assert cross_origin.value.status_code == 400
    assert too_large.value.status_code == 413
    assert malformed.value.status_code == 400


@pytest.mark.asyncio
async def test_preview_accepts_large_ascii_escaped_unicode_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)
    content = "\n".join(f"{'é' * 100}{index:04d}" for index in range(4_000))
    payload = {"content": content, "filename": "terms.csv"}

    assert len(content.encode("utf-8")) <= dictionary_routes.MAX_IMPORT_BYTES
    assert (
        len(json.dumps(payload).encode("utf-8"))
        > dictionary_routes.MAX_IMPORT_BYTES * 2 + 8 * 1024
    )

    response = await dictionary_routes.preview_dictionary_import(_request(payload))

    assert response["status"] == "ok"
    assert response["kind"] == "preview"


def test_pack_response_distinguishes_bundled_and_community_provenance() -> None:
    bundled = DictionaryPack(
        id="bundled",
        name="Bundled",
        description="Built in",
        terms=(PackTerm("Bundled term"),),
        sources=(("Project", "https://example.com/project"),),
    )
    community = DictionaryPack(
        id="community-123",
        name="Imported",
        description="Imported pack",
        terms=(PackTerm("ChatGPT", ("JetGPT",)),),
        sources=(("Publisher", "https://example.com/source"),),
    )

    class CatalogDictionary:
        def pack_catalog(self) -> tuple[DictionaryPack, ...]:
            return (bundled, community)

        def is_pack_enabled(self, pack_id: str) -> bool:
            return pack_id == "community-123"

        def community_pack_metadata(self, pack_id: str) -> dict[str, object] | None:
            if pack_id != "community-123":
                return None
            return {
                "document": {
                    "id": "publisher-ai",
                    "license": "CC0-1.0",
                    "author": "Publisher",
                },
                "source": {
                    "kind": "file",
                    "filename": "/private/path/terms.json",
                },
                "content_hash": "content-hash",
            }

    packs = dictionary_routes._pack_response(CatalogDictionary())  # type: ignore[arg-type]

    assert packs[0]["kind"] == "bundled"
    assert packs[1] == {
        "id": "community-123",
        "name": "Imported",
        "description": "Imported pack",
        "enabled": True,
        "term_count": 1,
        "alias_count": 1,
        "terms": [{"word": "ChatGPT", "aliases": ["JetGPT"]}],
        "sources": [{"title": "Publisher", "url": "https://example.com/source"}],
        "kind": "community",
        "document_id": "publisher-ai",
        "license": "CC0-1.0",
        "author": "Publisher",
        "source": {"kind": "file", "filename": "terms.json"},
        "content_hash": "content-hash",
    }


@pytest.mark.asyncio
async def test_delete_rejects_bundled_or_missing_community_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)

    with pytest.raises(HTTPException) as error:
        await dictionary_routes.delete_community_dictionary_pack(
            "coding", _request({}, method="DELETE")
        )

    assert error.value.status_code == 404


def test_preview_registry_expires_and_evicts_oldest_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = dictionary_routes._PreviewRegistry()
    now = 100.0
    monkeypatch.setattr(dictionary_routes.time, "monotonic", lambda: now)
    target = dictionary_routes._DictionaryTarget(
        _DEFAULT_APPLICATION,
        None,
        None,
        "/tmp/linux-whispr-test-dictionary.json",
    )
    first = registry.create(
        document=_native_document(),
        source={"kind": "file", "filename": "terms.json"},
        revision="r1",
        pack_id=None,
        target=target,
        has_conflicts=False,
    )
    for index in range(dictionary_routes._MAX_PENDING_PREVIEWS):
        registry.create(
            document=_native_document(),
            source={"kind": "file", "filename": f"terms-{index}.json"},
            revision=f"r{index}",
            pack_id=None,
            target=target,
            has_conflicts=False,
        )

    with pytest.raises(CommunityDictionaryConflict):
        registry.consume(first, acknowledge_conflicts=False)

    expired = registry.create(
        document=_native_document(),
        source={"kind": "file", "filename": "expiry.json"},
        revision="expiry",
        pack_id=None,
        has_conflicts=False,
        target=target,
    )
    now += dictionary_routes._PREVIEW_TTL_SECONDS + 1
    with pytest.raises(CommunityDictionaryConflict):
        registry.consume(expired, acknowledge_conflicts=False)


@pytest.mark.asyncio
async def test_url_input_errors_are_client_errors_and_timeouts_are_gateway_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dictionary = StubDictionary()
    monkeypatch.setattr(dictionary_routes, "_get_dictionary", lambda request: dictionary)

    monkeypatch.setattr(
        dictionary_routes,
        "fetch_dictionary_source",
        lambda url, filename=None: (_ for _ in ()).throw(
            DictionarySourceError("The selected Gist file was not found.", input_error=True)
        ),
    )
    with pytest.raises(HTTPException) as invalid:
        await dictionary_routes.preview_dictionary_import(
            _request(
                {
                    "url": "https://gist.github.com/example/abcdef",
                    "filename": "terms.json",
                }
            )
        )

    monkeypatch.setattr(
        dictionary_routes,
        "fetch_dictionary_source",
        lambda url, filename=None: (_ for _ in ()).throw(
            DictionarySourceError("Timed out while retrieving the dictionary source.")
        ),
    )
    with pytest.raises(HTTPException) as timeout:
        await dictionary_routes.preview_dictionary_import(
            _request({"url": "https://example.com/terms.json"})
        )

    assert invalid.value.status_code == 400
    assert timeout.value.status_code == 504
