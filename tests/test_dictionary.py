"""Tests for custom dictionary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from linux_whispr.features.community_dictionary import CommunityDictionaryConflict
from linux_whispr.features.dictionary import Dictionary


class TestDictionary:
    def test_add_and_build_prompt(self, tmp_path: Path) -> None:
        d = Dictionary(tmp_path / "dict.json")
        d.add_word("Kubernetes")
        d.add_word("SQLAlchemy", category="technical")

        prompt = d.build_initial_prompt()
        assert prompt is not None
        assert "Kubernetes" in prompt
        assert "SQLAlchemy" in prompt

    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "dict.json"
        d = Dictionary(path)
        d.add_word("TestWord")
        d.save()

        d2 = Dictionary(path)
        d2.load()
        assert len(d2.entries) == 1
        assert d2.entries[0].word == "TestWord"

    def test_remove_word(self, tmp_path: Path) -> None:
        d = Dictionary(tmp_path / "dict.json")
        d.add_word("ToRemove")
        assert d.remove_word("toremove")  # case-insensitive
        assert len(d.entries) == 0

    def test_duplicate_word_increments_frequency(self, tmp_path: Path) -> None:
        d = Dictionary(tmp_path / "dict.json")
        d.add_word("Dupe")
        d.add_word("Dupe")
        assert len(d.entries) == 1
        assert d.entries[0].frequency == 1

    def test_correction_pairs(self, tmp_path: Path) -> None:
        d = Dictionary(tmp_path / "dict.json")
        d.add_correction("sequel alchemy", "SQLAlchemy")
        d.add_correction("sequel alchemy", "SQLAlchemy")

        assert len(d.corrections) == 1
        assert d.corrections[0].count == 2

        # Should appear in prompt after meeting threshold
        prompt = d.build_initial_prompt(promotion_threshold=2)
        assert prompt is not None
        assert "SQLAlchemy" in prompt


class TestDictionaryPacks:
    def test_legacy_data_loads_with_empty_aliases_and_packs(self, tmp_path: Path) -> None:
        path = tmp_path / "dict.json"
        path.write_text(
            '{"entries":[{"word":"Müller","source":"manual","frequency":0,'
            '"added_at":"2024-01-01T00:00:00","category":"personal_names"}],'
            '"corrections":[]}',
            encoding="utf-8",
        )

        dictionary = Dictionary(path)
        dictionary.load()

        assert dictionary.entries[0].word == "Müller"
        assert dictionary.entries[0].aliases == ()
        assert dictionary.enabled_packs == ()

    def test_disabling_pack_keeps_personal_data(self, tmp_path: Path) -> None:
        dictionary = Dictionary(tmp_path / "dict.json")
        dictionary.add_word("Ada", aliases=["ayda"])
        dictionary.set_pack_enabled("coding", True)
        assert dictionary.apply_corrections("type script") == "TypeScript"

        dictionary.set_pack_enabled("coding", False)

        assert dictionary.entries[0].word == "Ada"
        assert dictionary.apply_corrections("type script") == "type script"
        reloaded = Dictionary(tmp_path / "dict.json")
        reloaded.load()
        assert reloaded.entries[0].aliases == ("ayda",)
        assert reloaded.enabled_packs == ()

    def test_personal_spelling_and_aliases_win_pack_and_correction_collisions(
        self, tmp_path: Path
    ) -> None:
        dictionary = Dictionary(tmp_path / "dict.json")
        dictionary.add_word("Typescript", aliases=["type script"])
        dictionary.add_correction("type script", "WrongTarget")
        dictionary.add_correction("type script", "WrongTarget")
        dictionary.set_pack_enabled("coding", True)

        assert dictionary.apply_corrections("type script") == "Typescript"

    def test_matcher_is_literal_bounded_non_cascading_and_protects_literals(
        self, tmp_path: Path
    ) -> None:
        dictionary = Dictionary(tmp_path / "dict.json")
        dictionary.add_word("Beta", aliases=["alpha", "a.b", "münchen"])
        dictionary.add_word("Gamma", aliases=["beta"])

        text = (
            "alpha beta a.b xa.b a.b2 prealpha alpha_value übermünchen münchen "
            "ftp://postgress.example/a.b foo@a.b `a.b` ``` a.b ``` ~~~ a.b"
        )

        assert dictionary.apply_corrections(text) == (
            "Beta Gamma Beta xa.b a.b2 prealpha alpha_value übermünchen Beta "
            "ftp://postgress.example/a.b foo@a.b `a.b` ``` a.b ``` ~~~ a.b"
        )

    def test_matcher_preserves_sharp_s_alias_and_uses_matched_alternative(
        self, tmp_path: Path
    ) -> None:
        dictionary = Dictionary(tmp_path / "dict.json")
        dictionary.add_word("Straßenbahn", aliases=["straßen bahn"])
        dictionary.add_word("CLI", aliases=["c l i"])

        assert dictionary.apply_corrections("straßen bahn STRAẞEN BAHN c l ı") == (
            "Straßenbahn Straßenbahn CLI"
        )


def _community_document(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "format": "linux-whispr-dictionary",
        "schema_version": 1,
        "id": "community-terms",
        "name": "Community terms",
        "entries": entries,
    }


def _community_source() -> dict[str, str]:
    return {"kind": "file", "filename": "terms.json"}


class TestCommunityDictionaryConflictPolicy:
    def test_unicode_equivalent_personal_aliases_win_preview_and_runtime(
        self, tmp_path: Path
    ) -> None:
        dictionary = Dictionary(tmp_path / "dictionary.json")
        dictionary.add_word("Personal", aliases=["ı", "ſ", "K", "ß"])
        document = _community_document(
            [
                {"word": "Community", "aliases": ["i", "s", "k"]},
                {"word": "Double S", "aliases": ["ss"]},
            ]
        )

        preview = dictionary.preview_community_pack(document, source=_community_source())
        dictionary.install_community_pack(
            document, source=_community_source(), expected_revision=preview["revision"]
        )

        assert {conflict["alias"] for conflict in preview["conflicts"]} == {"i", "s", "k"}
        assert dictionary.apply_corrections("i I İ ı s S ſ k K K") == (
            "Personal Personal Personal Personal Personal Personal Personal "
            "Personal Personal Personal"
        )
        assert dictionary.apply_corrections("ss ß") == "Double S Personal"

    def test_preview_and_install_share_promotion_threshold_policy(
        self, tmp_path: Path
    ) -> None:
        dictionary = Dictionary(tmp_path / "dictionary.json")
        dictionary.add_word("Learned spelling", source="auto-learned", aliases=["heard"])
        dictionary.add_word("Learned spelling")
        dictionary.add_word("Learned spelling")
        document = _community_document(
            [{"word": "Community spelling", "aliases": ["heard"]}]
        )

        default_preview = dictionary.preview_community_pack(
            document, source=_community_source()
        )
        threshold_preview = dictionary.preview_community_pack(
            document, source=_community_source(), promotion_threshold=3
        )

        assert default_preview["conflicts"]
        assert threshold_preview["conflicts"] == []
        assert default_preview["revision"] != threshold_preview["revision"]
        with pytest.raises(CommunityDictionaryConflict):
            dictionary.install_community_pack(
                document,
                source=_community_source(),
                expected_revision=threshold_preview["revision"],
            )

        dictionary.install_community_pack(
            document,
            source=_community_source(),
            expected_revision=threshold_preview["revision"],
            promotion_threshold=3,
        )

        assert dictionary.apply_corrections("heard") == "Learned spelling"
        assert (
            dictionary.apply_corrections("heard", promotion_threshold=3)
            == "Community spelling"
        )

    def test_updating_earlier_pack_reports_later_pack_alias_takeover(
        self, tmp_path: Path
    ) -> None:
        dictionary = Dictionary(tmp_path / "dictionary.json")
        first = _community_document([{"word": "First", "aliases": ["first alias"]}])
        first_preview = dictionary.preview_community_pack(first, source=_community_source())
        first_id = dictionary.install_community_pack(
            first, source=_community_source(), expected_revision=first_preview["revision"]
        )
        second = _community_document([{"word": "Second", "aliases": ["shared alias"]}])
        second_preview = dictionary.preview_community_pack(second, source=_community_source())
        dictionary.install_community_pack(
            second, source=_community_source(), expected_revision=second_preview["revision"]
        )
        replacement = _community_document(
            [{"word": "Updated first", "aliases": ["shared alias"]}]
        )

        update_preview = dictionary.preview_community_pack(
            replacement, source=_community_source(), pack_id=first_id
        )

        assert update_preview["conflicts"] == [
            {
                "alias": "shared alias",
                "existing": "Second",
                "incoming": "Updated first",
                "scope": "pack",
            }
        ]
        dictionary.install_community_pack(
            replacement,
            source=_community_source(),
            expected_revision=update_preview["revision"],
            pack_id=first_id,
        )
        assert dictionary.apply_corrections("shared alias") == "Updated first"

    def test_pack_reorder_invalidates_pending_preview(self, tmp_path: Path) -> None:
        path = tmp_path / "dictionary.json"
        dictionary = Dictionary(path)
        first = _community_document([{"word": "First", "aliases": ["first alias"]}])
        first_preview = dictionary.preview_community_pack(first, source=_community_source())
        dictionary.install_community_pack(
            first, source=_community_source(), expected_revision=first_preview["revision"]
        )
        second = _community_document([{"word": "Second", "aliases": ["second alias"]}])
        second_preview = dictionary.preview_community_pack(second, source=_community_source())
        dictionary.install_community_pack(
            second, source=_community_source(), expected_revision=second_preview["revision"]
        )
        pending = _community_document([{"word": "Pending", "aliases": ["pending alias"]}])
        preview = dictionary.preview_community_pack(pending, source=_community_source())

        persisted = json.loads(path.read_text(encoding="utf-8"))
        records = persisted["community_packs"]
        persisted["community_packs"] = {
            pack_id: records[pack_id] for pack_id in reversed(records)
        }
        path.write_text(json.dumps(persisted), encoding="utf-8")
        dictionary.load()

        with pytest.raises(CommunityDictionaryConflict):
            dictionary.install_community_pack(
                pending, source=_community_source(), expected_revision=preview["revision"]
            )
