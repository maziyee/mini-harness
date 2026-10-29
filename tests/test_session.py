from __future__ import annotations

import json
import os

import pytest

from mini_agent.session import SessionStore


def test_create_load_list_and_isolation(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    alice = store.create("alice", "window-1", title="天气与待办")
    alice.messages.append({"role": "user", "content": "hello"})
    store.save(alice)

    loaded = store.load("alice", "window-1")
    assert loaded is not None
    assert loaded.title == "天气与待办"
    assert loaded.messages[-1]["content"] == "hello"

    other = store.create("bob", "window-1", title="另一个用户")
    other.messages.append({"role": "user", "content": "bob's message"})
    store.save(other)

    assert store.load("alice", "window-1").messages[-1]["content"] == "hello"
    assert store.load("bob", "window-1").messages[-1]["content"] == "bob's message"
    assert [item["id"] for item in store.list("alice")] == ["window-1"]


def test_save_strips_thinking_blocks(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create("alice", "window-1")
    session.messages.append(
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "secret reasoning"},
                {"type": "text", "text": "final answer"},
            ],
        }
    )
    store.save(session)

    data = json.loads(
        (tmp_path / "sessions" / "alice" / "window-1.json").read_text(encoding="utf-8")
    )
    assert data["messages"][0]["content"] == [
        {"type": "text", "text": "final answer"}
    ]
    # In-memory history keeps thinking until the turn finishes; disk never does.
    assert session.messages[0]["content"][0]["type"] == "thinking"


def test_latest_and_delete(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    first = store.create("alice", "window-1")
    first.turn_count = 1
    store.save(first)
    second = store.create("alice", "window-2")
    second.turn_count = 2
    store.save(second)

    assert store.latest("alice").id == "window-2"
    assert store.delete("alice", "window-2")
    assert store.latest("alice").id == "window-1"


def test_invalid_ids(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    with pytest.raises(ValueError):
        store.create("../escape", "window-1")
    with pytest.raises(ValueError):
        store.create("alice", "../escape")
    with pytest.raises(ValueError):
        store.create("alice", "con")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges")
def test_session_store_rejects_symlink_escape(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / "alice")
    store = SessionStore(root)
    with pytest.raises(ValueError):
        store.create("alice", "window-1")
