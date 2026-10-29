"""System prompt assembly.

The static prefix is deliberately separated from the per-session tail: if a
provider supports prompt caching, the stable part can be cached while the
dynamic part changes each turn.
"""

from __future__ import annotations

from datetime import datetime

from .memory import MemoryRecord, MemoryStore
from .session import Session
from .tools.todo import format_todos

STATIC_SYSTEM = """You are MiniAgent, a minimal general-purpose assistant running in a local CLI.

## How you work
- Decide whether to answer directly or call a tool.
- Call a tool only when it is useful; never invent tool results.
- After a tool result, decide whether to call another tool or give the final answer.
- If a tool returns an error, read it and either fix the arguments or explain the problem.
- You may request multiple tools in one response; the runtime executes them in order.
- Keep final answers concise. Mention the tool you used when it matters.
- The runtime executes tool calls; you do not need to print JSON yourself.

## Tool selection
- todo: for multi-step tasks; keep the plan and progress visible.
- memory: save durable preferences, facts, or task state the user explicitly
  wants remembered; search when they refer to earlier conversations. Do not
  save transient details.
- calculator: use for any arithmetic instead of doing math in your head.
- search: quick lookups in the local mock corpus; returns title, snippet, source.
- read_docs: read a specific document under data/docs when you need details;
  paths are relative to data/docs.
- weather: mock weather for a city and optional date.
"""

SUMMARY_SYSTEM = """You are a conversation summarizer. Summarize the older part of a conversation.

Preserve, in this order:
1. The user's goal and hard constraints.
2. Explicit preferences and decisions.
3. What has been completed, including important tool results.
4. Open questions and the next step.

Be concise (at most 300 words). Do not invent facts. Output only the summary.
"""


def build_static_system_prompt() -> str:
    return STATIC_SYSTEM


def build_dynamic_system_context(
    session: Session,
    memories: list[MemoryRecord],
) -> str:
    lines: list[str] = [
        "## Current context",
        f"- User: {session.user_id}",
        f"- Session: {session.id}",
        f"- Date: {datetime.now().strftime('%Y-%m-%d')}",
        f"- Turn: {session.turn_count}",
    ]

    if session.summary:
        lines.extend(
            [
                "",
                "## Conversation summary (older turns; may omit details)",
                session.summary.strip(),
            ]
        )

    if session.todos:
        lines.extend(["", "## Current todos", format_todos(session.todos)])

    if memories:
        lines.extend(
            [
                "",
                "## Long-term memory (background, may be stale; current user instructions win)",
                MemoryStore.format_for_prompt(memories),
            ]
        )

    return "\n".join(lines)


def build_system_prompt(
    session: Session,
    memories: list[MemoryRecord],
) -> str:
    return (
        build_static_system_prompt()
        + "\n\n"
        + build_dynamic_system_context(session, memories)
    )
