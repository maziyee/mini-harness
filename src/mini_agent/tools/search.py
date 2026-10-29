"""Mock search over a small local corpus.

The assignment allows a mocked search tool.  Keeping the corpus local makes
demos and tests deterministic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .. import config
from .executor import ToolContext, ToolSpec

_FALLBACK = [
    {
        "title": "Agent Harness 笔试说明",
        "snippet": "从零实现最小 Agent：循环、工具注册、session、context、trace。",
        "source": "internal",
        "tags": ["agent", "harness", "笔试"],
    },
    {
        "title": "Anthropic 工具调用协议",
        "snippet": "assistant 返回 tool_use content block，user 用 tool_result 回填。",
        "source": "docs",
        "tags": ["anthropic", "tool_use", "protocol"],
    },
    {
        "title": "北京天气",
        "snippet": "北京秋季干燥，昼夜温差较大。",
        "source": "mock",
        "tags": ["weather", "北京"],
    },
]


def _corpus_path() -> Path:
    return config.REPO_ROOT / "data" / "search_corpus.json"


def _load_corpus() -> list[dict[str, Any]]:
    try:
        data = json.loads(_corpus_path().read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError):
        pass
    return _FALLBACK


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]+|[一-鿿]", text.lower())
        if token
    }


def _score(query: str, doc: dict[str, Any]) -> float:
    query_lower = query.lower().strip()
    title = str(doc.get("title", "")).lower()
    snippet = str(doc.get("snippet", "")).lower()
    source = str(doc.get("source", "")).lower()
    tags = " ".join(str(tag).lower() for tag in doc.get("tags") or [])
    score = 0.0
    if query_lower and query_lower in title:
        score += 4.0
    if query_lower and query_lower in snippet:
        score += 2.0
    for token in _tokens(query):
        if token in title:
            score += 3.0
        if token in tags:
            score += 2.0
        if token in snippet:
            score += 1.5
        if token in source:
            score += 0.5
    return score


def search_tool(args: dict[str, Any], ctx: ToolContext) -> str:
    query = str(args.get("query", "")).strip()
    top_k = int(args.get("top_k", 3))
    if not query:
        return "Error: query is required."
    scored = [(score, doc) for doc in _load_corpus() if (score := _score(query, doc)) > 0]
    scored.sort(key=lambda item: (-item[0], str(item[1].get("title", ""))))
    if not scored:
        titles = ", ".join(str(doc.get("title", "?")) for doc in _load_corpus())
        return f"No results for {query!r}. Available titles: {titles}"
    lines: list[str] = []
    for index, (_, doc) in enumerate(scored[:top_k], start=1):
        lines.append(
            f"{index}. {doc.get('title', '(untitled)')} [{doc.get('source', '?')}]\n"
            f"   {doc.get('snippet', '')}"
        )
    return "\n".join(lines)


def build_spec() -> ToolSpec:
    return ToolSpec(
        name="search",
        description=(
            "Search the local mock corpus for short references; "
            "returns title, snippet, and source."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 200},
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 3,
                },
            },
            "required": ["query"],
        },
        handler=search_tool,
        max_result_chars=3000,
    )
