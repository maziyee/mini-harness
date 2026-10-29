from __future__ import annotations

from pathlib import Path

from helpers import FakeLLM, text_response
from mini_agent.context import ContextManager
from mini_agent.session import Session


def _session_with_turns(turns: int = 10) -> Session:
    session = Session(id="s1", user_id="alice")
    for index in range(turns):
        session.messages.append({"role": "user", "content": f"user message {index}"})
        session.messages.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": f"assistant reply {index}"}],
            }
        )
    return session


def test_estimate_is_positive():
    manager = ContextManager()
    assert manager.estimate_tokens("system", [{"role": "user", "content": "hi"}]) > 0


def test_compaction_folds_old_turns_and_keeps_recent(tmp_path):
    session = _session_with_turns(10)
    manager = ContextManager(
        context_window=400,
        trigger_ratio=0.7,
        keep_messages=4,
        archive_dir=tmp_path / "transcripts",
    )
    llm = FakeLLM([text_response("summary of older turns")])

    info = manager.maybe_compact(session, llm, "system prompt")

    assert info is not None
    assert info["trigger"] == "tokens"
    assert session.summary == "summary of older turns"
    assert len(session.messages) <= 5
    assert session.messages[0]["role"] == "user"
    assert isinstance(session.messages[0]["content"], str)
    assert "user message 9" in session.messages[-2]["content"]
    transcript = Path(info["transcript"])
    assert transcript.exists()
    assert "user message 0" in transcript.read_text(encoding="utf-8")


def test_compaction_can_trigger_on_message_count(tmp_path):
    session = _session_with_turns(30)  # 60 messages
    manager = ContextManager(
        context_window=10_000_000,
        trigger_ratio=0.7,
        keep_messages=4,
        max_messages=10,
        archive_dir=tmp_path / "transcripts",
    )
    llm = FakeLLM([text_response("summary by count")])

    info = manager.maybe_compact(session, llm, "system prompt")

    assert info is not None
    assert info["trigger"] == "messages"
    assert session.summary == "summary by count"
    assert len(session.messages) <= 5
    assert Path(info["transcript"]).exists()
