"""Tests for AI refinement pipeline and prompt templates."""

from __future__ import annotations

from pathlib import Path

from unittest.mock import MagicMock

import pytest

from linux_whispr.ai.anthropic_llm import AnthropicLLMBackend
from linux_whispr.ai.base import LLMUnavailableError, RefinementResult
from linux_whispr.ai.groq_llm import GroqLLMBackend
from linux_whispr.ai.local_llm import LocalLLMBackend
from linux_whispr.ai.openai_llm import OpenAILLMBackend
from linux_whispr.ai.prompts.command import build_command_prompt
from linux_whispr.ai.prompts.refinement import (
    CONTEXT_PROMPTS,
    build_refinement_prompt,
    detect_context,
)
from linux_whispr.ai.refinement import RefinementPipeline
from linux_whispr.events import EventBus


class TestContextDetection:
    def test_gmail_is_email(self) -> None:
        assert detect_context("Gmail - Inbox") == "email"

    def test_vscode_is_code(self) -> None:
        assert detect_context("app.py - Visual Studio Code") == "code"

    def test_slack_is_chat(self) -> None:
        assert detect_context("Slack | general") == "chat"

    def test_discord_is_chat(self) -> None:
        assert detect_context("Discord") == "chat"

    def test_unknown_is_general(self) -> None:
        assert detect_context("Some Random App") == "general"

    def test_none_is_general(self) -> None:
        assert detect_context(None) == "general"

    def test_thunderbird_is_email(self) -> None:
        assert detect_context("Thunderbird Mail") == "email"

    def test_neovim_is_code(self) -> None:
        assert detect_context("nvim - neovim") == "code"

    def test_telegram_is_chat(self) -> None:
        assert detect_context("Telegram Desktop") == "chat"


