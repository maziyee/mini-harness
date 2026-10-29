"""Append-only JSONL trace.

One file per (user, session).  Events are small dictionaries; tool output
is recorded as a length/status, not the full payload, so traces stay cheap
and do not leak sensitive content.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .util import safe_id, safe_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"api_key", "apikey", "authorization", "auth_token"}:
                cleaned[key] = "***"
            else:
                cleaned[key] = _redact(item)
        return cleaned
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def trace_path(user_id: str, session_id: str, root: Path | None = None) -> Path:
    safe_id(user_id, "user")
    safe_id(session_id, "session")
    base = root if root is not None else config.logs_dir()
    return safe_path(base, f"{user_id}/{session_id}.jsonl", kind="trace path")


class TraceLogger:
    def __init__(
        self,
        user_id: str,
        session_id: str,
        root: Path | None = None,
    ) -> None:
        self.user_id = user_id
        self.session_id = session_id
        self.path = trace_path(user_id, session_id, root)
        self._lock = threading.Lock()
        self.enabled = True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.enabled = False

    def log(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        record = {
            "ts": _now(),
            "event": event,
            "user": self.user_id,
            "session": self.session_id,
            **_redact(fields),
        }
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
            with self._lock:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError:
            self.enabled = False
