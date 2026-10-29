from __future__ import annotations

from mini_agent.memory import MemoryStore
from mini_agent.protocol import ToolCall
from mini_agent.session import Session
from mini_agent.tools import build_default_tools
from mini_agent.tools.executor import ToolContext


def _ctx(tmp_path):
    session = Session(id="s1", user_id="alice")
    return ToolContext(
        user_id="alice",
        session=session,
        artifacts_dir=(tmp_path / "artifacts") if tmp_path is not None else None,
    )


def test_calculator():
    tool_executor = build_default_tools()
    ctx = _ctx(None)
    result = tool_executor.execute(
        ToolCall("c1", "calculator", {"expression": "1 + 2 * 3"}), ctx
    )
    assert not result.is_error
    assert "7" in result.content

    result = tool_executor.execute(
        ToolCall("c2", "calculator", {"expression": "1 / 0"}), ctx
    )
    assert result.is_error

    result = tool_executor.execute(
        ToolCall("c3", "calculator", {"expression": "__import__('os')"}), ctx
    )
    assert result.is_error


def test_todo_lifecycle(tmp_path):
    tool_executor = build_default_tools()
    ctx = _ctx(tmp_path)
    add = tool_executor.execute(
        ToolCall(
            "t1",
            "todo",
            {"action": "add", "content": "给张三回邮件"},
        ),
        ctx,
    )
    assert not add.is_error
    assert "t1" in add.content
    assert len(ctx.session.todos) == 1

    done = tool_executor.execute(
        ToolCall("t2", "todo", {"action": "done", "item_id": "t1"}), ctx
    )
    assert not done.is_error
    assert "[x]" in done.content

    missing = tool_executor.execute(
        ToolCall("t3", "todo", {"action": "done", "item_id": "t99"}), ctx
    )
    assert missing.is_error


def test_search_and_weather(tmp_path):
    tool_executor = build_default_tools()
    ctx = _ctx(tmp_path)
    result = tool_executor.execute(
        ToolCall("s1", "search", {"query": "anthropic tool_use"}), ctx
    )
    assert not result.is_error
    assert "Anthropic" in result.content

    result = tool_executor.execute(
        ToolCall("w1", "weather", {"city": "北京", "date": "2026-10-26"}), ctx
    )
    assert not result.is_error
    assert "多云" in result.content

    result = tool_executor.execute(
        ToolCall("w2", "weather", {"city": "不存在的城市"}), ctx
    )
    assert result.is_error


def test_read_docs_and_traversal(tmp_path):
    tool_executor = build_default_tools()
    ctx = _ctx(tmp_path)
    result = tool_executor.execute(
        ToolCall("r1", "read_docs", {"path": "agent-notes.md"}), ctx
    )
    assert not result.is_error
    assert "Agent Loop" in result.content

    result = tool_executor.execute(
        ToolCall("r2", "read_docs", {"path": "../README.md"}), ctx
    )
    assert result.is_error
    assert "escapes" in result.content


def test_memory_tool_save_search_list(tmp_path):
    tool_executor = build_default_tools()
    session = Session(id="s1", user_id="alice")
    store = MemoryStore(tmp_path / "memory")
    ctx = ToolContext(
        user_id="alice",
        session=session,
        memory_store=store,
    )

    saved = tool_executor.execute(
        ToolCall(
            "m1",
            "memory",
            {
                "action": "save",
                "type": "preference",
                "content": "用户喜欢简洁回答",
            },
        ),
        ctx,
    )
    assert not saved.is_error
    assert len(store.load("alice")) == 1

    found = tool_executor.execute(
        ToolCall("m2", "memory", {"action": "search", "query": "简洁"}), ctx
    )
    assert not found.is_error
    assert "简洁" in found.content

    listed = tool_executor.execute(
        ToolCall("m3", "memory", {"action": "list"}), ctx
    )
    assert not listed.is_error
    assert "preference" in listed.content

    missing = tool_executor.execute(
        ToolCall("m4", "memory", {"action": "save", "type": "fact"}), ctx
    )
    assert missing.is_error


def test_executor_validation(tmp_path):
    tool_executor = build_default_tools()
    ctx = _ctx(tmp_path)

    unknown = tool_executor.execute(ToolCall("u1", "nope", {}), ctx)
    assert unknown.is_error
    assert "Unknown tool" in unknown.content

    missing = tool_executor.execute(
        ToolCall("m1", "calculator", {}), ctx
    )
    assert missing.is_error
    assert "missing required" in missing.content

    bad_enum = tool_executor.execute(
        ToolCall("e1", "todo", {"action": "explode"}), ctx
    )
    assert bad_enum.is_error
    assert "must be one of" in bad_enum.content
