"""Safe arithmetic calculator (AST based, no eval)."""

from __future__ import annotations

import ast
import operator
from typing import Any

from .executor import ToolContext, ToolSpec

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if type(node.value) not in (int, float):
            raise ValueError("only numeric constants are allowed")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval(node.left)
        right = _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("exponent is too large")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def calculator_tool(args: dict[str, Any], ctx: ToolContext) -> str:
    expression = str(args.get("expression", "")).strip()
    if not expression:
        return "Error: expression is required."
    if len(expression) > 200:
        return "Error: expression is too long (max 200 chars)."
    try:
        tree = ast.parse(expression, mode="eval")
        value = _eval(tree)
    except ZeroDivisionError:
        return "Error: division by zero."
    except SyntaxError as exc:
        return f"Error: invalid expression: {exc.msg}"
    except ValueError as exc:
        return f"Error: {exc}"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{expression} = {value}"


def build_spec() -> ToolSpec:
    return ToolSpec(
        name="calculator",
        description=(
            "Evaluate a basic arithmetic expression "
            "(+ - * / // % **, parentheses)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                }
            },
            "required": ["expression"],
        },
        handler=calculator_tool,
        max_result_chars=1000,
    )
