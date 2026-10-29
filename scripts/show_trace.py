#!/usr/bin/env python3
"""Pretty-print a MiniAgent JSONL trace.

Usage:
    python scripts/show_trace.py logs/alice/window-1.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _summary(event: str, record: dict) -> str:
    if event == "user_message":
        return str(record.get("text", ""))[:100]
    if event == "llm_request":
        return (
            f"model={record.get('model')} messages={record.get('messages')} "
            f"~tokens={record.get('estimated_tokens')}"
        )
    if event == "llm_response":
        calls = record.get("tool_calls") or []
        names = ", ".join(str(call.get("name")) for call in calls)
        return (
            f"stop={record.get('stop_reason')} "
            f"in={record.get('usage', {}).get('input_tokens')} "
            f"out={record.get('usage', {}).get('output_tokens')} "
            + (f"tools=[{names}]" if names else "final")
        )
    if event == "tool_call":
        return f"{record.get('tool')}({record.get('arguments')})"
    if event == "tool_result":
        status = "ok" if record.get("ok") else "error"
        return f"{record.get('tool')} -> {status}, {record.get('chars')} chars"
    if event == "compact":
        return (
            f"{record.get('before_tokens')} -> {record.get('after_tokens')} tokens, "
            f"folded={record.get('folded_messages')}"
        )
    if event == "memory_write":
        return f"{record.get('memory_type')}: {record.get('content')}"
    if event == "memory_recall":
        return f"ids={record.get('ids')} reason={record.get('reason')}"
    if event == "error":
        return str(record.get("error", ""))[:160]
    if event == "turn_end":
        return f"turn={record.get('turn')} tools={record.get('tools_used')}"
    return ""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"Trace not found: {path}")
        return 1
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = str(record.get("event", "?"))
        ts = str(record.get("ts", ""))[11:19]
        print(f"[{ts}] {event:<14} {_summary(event, record)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
