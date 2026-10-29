from __future__ import annotations

import os

import pytest

from mini_agent.util import safe_id, safe_path


def test_safe_id_accepts_normal_ids():
    for value in [
        "alice",
        "window-1",
        "s-20261026-141359-80d8",
        "A_B.c",
        "a..b",
    ]:
        assert safe_id(value, "user") == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "../escape",
        "a/b",
        "a\\b",
        ".hidden",
        "con",
        "CON.txt",
        "nul",
        "com1",
        "lpt9",
        "name.",
        "name ",
        "a" * 65,
    ],
)
def test_safe_id_rejects_dangerous_ids(value):
    with pytest.raises(ValueError):
        safe_id(value, "user")


def test_safe_path_allows_inside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = safe_path(root, "a/b.json")
    assert target == (root / "a/b.json").resolve()


def test_safe_path_blocks_traversal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        safe_path(root, "../secret.txt")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges")
def test_safe_path_blocks_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    os.symlink(outside, root / "link")
    with pytest.raises(ValueError, match="escapes"):
        safe_path(root, "link/secret.txt")
