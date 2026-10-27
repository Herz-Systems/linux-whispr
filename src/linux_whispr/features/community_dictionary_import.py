"""Secure retrieval of community dictionary documents from public HTTPS sources.

The importer deliberately uses a small HTTP client rather than ``urllib`` so that
it can connect to the validated numeric address.  This prevents a second DNS
lookup between validation and the TLS socket connection (DNS rebinding).
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from .community_dictionary import MAX_IMPORT_BYTES


MAX_REDIRECTS = 3
MAX_GIST_METADATA_BYTES = 256 * 1024
REQUEST_TIMEOUT_SECONDS = 10.0
_MAX_WORKER_REQUEST_BYTES = MAX_IMPORT_BYTES
_MAX_WORKER_RESPONSE_BYTES = (MAX_IMPORT_BYTES * 6) + MAX_GIST_METADATA_BYTES + 1024
_WORKER_ARGUMENT = "--fetch-worker"
_ALLOWED_EXTENSIONS = (".json", ".csv")
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class DictionarySourceError(ValueError):
    """A safe, actionable error while retrieving a remote dictionary."""

    def __init__(self, message: str, *, input_error: bool = False) -> None:
        super().__init__(message)
        self.input_error = input_error


def is_dictionary_source_input_error(error: DictionarySourceError) -> bool:
    """Return whether an error was caused by the caller's URL or filename."""
    return error.input_error


@dataclass(frozen=True)
class _ValidatedUrl:
    url: str
    hostname: str
    port: int
    target: str

