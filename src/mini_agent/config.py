"""Runtime paths and config-file loading.

Runtime data defaults to the repository:

    sessions/<user>/<session>.json
    memory/<user>.json
    logs/<user>/<session>.jsonl
    artifacts/

Set MINI_AGENT_HOME (or storage.root in config.json) to move it.

Agent settings are loaded from config.json at the repository root (or the
path in MINI_AGENT_CONFIG / --config).  Precedence:

    CLI arguments > config.json > environment / .env > built-in defaults

Empty strings / null in config.json mean "not set, fall back".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


# ─── Runtime paths ──────────────────────────────────────────


def data_root() -> Path:
    raw = (os.environ.get("MINI_AGENT_HOME") or "").strip()
    return Path(raw).expanduser().resolve() if raw else REPO_ROOT


def sessions_dir() -> Path:
    return data_root() / "sessions"


def memory_dir() -> Path:
    return data_root() / "memory"


def logs_dir() -> Path:
    return data_root() / "logs"


def artifacts_dir() -> Path:
    return data_root() / "artifacts"


def docs_dir() -> Path:
    return REPO_ROOT / "data" / "docs"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


# ─── App config ─────────────────────────────────────────────


@dataclass
class LLMConfig:
    api_key: str | None = None
    auth_token: str | None = None
    base_url: str | None = None
    model: str | None = None
    max_tokens: int | None = None
    timeout: float | None = None
    max_retries: int | None = None
    thinking: bool | None = None
    thinking_budget: int | None = None
    show_thinking: bool | None = None
    keep_thinking_in_memory: bool | None = None


@dataclass
class AgentConfig:
    max_steps: int | None = None
    max_turns: int | None = None
    context_window: int | None = None


@dataclass
class StorageConfig:
    root: str | None = None


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    loaded: bool = False
    path: str | None = None


def config_path(path: str | Path | None = None) -> Path:
    raw = path or os.environ.get("MINI_AGENT_CONFIG") or (REPO_ROOT / "config.json")
    return Path(raw).expanduser()


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"config.{name} must be an object")
    return value


def _opt_str(section: dict[str, Any], key: str, name: str) -> str | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"config.{name}.{key} must be a string")
    value = value.strip()
    return value or None


def _opt_int(section: dict[str, Any], key: str, name: str) -> int | None:
    value = section.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"config.{name}.{key} must be an integer")
    return value


def _opt_float(section: dict[str, Any], key: str, name: str) -> float | None:
    value = section.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"config.{name}.{key} must be a number")
    return float(value)


def _opt_bool(section: dict[str, Any], key: str, name: str) -> bool | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"config.{name}.{key} must be true/false")
    return value


def load_app_config(path: str | Path | None = None) -> AppConfig:
    """Load config.json; missing file -> all defaults (env fallback)."""
    resolved = config_path(path)
    if not resolved.exists():
        return AppConfig()

    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid config file {resolved}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid config file {resolved}: root must be an object")

    llm_data = _section(raw, "llm")
    agent_data = _section(raw, "agent")
    storage_data = _section(raw, "storage")

    return AppConfig(
        llm=LLMConfig(
            api_key=_opt_str(llm_data, "api_key", "llm"),
            auth_token=_opt_str(llm_data, "auth_token", "llm"),
            base_url=_opt_str(llm_data, "base_url", "llm"),
            model=_opt_str(llm_data, "model", "llm"),
            max_tokens=_opt_int(llm_data, "max_tokens", "llm"),
            timeout=_opt_float(llm_data, "timeout", "llm"),
            max_retries=_opt_int(llm_data, "max_retries", "llm"),
            thinking=_opt_bool(llm_data, "thinking", "llm"),
            thinking_budget=_opt_int(llm_data, "thinking_budget", "llm"),
            show_thinking=_opt_bool(llm_data, "show_thinking", "llm"),
            keep_thinking_in_memory=_opt_bool(
                llm_data, "keep_thinking_in_memory", "llm"
            ),
        ),
        agent=AgentConfig(
            max_steps=_opt_int(agent_data, "max_steps", "agent"),
            max_turns=_opt_int(agent_data, "max_turns", "agent"),
            context_window=_opt_int(agent_data, "context_window", "agent"),
        ),
        storage=StorageConfig(root=_opt_str(storage_data, "root", "storage")),
        loaded=True,
        path=str(resolved),
    )
