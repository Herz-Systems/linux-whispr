"""Validation and normalization for offline community dictionary documents."""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from pathlib import Path

MAX_IMPORT_BYTES = 1_048_576
MAX_TERMS = 5_000
MAX_ALIASES = 20_000
MAX_TERM_LENGTH = 200

_IGNORECASE_SINGLE_CODEPOINT_EQUIVALENTS = {"\u0130": "i", "\u0131": "i"}


def literal_alias_key(value: str) -> str:
    """Return a key matching ``re.IGNORECASE`` without expanding literals.

    Whole-string ``casefold()`` can turn one source character into several
    characters (for example, ``ß`` into ``ss``), which Python's regular
    expression ignore-case matching does not do.  Key each code point
    independently instead, including the two Turkish-I characters that
    ``re.IGNORECASE`` treats as equivalent to ASCII ``i``.
    """
    keyed: list[str] = []
    for character in value:
        equivalent = _IGNORECASE_SINGLE_CODEPOINT_EQUIVALENTS.get(character)
        if equivalent is not None:
            keyed.append(equivalent)
            continue
        folded = character.casefold()
        if len(folded) == 1:
            keyed.append(folded)
            continue
        lowered = character.lower()
        keyed.append(lowered if len(lowered) == 1 else character)
    return "".join(keyed)


class CommunityDictionaryError(ValueError):
    """Raised when a community dictionary document is unsafe or invalid."""


class CommunityDictionaryConflict(CommunityDictionaryError):
    """Raised when a reviewed import no longer matches the current dictionary."""


class _NormalizedDocument(dict[str, object]):
    """A plain JSON-compatible document which retains parser-only diagnostics."""

    duplicate_count: int