@dataclass(frozen=True)
class _GistReference:
    owner: str
    gist_id: str
    revision: str | None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection whose TCP peer is a previously validated IP address."""

    def __init__(
        self,
        hostname: str,
        port: int,
        address: str,
        timeout: float,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self._address = ipaddress.ip_address(address)

    def connect(self) -> None:
        """Connect directly to the numeric peer while TLS still authenticates hostname."""
        family = socket.AF_INET6 if self._address.version == 6 else socket.AF_INET
        raw_socket = socket.socket(family, socket.SOCK_STREAM)
        raw_socket.settimeout(self.timeout)
        try:
            if family == socket.AF_INET6:
                raw_socket.connect((str(self._address), self.port, 0, 0))
            else:
                raw_socket.connect((str(self._address), self.port))
            # ``self.host`` is the DNS hostname, not the pinned address.  It is
            # therefore both TLS SNI and the certificate-validation hostname.
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


def fetch_dictionary_source(url: str, filename: str | None = None) -> dict[str, Any]:
    """Fetch one untrusted dictionary source within a wall-clock deadline.

    Remote work runs in a short-lived subprocess so the deadline also terminates
    blocked DNS, TCP/TLS, response-header, response-body, and redirect activity.
    """
    validated = _validate_url(url, input_error=True)
    if filename is not None:
        try:
            filename = _safe_filename(filename)
        except DictionarySourceError as error:
            raise DictionarySourceError(str(error), input_error=True) from error

    request = json.dumps(
        {"url": validated.url, "filename": filename},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(request) > _MAX_WORKER_REQUEST_BYTES:
        raise DictionarySourceError("The dictionary URL is too large.", input_error=True)

    try:
        completed = subprocess.run(
            [sys.executable, "-m", __name__, _WORKER_ARGUMENT],
            input=request,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise DictionarySourceError("Timed out while retrieving the dictionary source.") from error
    except OSError as error:
        raise DictionarySourceError("Could not retrieve the dictionary source.") from error

    if completed.returncode != 0 or len(completed.stdout) > _MAX_WORKER_RESPONSE_BYTES:
        raise DictionarySourceError("Could not retrieve the dictionary source.")
    try:
        response = json.loads(completed.stdout)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DictionarySourceError("Could not retrieve the dictionary source.") from error
    if not isinstance(response, dict):
        raise DictionarySourceError("Could not retrieve the dictionary source.")
    if response.get("ok") is True and isinstance(response.get("result"), dict):
        return response["result"]
    if response.get("ok") is False and isinstance(response.get("error"), str):
        raise DictionarySourceError(
            response["error"],
            input_error=response.get("input_error") is True,
        )
    raise DictionarySourceError("Could not retrieve the dictionary source.")


def _fetch_dictionary_source(url: str, filename: str | None = None) -> dict[str, Any]:
    """Fetch a dictionary source in the deadline-supervised worker process."""
    validated = _validate_url(url, input_error=True)
    normalized_url = validated.url

    gist = _parse_gist_url(validated)
    if gist is not None:
        return _fetch_gist(gist, filename)

    download_url = _github_blob_raw_url(validated) or normalized_url
    resolved_filename = _source_filename(filename, validated)
    content = _fetch_text(download_url, MAX_IMPORT_BYTES)
    return {
        "kind": "file",
        "content": content,
        "filename": resolved_filename,
        "source": {
            "kind": "url",
            "url": normalized_url,
            "filename": resolved_filename,
        },
    }


def _fetch_gist(gist: _GistReference, requested_filename: str | None) -> dict[str, Any]:
    stable_url = f"https://gist.github.com/{quote(gist.owner, safe='-._~')}/{gist.gist_id}"
    metadata_url = f"https://api.github.com/gists/{gist.gist_id}"
    if gist.revision is not None:
        stable_url += f"/{gist.revision}"
        metadata_url += f"/{gist.revision}"
    metadata_text = _fetch_text(metadata_url, MAX_GIST_METADATA_BYTES)
    try:
        metadata = json.loads(metadata_text)
    except json.JSONDecodeError as error:
        raise DictionarySourceError("The Gist metadata was not valid JSON.") from error

    if not isinstance(metadata, dict) or metadata.get("public") is not True:
        raise DictionarySourceError("The Gist must be public.")
    if metadata.get("truncated") is True:
        raise DictionarySourceError("The Gist file listing is truncated; select a smaller Gist.")

    files_value = metadata.get("files")
    if not isinstance(files_value, dict):
        raise DictionarySourceError("The Gist did not provide a valid file listing.")

    files: list[tuple[str, int, str]] = []
    for supplied_name, details in files_value.items():
        if not isinstance(supplied_name, str) or not isinstance(details, dict):
            raise DictionarySourceError("The Gist did not provide a valid file listing.")
        if details.get("truncated") is True:
            raise DictionarySourceError("The Gist file listing is truncated; select a smaller Gist.")
        safe_name = _safe_filename(supplied_name)
        if not _is_dictionary_filename(safe_name):
            continue
        size = details.get("size")
        raw_url = details.get("raw_url")
        if type(size) is not int or size < 0 or not isinstance(raw_url, str):
            raise DictionarySourceError("The Gist did not provide valid dictionary file details.")
        if size > MAX_IMPORT_BYTES:
            raise DictionarySourceError("The selected dictionary file is too large.")
        if any(existing_name == safe_name for existing_name, _, _ in files):
            raise DictionarySourceError("The Gist has ambiguous dictionary filenames.")
        files.append((safe_name, size, raw_url))

    if not files:
        raise DictionarySourceError("The public Gist has no JSON or CSV dictionary files.")
    files.sort(key=lambda item: item[0].casefold())

    selected: tuple[str, int, str] | None = None
    if requested_filename is not None:
        try:
            requested_name = _safe_filename(requested_filename)
        except DictionarySourceError as error:
            raise DictionarySourceError(str(error), input_error=True) from error
        matching = [item for item in files if item[0] == requested_name]
        if len(matching) != 1:
            raise DictionarySourceError("The selected dictionary file was not found in this Gist.")
        selected = matching[0]
    elif len(files) == 1:
        selected = files[0]
    else:
        return {
            "kind": "selection",
            "source_url": stable_url,
            "files": [{"name": name, "size": size} for name, size, _ in files],
        }

    assert selected is not None
    selected_name, _, raw_url = selected
    content = _fetch_text(raw_url, MAX_IMPORT_BYTES)
    return {
        "kind": "file",
        "content": content,
        "filename": selected_name,
        "source": {"kind": "url", "url": stable_url, "filename": selected_name},
    }


def _fetch_text(url: str, maximum_bytes: int) -> str:
    body = _fetch_bytes(url, maximum_bytes)
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DictionarySourceError("The dictionary source must be UTF-8 text.") from error


def _fetch_bytes(url: str, maximum_bytes: int) -> bytes:
    current = _validate_url(url)
    for redirect_count in range(MAX_REDIRECTS + 1):
        response: http.client.HTTPResponse | None = None
        connection: _PinnedHTTPSConnection | None = None
        try:
            addresses = _resolve_public_addresses(current.hostname, current.port)
            # Selecting a validated numeric address before constructing the
            # connection ensures no resolver call occurs during socket setup.
            connection = _PinnedHTTPSConnection(
                current.hostname, current.port, addresses[0], REQUEST_TIMEOUT_SECONDS
            )
            connection.request(
                "GET",
                current.target,
                headers={
                    "Accept": "application/json, text/csv, application/octet-stream;q=0.8",
                    "User-Agent": "Linux-Whispr dictionary importer",
                },
            )
            response = connection.getresponse()
            status = response.status
            if status in _REDIRECT_STATUSES:
                location = response.getheader("Location")
                if not location:
                    raise DictionarySourceError("The remote server sent a redirect without a location.")
                if redirect_count == MAX_REDIRECTS:
                    raise DictionarySourceError("The dictionary source redirected too many times.")
                current = _validate_url(urljoin(current.url, location))
                continue
            if status == 404:
                raise DictionarySourceError("The dictionary source was not found.")
            if status >= 400:
                raise DictionarySourceError("The remote dictionary source could not be retrieved.")
            if status < 200 or status >= 300:
                raise DictionarySourceError("The remote dictionary source returned an unexpected response.")

            content_length = response.getheader("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError:
                    pass
                else:
                    if declared_length > maximum_bytes:
                        raise DictionarySourceError("The dictionary source is too large.")
            body = response.read(maximum_bytes + 1)
            if len(body) > maximum_bytes:
                raise DictionarySourceError("The dictionary source is too large.")
            return body
        except DictionarySourceError:
            raise
        except (socket.timeout, TimeoutError) as error:
            raise DictionarySourceError("Timed out while retrieving the dictionary source.") from error
        except ssl.SSLError as error:
            raise DictionarySourceError("Could not establish a secure connection to the dictionary source.") from error
        except (OSError, http.client.HTTPException) as error:
            raise DictionarySourceError("Could not retrieve the dictionary source.") from error
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()

    raise DictionarySourceError("The dictionary source redirected too many times.")


def _validate_url(value: str, *, input_error: bool = False) -> _ValidatedUrl:
    def fail(message: str) -> DictionarySourceError:
        return DictionarySourceError(message, input_error=input_error)

    if not isinstance(value, str) or not value.strip():
        raise fail("A public HTTPS URL is required.")
    if value != value.strip() or any(not character.isprintable() for character in value):
        raise fail("The dictionary URL contains invalid characters.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise fail("The dictionary URL has an invalid port.") from error
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise fail("Only public HTTPS URLs are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise fail("Dictionary URLs must not include credentials.")
    if port not in (None, 443):
        raise fail("Dictionary URLs must use HTTPS port 443.")
    if parsed.fragment:
        parsed = parsed._replace(fragment="")
    try:
        hostname = _normalise_hostname(parsed.hostname)
        _reject_ip_literal(hostname)
    except DictionarySourceError as error:
        raise fail(str(error)) from error
    path = _normalise_url_path(parsed.path or "/")
    target = path + (f"?{parsed.query}" if parsed.query else "")
    normalized = urlunsplit(("https", hostname, path, parsed.query, ""))
    return _ValidatedUrl(normalized, hostname, 443, target)


def _normalise_hostname(hostname: str) -> str:
    try:
        encoded = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise DictionarySourceError("The dictionary URL has an invalid hostname.") from error
    if not encoded:
        raise DictionarySourceError("The dictionary URL has an invalid hostname.")
    return encoded


def _reject_ip_literal(hostname: str) -> None:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return
    raise DictionarySourceError("Dictionary URLs must use a public hostname, not an IP address.")


def _resolve_public_addresses(hostname: str, port: int) -> list[str]:
    try:
        results = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise DictionarySourceError("Could not resolve the dictionary hostname.") from error

    addresses: list[str] = []
    for family, _, _, _, sockaddr in results:
        if family not in (socket.AF_INET, socket.AF_INET6) or not sockaddr:
            continue
        address = str(sockaddr[0])
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as error:
            raise DictionarySourceError("The dictionary hostname resolved to an invalid address.") from error
        if not _is_public_address(parsed):
            raise DictionarySourceError("The dictionary hostname resolved to a non-public address.")
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise DictionarySourceError("Could not resolve a public address for the dictionary hostname.")
    return addresses


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return _is_public_address(address.ipv4_mapped)
    return address.is_global and not any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def _parse_gist_url(url: _ValidatedUrl) -> _GistReference | None:
    if url.hostname != "gist.github.com":
        return None
    segments = [unquote(part) for part in urlsplit(url.url).path.split("/") if part]
    if len(segments) not in (2, 3) or not all(segments):
        raise DictionarySourceError("Gist URLs must identify a public Gist.", input_error=True)
    owner, gist_id = segments[0], segments[1]
    if not gist_id.isascii() or not gist_id.isalnum():
        raise DictionarySourceError("The Gist URL has an invalid identifier.", input_error=True)
    revision = segments[2] if len(segments) == 3 else None
    if revision is not None and (
        len(revision) != 40 or any(character not in "0123456789abcdefABCDEF" for character in revision)
    ):
        raise DictionarySourceError("The Gist URL has an invalid revision.", input_error=True)
    return _GistReference(owner=owner, gist_id=gist_id, revision=revision)


def _github_blob_raw_url(url: _ValidatedUrl) -> str | None:
    if url.hostname != "github.com":
        return None
    segments = [unquote(part) for part in urlsplit(url.url).path.split("/") if part]
    if len(segments) < 5 or segments[2] != "blob":
        return None
    owner, repository, _, revision, *file_parts = segments
    if not owner or not repository or not revision or not file_parts:
        return None
    encoded = [quote(part, safe="-._~") for part in (owner, repository, revision, *file_parts)]
    return "https://raw.githubusercontent.com/" + "/".join(encoded)


def _normalise_url_path(path: str) -> str:
    return "/".join(quote(unquote(part), safe="-._~") for part in path.split("/")) or "/"


def _source_filename(requested_filename: str | None, url: _ValidatedUrl) -> str:
    if requested_filename is not None:
        try:
            return _safe_filename(requested_filename)
        except DictionarySourceError as error:
            raise DictionarySourceError(str(error), input_error=True) from error
    parts = [unquote(part) for part in urlsplit(url.url).path.split("/") if part]
    if not parts:
        return "dictionary"
    try:
        return _safe_filename(parts[-1])
    except DictionarySourceError as error:
        raise DictionarySourceError(str(error), input_error=True) from error


def _safe_filename(value: str) -> str:
    if not isinstance(value, str):
        raise DictionarySourceError("The dictionary filename is invalid.")
    name = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."} or len(name) > 255 or any(
        not char.isprintable() for char in name
    ):
        raise DictionarySourceError("The dictionary filename is invalid.")
    return name


def _is_dictionary_filename(filename: str) -> bool:
    return filename.casefold().endswith(_ALLOWED_EXTENSIONS)


def _run_fetch_worker() -> int:
    """Run one bounded fetch request without importing or launching the application."""
    try:
        request_bytes = sys.stdin.buffer.read(_MAX_WORKER_REQUEST_BYTES + 1)
        if len(request_bytes) > _MAX_WORKER_REQUEST_BYTES:
            raise DictionarySourceError("The dictionary URL is too large.", input_error=True)
        request = json.loads(request_bytes)
        if not isinstance(request, dict) or set(request) != {"url", "filename"}:
            raise DictionarySourceError("The dictionary request is invalid.", input_error=True)
        url = request["url"]
        filename = request["filename"]
        if not isinstance(url, str) or (filename is not None and not isinstance(filename, str)):
            raise DictionarySourceError("The dictionary request is invalid.", input_error=True)
        response: dict[str, Any] = {
            "ok": True,
            "result": _fetch_dictionary_source(url, filename),
        }
    except DictionarySourceError as error:
        response = {"ok": False, "error": str(error), "input_error": error.input_error}
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        response = {
            "ok": False,
            "error": "The dictionary request is invalid.",
            "input_error": True,
        }
    except Exception:
        response = {"ok": False, "error": "Could not retrieve the dictionary source."}

    output = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(output) > _MAX_WORKER_RESPONSE_BYTES:
        output = b'{"ok":false,"error":"Could not retrieve the dictionary source."}'
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == [_WORKER_ARGUMENT]:
        raise SystemExit(_run_fetch_worker())
    raise SystemExit(2)