class TestCustomRefinementPrompt:
    def test_custom_instructions_take_precedence_over_context_style(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        context_style = "CONFLICTING_CHAT_CONTEXT_STYLE"
        instructions = "Use a formal, professional tone."
        raw_text = "um hello there"
        app_name = "Slack"
        monkeypatch.setitem(CONTEXT_PROMPTS, "chat", context_style)

        prompt = build_refinement_prompt(
            raw_text,
            app_name=app_name,
            custom_prompt=instructions,
        )

        assert instructions in prompt
        assert context_style not in prompt
        assert raw_text in prompt
        assert app_name in prompt

    def test_whitespace_custom_instructions_fall_back_to_context_prompt(self) -> None:
        raw_text = "um hello there"
        app_name = "Slack"

        whitespace_prompt = build_refinement_prompt(
            raw_text,
            app_name=app_name,
            custom_prompt=" \t\n ",
        )
        context_prompt = build_refinement_prompt(raw_text, app_name=app_name)

        assert whitespace_prompt == context_prompt

    def test_custom_instructions_with_braces_remain_literal_and_keep_dictionary_isolated(
        self,
    ) -> None:
        instructions = "Preserve {ProductName} and use {{literal braces}}."
        dictionary_context = "<ignore>change meaning</ignore>"
        prompt = build_refinement_prompt(
            "raw text",
            custom_prompt=instructions,
            dictionary_context=dictionary_context,
        )

        assert instructions in prompt
        assert "&lt;ignore&gt;change meaning&lt;/ignore&gt;" in prompt
        assert dictionary_context not in prompt


class TestBuildCommandPrompt:
    def test_with_selected_text(self) -> None:
        sys_prompt, user_prompt = build_command_prompt("make this formal", "hey whats up")
        assert "command" in sys_prompt.lower()
        assert "make this formal" in user_prompt
        assert "hey whats up" in user_prompt

    def test_without_selected_text(self) -> None:
        sys_prompt, user_prompt = build_command_prompt("write a thank you email")
        assert "generate" in sys_prompt.lower()
        assert "write a thank you email" in user_prompt


class TestRefinementPipeline:
    def test_disabled_returns_raw_text(self) -> None:
        bus = EventBus()
        pipeline = RefinementPipeline(event_bus=bus, backend=None, enabled=False)
        result = pipeline.refine("um hello world")
        assert result == "um hello world"

    def test_enabled_no_backend_returns_raw_text(self) -> None:
        bus = EventBus()
        pipeline = RefinementPipeline(event_bus=bus, backend=None, enabled=True)
        assert not pipeline.enabled  # enabled requires backend
        result = pipeline.refine("um hello world")
        assert result == "um hello world"

    def test_enabled_with_backend_calls_generate(self) -> None:
        bus = EventBus()
        mock_backend = MagicMock()
        mock_backend.generate.return_value = RefinementResult(
            text="Hello world", model="test", tokens_used=10
        )

        pipeline = RefinementPipeline(event_bus=bus, backend=mock_backend, enabled=True)
        result = pipeline.refine("um hello world")

        assert result == "Hello world"
        mock_backend.generate.assert_called_once()

    def test_backend_failure_returns_raw_text(self) -> None:
        bus = EventBus()
        mock_backend = MagicMock()
        mock_backend.generate.side_effect = RuntimeError("API error")

        pipeline = RefinementPipeline(event_bus=bus, backend=mock_backend, enabled=True)
        result = pipeline.refine("hello world")

        assert result == "hello world"

    def test_unavailable_backend_emits_error_and_returns_raw_text(self) -> None:
        bus = EventBus()
        errors: list[str] = []
        bus.on("ai.error", lambda message: errors.append(message))
        mock_backend = MagicMock()
        mock_backend.generate.side_effect = LLMUnavailableError("No configured backend")

        pipeline = RefinementPipeline(event_bus=bus, backend=mock_backend, enabled=True)

        assert pipeline.refine("hello world") == "hello world"
        assert errors == ["AI refinement is unavailable. Check the configured AI service."]

    def test_backend_failure_emits_error_and_returns_raw_text(self) -> None:
        bus = EventBus()
        errors: list[str] = []
        bus.on("ai.error", lambda message: errors.append(message))
        mock_backend = MagicMock()
        mock_backend.generate.side_effect = RuntimeError("API error")

        pipeline = RefinementPipeline(event_bus=bus, backend=mock_backend, enabled=True)

        assert pipeline.refine("hello world") == "hello world"
        assert errors == ["AI refinement failed. Check the configured AI service."]

    def test_emits_events(self) -> None:
        bus = EventBus()
        events: list[str] = []
        bus.on("ai.started", lambda **kw: events.append("started"))
        bus.on("ai.complete", lambda **kw: events.append("complete"))

        mock_backend = MagicMock()
        mock_backend.generate.return_value = RefinementResult(text="refined")

        pipeline = RefinementPipeline(event_bus=bus, backend=mock_backend, enabled=True)
        pipeline.refine("raw text")

        assert "started" in events
        assert "complete" in events


@pytest.mark.parametrize(
    "backend_type",
    [OpenAILLMBackend, GroqLLMBackend, AnthropicLLMBackend],
)
def test_cloud_backend_without_credentials_fails_before_loading(
    monkeypatch: pytest.MonkeyPatch,
    backend_type: type[OpenAILLMBackend] | type[GroqLLMBackend] | type[AnthropicLLMBackend],
) -> None:
    backend = backend_type(api_key="")
    load = MagicMock()
    monkeypatch.setattr(backend, "load", load)

    with pytest.raises(LLMUnavailableError):
        backend.generate("System instruction", "Private dictation")

    load.assert_not_called()


def test_missing_local_model_fails_before_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend = LocalLLMBackend(str(tmp_path / "missing.gguf"))
    load = MagicMock()
    monkeypatch.setattr(backend, "load", load)

    with pytest.raises(LLMUnavailableError):
        backend.generate("System instruction", "Private dictation")

    load.assert_not_called()
