"""Security and contract tests for community dictionary URL retrieval."""

from __future__ import annotations

import socket
from collections.abc import Callable

import pytest

from linux_whispr.features import community_dictionary_import as source_import


class _Response:
    def __init__(
        self,
        body: bytes = b"",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.headers = headers or {}
        self.read_sizes: list[int] = []
        self.closed = False

    def getheader(self, name: str) -> str | None:
        for header_name, value in self.headers.items():
            if header_name.lower() == name.lower():
                return value
        return None

    def read(self, amount: int) -> bytes:
        self.read_sizes.append(amount)
        return self.body[:amount]

    def close(self) -> None:
        self.closed = True


class _Connection:
    responses: list[_Response] = []
    calls: list[tuple[str, int, str, float, str, str, dict[str, str]]] = []

    def __init__(self, hostname: str, port: int, address: str, timeout: float) -> None:
        self.hostname = hostname
        self.port = port
        self.address = address
        self.timeout = timeout

    def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
        self.calls.append(
            (self.hostname, self.port, self.address, self.timeout, method, target, headers)
        )

    def getresponse(self) -> _Response:
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def _transport(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[_Response],
    resolver: Callable[[str, int], list[str]] | None = None,
) -> None:
    _Connection.responses = responses.copy()
    _Connection.calls = []
    monkeypatch.setattr(source_import, "_PinnedHTTPSConnection", _Connection)
    monkeypatch.setattr(
        source_import,
        "_resolve_public_addresses",
        resolver or (lambda hostname, port: ["8.8.8.8"]),
    )


def test_fetch_pins_the_single_validated_resolution_and_preserves_original_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def rebinding_resolver(hostname: str, port: int) -> list[str]:
        nonlocal calls
        calls += 1
        assert (hostname, port) == ("dictionary.example", 443)
        if calls > 1:
            raise AssertionError("the importer must not resolve again after validation")
        return ["8.8.8.8"]

    _transport(monkeypatch, [_Response(b'{"entries": []}')], rebinding_resolver)

    result = source_import._fetch_dictionary_source("https://dictionary.example/packs/words.json")

    assert result == {
        "kind": "file",
        "content": '{"entries": []}',
        "filename": "words.json",
        "source": {
            "kind": "url",
            "url": "https://dictionary.example/packs/words.json",
            "filename": "words.json",
        },
    }
    assert calls == 1
    assert _Connection.calls[0][0:5] == ("dictionary.example", 443, "8.8.8.8", 10.0, "GET")
    assert _Connection.calls[0][5] == "/packs/words.json"


def test_pinned_connection_opens_numeric_socket_but_keeps_hostname_for_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.timeout: float | None = None
            self.destination: tuple[object, ...] | None = None
            self.closed = False

        def settimeout(self, timeout: float) -> None:
            self.timeout = timeout

        def connect(self, destination: tuple[object, ...]) -> None:
            self.destination = destination

        def close(self) -> None:
            self.closed = True

    class FakeTlsContext:
        def __init__(self) -> None:
            self.server_hostname: str | None = None

        def wrap_socket(self, raw_socket: FakeSocket, *, server_hostname: str) -> str:
            self.server_hostname = server_hostname
            return "tls socket"

    fake_socket = FakeSocket()
    context = FakeTlsContext()
    monkeypatch.setattr(source_import.socket, "socket", lambda *_: fake_socket)
    connection = source_import._PinnedHTTPSConnection("public.example", 443, "8.8.4.4", 3.0)
    connection._context = context  # type: ignore[assignment]

    connection.connect()

    assert fake_socket.timeout == 3.0
    assert fake_socket.destination == ("8.8.4.4", 443)
    assert context.server_hostname == "public.example"
    assert connection.sock == "tls socket"


@pytest.mark.parametrize(
    ("address", "error"),
    [
        ("127.0.0.1", "non-public"),
        ("10.0.0.1", "non-public"),
        ("240.0.0.1", "non-public"),
        ("::1", "non-public"),
        ("::ffff:127.0.0.1", "non-public"),
    ],
)
def test_resolver_rejects_private_reserved_and_ipv4_mapped_addresses(
    monkeypatch: pytest.MonkeyPatch, address: str, error: str
) -> None:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(
        source_import.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(family, socket.SOCK_STREAM, 6, "", (address, 443))],
    )

    with pytest.raises(source_import.DictionarySourceError, match=error):
        source_import._resolve_public_addresses("dictionary.example", 443)


