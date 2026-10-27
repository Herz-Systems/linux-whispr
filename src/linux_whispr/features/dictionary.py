"""Custom dictionary and opt-in vocabulary pack manager for dictation."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from linux_whispr.constants import DICTIONARY_FILE
from linux_whispr.features.community_dictionary import (
    CommunityDictionaryConflict,
    CommunityDictionaryError,
    _normalize_native_document,
    literal_alias_key,
)
from linux_whispr.features.dictionary_packs import BUNDLED_PACKS, DictionaryPack, PackTerm

logger = logging.getLogger(__name__)

# Whisper and the optional refinement prompt both consume this bounded vocabulary
# context. Keep it small enough to avoid displacing the actual dictated text.
CONTEXT_MAX_CHARS = 1_000

_PROTECTED_LITERAL_RE = re.compile(
    r"(?is)(?:```|~~~).*?(?:```|~~~|\Z)|`[^`\n]*`|"
    r"\b(?:[a-z][a-z0-9+.-]*://|www\.)[^\s<>()]+|"
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
)


@dataclass(frozen=True)
class DictionaryEntry:
    """A single personal dictionary entry."""

    word: str
    source: str = "manual"  # "manual" | "auto-learned"
    frequency: int = 0
    added_at: str = field(default_factory=lambda: datetime.now().isoformat())
    category: str = "general"  # "personal_names" | "technical" | "brand" | "general"
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorrectionPair:
    """A learned correction pair from adaptive dictionary."""

    heard: str
    corrected: str
    count: int = 1
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())


def _normalize_aliases(aliases: Iterable[str]) -> tuple[str, ...]:
    """Return non-empty aliases once, preserving their user-provided spelling."""
    seen: set[str] = set()
    normalized: list[str] = []
    for alias in aliases:
        if not isinstance(alias, str):
            continue
        value = alias.strip()
        key = literal_alias_key(value)
        if value and key not in seen:
            seen.add(key)
            normalized.append(value)
    return tuple(normalized)


class Dictionary:
    """Manages personal entries, learned corrections, and opt-in vocabulary packs."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DICTIONARY_FILE
        self._lock = threading.RLock()
        self._entries: tuple[DictionaryEntry, ...] = ()
        self._corrections: tuple[CorrectionPair, ...] = ()
        self._enabled_packs: tuple[str, ...] = ()
        self._community_packs: dict[str, dict[str, object]] = {}
        self._matcher_signature: tuple[object, ...] | None = None
        self._matcher: re.Pattern[str] | None = None
        self._replacement_targets: tuple[str, ...] = ()

    @staticmethod
    def _copy_json(value: object) -> object:
        return copy.deepcopy(value)

    @staticmethod
    def _content_hash(document: dict[str, object]) -> str:
        encoded = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _normalize_source(source: object) -> dict[str, str]:
        if not isinstance(source, dict):
            raise CommunityDictionaryError("Community dictionary source must be an object.")
        kind = source.get("kind")
        if not isinstance(kind, str) or kind not in {"file", "url"}:
            raise CommunityDictionaryError("Community dictionary source kind is invalid.")
        allowed = {"kind", "filename"} if kind == "file" else {"kind", "url", "filename"}
        if set(source) != allowed:
            raise CommunityDictionaryError("Community dictionary source has invalid fields.")
        filename = source.get("filename")
        if (
            not isinstance(filename, str)
            or not filename.strip()
            or len(filename.strip()) > 255
            or "/" in filename
            or "\\" in filename
            or any(character.isspace() and character not in {" ", "\t"} for character in filename)
        ):
            raise CommunityDictionaryError("Community dictionary source filename is invalid.")
        normalized: dict[str, str] = {"kind": kind, "filename": filename.strip()}
        if kind == "url":
            url = source.get("url")
            if (
                not isinstance(url, str)
                or not url.strip()
                or len(url.strip()) > 2_048
                or any(character.isspace() for character in url)
            ):
                raise CommunityDictionaryError("Community dictionary source URL is invalid.")
            normalized["url"] = url.strip()
        return normalized

    @classmethod
    def _normalize_community_record(cls, record: object) -> dict[str, object]:
        if not isinstance(record, dict) or set(record) - {
            "document",
            "source",
            "content_hash",
            "installed_at",
        }:
            raise CommunityDictionaryError("Community dictionary storage record is invalid.")
        document, _ = _normalize_native_document(record.get("document"))
        source = cls._normalize_source(record.get("source"))
        normalized: dict[str, object] = {
            "document": document,
            "source": source,
            "content_hash": cls._content_hash(document),
        }
        installed_at = record.get("installed_at")
        if isinstance(installed_at, str):
            normalized["installed_at"] = installed_at
        return normalized

    def load(self) -> None:
        """Load dictionary data without allowing one malformed record to erase others."""
        if not self._path.exists():
            logger.info("No dictionary file found at %s", self._path)
            return

        try:
            with open(self._path, encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                raise ValueError("Dictionary storage must be a JSON object.")

            entries: list[DictionaryEntry] = []
            for entry in data.get("entries", []):
                if not isinstance(entry, dict) or not isinstance(entry.get("word"), str):
                    logger.warning("Skipping malformed personal dictionary entry.")
                    continue
                entries.append(
                    DictionaryEntry(
                        word=entry["word"],
                        source=entry.get("source", "manual"),
                        frequency=entry.get("frequency", 0),
                        added_at=entry.get("added_at", datetime.now().isoformat()),
                        category=entry.get("category", "general"),
                        aliases=_normalize_aliases(entry.get("aliases", ())),
                    )
                )
            corrections: list[CorrectionPair] = []
            for correction in data.get("corrections", []):
                if not isinstance(correction, dict) or not all(
                    isinstance(correction.get(field), str) for field in ("heard", "corrected")
                ):
                    logger.warning("Skipping malformed adaptive dictionary correction.")
                    continue
                corrections.append(
                    CorrectionPair(
                        heard=correction["heard"],
                        corrected=correction["corrected"],
                        count=correction.get("count", 1),
                        last_seen=correction.get("last_seen", datetime.now().isoformat()),
                    )
                )

            community_packs: dict[str, dict[str, object]] = {}
            raw_community = data.get("community_packs", {})
            if isinstance(raw_community, dict):
                for pack_id, record in raw_community.items():
                    if not isinstance(pack_id, str) or not pack_id.startswith("community-"):
                        logger.warning("Skipping malformed community dictionary pack id.")
                        continue
                    try:
                        community_packs[pack_id] = self._normalize_community_record(record)
                    except CommunityDictionaryError:
                        logger.warning("Skipping malformed community dictionary pack '%s'.", pack_id)
            enabled_packs = tuple(
                pack_id
                for pack_id in dict.fromkeys(data.get("enabled_packs", []))
                if isinstance(pack_id, str)
                and (pack_id in {pack.id for pack in BUNDLED_PACKS} or pack_id in community_packs)
            )
            with self._lock:
                self._entries = tuple(entries)
                self._corrections = tuple(corrections)
                self._community_packs = community_packs
                self._enabled_packs = enabled_packs
                self._invalidate_matcher()
            logger.info(
                "Loaded dictionary: %d entries, %d corrections, %d enabled packs",
                len(entries),
                len(corrections),
                len(enabled_packs),
            )
        except Exception:
            logger.exception("Failed to load dictionary from %s", self._path)

    def _storage_data_locked(
        self,
        *,
        community_packs: dict[str, dict[str, object]] | None = None,
        enabled_packs: tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        return {
            "entries": [asdict(entry) for entry in self._entries],
            "corrections": [asdict(correction) for correction in self._corrections],
            "enabled_packs": list(enabled_packs if enabled_packs is not None else self._enabled_packs),
            "community_packs": self._copy_json(
                community_packs if community_packs is not None else self._community_packs
            ),
        }

    def _write_data_locked(self, data: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            raise

    def _save_locked(self) -> None:
        self._write_data_locked(self._storage_data_locked())

    def save(self) -> None:
        """Atomically persist a coherent immutable dictionary snapshot."""
        with self._lock:
            self._save_locked()
        logger.debug("Saved dictionary to %s", self._path)

    def _invalidate_matcher(self) -> None:
        self._matcher_signature = None
        self._matcher = None
        self._replacement_targets = ()

    def add_word(
        self,
        word: str,
        source: str = "manual",
        category: str = "general",
        aliases: Iterable[str] | None = None,
    ) -> None:
        """Add a personal word or update its aliases without duplicating it."""
        normalized_word = word.strip()
        if not normalized_word:
            raise ValueError("Dictionary words must not be empty.")
        normalized_aliases = None if aliases is None else _normalize_aliases(aliases)
        with self._lock:
            for index, entry in enumerate(self._entries):
                if entry.word.casefold() != normalized_word.casefold():
                    continue
                if normalized_aliases is None:
                    self._entries = (
                        *self._entries[:index],
                        DictionaryEntry(
                            word=entry.word,
                            source=entry.source,
                            frequency=entry.frequency + 1,
                            added_at=entry.added_at,
                            category=entry.category,
                            aliases=entry.aliases,
                        ),
                        *self._entries[index + 1 :],
                    )
                else:
                    self._entries = (
                        *self._entries[:index],
                        DictionaryEntry(
                            word=entry.word,
                            source=entry.source,
                            frequency=entry.frequency,
                            added_at=entry.added_at,
                            category=entry.category,
                            aliases=normalized_aliases,
                        ),
                        *self._entries[index + 1 :],
                    )
                self._invalidate_matcher()
                self._save_locked()
                return

            self._entries = (
                *self._entries,
                DictionaryEntry(
                    word=normalized_word,
                    source=source,
                    category=category,
                    aliases=normalized_aliases or (),
                ),
            )
            self._invalidate_matcher()
            self._save_locked()

    def remove_word(self, word: str) -> bool:
        """Remove a personal word. Bundled vocabulary is never modified."""
        with self._lock:
            for index, entry in enumerate(self._entries):
                if entry.word.casefold() == word.casefold():
                    self._entries = (*self._entries[:index], *self._entries[index + 1 :])
                    self._invalidate_matcher()
                    self._save_locked()
                    return True
        return False

    def add_correction(self, heard: str, corrected: str) -> None:
        """Record a correction pair for adaptive learning."""
        with self._lock:
            for index, pair in enumerate(self._corrections):
                if pair.heard.casefold() == heard.casefold() and pair.corrected == corrected:
                    self._corrections = (
                        *self._corrections[:index],
                        CorrectionPair(
                            heard=pair.heard,
                            corrected=pair.corrected,
                            count=pair.count + 1,
                            last_seen=datetime.now().isoformat(),
                        ),
                        *self._corrections[index + 1 :],
                    )
                    self._invalidate_matcher()
                    self._save_locked()
                    return
            self._corrections = (
                *self._corrections,
                CorrectionPair(heard=heard, corrected=corrected),
            )
            self._invalidate_matcher()
            self._save_locked()

    def remove_correction(self, index: int) -> CorrectionPair | None:
        """Remove one learned correction and return it when the index is valid."""
        with self._lock:
            if not 0 <= index < len(self._corrections):
                return None
            removed = self._corrections[index]
            self._corrections = (
                *self._corrections[:index],
                *self._corrections[index + 1 :],
            )
            self._invalidate_matcher()
            self._save_locked()
            return removed

    def set_pack_enabled(self, pack_id: str, enabled: bool) -> None:
        """Enable or disable one known bundled or community pack."""
        with self._lock:
            known_ids = {pack.id for pack in BUNDLED_PACKS} | set(self._community_packs)
            if pack_id not in known_ids:
                raise KeyError(pack_id)
            current = list(self._enabled_packs)
            if enabled and pack_id not in current:
                current.append(pack_id)
            elif not enabled and pack_id in current:
                current.remove(pack_id)
            else:
                return
            self._enabled_packs = tuple(current)
            self._invalidate_matcher()
            self._save_locked()

    @staticmethod
    def _community_pack_as_catalog_item(
        pack_id: str, record: dict[str, object]
    ) -> DictionaryPack:
        document = record["document"]
        assert isinstance(document, dict)
        terms = document["entries"]
        assert isinstance(terms, list)
        sources = document.get("sources", [])
        assert isinstance(sources, list)
        return DictionaryPack(
            id=pack_id,
            name=str(document["name"]),
            description=str(document.get("description", "")),
            terms=tuple(
                PackTerm(str(entry["word"]), tuple(str(alias) for alias in entry["aliases"]))
                for entry in terms
                if isinstance(entry, dict)
            ),
            sources=tuple(
                (str(source["title"]), str(source["url"]))
                for source in sources
                if isinstance(source, dict)
            ),
        )

    def pack_catalog(self) -> tuple[DictionaryPack, ...]:
        """Return bundled packs followed by persisted community packs in install order."""
        with self._lock:
            return (
                *BUNDLED_PACKS,
                *(
                    self._community_pack_as_catalog_item(pack_id, record)
                    for pack_id, record in self._community_packs.items()
                ),
            )

    def is_pack_enabled(self, pack_id: str) -> bool:
        with self._lock:
            return pack_id in self._enabled_packs

    def _active_packs_locked(self) -> tuple[DictionaryPack, ...]:
        enabled = set(self._enabled_packs)
        return tuple(pack for pack in self.pack_catalog() if pack.id in enabled)

    def _revision_locked(self, promotion_threshold: int = 2) -> str:
        serialized = json.dumps(
            {
                "dictionary": self._storage_data_locked(),
                "community_pack_order": list(self._community_packs),
                "promotion_threshold": promotion_threshold,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    @staticmethod
    def _entry_changes(
        previous: list[dict[str, object]], incoming: list[dict[str, object]]
    ) -> dict[str, list[dict[str, object]]]:
        previous_by_word = {str(entry["word"]).casefold(): entry for entry in previous}
        incoming_by_word = {str(entry["word"]).casefold(): entry for entry in incoming}
        added = [
            copy.deepcopy(entry)
            for key, entry in incoming_by_word.items()
            if key not in previous_by_word
        ]
        removed = [
            copy.deepcopy(entry)
            for key, entry in previous_by_word.items()
            if key not in incoming_by_word
        ]
        changed = [
            {"before": copy.deepcopy(previous_by_word[key]), "after": copy.deepcopy(entry)}
            for key, entry in incoming_by_word.items()
            if key in previous_by_word and previous_by_word[key] != entry
        ]
        return {"added": added, "removed": removed, "changed": changed}

    def _active_entries_locked(
        self, promotion_threshold: int
    ) -> tuple[DictionaryEntry, ...]:
        return tuple(
            entry
            for entry in self._entries
            if entry.source == "manual" or entry.frequency >= promotion_threshold
        )

    def _replacement_owners_locked(
        self,
        *,
        promotion_threshold: int,
        through_pack_id: str | None = None,
    ) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
        """Return higher-priority literal aliases and personal spellings."""
        replacements: dict[str, tuple[str, str]] = {}
        personal_spellings: dict[str, str] = {}

        def add(alias: str, target: str, scope: str) -> None:
            replacements.setdefault(literal_alias_key(alias), (target, scope))

        active_entries = self._active_entries_locked(promotion_threshold)
        for entry in active_entries:
            personal_spellings.setdefault(literal_alias_key(entry.word), entry.word)
        for entry in active_entries:
            for alias in entry.aliases:
                add(alias, entry.word, "personal")
        for entry in active_entries:
            add(entry.word, entry.word, "personal")
        for pair in self._corrections:
            if pair.count >= promotion_threshold:
                add(pair.heard, pair.corrected, "adaptive")

        enabled = set(self._enabled_packs)
        for pack in self.pack_catalog():
            if through_pack_id is not None and pack.id == through_pack_id:
                break
            if pack.id not in enabled:
                continue
            for term in pack.terms:
                target = personal_spellings.get(literal_alias_key(term.word), term.word)
                for alias in term.aliases:
                    add(alias, target, "pack")
        return replacements, personal_spellings

    def _later_pack_owners_locked(
        self, pack_id: str, personal_spellings: dict[str, str]
    ) -> dict[str, tuple[str, str]]:
        """Return aliases whose active owner follows an updated pack."""
        replacements: dict[str, tuple[str, str]] = {}
        found_target = False
        enabled = set(self._enabled_packs)
        for pack in self.pack_catalog():
            if pack.id == pack_id:
                found_target = True
                continue
            if not found_target or pack.id not in enabled:
                continue
            for term in pack.terms:
                target = personal_spellings.get(literal_alias_key(term.word), term.word)
                for alias in term.aliases:
                    replacements.setdefault(literal_alias_key(alias), (target, "pack"))
        return replacements

    def preview_community_pack(
        self,
        document: dict[str, object],
        *,
        source: dict[str, object] | dict[str, str],
        pack_id: str | None = None,
        promotion_threshold: int = 2,
    ) -> dict[str, object]:
        """Describe an import/update without changing persistent or live state."""
        duplicate_count = getattr(document, "duplicate_count", 0)
        normalized_document, normalized_duplicates = _normalize_native_document(document)
        normalized_source = self._normalize_source(source)
        duplicate_count = max(int(duplicate_count), normalized_duplicates)
        with self._lock:
            previous_entries: list[dict[str, object]] = []
            if pack_id is not None:
                record = self._community_packs.get(pack_id)
                if record is None:
                    raise CommunityDictionaryConflict("Community dictionary update target is missing.")
                stored_document = record["document"]
                assert isinstance(stored_document, dict)
                stored_entries = stored_document["entries"]
                assert isinstance(stored_entries, list)
                previous_entries = copy.deepcopy(stored_entries)
            replacements, personal_spellings = self._replacement_owners_locked(
                promotion_threshold=promotion_threshold,
                through_pack_id=pack_id,
            )
            later_replacements = (
                self._later_pack_owners_locked(pack_id, personal_spellings)
                if pack_id is not None and pack_id in self._enabled_packs
                else {}
            )
            incoming_entries = normalized_document["entries"]
            assert isinstance(incoming_entries, list)
            conflicts: list[dict[str, str]] = []
            for entry in incoming_entries:
                assert isinstance(entry, dict)
                word = str(entry["word"])
                target = personal_spellings.get(literal_alias_key(word), word)
                aliases = entry["aliases"]
                assert isinstance(aliases, list)
                for alias in aliases:
                    existing = replacements.get(literal_alias_key(str(alias)))
                    if existing is None:
                        existing = later_replacements.get(literal_alias_key(str(alias)))
                    if (
                        existing is not None
                        and literal_alias_key(existing[0]) != literal_alias_key(target)
                    ):
                        conflicts.append(
                            {
                                "alias": str(alias),
                                "existing": existing[0],
                                "incoming": target,
                                "scope": existing[1],
                            }
                        )
            changes = self._entry_changes(previous_entries, incoming_entries)
            return {
                "revision": self._revision_locked(promotion_threshold),
                "pack_id": pack_id,
                "document": copy.deepcopy(normalized_document),
                "source": copy.deepcopy(normalized_source),
                "term_count": len(incoming_entries),
                "alias_count": sum(len(entry["aliases"]) for entry in incoming_entries),
                "duplicates": duplicate_count,
                "conflicts": conflicts,
                "changes": changes,
                "unchanged": not any(changes.values()),
            }

    def install_community_pack(
        self,
        document: dict[str, object],
        *,
        source: dict[str, object] | dict[str, str],
        expected_revision: str,
        pack_id: str | None = None,
        promotion_threshold: int = 2,
    ) -> str:
        """Persist a reviewed community pack atomically and apply it immediately."""
        normalized_document, _ = _normalize_native_document(document)
        normalized_source = self._normalize_source(source)
        if not isinstance(expected_revision, str):
            raise CommunityDictionaryConflict("Community dictionary revision is invalid.")
        with self._lock:
            if expected_revision != self._revision_locked(promotion_threshold):
                raise CommunityDictionaryConflict("Community dictionary preview is stale.")
            if pack_id is not None and pack_id not in self._community_packs:
                raise CommunityDictionaryConflict("Community dictionary update target is missing.")
            if pack_id is None:
                pack_id = f"community-{uuid.uuid4().hex}"
                while pack_id in self._community_packs:
                    pack_id = f"community-{uuid.uuid4().hex}"
                installed_at = datetime.now().isoformat()
            else:
                prior = self._community_packs[pack_id]
                installed_at = prior.get("installed_at", datetime.now().isoformat())
            updated_packs = copy.deepcopy(self._community_packs)
            updated_packs[pack_id] = {
                "document": copy.deepcopy(normalized_document),
                "source": copy.deepcopy(normalized_source),
                "content_hash": self._content_hash(normalized_document),
                "installed_at": installed_at,
            }
            updated_enabled = self._enabled_packs
            if pack_id not in self._community_packs and pack_id not in updated_enabled:
                updated_enabled = (*updated_enabled, pack_id)
            self._write_data_locked(
                self._storage_data_locked(
                    community_packs=updated_packs, enabled_packs=updated_enabled
                )
            )
            self._community_packs = updated_packs
            self._enabled_packs = updated_enabled
            self._invalidate_matcher()
            return pack_id

    def community_pack_metadata(self, pack_id: str) -> dict[str, object] | None:
        """Return a detached persisted community-pack snapshot, if one exists."""
        with self._lock:
            record = self._community_packs.get(pack_id)
            return None if record is None else copy.deepcopy(record)

    def remove_community_pack(self, pack_id: str) -> bool:
        """Atomically remove one community pack without touching bundled packs."""
        with self._lock:
            if pack_id not in self._community_packs:
                return False
            updated_packs = copy.deepcopy(self._community_packs)
            del updated_packs[pack_id]
            updated_enabled = tuple(item for item in self._enabled_packs if item != pack_id)
            self._write_data_locked(
                self._storage_data_locked(
                    community_packs=updated_packs, enabled_packs=updated_enabled
                )
            )
            self._community_packs = updated_packs
            self._enabled_packs = updated_enabled
            self._invalidate_matcher()
            return True

    def _personal_words_locked(self, promotion_threshold: int) -> list[str]:
        words = [
            entry.word
            for entry in self._entries
            if entry.source == "manual" or entry.frequency >= promotion_threshold
        ]
        words.extend(
            pair.corrected
            for pair in self._corrections
            if pair.count >= promotion_threshold
        )
        return words

    def _preferred_words_locked(self, promotion_threshold: int) -> list[str]:
        words = self._personal_words_locked(promotion_threshold)
        words.extend(
            term.word for pack in self._active_packs_locked() for term in pack.terms
        )
        unique: list[str] = []
        seen: set[str] = set()
        for word in words:
            key = word.casefold()
            if word and key not in seen:
                seen.add(key)
                unique.append(word)
        return unique

    @staticmethod
    def _bounded_context(prefix: str, words: Iterable[str]) -> str | None:
        selected: list[str] = []
        length = len(prefix) + 1  # final period
        for word in words:
            separator = 2 if selected else 0
            if length + separator + len(word) > CONTEXT_MAX_CHARS:
                break
            selected.append(word)
            length += separator + len(word)
        if not selected:
            return None
        return prefix + ", ".join(selected) + "."

    def build_initial_prompt(self, promotion_threshold: int = 2) -> str | None:
        """Build a bounded personal-first Whisper vocabulary hint."""
        with self._lock:
            return self._bounded_context(
                "Context words: ", self._preferred_words_locked(promotion_threshold)
            )

    def build_ai_context(self, promotion_threshold: int = 2) -> str:
        """Build a bounded personal-first preferred-spelling hint for refinement."""
        with self._lock:
            return (
                self._bounded_context(
                    "Preferred spellings: ",
                    self._preferred_words_locked(promotion_threshold),
                )
                or ""
            )

    def _compile_matcher_locked(self, promotion_threshold: int) -> None:
        signature = (
            promotion_threshold,
            self._entries,
            self._corrections,
            self._enabled_packs,
            tuple(
                (pack_id, str(record["content_hash"]))
                for pack_id, record in self._community_packs.items()
            ),
        )
        if signature == self._matcher_signature:
            return

        replacements: dict[str, tuple[str, str]] = {}
        personal_spellings: dict[str, str] = {}

        def add_replacement(alias: str, target: str) -> None:
            """Keep the first-priority original spelling for each regex-equivalent alias."""
            replacements.setdefault(literal_alias_key(alias), (alias, target))

        active_entries = self._active_entries_locked(promotion_threshold)
        for entry in active_entries:
            personal_spellings.setdefault(literal_alias_key(entry.word), entry.word)

        # Explicit aliases express stronger intent than an implicit canonical spelling.
        for entry in active_entries:
            for alias in entry.aliases:
                add_replacement(alias, entry.word)
        for entry in active_entries:
            add_replacement(entry.word, entry.word)

        # Validated adaptive corrections are next, but never replace personal aliases.
        for pair in self._corrections:
            if pair.count >= promotion_threshold:
                add_replacement(pair.heard, pair.corrected)

        # Pack entries are only applied for explicit aliases. Hint-only terms stay hints.
        for pack in self._active_packs_locked():
            for term in pack.terms:
                canonical = personal_spellings.get(literal_alias_key(term.word), term.word)
                for alias in term.aliases:
                    add_replacement(alias, canonical)

        aliases = sorted(
            replacements.values(),
            key=lambda replacement: (-len(replacement[0]), replacement[0]),
        )
        self._matcher = (
            re.compile(
                r"(?<!\w)(?:"
                + "|".join(f"({re.escape(alias)})" for alias, _ in aliases)
                + r")(?!\w)",
                re.IGNORECASE,
            )
            if aliases
            else None
        )
        self._replacement_targets = tuple(target for _, target in aliases)
        self._matcher_signature = signature

    def apply_corrections(self, text: str, promotion_threshold: int = 2) -> str:
        """Apply one literal, non-cascading pass outside URLs, email, and code."""
        with self._lock:
            self._compile_matcher_locked(promotion_threshold)
            matcher = self._matcher
            replacement_targets = self._replacement_targets
        if matcher is None:
            return text

        def replace(match: re.Match[str]) -> str:
            assert match.lastindex is not None
            return replacement_targets[match.lastindex - 1]

        def correct_unprotected(segment: str) -> str:
            return matcher.sub(replace, segment)

        parts: list[str] = []
        cursor = 0
        for protected in _PROTECTED_LITERAL_RE.finditer(text):
            parts.append(correct_unprotected(text[cursor : protected.start()]))
            parts.append(protected.group(0))
            cursor = protected.end()
        parts.append(correct_unprotected(text[cursor:]))
        return "".join(parts)

    @property
    def entries(self) -> tuple[DictionaryEntry, ...]:
        with self._lock:
            return self._entries

    @property
    def corrections(self) -> tuple[CorrectionPair, ...]:
        with self._lock:
            return self._corrections

    @property
    def enabled_packs(self) -> tuple[str, ...]:
        with self._lock:
            return self._enabled_packs
