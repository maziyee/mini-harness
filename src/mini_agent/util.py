"""Small shared helpers: id validation, timestamps, atomic JSON writes."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
}


def now_iso() -> str:
    # Microseconds keep "latest session" ordering stable when two sessions
    # are created in the same second.
    return datetime.now(timezone.utc).isoformat()


def safe_id(value: str, kind: str) -> str:
    """Validate an identifier that will become a single file-name component.

    This is intentionally stricter than a path check: identifiers must start
    with an alphanumeric, may not end with a dot/space, and may not collide
    with Windows reserved device names.  Path *containment* is handled by
    safe_path(); the two checks protect different things.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"Invalid {kind} id {value!r}: id is empty")
    if value in {".", ".."} or not _ID_RE.fullmatch(value):
        raise ValueError(
            f"Invalid {kind} id {value!r}: use 1-64 chars from A-Z a-z 0-9 . _ - "
            "and start with a letter or digit"
        )
    if value.endswith((".", " ")):
        raise ValueError(f"Invalid {kind} id {value!r}: may not end with dot/space")
    if value.split(".", 1)[0].lower() in _WINDOWS_RESERVED:
        raise ValueError(f"Invalid {kind} id {value!r}: reserved device name")
    return value


def safe_path(root: str | Path, relative: str | Path, kind: str = "path") -> Path:
    """Resolve relative under root and reject traversal / symlink escapes.

    Uses the resolve + relative_to containment pattern:

        candidate = (root / relative).resolve()
        candidate.relative_to(root)   # ValueError if it escapes

    resolve() follows symlinks, so a link inside the data root that points
    outside is rejected as well.
    """
    base = Path(root).expanduser().resolve()
    try:
        candidate = (base / relative).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"Invalid {kind} {str(relative)!r}: cannot resolve") from exc
    try:
        candidate.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Invalid {kind} {str(relative)!r}: escapes {base}"
        ) from None
    return candidate


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
    )


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
