"""Session persistence and isolation.

A session is one "window".  Sessions are keyed by (user_id, session_id) and
stored as JSON under ``sessions/<user>/<session>.json``.  Writes are atomic
so killing the process mid-turn does not corrupt the history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config
from .protocol import strip_thinking_blocks
from .util import atomic_write_json, now_iso, read_json, safe_id, safe_path


def _new_session_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"s-{stamp}-{uuid.uuid4().hex[:4]}"


@dataclass
class Session:
    id: str
    user_id: str
    title: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None
    todos: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    status: str = "idle"

    def touch(self) -> None:
        self.updated_at = now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            # Thinking blocks are display-only; never persist them.
            "messages": strip_thinking_blocks(self.messages),
            "summary": self.summary,
            "todos": self.todos,
            "turn_count": self.turn_count,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            id=str(data.get("id", "")),
            user_id=str(data.get("user_id", "")),
            title=str(data.get("title", "")),
            created_at=str(data.get("created_at", now_iso())),
            updated_at=str(data.get("updated_at", now_iso())),
            messages=list(data.get("messages") or []),
            summary=data.get("summary"),
            todos=list(data.get("todos") or []),
            turn_count=int(data.get("turn_count") or 0),
            status=str(data.get("status") or "idle"),
        )


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else config.sessions_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str, session_id: str) -> Path:
        safe_id(user_id, "user")
        safe_id(session_id, "session")
        return safe_path(
            self.root,
            f"{user_id}/{session_id}.json",
            kind="session path",
        )

    def create(
        self, user_id: str, session_id: str | None = None, title: str = ""
    ) -> Session:
        safe_id(user_id, "user")
        session_id = session_id or _new_session_id()
        safe_id(session_id, "session")
        session = Session(id=session_id, user_id=user_id, title=title)
        self.save(session)
        return session

    def get_or_create(
        self, user_id: str, session_id: str | None = None, title: str = ""
    ) -> Session:
        if session_id:
            existing = self.load(user_id, session_id)
            if existing is not None:
                return existing
        return self.create(user_id, session_id=session_id, title=title)

    def load(self, user_id: str, session_id: str) -> Session | None:
        data = read_json(self._path(user_id, session_id))
        if not isinstance(data, dict):
            return None
        session = Session.from_dict(data)
        if session.id != session_id or session.user_id != user_id:
            return None
        return session

    def save(self, session: Session) -> None:
        session.touch()
        atomic_write_json(self._path(session.user_id, session.id), session.to_dict())

    def list(self, user_id: str) -> list[dict[str, Any]]:
        safe_id(user_id, "user")
        user_dir = safe_path(self.root, user_id, kind="user path")
        if not user_dir.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(user_dir.glob("*.json")):
            data = read_json(path)
            if not isinstance(data, dict):
                continue
            items.append(
                {
                    "id": data.get("id", path.stem),
                    "title": data.get("title", ""),
                    "updated_at": data.get("updated_at", ""),
                    "turn_count": data.get("turn_count", 0),
                    "status": data.get("status", "idle"),
                }
            )
        items.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return items

    def latest(self, user_id: str) -> Session | None:
        items = self.list(user_id)
        if not items:
            return None
        return self.load(user_id, str(items[0]["id"]))

    def delete(self, user_id: str, session_id: str) -> bool:
        path = self._path(user_id, session_id)
        try:
            path.unlink()
            return True
        except OSError:
            return False
