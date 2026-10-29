"""Anthropic Messages API adapter.

This is the only backend implemented for the exam.  It converts Anthropic's
text / tool_use content blocks into the internal ModelResponse, and converts
tool results back into a user message containing tool_result blocks.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any

from ..protocol import (
    ModelResponse,
    text_from_content,
    thinking_text_from_content,
    tool_calls_from_content,
)
from .base import LLMClient, LLMError

DEFAULT_MODEL = "claude-sonnet-5-5"


class AnthropicClient(LLMClient):
    def __init__(
        self,
        api_key: str | None = None,
        auth_token: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        max_tokens: int | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        thinking: bool | None = None,
        thinking_budget: int | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on install
            raise LLMError(
                "The 'anthropic' package is required. Run: pip install -e ."
            ) from exc

        self._anthropic = anthropic
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.auth_token = (
            auth_token
            if auth_token is not None
            else os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
        )
        if api_key:
            # An explicitly supplied key wins over an ambient gateway token.
            self.auth_token = ""
        if not self.api_key and not self.auth_token:
            raise LLMError(
                "Set ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN). "
                "Copy .env.example to .env and fill it in."
            )
        self.model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens or int(
            os.environ.get("ANTHROPIC_MAX_TOKENS", "4096")
        )
        self.max_retries = max_retries
        self.timeout = timeout
        if thinking is None:
            thinking = os.environ.get("ANTHROPIC_THINKING", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        budget = thinking_budget or int(
            os.environ.get("ANTHROPIC_THINKING_BUDGET", "2048") or 2048
        )
        self.thinking_budget = max(1024, budget) if thinking else 0

        client_kwargs: dict[str, Any] = {"timeout": timeout}
        if self.auth_token:
            # Some Anthropic-compatible gateways use a bearer token.
            client_kwargs["auth_token"] = self.auth_token
        else:
            client_kwargs["api_key"] = self.api_key
        resolved_base = (base_url or os.environ.get("ANTHROPIC_BASE_URL", "")).strip()
        if resolved_base:
            client_kwargs["base_url"] = resolved_base
        self.client = anthropic.Anthropic(**client_kwargs)

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            request["tools"] = tools
        if self.thinking_budget:
            # Anthropic requires budget_tokens < max_tokens.
            request["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }
            request["max_tokens"] = max(
                self.max_tokens, self.thinking_budget + 1024
            )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.messages.create(**request)
                content = []
                for block in response.content:
                    converted = self._block_to_dict(block)
                    if converted is not None:
                        content.append(converted)
                if not content:
                    raise LLMError("Anthropic returned an empty response.")
                usage = getattr(response, "usage", None)
                final_text = text_from_content(content)
                tool_calls = tool_calls_from_content(content)
                thought = thinking_text_from_content(content)
                if not final_text and not tool_calls:
                    if thought:
                        raise LLMError(
                            "Model returned only thinking; no final answer or "
                            "tool call."
                        )
                    raise LLMError("Anthropic returned an empty response.")
                return ModelResponse(
                    text=final_text or None,
                    thought=thought,
                    tool_calls=tool_calls,
                    stop_reason=str(getattr(response, "stop_reason", "end_turn") or "end_turn"),
                    usage={
                        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                    },
                    raw_content=content,
                )
            except Exception as exc:  # noqa: BLE001 - classify below
                last_error = exc
                if attempt >= self.max_retries or not self._is_retryable(exc):
                    break
                delay = min(2.0**attempt, 8.0) + random.random()
                time.sleep(delay)

        status = getattr(last_error, "status_code", None)
        name = type(last_error).__name__
        raise LLMError(
            f"Anthropic API error ({name}"
            + (f", status={status}" if status else "")
            + f"): {last_error}"
        ) from last_error

    @staticmethod
    def _block_to_dict(block: Any) -> dict[str, Any] | None:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            return {"type": "text", "text": str(getattr(block, "text", ""))}
        if block_type == "tool_use":
            return {
                "type": "tool_use",
                "id": str(getattr(block, "id", "")),
                "name": str(getattr(block, "name", "")),
                "input": dict(getattr(block, "input", {}) or {}),
            }
        if block_type == "thinking":
            return {
                "type": "thinking",
                "thinking": str(getattr(block, "thinking", "")),
                "signature": str(getattr(block, "signature", "")),
            }
        if block_type == "redacted_thinking":
            return {
                "type": "redacted_thinking",
                "data": str(getattr(block, "data", "")),
            }
        return None

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status in {408, 409, 429}:
            return True
        if isinstance(status, int) and status >= 500:
            return True
        name = type(exc).__name__
        return name in {
            "RateLimitError",
            "APIConnectionError",
            "APITimeoutError",
            "InternalServerError",
            "OverloadedError",
        }
