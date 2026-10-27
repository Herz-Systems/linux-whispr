"""Text refinement pipeline — orchestrates AI post-processing of transcriptions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from linux_whispr.ai.base import LLMUnavailableError
from linux_whispr.ai.prompts.refinement import (
    build_refinement_prompt,
    build_refinement_system_prompt,
)

if TYPE_CHECKING:
    from linux_whispr.ai.base import LLMBackend, RefinementResult
    from linux_whispr.events import EventBus

logger = logging.getLogger(__name__)


class RefinementPipeline:
    """Orchestrates AI text refinement after STT transcription.

    Pipeline: raw_text → context detection → prompt building → LLM → refined_text
    """

    def __init__(
        self,
        event_bus: EventBus,
        backend: LLMBackend | None = None,
        enabled: bool = False,
        custom_prompt: str = "",
    ) -> None:
        self._event_bus = event_bus
        self._backend = backend
        self._enabled = enabled
        self._custom_prompt = custom_prompt

    @property
    def enabled(self) -> bool:
        return self._enabled and self._backend is not None

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def refine(
        self,
        raw_text: str,
        app_name: str | None = None,
        dictionary_context: str = "",
        language: str | None = None,
    ) -> str:
        """Refine raw transcription text using AI.

        If disabled or no backend available, returns raw_text unchanged.
        """
        if not self.enabled:
            return raw_text

        assert self._backend is not None

        self._event_bus.emit("ai.started")

        prompt = build_refinement_prompt(
            raw_text=raw_text,
            app_name=app_name,
            dictionary_context=dictionary_context,
            custom_prompt=self._custom_prompt,
        )

        system_prompt = build_refinement_system_prompt(language)

        try:
            result: RefinementResult = self._backend.generate(
                system_prompt=system_prompt,
                user_prompt=prompt,
            )
            refined = result.text.strip()
            logger.info(
                "Refinement complete: %d → %d chars (model=%s, tokens=%d)",
                len(raw_text),
                len(refined),
                result.model,
                result.tokens_used,
            )
            self._event_bus.emit("ai.complete", text=refined)
            return refined

        except LLMUnavailableError:
            logger.warning("LLM backend unavailable, returning raw text")
            self._event_bus.emit(
                "ai.error",
                message="AI refinement is unavailable. Check the configured AI service.",
            )
            return raw_text

        except Exception:
            logger.exception("AI refinement failed, returning raw text")
            self._event_bus.emit(
                "ai.error",
                message="AI refinement failed. Check the configured AI service.",
            )
            return raw_text
