"""LLM client interface.

The loop depends on this protocol, not on the Anthropic SDK.  Tests use a
scripted fake implementation; the CLI uses AnthropicClient.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..protocol import ModelResponse


class LLMError(RuntimeError):
    """A user-visible model/transport error."""


class LLMClient(Protocol):
    model: str

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        ...
