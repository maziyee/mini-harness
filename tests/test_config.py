from __future__ import annotations

import json

import pytest

from mini_agent.config import load_app_config


def test_missing_config_uses_defaults(tmp_path):
    cfg = load_app_config(tmp_path / "missing.json")
    assert cfg.loaded is False
    assert cfg.llm.model is None
    assert cfg.agent.max_turns is None


def test_load_config_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "_notes": "ignored",
                "llm": {
                    "api_key": "sk-test",
                    "model": "claude-sonnet-5-5",
                    "max_tokens": 2048,
                    "timeout": 30.5,
                    "max_retries": 2,
                    "thinking": True,
                    "thinking_budget": 1024,
                    "show_thinking": False,
                    "keep_thinking_in_memory": True,
                },
                "agent": {
                    "max_steps": 4,
                    "max_turns": 10,
                    "context_window": 8000,
                },
                "storage": {"root": "~/mini-agent-test"},
            }
        ),
        encoding="utf-8",
    )

    cfg = load_app_config(path)
    assert cfg.loaded is True
    assert cfg.llm.api_key == "sk-test"
    assert cfg.llm.model == "claude-sonnet-5-5"
    assert cfg.llm.max_tokens == 2048
    assert cfg.llm.timeout == 30.5
    assert cfg.llm.max_retries == 2
    assert cfg.llm.thinking is True
    assert cfg.llm.thinking_budget == 1024
    assert cfg.llm.show_thinking is False
    assert cfg.llm.keep_thinking_in_memory is True
    assert cfg.agent.max_steps == 4
    assert cfg.agent.max_turns == 10
    assert cfg.agent.context_window == 8000
    assert cfg.storage.root == "~/mini-agent-test"


def test_empty_strings_mean_unset(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "llm": {"api_key": "", "auth_token": "", "base_url": ""},
                "storage": {"root": ""},
            }
        ),
        encoding="utf-8",
    )
    cfg = load_app_config(path)
    assert cfg.llm.api_key is None
    assert cfg.llm.auth_token is None
    assert cfg.llm.base_url is None
    assert cfg.storage.root is None


def test_invalid_json_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid config file"):
        load_app_config(path)


def test_invalid_type_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"agent": {"max_turns": "ten"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="max_turns"):
        load_app_config(path)
