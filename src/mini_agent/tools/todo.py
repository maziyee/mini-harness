"""Todo tool: per-session task list."""

from __future__ import annotations

from typing import Any

from ..util import now_iso
from .executor import ToolContext, ToolSpec


def format_todos(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return "No todos."
    lines: list[str] = []
    for item in todos:
        marker = "[x]" if item.get("status") == "done" else "[ ]"
        lines.append(f"{marker} {item.get('id')}: {item.get('content')}")
    done = sum(1 for item in todos if item.get("status") == "done")
    lines.append(f"({done}/{len(todos)} done)")
    return "\n".join(lines)


def _find(todos: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in todos:
        if item.get("id") == item_id:
            return item
    return None


def todo_tool(args: dict[str, Any], ctx: ToolContext) -> str:
    action = str(args.get("action", "")).strip()
    todos = ctx.session.todos

    if action == "list":
        return format_todos(todos)

    if action == "add":
        content = str(args.get("content", "")).strip()
        if not content:
            return "Error: content is required when action=add."
        existing_ids = {
            int(str(item.get("id", "t0")).lstrip("t"))
            for item in todos
            if str(item.get("id", "")).lstrip("t").isdigit()
        }
        next_number = max(existing_ids, default=0) + 1
        item = {
            "id": f"t{next_number}",
            "content": content,
            "status": "open",
            "created_at": now_iso(),
        }
        todos.append(item)
        return (
            f"Created new todo {item['id']}: {content}\n"
            f"Current list ({len(todos)} item(s)):\n{format_todos(todos)}"
        )

    if action in {"update", "done"}:
        item_id = str(args.get("item_id", "")).strip()
        item = _find(todos, item_id)
        if item is None:
            return f"Error: todo {item_id!r} not found. Use action=list to see ids."
        if action == "update":
            content = str(args.get("content", "")).strip()
            if not content:
                return "Error: content is required when action=update."
            item["content"] = content
        else:
            item["status"] = "done"
            item["completed_at"] = now_iso()
        return format_todos(todos)

    if action == "clear":
        todos.clear()
        return "Todo list cleared."

    return "Error: action must be one of add/list/update/done/clear."


def build_spec() -> ToolSpec:
    return ToolSpec(
        name="todo",
        description=(
            "Manage the current session's todo list "
            "(actions: add, list, update, done, clear)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "update", "done", "clear"],
                },
                "content": {"type": "string", "maxLength": 500},
                "item_id": {"type": "string", "maxLength": 32},
            },
            "required": ["action"],
        },
        handler=todo_tool,
        max_result_chars=3000,
    )
