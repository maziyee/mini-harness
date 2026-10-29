"""Internal message and tool-call protocol.

The rest of the runtime speaks this small, provider-neutral shape.  The
Anthropic adapter is the only place that knows about ``tool_use`` /
``tool_result`` content blocks; switching providers later means writing
another adapter, not touching the loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

THINKING_BLOCK_TYPES = {"thinking", "redacted_thinking"}


def thinking_text_from_content(content: list[dict[str, Any]]) -> str | None:
    """Join native Anthropic thinking blocks for display/tracing.

    Thinking blocks stay in ``raw_content`` so tool loops can pass them back
    to the API; persistence strips them via ``strip_thinking_blocks``.
    """
    parts: list[str] = []
    for block in content:
        if block.get("type") != "thinking":
            continue
        text = block.get("thinking") or block.get("text") or ""
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip() or None


def strip_thinking_blocks(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a copy of messages without thinking / redacted_thinking blocks.

    Used before writing to session JSON, transcripts, or summary prompts so
    reasoning never reaches disk.  Text and tool_use blocks are preserved.
    """
    cleaned: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            filtered = [
                block
                for block in content
                if not (
                    isinstance(block, dict)
                    and block.get("type") in THINKING_BLOCK_TYPES
                )
            ]
            if not filtered:
                # A message made only of thinking has nothing left to replay.
                continue
            cleaned.append({**message, "content": filtered})
        else:
            cleaned.append(message)
    return cleaned


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class ModelResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)
    # Provider-native assistant content blocks.  The loop appends these
    # verbatim so tool_use ids stay paired with their tool_result blocks.
    raw_content: list[dict[str, Any]] = field(default_factory=list)
    thought: str | None = None


def text_from_content(content: list[dict[str, Any]]) -> str:
    """Join all text blocks, ignoring tool_use / thinking blocks."""
    parts: list[str] = []
    for block in content:
        if block.get("type") == "text" and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


def tool_calls_from_content(content: list[dict[str, Any]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for block in content:
        if block.get("type") != "tool_use":
            continue
        calls.append(
            ToolCall(
                id=str(block.get("id", "")),
                name=str(block.get("name", "")),
                arguments=dict(block.get("input") or {}),
            )
        )
    return calls


def user_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def assistant_message(content: list[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def tool_result_message(results: list[ToolResult]) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": result.tool_use_id,
                "content": result.content,
                "is_error": result.is_error,
            }
            for result in results
        ],
    }


def message_text(message: dict[str, Any]) -> str:
    """Best-effort text extraction for /history and tracing."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        elif block.get("type") == "tool_use":
            parts.append(f"[tool_use {block.get('name')} {block.get('input')}]")
        elif block.get("type") == "tool_result":
            parts.append(f"[tool_result {block.get('tool_use_id')}]")
    return "\n".join(p for p in parts if p)
