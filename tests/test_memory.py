from __future__ import annotations

from mini_agent.memory import MemoryStore


def test_add_dedup_and_recall(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    first = store.add("alice", "preference", "用户喜欢简洁回答")
    assert first is not None

    duplicate = store.add("alice", "preference", "用户喜欢简洁回答")
    assert duplicate is not None
    assert len(store.load("alice")) == 1

    recalled = store.recall("alice", "回答可以简洁一点吗")
    assert [record.id for record in recalled] == [first.id]


def test_capture_explicit_signal(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    captured = store.capture_from_user_text(
        "alice", "记住：我的项目代号是 mini-agent", "window-1"
    )
    assert len(captured) == 1
    assert captured[0].type == "fact"
    assert "mini-agent" in captured[0].content

    no_capture = store.capture_from_user_text("alice", "今天天气不错", "window-1")
    assert no_capture == []

    # Stop at sentence punctuation: only the "remember" clause is stored.
    captured = store.capture_from_user_text(
        "alice",
        "记住：代号是 mini-agent。另外帮我记一条待办：买牛奶。",
        "window-1",
    )
    assert len(captured) == 1
    assert captured[0].content == "代号是 mini-agent"


def test_startup_and_format(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    store.add("alice", "fact", "用户在准备 Agent 笔试")
    store.add("alice", "preference", "用户偏好先给结论")
    startup = store.startup_memories("alice", top_k=5)
    assert any(record.type == "preference" for record in startup)
    text = store.format_for_prompt(startup)
    assert "preference" in text
    assert "结论" in text


def test_readonly_markdown_mirror(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    store.add("alice", "preference", "用户喜欢简洁回答")
    store.add("alice", "fact", "项目代号是 mini-agent")

    md_path = store.markdown_path("alice")
    assert md_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "preference" in text
    assert "用户喜欢简洁回答" in text
    assert "项目代号是 mini-agent" in text
    assert "read-only mirror" in text

    # The JSON store remains canonical; the mirror follows updates.
    store.add("alice", "fact", "截止日期是 2026-11-01")
    assert "截止日期是 2026-11-01" in md_path.read_text(encoding="utf-8")
