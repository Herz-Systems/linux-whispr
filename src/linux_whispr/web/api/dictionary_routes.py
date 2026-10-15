"""Dictionary API routes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from linux_whispr.features.dictionary import Dictionary

router = APIRouter(tags=["dictionary"])


class AddWordRequest(BaseModel):
    word: str
    source: str = "manual"
    category: str = "general"
    aliases: list[str] | None = None


class SetPackEnabledRequest(BaseModel):
    enabled: bool




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


def _pack_response(dictionary: Dictionary) -> list[dict[str, object]]:
    return [
        {
            "id": pack.id,
            "name": pack.name,
            "description": pack.description,
            "enabled": dictionary.is_pack_enabled(pack.id),
            "term_count": len(pack.terms),
            "alias_count": sum(len(term.aliases) for term in pack.terms),
            "terms": [
                {"word": term.word, "aliases": list(term.aliases)} for term in pack.terms
            ],
            "sources": [{"title": title, "url": url} for title, url in pack.sources],
        }
        for pack in dictionary.pack_catalog()
    ]


@router.get("/dictionary")
async def get_dictionary(request: Request) -> dict[str, object]:
    """Get personal dictionary data and the immutable bundled pack catalog."""
    dictionary = _get_dictionary(request)
    return {
        "entries": [asdict(entry) for entry in dictionary.entries],
        "corrections": [asdict(correction) for correction in dictionary.corrections],
        "packs": _pack_response(dictionary),
    }


@router.post("/dictionary/words")
async def add_word(req: AddWordRequest, request: Request) -> dict[str, str]:
    """Add a personal word or update aliases for an existing personal word."""
    dictionary = _get_dictionary(request)
    dictionary.add_word(
        req.word, source=req.source, category=req.category, aliases=req.aliases
    )
    return {"status": "ok", "message": f"Word '{req.word}' added"}


@router.delete("/dictionary/words/{word}")
async def remove_word(word: str, request: Request) -> dict[str, str]:
    """Remove a personal dictionary word."""
    dictionary = _get_dictionary(request)
    removed = dictionary.remove_word(word)
    if removed:
        return {"status": "ok", "message": f"Word '{word}' removed"}
    return {"status": "error", "message": f"Word '{word}' not found"}


@router.delete("/dictionary/corrections/{index}")
async def remove_correction(index: int, request: Request) -> dict[str, str]:
    """Remove a correction by index."""
    removed = _get_dictionary(request).remove_correction(index)
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
        _get_dictionary(request).set_pack_enabled(pack_id, req.enabled)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail=f"Unknown dictionary pack '{pack_id}'."
        ) from error
    return {"status": "ok"}
