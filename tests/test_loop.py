from __future__ import annotations

import json

from helpers import FakeLLM, FailingLLM, text_response, tool_response
from mini_agent.context import ContextManager
from mini_agent.loop import AgentLoop
from mini_agent.memory import MemoryStore
from mini_agent.protocol import ModelResponse, ToolCall
from mini_agent.session import SessionStore
from mini_agent.tools import build_default_tools
from mini_agent.trace import TraceLogger


def _make_loop(
    tmp_path,
    responses,
    max_steps=4,
    max_turns=5,
    on_thought=None,
    keep_thinking_in_memory=False,
):
    store = SessionStore(tmp_path / "sessions")
    memory = MemoryStore(tmp_path / "memory")
    loop = AgentLoop(
        llm=FakeLLM(responses),
        tool_executor=build_default_tools(),
        session_store=store,
        memory_store=memory,
        context=ContextManager(context_window=1_000_000),
        trace_factory=lambda user, session: TraceLogger(
            user, session, root=tmp_path / "logs"
        ),
        on_thought=on_thought,
        keep_thinking_in_memory=keep_thinking_in_memory,
        max_steps=max_steps,
        max_turns=max_turns,
    )
    return loop, store, memory


def test_thinking_is_output_but_not_persisted(tmp_path):
    thoughts: list[str] = []
    response = ModelResponse(
        text="答案",
        thought="内部推理",
        raw_content=[
            {"type": "thinking", "thinking": "内部推理", "signature": "sig"},
            {"type": "text", "text": "答案"},
        ],
        stop_reason="end_turn",
    )
    loop, store, _ = _make_loop(
        tmp_path, [response], on_thought=thoughts.append
    )
    session = store.create("alice", "s1")

    assert loop.run_turn(session, "问题") == "答案"
    assert thoughts == ["内部推理"]

    # In-memory history is cleaned at turn end.
    blocks = [
        block
        for message in session.messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
    ]
    assert all(
        block.get("type") not in {"thinking", "redacted_thinking"}
        for block in blocks
    )

    # Disk history never contains thinking.
    data = json.loads(
        (tmp_path / "sessions" / "alice" / "s1.json").read_text(encoding="utf-8")
    )
    disk_blocks = [
        block
        for message in data["messages"]
        if isinstance(message.get("content"), list)
        for block in message["content"]
    ]
    assert all(
        block.get("type") not in {"thinking", "redacted_thinking"}
        for block in disk_blocks
    )


def test_keep_thinking_in_memory_across_turns(tmp_path):
    first = ModelResponse(
        text="答案1",
        thought="思考1",
        raw_content=[
            {"type": "thinking", "thinking": "思考1", "signature": "sig-1"},
            {"type": "text", "text": "答案1"},
        ],
        stop_reason="end_turn",
    )
    second = ModelResponse(
        text="答案2",
        raw_content=[{"type": "text", "text": "答案2"}],
        stop_reason="end_turn",
    )
    loop, store, _ = _make_loop(
        tmp_path,
        [first, second],
        keep_thinking_in_memory=True,
    )
    session = store.create("alice", "s1")

    loop.run_turn(session, "问题1")
    blocks = [
        block
        for message in session.messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
    ]
    assert any(block.get("type") == "thinking" for block in blocks)

    # Disk is still clean even when in-memory replay is enabled.
    data = json.loads(
        (tmp_path / "sessions" / "alice" / "s1.json").read_text(encoding="utf-8")
    )
    disk_blocks = [
        block
        for message in data["messages"]
        if isinstance(message.get("content"), list)
        for block in message["content"]
    ]
    assert all(
        block.get("type") not in {"thinking", "redacted_thinking"}
        for block in disk_blocks
    )

    loop.run_turn(session, "问题2")
    # The second model call should have received the prior thinking block.
    second_call_messages = loop.llm.calls[-1]["messages"]
    second_call_blocks = [
        block
        for message in second_call_messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
    ]
    assert any(block.get("type") == "thinking" for block in second_call_blocks)


