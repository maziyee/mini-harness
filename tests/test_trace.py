from __future__ import annotations

import pytest

from mini_agent.trace import trace_path


def test_trace_path_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        trace_path("../escape", "window-1", root=tmp_path)
    with pytest.raises(ValueError):
        trace_path("alice", "con", root=tmp_path)


def test_trace_path_is_under_root(tmp_path):
    path = trace_path("alice", "window-1", root=tmp_path)
    assert path == (tmp_path / "alice" / "window-1.jsonl").resolve()
