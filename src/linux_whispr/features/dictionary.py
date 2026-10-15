"""Custom dictionary and opt-in vocabulary pack manager for dictation."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from linux_whispr.constants import DICTIONARY_FILE
from linux_whispr.features.dictionary_packs import BUNDLED_PACKS, DictionaryPack

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
        key = value.casefold()
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
        self._matcher_signature: tuple[object, ...] | None = None
        self._matcher: re.Pattern[str] | None = None
        self._replacement_targets: tuple[str, ...] = ()

    def load(self) -> None:
        """Load dictionary data, preserving legacy files without aliases or packs."""
        if not self._path.exists():
            logger.info("No dictionary file found at %s", self._path)
            return

        try:
            with open(self._path, encoding="utf-8") as file:
                data = json.load(file)

            entries = tuple(
                DictionaryEntry(
                    word=entry["word"],
                    source=entry.get("source", "manual"),
                    frequency=entry.get("frequency", 0),
                    added_at=entry.get("added_at", datetime.now().isoformat()),
                    category=entry.get("category", "general"),
                    aliases=_normalize_aliases(entry.get("aliases", ())),
                )
                for entry in data.get("entries", [])
            )
            corrections = tuple(
                CorrectionPair(
                    heard=correction["heard"],
                    corrected=correction["corrected"],
                    count=correction.get("count", 1),
                    last_seen=correction.get("last_seen", datetime.now().isoformat()),
                )
                for correction in data.get("corrections", [])
            )
            enabled_packs = tuple(
                pack_id
                for pack_id in dict.fromkeys(data.get("enabled_packs", []))
                if isinstance(pack_id, str)
            )
            with self._lock:
                self._entries = entries
                self._corrections = corrections
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

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [asdict(entry) for entry in self._entries],
            "corrections": [asdict(correction) for correction in self._corrections],
            "enabled_packs": list(self._enabled_packs),
        }
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
        """Enable or disable one known bundled pack without touching personal data."""
        known_ids = {pack.id for pack in BUNDLED_PACKS}
        if pack_id not in known_ids:
            raise KeyError(pack_id)
        with self._lock:
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

    def pack_catalog(self) -> tuple[DictionaryPack, ...]:
        """Return immutable bundled pack definitions in their stable display order."""
        return BUNDLED_PACKS

    def is_pack_enabled(self, pack_id: str) -> bool:
        with self._lock:
            return pack_id in self._enabled_packs

    def _active_packs_locked(self) -> tuple[DictionaryPack, ...]:
        enabled = set(self._enabled_packs)
        return tuple(pack for pack in BUNDLED_PACKS if pack.id in enabled)

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
        )
        if signature == self._matcher_signature:
            return

        replacements: dict[str, tuple[str, str]] = {}
        manual_spellings: dict[str, str] = {}

        def add_replacement(alias: str, target: str) -> None:
            """Keep the first-priority original spelling for each folded alias."""
            replacements.setdefault(alias.casefold(), (alias, target))

        active_entries = tuple(
            entry
            for entry in self._entries
            if entry.source == "manual" or entry.frequency >= promotion_threshold
        )
        for entry in active_entries:
            manual_spellings[entry.word.casefold()] = entry.word

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
                canonical = manual_spellings.get(term.word.casefold(), term.word)
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
