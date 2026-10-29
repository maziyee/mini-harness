from __future__ import annotations

from types import SimpleNamespace

import pytest

from mini_agent.llm.anthropic import AnthropicClient
from mini_agent.llm.base import LLMError


def test_anthropic_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(LLMError):
        AnthropicClient(api_key="")


def test_thinking_budget_config():
    assert AnthropicClient(api_key="test", thinking=True, thinking_budget=2048).thinking_budget == 2048
    assert AnthropicClient(api_key="test", thinking=True, thinking_budget=100).thinking_budget == 1024
    assert AnthropicClient(api_key="test", thinking=False).thinking_budget == 0


def test_block_to_dict_keeps_native_thinking():
    thinking = SimpleNamespace(
        type="thinking", thinking="内部推理", signature="sig-1"
    )
    assert AnthropicClient._block_to_dict(thinking) == {
        "type": "thinking",
        "thinking": "内部推理",
        "signature": "sig-1",
    }

    redacted = SimpleNamespace(type="redacted_thinking", data="encrypted")
    assert AnthropicClient._block_to_dict(redacted) == {
        "type": "redacted_thinking",
        "data": "encrypted",
    }
