"""Built-in tools and the default executor."""

from __future__ import annotations

from . import calculator, memory, read_docs, search, todo, weather
from .executor import ToolContext, ToolExecutor, ToolSpec

__all__ = [
    "ToolContext",
    "ToolExecutor",
    "ToolSpec",
    "build_default_tools",
]


def build_default_tools() -> ToolExecutor:
    executor = ToolExecutor()
    for module in (todo, calculator, search, read_docs, weather, memory):
        executor.register(module.build_spec())
    return executor
