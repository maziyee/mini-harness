"""Deterministic mock weather tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config
from .executor import ToolContext, ToolSpec

_FALLBACK = {
    "北京": {
        "default": {"condition": "晴", "temp": "8-18℃", "wind": "北风 2 级"},
        "2026-10-26": {"condition": "多云", "temp": "9-17℃", "wind": "南风 1 级"},
    },
    "上海": {
        "default": {"condition": "小雨", "temp": "16-22℃", "wind": "东风 3 级"},
    },
    "广州": {
        "default": {"condition": "多云", "temp": "22-29℃", "wind": "东南风 2 级"},
    },
}


def _weather_path() -> Path:
    return config.REPO_ROOT / "data" / "weather.json"


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_weather_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return _FALLBACK


def weather_tool(args: dict[str, Any], ctx: ToolContext) -> str:
    city = str(args.get("city", "")).strip()
    date = str(args.get("date", "")).strip()
    if not city:
        return "Error: city is required."
    data = _load()
    if city not in data:
        return f"Error: no mock weather for {city!r}. Supported cities: {', '.join(sorted(data))}"
    city_data = data[city]
    entry = city_data.get(date) if date else None
    if entry is None:
        entry = city_data.get("default") or next(iter(city_data.values()), None)
    if not isinstance(entry, dict):
        return f"Error: malformed weather data for {city!r}."
    when = date or "today"
    return (
        f"{city} {when}: {entry.get('condition', 'unknown')}, "
        f"{entry.get('temp', '?')}, {entry.get('wind', '?')} (mock data)"
    )


def build_spec() -> ToolSpec:
    return ToolSpec(
        name="weather",
        description=(
            "Look up mock weather for a city and optional date. This is deterministic "
            "demo data, not a live weather service."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "city": {"type": "string", "minLength": 1, "maxLength": 32},
                "date": {"type": "string", "maxLength": 32},
            },
            "required": ["city"],
        },
        handler=weather_tool,
        max_result_chars=1000,
    )
