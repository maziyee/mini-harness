"""Read local documentation under data/docs with a path-traversal guard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import config
from ..util import safe_path
from .executor import ToolContext, ToolSpec


def _docs_root() -> Path:
    # Intentionally scoped to data/docs: this is a demo knowledge-base
    # reader, not a general filesystem reader. Broad file access belongs in a
    # separate read_file tool with its own workspace root and permission policy.
    return config.docs_dir()


def _resolve(relative: str) -> Path:
    return safe_path(_docs_root(), relative or ".", kind="doc path")


def _available() -> list[str]:
    root = _docs_root()
    if not root.exists():
        return []
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}
    )


def read_docs_tool(args: dict[str, Any], ctx: ToolContext) -> str:
    relative = str(args.get("path", "")).strip().lstrip("/")
    start_line = int(args.get("start_line", 1))
    end_line = int(args.get("end_line", 0))
    try:
        target = _resolve(relative or ".")
    except ValueError as exc:
        return f"Error: {exc}"

    if not target.exists():
        available = ", ".join(_available()) or "(no docs)"
        return f"Error: {relative!r} not found. Available docs: {available}"
    if target.is_dir():
        files = _available()
        return "Available docs:\n" + ("\n".join(f"- {name}" for name in files) or "(none)")

    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"Error: cannot read {relative!r}: {exc}"

    start = max(1, start_line)
    end = end_line if end_line >= start else min(len(lines), start + 199)
    end = min(end, len(lines))
    selected = lines[start - 1 : end]
    numbered = [f"{number:>4} | {line}" for number, line in enumerate(selected, start=start)]
    header = f"{relative} (lines {start}-{end} of {len(lines)})"
    return header + "\n" + "\n".join(numbered)


def build_spec() -> ToolSpec:
    return ToolSpec(
        name="read_docs",
        description=(
            "Read a local documentation file under data/docs; "
            "paths are relative to data/docs."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "maxLength": 300},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
        },
        handler=read_docs_tool,
        max_result_chars=5000,
    )
