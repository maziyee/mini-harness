"""Context budgeting and basic compaction.

Two cheap-to-expensive layers:
  L1: tool results are truncated by the tool executor (no model call).
  L2: when the estimated prompt exceeds the budget, older turns are folded
      into a structured summary stored on the session.  The summary is
      injected into the system prompt, so message roles stay valid.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .llm.base import LLMClient
from .prompt import SUMMARY_SYSTEM
from .protocol import strip_thinking_blocks
from .session import Session
from .util import atomic_write_text, safe_id, safe_path


class ContextManager:
    def __init__(
        self,
        context_window: int = 200_000,
        trigger_ratio: float = 0.7,
        keep_messages: int = 6,
        max_messages: int = 80,
        archive_dir: Path | None = None,
    ) -> None:
        self.context_window = context_window
        self.trigger_ratio = trigger_ratio
        self.keep_messages = keep_messages
        self.max_messages = max_messages
        self.archive_dir = Path(archive_dir) if archive_dir is not None else None

    @staticmethod
    def estimate_tokens(system: str, messages: list[dict[str, Any]]) -> int:
        """Cheap character-based estimate; good enough for a demo budget."""
        payload = json.dumps(messages, ensure_ascii=False, default=str)
        return (len(system) + len(payload)) // 4

    def build(self, session: Session) -> list[dict[str, Any]]:
        return list(session.messages)

    def maybe_compact(
        self, session: Session, llm: LLMClient, system: str
    ) -> dict[str, Any] | None:
        before = self.estimate_tokens(system, session.messages)
        budget = int(self.context_window * self.trigger_ratio)
        over_tokens = before >= budget
        over_count = len(session.messages) > self.max_messages
        if not (over_tokens or over_count):
            return None
        if len(session.messages) <= self.keep_messages + 2:
            return None

        # Compact only at a user-turn boundary so tool_use / tool_result
        # blocks stay paired.
        start = max(0, len(session.messages) - self.keep_messages)
        while start > 0 and not self._is_plain_user_message(session.messages[start]):
            start -= 1
        if start <= 0:
            return None

        # Thinking is display-only and must not enter transcripts/summaries.
        older_raw = session.messages[:start]
        older = strip_thinking_blocks(older_raw)
        kept = session.messages[start:]
        summary_prompt = SUMMARY_SYSTEM
        if session.summary:
            summary_prompt += f"\n\nPrevious summary:\n{session.summary}"

        summary_messages = older + [
            {
                "role": "user",
                "content": "Summarize the conversation above according to the system instructions.",
            }
        ]
        try:
            response = llm.complete(summary_prompt, summary_messages, [])
        except Exception:
            return None
        summary = (response.text or "").strip()
        if not summary:
            return None

        # Archive the raw older messages before removing them from the
        # session.  If the archive write fails, do not compact: keeping the
        # history in the session is preferable to losing it silently.
        try:
            transcript = self._archive_messages(session, older)
        except (OSError, ValueError):
            return None

        session.summary = summary
        session.messages = kept
        after = self.estimate_tokens(system, session.messages)
        triggers = []
        if over_tokens:
            triggers.append("tokens")
        if over_count:
            triggers.append("messages")
        return {
            "trigger": "+".join(triggers),
            "before_tokens": before,
            "after_tokens": after,
            "folded_messages": len(older),
            "kept_messages": len(kept),
            "transcript": str(transcript),
        }

    def _archive_messages(
        self, session: Session, messages: list[dict[str, Any]]
    ) -> Path:
        """Write the raw messages that will be folded into the summary.

        Mirrors learn-claude-code/s08's ``write_transcript``: compaction
        should change the *working context*, not destroy the audit trail.
        """
        safe_id(session.user_id, "user")
        safe_id(session.id, "session")
        messages = strip_thinking_blocks(messages)
        base = (
            self.archive_dir
            if self.archive_dir is not None
            else config.artifacts_dir() / "transcripts"
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        path = safe_path(
            base,
            f"{session.user_id}/{session.id}-{stamp}.jsonl",
            kind="transcript path",
        )
        text = "\n".join(
            json.dumps(message, ensure_ascii=False, default=str)
            for message in messages
        )
        atomic_write_text(path, text + "\n")
        return path

    @staticmethod
    def _is_plain_user_message(message: dict[str, Any]) -> bool:
        if message.get("role") != "user":
            return False
        return isinstance(message.get("content"), str)