def test_direct_answer(tmp_path):
    loop, store, _ = _make_loop(tmp_path, [text_response("hello")])
    session = store.create("alice", "s1")

    assert loop.run_turn(session, "hi") == "hello"
    assert session.turn_count == 1
    assert len(session.messages) == 2
    assert session.messages[0]["content"] == "hi"
    assert (tmp_path / "logs" / "alice" / "s1.jsonl").exists()


def test_tool_call_round_trip(tmp_path):
    call = ToolCall("call-1", "todo", {"action": "add", "content": "写周报"})
    loop, store, _ = _make_loop(
        tmp_path, [tool_response([call]), text_response("已添加待办")]
    )
    session = store.create("alice", "s1")

    assert loop.run_turn(session, "记一条待办：写周报") == "已添加待办"
    assert session.turn_count == 1
    assert len(session.todos) == 1
    assert session.todos[0]["content"] == "写周报"
    # user, assistant(tool_use), user(tool_result), assistant(text)
    assert len(session.messages) == 4


def test_max_steps_stops(tmp_path):
    calls = [
        tool_response([ToolCall("c1", "calculator", {"expression": "1+1"})]),
        tool_response([ToolCall("c2", "calculator", {"expression": "2+2"})]),
    ]
    loop, store, _ = _make_loop(tmp_path, calls, max_steps=2)
    session = store.create("alice", "s1")

    result = loop.run_turn(session, "算一下")
    assert "Stopped after 2" in result
    assert session.turn_count == 1
    assert session.messages[-1]["role"] == "assistant"
    assert "Stopped after 2" in session.messages[-1]["content"][0]["text"]


def test_llm_error_rolls_back_user_message(tmp_path):
    loop, store, _ = _make_loop(tmp_path, [])
    loop.llm = FailingLLM()
    session = store.create("alice", "s1")

    result = loop.run_turn(session, "hi")
    assert result.startswith("[LLM error]")
    assert session.messages == []
    assert session.status == "error"


def test_follow_up_sees_session_todos(tmp_path):
    add_call = ToolCall("call-1", "todo", {"action": "add", "content": "写周报"})
    responses = [
        tool_response([add_call]),
        text_response("已添加待办"),
        text_response("你有一条待办：写周报"),
    ]
    loop, store, _ = _make_loop(tmp_path, responses)
    session = store.create("alice", "s1")

    loop.run_turn(session, "记一条待办：写周报")
    reply = loop.run_turn(session, "刚才那条待办是什么？")

    assert "写周报" in reply
    system = loop.llm.calls[-1]["system"]
    assert "Current todos" in system
    assert "写周报" in system
    assert session.turn_count == 2


def test_memory_tool_round_trip(tmp_path):
    call = ToolCall(
        "call-m1",
        "memory",
        {
            "action": "save",
            "type": "fact",
            "content": "项目代号是 mini-agent",
        },
    )
    loop, store, memory = _make_loop(
        tmp_path, [tool_response([call]), text_response("已保存")]
    )
    session = store.create("alice", "s1")

    assert loop.run_turn(session, "请保存这个事实") == "已保存"
    records = memory.load("alice")
    assert len(records) == 1
    assert records[0].content == "项目代号是 mini-agent"
    assert records[0].source_session == "s1"


def test_two_sessions_are_isolated(tmp_path):
    responses = [text_response("one"), text_response("two")]
    loop, store, _ = _make_loop(tmp_path, responses)
    first = store.create("alice", "window-1")
    second = store.create("alice", "window-2")

    loop.run_turn(first, "first window")
    loop.run_turn(second, "second window")

    assert first.messages[0]["content"] == "first window"
    assert second.messages[0]["content"] == "second window"
    assert len(first.todos) == 0
    assert len(second.todos) == 0