@pytest.mark.parametrize(
    "url",
    [
        "http://dictionary.example/terms.json",
        "https://user:pass@dictionary.example/terms.json",
        "https://dictionary.example:444/terms.json",
        "https://127.0.0.1/terms.json",
        "https://[::ffff:127.0.0.1]/terms.json",
    ],
)
def test_fetch_rejects_non_public_url_forms_before_connecting(url: str) -> None:
    with pytest.raises(source_import.DictionarySourceError):
        source_import.fetch_dictionary_source(url)


def test_invalid_initial_url_is_classified_for_a_client_error() -> None:
    with pytest.raises(source_import.DictionarySourceError) as captured:
        source_import.fetch_dictionary_source("http://dictionary.example/terms.json")

    assert source_import.is_dictionary_source_input_error(captured.value)


def test_fetch_enforces_wall_clock_timeout_for_entire_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def timeout_worker(command: list[str], **kwargs: object) -> None:
        observed["command"] = command
        observed.update(kwargs)
        raise source_import.subprocess.TimeoutExpired(command, source_import.REQUEST_TIMEOUT_SECONDS)

    monkeypatch.setattr(source_import.subprocess, "run", timeout_worker)

    with pytest.raises(source_import.DictionarySourceError, match="Timed out"):
        source_import.fetch_dictionary_source("https://dictionary.example/terms.json")

    assert observed["command"] == [
        source_import.sys.executable,
        "-m",
        source_import.__name__,
        source_import._WORKER_ARGUMENT,
    ]
    assert observed["timeout"] == source_import.REQUEST_TIMEOUT_SECONDS
    assert observed["check"] is False
    assert observed["stdout"] is source_import.subprocess.PIPE
    assert observed["stderr"] is source_import.subprocess.DEVNULL


def test_redirect_revalidates_destination_and_rejects_private_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _transport(
        monkeypatch,
        [_Response(status=302, headers={"Location": "https://127.0.0.1/secret.json"})],
    )

    with pytest.raises(source_import.DictionarySourceError, match="public hostname") as captured:
        source_import._fetch_dictionary_source("https://dictionary.example/terms.json")

    assert not source_import.is_dictionary_source_input_error(captured.value)
    assert len(_Connection.calls) == 1


def test_redirect_revalidates_public_destination_without_changing_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved: list[str] = []

    def resolver(hostname: str, _port: int) -> list[str]:
        resolved.append(hostname)
        return ["8.8.8.8"]

    _transport(
        monkeypatch,
        [
            _Response(status=302, headers={"Location": "https://cdn.example/final.csv"}),
            _Response(b"word\n"),
        ],
        resolver,
    )

    result = source_import._fetch_dictionary_source("https://dictionary.example/terms.csv")

    assert result["content"] == "word\n"
    assert result["source"]["url"] == "https://dictionary.example/terms.csv"
    assert resolved == ["dictionary.example", "cdn.example"]


def test_fetch_limits_redirect_hops(monkeypatch: pytest.MonkeyPatch) -> None:
    _transport(
        monkeypatch,
        [
            _Response(status=302, headers={"Location": "https://dictionary.example/next.json"})
            for _ in range(source_import.MAX_REDIRECTS + 1)
        ],
    )

    with pytest.raises(source_import.DictionarySourceError, match="too many"):
        source_import._fetch_dictionary_source("https://dictionary.example/terms.json")

    assert len(_Connection.calls) == source_import.MAX_REDIRECTS + 1


