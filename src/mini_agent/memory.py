"""Long-term memory.

Three record types: preference, fact, task_state.  Memory is deliberately
small and inspectable: one JSON file per user under ``memory/<user>.json``,
plus a read-only Markdown mirror for humans.

Writes can come from two paths:
  - the model calls the ``memory`` tool (save/search/list);
  - the runtime captures explicit "记住 / 以后都 / 我喜欢" signals as a
    deterministic fallback.

Recall is keyword + recency based.  No vector store.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from . import config
from .util import (
    atomic_write_json,
    atomic_write_text,
    now_iso,
    read_json,
    safe_id,
    safe_path,
)

VALID_TYPES = {"preference", "fact", "task_state"}
MAX_RECORDS = 200
MAX_PROMPT_CHARS = 700


@dataclass
class MemoryRecord:
    id: str
    type: str
    content: str
    created_at: str = field(default_factory=now_iso)
    last_used_at: str = field(default_factory=now_iso)
    source_session: str = ""
    confidence: float = 0.8
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "source_session": self.source_session,
            "confidence": self.confidence,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        mem_type = str(data.get("type", "fact"))
        return cls(
            id=str(data.get("id", "")),
            type=mem_type if mem_type in VALID_TYPES else "fact",
            content=str(data.get("content", "")),
            created_at=str(data.get("created_at", now_iso())),
            last_used_at=str(data.get("last_used_at", now_iso())),
            source_session=str(data.get("source_session", "")),
            confidence=float(data.get("confidence", 0.8)),
            status=str(data.get("status", "active")),
        )


class MemoryBackend(Protocol):
    """Storage/recall interface used by the loop and the memory tool.

    MemoryStore is the JSON implementation.  A Markdown-backed store can
    implement the same methods later without changing the loop or tools.
    """

    def load(self, user_id: str) -> list[MemoryRecord]:
        ...

    def save(self, user_id: str, records: list[MemoryRecord]) -> None:
        ...

    def add(
        self,
        user_id: str,
        mem_type: str,
        content: str,
        source_session: str = "",
        confidence: float = 0.8,
    ) -> MemoryRecord | None:
        ...

    def capture_from_user_text(
        self, user_id: str, text: str, source_session: str = ""
    ) -> list[MemoryRecord]:
        ...

    def recall(
        self, user_id: str, query: str, top_k: int = 3
    ) -> list[MemoryRecord]:
        ...

    def startup_memories(
        self, user_id: str, top_k: int = 5
    ) -> list[MemoryRecord]:
        ...

    def touch(self, user_id: str, record_ids: list[str]) -> None:
        ...


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokens(text: str) -> set[str]:
    # Latin words + individual CJK characters; enough for a small demo.
    words = re.findall(r"[a-zA-Z0-9_]+|[一-鿿]", text.lower())
    return {w for w in words if len(w) > 0}


class MemoryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else config.memory_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        safe_id(user_id, "user")
        return safe_path(self.root, f"{user_id}.json", kind="memory path")

    def json_path(self, user_id: str) -> Path:
        return self._path(user_id)

    def markdown_path(self, user_id: str) -> Path:
        safe_id(user_id, "user")
        return safe_path(self.root, f"{user_id}.md", kind="memory markdown")

    def load(self, user_id: str) -> list[MemoryRecord]:
        data = read_json(self._path(user_id))
        if not isinstance(data, list):
            return []
        records: list[MemoryRecord] = []
        for item in data:
            if isinstance(item, dict):
                record = MemoryRecord.from_dict(item)
                if record.id and record.content:
                    records.append(record)
        return records

    def save(self, user_id: str, records: list[MemoryRecord]) -> None:
        # Keep the newest records when the cap is reached.
        kept = records[-MAX_RECORDS:]
        atomic_write_json(self._path(user_id), [record.to_dict() for record in kept])
        self._write_markdown_mirror(user_id, kept)

    def render_markdown(
        self, user_id: str, records: list[MemoryRecord] | None = None
    ) -> str:
        """Human-readable, read-only view of the JSON store.

        The markdown mirror is intentionally derived data: it is easy to
        inspect/grep/diff, but edits are overwritten on the next save.  This
        keeps one canonical source (JSON) while still giving reviewers a
        readable memory file.
        """
        records = self.load(user_id) if records is None else records
        lines = [
            f"# Long-term memory: {user_id}",
            "",
            f"<!-- generated from {user_id}.json; read-only mirror -->",
            "",
        ]
        if not records:
            lines.append("(no memories)")
            return "\n".join(lines) + "\n"
        for mem_type in ("preference", "fact", "task_state"):
            items = [record for record in records if record.type == mem_type]
            if not items:
                continue
            lines.append(f"## {mem_type}")
            for record in items:
                content = " ".join(record.content.split())
                lines.append(
                    f"- [{record.created_at[:10]}] {content} "
                    f"(id={record.id}, confidence={record.confidence:g}, "
                    f"status={record.status})"
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _write_markdown_mirror(
        self, user_id: str, records: list[MemoryRecord]
    ) -> None:
        try:
            atomic_write_text(
                self.markdown_path(user_id),
                self.render_markdown(user_id, records),
            )
        except (OSError, ValueError):
            # The JSON store is canonical; a failed mirror must not break
            # memory operations.
            pass

    def add(
        self,
        user_id: str,
        mem_type: str,
        content: str,
        source_session: str = "",
        confidence: float = 0.8,
    ) -> MemoryRecord | None:
        content = content.strip()
        if not content:
            return None
        mem_type = mem_type if mem_type in VALID_TYPES else "fact"
        records = self.load(user_id)
        normalized = _normalize(content)
        for record in records:
            if record.status == "active" and _normalize(record.content) == normalized:
                record.last_used_at = now_iso()
                self.save(user_id, records)
                return record
        record = MemoryRecord(
            id=f"m-{uuid.uuid4().hex[:8]}",
            type=mem_type,
            content=content,
            source_session=source_session,
            confidence=confidence,
        )
        records.append(record)
        self.save(user_id, records)
        return record

    def capture_from_user_text(
        self, user_id: str, text: str, source_session: str = ""
    ) -> list[MemoryRecord]:
        """Conservative rule-based capture: only explicit "remember" signals."""
        captured: list[MemoryRecord] = []
        # Stop at sentence punctuation so a long message like
        # "记住：代号是 X。另外帮我..." only stores the first clause.
        clause = r"([^。；;！!？?\n]+)"
        # (pattern, type, group to store)
        patterns = [
            (rf"记住[：:\s]*{clause}", "fact", 1),
            (rf"以后都{clause}", "preference", 0),
            (rf"我喜欢{clause}", "preference", 0),
            (rf"我的{clause}是{clause}", "fact", 0),
        ]
        for pattern, mem_type, group_index in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            content = match.group(group_index).strip()
            if content and len(content) <= 200:
                record = self.add(
                    user_id,
                    mem_type,
                    content,
                    source_session=source_session,
                    confidence=0.9,
                )
                if record is not None:
                    captured.append(record)
            break
        return captured

    def recall(
        self, user_id: str, query: str, top_k: int = 3
    ) -> list[MemoryRecord]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        now = datetime.now(timezone.utc)
        scored: list[tuple[float, MemoryRecord]] = []
        for record in self.load(user_id):
            if record.status != "active":
                continue
            record_tokens = _tokens(record.content)
            overlap = len(query_tokens & record_tokens)
            if overlap == 0:
                continue
            score = float(overlap)
            if record.type == "preference":
                score += 0.5
            elif record.type == "task_state":
                score += 0.3
            try:
                seen = datetime.fromisoformat(record.last_used_at)
                days = max(0.0, (now - seen).total_seconds() / 86400)
                score += 1.0 / (1.0 + days / 30.0)
            except ValueError:
                pass
            scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored[:top_k]]

    def startup_memories(self, user_id: str, top_k: int = 5) -> list[MemoryRecord]:
        records = [r for r in self.load(user_id) if r.status == "active"]
        records.sort(key=lambda r: r.last_used_at, reverse=True)
        preferred = [r for r in records if r.type in {"preference", "task_state"}]
        others = [r for r in records if r.type not in {"preference", "task_state"}]
        return (preferred + others)[:top_k]

    def touch(self, user_id: str, record_ids: list[str]) -> None:
        if not record_ids:
            return
        wanted = set(record_ids)
        records = self.load(user_id)
        changed = False
        for record in records:
            if record.id in wanted:
                record.last_used_at = now_iso()
                changed = True
        if changed:
            self.save(user_id, records)

    @staticmethod
    def format_for_prompt(records: list[MemoryRecord]) -> str:
        if not records:
            return ""
        lines: list[str] = []
        for record in records:
            date = record.created_at[:10]
            lines.append(f"- [{record.type}, {date}] {record.content}")
        text = "\n".join(lines)
        if len(text) > MAX_PROMPT_CHARS:
            text = text[:MAX_PROMPT_CHARS].rstrip() + "\n- ... (truncated)"
        return text
