"""Tool executor: schema, validation, dispatch, error wrapping."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from ..protocol import ToolCall, ToolResult

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from ..memory import MemoryBackend
    from ..session import Session
    from ..trace import TraceLogger


@dataclass
class ToolContext:
    user_id: str
    session: "Session"
    trace: "TraceLogger | None" = None
    artifacts_dir: Path | None = None
    memory_store: "MemoryBackend | None" = None


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any], ToolContext], str]
    max_result_chars: int = 4000


def validate_value(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    """Validate the JSON-Schema subset used by our tools."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path}: missing required field {required!r}")
        properties = schema.get("properties") or {}
        for key, sub_schema in properties.items():
            if key in value:
                errors.extend(validate_value(sub_schema, value[key], f"{path}.{key}"))
    elif expected == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array"]
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            errors.append(f"{path}: expected at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            errors.append(f"{path}: expected at most {schema['maxItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_value(item_schema, item, f"{path}[{index}]"))
    elif expected == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string")
        else:
            if "minLength" in schema and len(value) < int(schema["minLength"]):
                errors.append(f"{path}: string too short")
            if "maxLength" in schema and len(value) > int(schema["maxLength"]):
                errors.append(f"{path}: string too long")
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path}: expected integer")
        else:
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{path}: must be >= {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{path}: must be <= {schema['maximum']}")
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{path}: expected number")
    elif expected == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    return errors


class ToolExecutor:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
            }
            for spec in self._tools.values()
        ]

    def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        spec = self._tools.get(call.name)
        if spec is None:
            available = ", ".join(self._tools) or "(none)"
            return ToolResult(
                tool_use_id=call.id,
                content=f"Unknown tool {call.name!r}. Available tools: {available}",
                is_error=True,
            )

        errors = validate_value(spec.input_schema, call.arguments)
        if errors:
            return ToolResult(
                tool_use_id=call.id,
                content="Invalid arguments: " + "; ".join(errors),
                is_error=True,
            )

        try:
            content = spec.handler(call.arguments, ctx)
        except Exception as exc:  # tools must never crash the loop
            return ToolResult(
                tool_use_id=call.id,
                content=f"Tool {call.name!r} failed: {type(exc).__name__}: {exc}",
                is_error=True,
            )

        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, default=str)
        # Tool handlers use an "Error: ..." prefix for expected failures
        # (bad city, missing todo, path traversal, ...).  Surface that as a
        # structured is_error so the model and trace can react to it.
        is_error = content.startswith("Error:")
        if len(content) > spec.max_result_chars:
            content = self._truncate(content, spec, ctx)
        return ToolResult(tool_use_id=call.id, content=content, is_error=is_error)

    @staticmethod
    def _truncate(content: str, spec: ToolSpec, ctx: ToolContext) -> str:
        limit = spec.max_result_chars
        keep = max(200, (limit - 120) // 2)
        head, tail = content[:keep], content[-keep:]
        note = f"\n\n[... {len(content) - keep * 2} chars truncated ...]\n\n"
        artifact_note = ""
        if ctx.artifacts_dir is not None:
            try:
                ctx.artifacts_dir.mkdir(parents=True, exist_ok=True)
                # UUID suffix avoids clobbering when two truncated results
                # from the same tool land in the same second.
                safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", spec.name)[:40] or "tool"
                name = (
                    f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
                    f"{uuid.uuid4().hex[:8]}-{safe_name}.txt"
                )
                path = ctx.artifacts_dir / name
                path.write_text(content, encoding="utf-8")
                artifact_note = f"\nFull result saved to: {path}\n"
            except OSError:
                pass
        return head + note + tail + artifact_note