_REQUIRED_DOCUMENT_FIELDS = {"format", "schema_version", "id", "name", "entries"}
_OPTIONAL_DOCUMENT_FIELDS = {"license", "author", "description", "sources", "$schema"}
_ALLOWED_DOCUMENT_FIELDS = _REQUIRED_DOCUMENT_FIELDS | _OPTIONAL_DOCUMENT_FIELDS
_HTML_PREFIX_RE = re.compile(
    r"^\s*(?:<!doctype\s+html|<!--|<(?:html|head|body|script|title|meta|div)\b)",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")


def _encoded_size(content: str) -> int:
    try:
        return len(content.encode("utf-8", "strict"))
    except UnicodeEncodeError as error:
        raise CommunityDictionaryError("Dictionary content must be valid UTF-8 text.") from error


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise CommunityDictionaryError(f"{field} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise CommunityDictionaryError(f"{field} must not be empty.")
    if len(normalized) > maximum:
        raise CommunityDictionaryError(f"{field} must be at most {maximum} characters.")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise CommunityDictionaryError(f"{field} must not contain control characters.")
    return normalized


def _metadata_text(value: object, field: str, maximum: int) -> str:
    return _text(value, field, maximum)


def _normalize_entries(entries: object) -> tuple[list[dict[str, object]], int]:
    if not isinstance(entries, list) or not entries:
        raise CommunityDictionaryError("entries must be a non-empty list.")
    if len(entries) > MAX_TERMS:
        raise CommunityDictionaryError(f"A dictionary may contain at most {MAX_TERMS} terms.")

    normalized: list[dict[str, object]] = []
    by_word: dict[str, int] = {}
    aliases: dict[str, str] = {}
    alias_count = 0
    duplicates = 0

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) - {"word", "aliases"} or "word" not in entry:
            raise CommunityDictionaryError(f"entries[{index}] must contain only word and aliases.")
        word = _text(entry["word"], f"entries[{index}].word", MAX_TERM_LENGTH)
        raw_aliases = entry.get("aliases", [])
        if not isinstance(raw_aliases, list):
            raise CommunityDictionaryError(f"entries[{index}].aliases must be a list.")

        word_key = literal_alias_key(word)
        existing_index = by_word.get(word_key)
        if existing_index is None:
            existing_index = len(normalized)
            by_word[word_key] = existing_index
            normalized.append({"word": word, "aliases": []})
        else:
            duplicates += 1

        output_aliases = normalized[existing_index]["aliases"]
        assert isinstance(output_aliases, list)
        seen_entry_aliases: set[str] = {literal_alias_key(alias) for alias in output_aliases}
        for alias_index, raw_alias in enumerate(raw_aliases):
            alias = _text(
                raw_alias,
                f"entries[{index}].aliases[{alias_index}]",
                MAX_TERM_LENGTH,
            )
            alias_key = literal_alias_key(alias)
            alias_count += 1
            if alias_count > MAX_ALIASES:
                raise CommunityDictionaryError(
                    f"A dictionary may contain at most {MAX_ALIASES} aliases."
                )
            previous_target = aliases.get(alias_key)
            if previous_target is not None and previous_target != word_key:
                raise CommunityDictionaryError(
                    f"Alias '{alias}' maps to more than one dictionary word."
                )
            aliases[alias_key] = word_key
            if alias_key in seen_entry_aliases:
                duplicates += 1
                continue
            seen_entry_aliases.add(alias_key)
            output_aliases.append(alias)

    return normalized, duplicates


def _normalize_sources(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise CommunityDictionaryError("sources must be a list.")
    if len(value) > 50:
        raise CommunityDictionaryError("sources may contain at most 50 entries.")
    normalized: list[dict[str, str]] = []
    for index, source in enumerate(value):
        if not isinstance(source, dict) or set(source) != {"title", "url"}:
            raise CommunityDictionaryError(f"sources[{index}] must contain title and url.")
        title = _metadata_text(source.get("title"), f"sources[{index}].title", 200)
        url = _metadata_text(source.get("url"), f"sources[{index}].url", 2_048)
        normalized.append({"title": title, "url": url})
    return normalized


def _normalize_native_document(document: object) -> tuple[dict[str, object], int]:
    if not isinstance(document, dict):
        raise CommunityDictionaryError("Dictionary JSON must be an object.")
    unknown = set(document) - _ALLOWED_DOCUMENT_FIELDS
    missing = _REQUIRED_DOCUMENT_FIELDS - set(document)
    if unknown:
        raise CommunityDictionaryError(
            f"Unsupported dictionary field: {sorted(unknown)[0]}."
        )
    if missing:
        raise CommunityDictionaryError(f"Missing dictionary field: {sorted(missing)[0]}.")
    if document["format"] != "linux-whispr-dictionary":
        raise CommunityDictionaryError("Unsupported dictionary format.")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise CommunityDictionaryError("Unsupported dictionary schema version.")

    identifier = _metadata_text(document["id"], "id", 100)
    if not _ID_RE.fullmatch(identifier):
        raise CommunityDictionaryError("id must use lowercase letters, digits, dots, underscores, or hyphens.")
    name = _metadata_text(document["name"], "name", 200)
    entries, duplicates = _normalize_entries(document["entries"])
    normalized: dict[str, object] = {
        "format": "linux-whispr-dictionary",
        "schema_version": 1,
        "id": identifier,
        "name": name,
        "entries": entries,
    }
    for field, maximum in (("license", 200), ("author", 200), ("description", 2_000), ("$schema", 2_048)):
        if field in document:
            normalized[field] = _metadata_text(document[field], field, maximum)
    if "sources" in document:
        normalized["sources"] = _normalize_sources(document["sources"])
    return normalized, duplicates


def _csv_document(content: str, filename: str) -> tuple[dict[str, object], int]:
    try:
        rows = list(csv.reader(io.StringIO(content, newline=""), strict=True))
    except csv.Error as error:
        raise CommunityDictionaryError("Invalid CSV dictionary.") from error
    if not rows:
        raise CommunityDictionaryError("CSV dictionary is empty.")

    entries: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if len(row) not in (1, 2):
            raise CommunityDictionaryError(f"CSV row {index + 1} must have one or two columns.")
        heard = row[0]
        if not heard.strip():
            raise CommunityDictionaryError(f"CSV row {index + 1} has an empty vocabulary word.")
        if len(row) == 1 or not row[1].strip():
            entries.append({"word": heard, "aliases": []})
        else:
            entries.append({"word": row[1], "aliases": [heard]})

    stem = Path(filename or "community-dictionary.csv").stem.strip() or "community-dictionary"
    generated_id = re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-") or "community-dictionary"
    generated_id = generated_id[:100].rstrip("-")
    document = {
        "format": "linux-whispr-dictionary",
        "schema_version": 1,
        "id": generated_id,
        "name": _text(stem, "filename", 200),
        "entries": entries,
    }
    return _normalize_native_document(document)


def parse_dictionary_document(content: str, filename: str) -> tuple[dict[str, object], int]:
    """Parse one bounded JSON or Wispr-compatible CSV dictionary without I/O."""
    if not isinstance(content, str):
        raise CommunityDictionaryError("Dictionary content must be text.")
    if not isinstance(filename, str):
        raise CommunityDictionaryError("Dictionary filename must be text.")
    if _encoded_size(content) > MAX_IMPORT_BYTES:
        raise CommunityDictionaryError("Dictionary content exceeds 1 MiB.")
    content_without_bom = content.removeprefix("\ufeff")
    if _HTML_PREFIX_RE.match(content_without_bom):
        raise CommunityDictionaryError("Dictionary content appears to be HTML, not JSON or CSV.")

    suffix = Path(filename).suffix.casefold()
    stripped = content_without_bom.lstrip(" \t\r\n")
    looks_like_json = stripped.startswith(("{", "["))
    if suffix == ".json" or looks_like_json:
        try:
            decoded = json.loads(stripped)
        except (json.JSONDecodeError, RecursionError) as error:
            raise CommunityDictionaryError("Invalid JSON dictionary.") from error
        normalized, duplicates = _normalize_native_document(decoded)
    else:
        normalized, duplicates = _csv_document(content_without_bom, filename)
    normalized_document = _NormalizedDocument(normalized)
    normalized_document.duplicate_count = duplicates
    return normalized_document, duplicates


def dictionary_schema() -> dict[str, object]:
    """Return the published JSON Schema 2020-12 for native dictionary files."""
    term = {
        "type": "object",
        "additionalProperties": False,
        "required": ["word"],
        "properties": {
            "word": {"type": "string", "minLength": 1, "maxLength": MAX_TERM_LENGTH},
            "aliases": {
                "type": "array",
                "maxItems": MAX_ALIASES,
                "items": {"type": "string", "minLength": 1, "maxLength": MAX_TERM_LENGTH},
            },
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Linux Whispr community dictionary",
        "type": "object",
        "additionalProperties": False,
        "required": ["format", "schema_version", "id", "name", "entries"],
        "properties": {
            "format": {"const": "linux-whispr-dictionary"},
            "schema_version": {"const": 1},
            "id": {"type": "string", "pattern": _ID_RE.pattern, "maxLength": 100},
            "name": {"type": "string", "minLength": 1, "maxLength": 200},
            "license": {"type": "string", "minLength": 1, "maxLength": 200},
            "author": {"type": "string", "minLength": 1, "maxLength": 200},
            "description": {"type": "string", "minLength": 1, "maxLength": 2000},
            "$schema": {"type": "string", "minLength": 1, "maxLength": 2048},
            "sources": {
                "type": "array",
                "maxItems": 50,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "url"],
                    "properties": {
                        "title": {"type": "string", "minLength": 1, "maxLength": 200},
                        "url": {"type": "string", "minLength": 1, "maxLength": 2048},
                    },
                },
            },
            "entries": {"type": "array", "minItems": 1, "maxItems": MAX_TERMS, "items": term},
        },
    }
