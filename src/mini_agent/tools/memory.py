"""Model-callable long-term memory tool.

The reference design lets the model decide what to remember (it writes
Markdown memory files).  We keep that agency, but through a narrow tool
instead of a general ``write_file``: save/search/list only, scoped to the
current user.  The runtime's explicit-signal capture remains as a fallback.
"""

from __future__ import annotations

from typing import Any

from ..memory import VALID_TYPES
from .executor import ToolContext, ToolSpec


def _format(records) -> str:
    if not records:
        return "No memories."
    return "\n".join(
        f"- [{record.type}] {record.content} (id={record.id})"
        for record in records
    )


def memory_tool(args: dict[str, Any], ctx: ToolContext) -> str:
    store = ctx.memory_store
    if store is None:
        return "Error: memory backend is not configured."
    action = str(args.get("action", "")).strip().lower()

    if action == "save":
        content = str(args.get("content", "")).strip()
        mem_type = str(args.get("type", "fact")).strip().lower()
        if not content:
            return "Error: content is required when action=save."
        if mem_type not in VALID_TYPES:
            return f"Error: type must be one of {sorted(VALID_TYPES)}."
        record = store.add(
            ctx.user_id,
            mem_type,
            content,
            source_session=ctx.session.id,
            confidence=0.9,
        )
        if record is None:
            return "Error: memory was not saved."
        if ctx.trace is not None:
            ctx.trace.log(
                "memory_write",
                memory_id=record.id,
                memory_type=record.type,
                content_chars=len(record.content),
                preview=record.content[:120],
            )
        return f"Saved memory {record.id} ({record.type}): {record.content}"

    if action == "search":
        query = str(args.get("query", "")).strip()
        if not query:
            return "Error: query is required when action=search."
        top_k = int(args.get("top_k", 3))
        records = store.recall(ctx.user_id, query, top_k=top_k)
        if ctx.trace is not None:
            ctx.trace.log(
                "memory_recall",
                ids=[record.id for record in records],
                reason="tool",
            )
        return _format(records) if records else f"No memories matched {query!r}."

    if action == "list":
        return _format(store.load(ctx.user_id))

    return "Error: action must be one of save/search/list."


def build_spec() -> ToolSpec:
    return ToolSpec(
        name="memory",
        description=(
            "Save, search, or list the current user's long-term memory "
            "(types: preference, fact, task_state)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "search", "list"],
                },
                "type": {
                    "type": "string",
                    "enum": ["preference", "fact", "task_state"],
                },
                "content": {"type": "string", "maxLength": 500},
                "query": {"type": "string", "maxLength": 200},
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": ["action"],
        },
        handler=memory_tool,
        max_result_chars=3000,
    )
