from __future__ import annotations

from mini_agent.memory import MemoryRecord
from mini_agent.prompt import build_system_prompt
from mini_agent.session import Session


def test_prompt_places_summary_todos_and_memory():
    session = Session(id="s1", user_id="alice")
    session.summary = "用户在做 Agent 笔试，硬约束是只实现 Anthropic。"
    session.todos = [{"id": "t1", "content": "写周报", "status": "open"}]
    memories = [
        MemoryRecord(
            id="m1",
            type="preference",
            content="用户偏好先给结论",
        )
    ]

    system = build_system_prompt(session, memories)

    assert "## Conversation summary" in system
    assert "只实现 Anthropic" in system
    assert "## Current todos" in system
    assert "写周报" in system
    assert "## Long-term memory" in system
    assert "先给结论" in system
    assert "may be stale" in system
    assert "## Tool selection" in system
    for tool_name in ("todo", "memory", "calculator", "search", "read_docs", "weather"):
        assert tool_name in system
    # Tool descriptions live in the API schemas, not duplicated in the prompt.
    assert "## Available tools" not in system