def test_fetch_rejects_declared_and_streamed_oversize_bodies(monkeypatch: pytest.MonkeyPatch) -> None:
    _transport(
        monkeypatch,
        [_Response(headers={"content-length": str(source_import.MAX_IMPORT_BYTES + 1)})],
    )
    with pytest.raises(source_import.DictionarySourceError, match="too large"):
        source_import._fetch_dictionary_source("https://dictionary.example/terms.json")

    _transport(monkeypatch, [_Response(b"x" * (source_import.MAX_IMPORT_BYTES + 1))])
    with pytest.raises(source_import.DictionarySourceError, match="too large"):
        source_import._fetch_dictionary_source("https://dictionary.example/terms.json")


def test_github_blob_conversion_preserves_encoded_path_and_original_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def fetch_text(url: str, maximum_bytes: int) -> str:
        calls.append((url, maximum_bytes))
        return "heard,corrected\n"

    monkeypatch.setattr(source_import, "_fetch_text", fetch_text)

    result = source_import._fetch_dictionary_source(
        "https://github.com/owner/repo/blob/main/folder/My%20Dictionary.csv"
    )

    assert calls == [
        ("https://raw.githubusercontent.com/owner/repo/main/folder/My%20Dictionary.csv", source_import.MAX_IMPORT_BYTES)
    ]
    assert result["filename"] == "My Dictionary.csv"
    assert result["source"]["url"] == (
        "https://github.com/owner/repo/blob/main/folder/My%20Dictionary.csv"
    )


def test_gist_selection_preserves_revision_in_its_metadata_request_and_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "0123456789abcdef0123456789abcdef01234567"

    def fetch_text(url: str, _maximum_bytes: int) -> str:
        assert url == f"https://api.github.com/gists/abcdef123456/{revision}"
        return (
            '{"public": true, "truncated": false, "files": {'
            '"terms.csv": {"size": 12, "raw_url": "https://gist.example/terms.csv"}, '
            '"terms.json": {"size": 20, "raw_url": "https://gist.example/terms.json"}}}'
        )

    monkeypatch.setattr(source_import, "_fetch_text", fetch_text)

    result = source_import._fetch_dictionary_source(
        f"https://gist.github.com/example/abcdef123456/{revision}"
    )

    assert result == {
        "kind": "selection",
        "source_url": f"https://gist.github.com/example/abcdef123456/{revision}",
        "files": [{"name": "terms.csv", "size": 12}, {"name": "terms.json", "size": 20}],
    }


def test_gist_selection_uses_revision_qualified_url_and_fetches_selected_raw_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "0123456789abcdef0123456789abcdef01234567"
    metadata_url = f"https://api.github.com/gists/abcdef123456/{revision}"
    raw_url = "https://gist.githubusercontent.com/example/raw/revision/terms.csv"

    def fetch_text(url: str, _maximum_bytes: int) -> str:
        if url == metadata_url:
            return (
                '{"public": true, "files": {'
                '"terms.csv": {"size": 5, "raw_url": "'
                + raw_url
                + '"}, "other.json": {"size": 1, "raw_url": "https://example.test/other"}}}'
            )
        assert url == raw_url
        return "word\n"

    monkeypatch.setattr(source_import, "_fetch_text", fetch_text)

    result = source_import._fetch_dictionary_source(
        f"https://gist.github.com/example/abcdef123456/{revision}", "terms.csv"
    )

    assert result["content"] == "word\n"
    assert result["filename"] == "terms.csv"
    assert result["source"] == {
        "kind": "url",
        "url": f"https://gist.github.com/example/abcdef123456/{revision}",
        "filename": "terms.csv",
    }


def test_gist_refuses_truncated_listing_instead_of_selecting_partial_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        source_import,
        "_fetch_text",
        lambda *_: '{"public": true, "truncated": true, "files": {}}',
    )

    with pytest.raises(source_import.DictionarySourceError, match="truncated"):
        source_import._fetch_dictionary_source("https://gist.github.com/example/abcdef123456")


def test_gist_rejects_invalid_revision_instead_of_fetching_head() -> None:
    with pytest.raises(source_import.DictionarySourceError, match="invalid revision") as captured:
        source_import._fetch_dictionary_source(
            "https://gist.github.com/example/abcdef123456/not-a-revision"
        )

    assert source_import.is_dictionary_source_input_error(captured.value)
