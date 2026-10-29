from __future__ import annotations

from mini_agent.protocol import (
    message_text,
    strip_thinking_blocks,
    text_from_content,
    thinking_text_from_content,
    tool_calls_from_content,
)


def test_text_and_tool_calls_from_content():
    content = [
        {"type": "text", "text": "let me check"},
        {
            "type": "tool_use",
            "id": "call-1",
            "name": "weather",
            "input": {"city": "北京"},
        },
    ]
    assert text_from_content(content) == "let me check"
    calls = tool_calls_from_content(content)
    assert len(calls) == 1
    assert calls[0].id == "call-1"
    assert calls[0].name == "weather"
    assert calls[0].arguments == {"city": "北京"}


def test_thinking_text_from_content():
    content = [
        {"type": "thinking", "thinking": "先查天气", "signature": "sig-1"},
        {"type": "redacted_thinking", "data": "encrypted"},
        {"type": "text", "text": "北京今天晴。"},
        {"type": "thinking", "thinking": "再记待办", "signature": "sig-2"},
    ]
    assert thinking_text_from_content(content) == "先查天气\n再记待办"
    assert text_from_content(content) == "北京今天晴。"


def test_strip_thinking_blocks_preserves_text_and_tool_use():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "内部推理", "signature": "sig"},
                {"type": "text", "text": "最终答案"},
                {
                    "type": "tool_use",
                    "id": "call-1",
                    "name": "todo",
                    "input": {"action": "list"},
                },
                {"type": "redacted_thinking", "data": "encrypted"},
            ],
        },
        {"role": "user", "content": "继续"},
    ]
    cleaned = strip_thinking_blocks(messages)
    assert cleaned[0]["content"] == [
        {"type": "text", "text": "最终答案"},
        {
            "type": "tool_use",
            "id": "call-1",
            "name": "todo",
            "input": {"action": "list"},
        },
    ]
    assert cleaned[1]["content"] == "继续"


def test_strip_thinking_blocks_drops_thinking_only_message():
    messages = [
        {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "只有思考"}],
        }
    ]
    assert strip_thinking_blocks(messages) == []


def test_message_text_handles_blocks():
    message = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "name": "todo", "input": {"action": "list"}},
        ],
    }
    text = message_text(message)
    assert "hello" in text
    assert "tool_use todo" in text
