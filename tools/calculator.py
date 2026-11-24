"""Deterministic safe calculator. Restricted-AST, no eval/exec, no imports.

Accepts a strict JSON payload {"expression": "<arith>"} and returns a
deterministic result with explicit precision limits and error details.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from decimal import Decimal, DivisionByZero, InvalidOperation, getcontext
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.exceptions import ToolExecutionError

getcontext().prec = 50

MAX_EXPR_LEN = 200
MAX_OPS = 50
MAX_DIGITS = 24  # max digits per numeric literal
MAX_RESULT_MAGNITUDE = Decimal("1e30")


class CalculatorArgs(BaseModel):
    """Strict schema for the calculator tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    expression: str = Field(min_length=1, max_length=MAX_EXPR_LEN)


def _pow(a: Decimal, b: Decimal) -> Decimal:
    """Restricted power: only tiny integer exponents (deterministic, bounded)."""
    if b != b.to_integral_value():
        raise ToolExecutionError("Fractional exponents are not supported.")
    if abs(b) > 8:
        raise ToolExecutionError("Exponent magnitude limited to 8.")
    try:
        out = a ** int(b)
    except (InvalidOperation, OverflowError, DivisionByZero) as exc:
        raise ToolExecutionError("Power operation failed (overflow or invalid base).") from exc
    if not out.is_finite():
        raise ToolExecutionError("Power operation produced a non-finite value.")
    return out


_BIN_OPS: dict[type, Callable[[Decimal, Decimal], Decimal]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: _pow,
}
_UNARY_OPS: dict[type, Callable[[Decimal], Decimal]] = {
    ast.USub: operator.neg,
    ast.UAdd: lambda v: v,
}


def _format(d: Decimal) -> str:
    """Normalized output: no exponent notation, deterministic digits."""
    if d == 0:
        return "0"
    if d == d.to_integral_value():
        return str(int(d))
    s = format(d.normalize(), "f")
    if "e" in s or "E" in s:
        s = format(d, "f")
    return s


class CalculatorTool:
    """Evaluate an arithmetic expression via a restricted AST (no eval/exec)."""

    name = "calculator"
    description = (
        "Evaluate a single arithmetic expression deterministically. Supports "
        "+ - * / parentheses, unary minus, small integer powers, and decimals. "
        "No variables, functions, imports, strings, or attribute access."
    )
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression, e.g. (250 * 84.5) * (1 - 0.02)",
                "maxLength": MAX_EXPR_LEN,
                "minLength": 1,
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    }

    def __init__(self) -> None:
        self._op_count = 0

    def schema(self) -> dict[str, Any]:
        return self.parameters

    def args_model(self) -> type[BaseModel]:
        return CalculatorArgs

    async def run(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate args, parse, and evaluate a restricted-AST expression."""
        try:
            args = CalculatorArgs.model_validate(raw)
        except ValidationError as exc:
            raise ToolExecutionError(f"Invalid calculator arguments: {exc.errors()[:3]}") from None
        expr = args.expression

        if not expr.strip():
            raise ToolExecutionError("Empty expression.")

        try:
            tree = ast.parse(expr, mode="eval")
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            raise ToolExecutionError("Cannot parse expression (malformed or too nested).") from None
        if len(expr) > MAX_EXPR_LEN:  # defence in depth
            raise ToolExecutionError(f"Expression too long (> {MAX_EXPR_LEN} chars).")

        self._op_count = 0
        try:
            result = self._eval_node(tree.body)
        except RecursionError:
            raise ToolExecutionError("Expression too deeply nested.") from None
        if not result.is_finite():
            raise ToolExecutionError("Result is not finite (overflow).")
        if abs(result) > MAX_RESULT_MAGNITUDE:
            raise ToolExecutionError(
                f"Result magnitude exceeds limit (|result| > {MAX_RESULT_MAGNITUDE})."
            )
        result_str = _format(result)
        return {
            "expression": expr,
            "result": result_str,
            "result_number": result_str,
            "precision_note": (
                "Exact decimal arithmetic (context precision 50, "
                f"max {MAX_OPS} operations, max {MAX_DIGITS} digits/literal)."
            ),
        }

    def _eval_node(self, node: ast.AST) -> Decimal:
        if self._op_count > MAX_OPS:
            raise ToolExecutionError(f"Expression exceeds {MAX_OPS} operations.")
        self._op_count += 1

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):  # bool is an int subclass; reject first
                raise ToolExecutionError("Booleans are not allowed.")
            if isinstance(node.value, int):
                if abs(node.value) >= 10**MAX_DIGITS:
                    raise ToolExecutionError(
                        f"Integer literal too large (max {MAX_DIGITS} digits)."
                    )
                return Decimal(node.value)
            if isinstance(node.value, float):
                if node.value != node.value or node.value in (float("inf"), float("-inf")):
                    raise ToolExecutionError("Non-finite literals are not allowed.")
                if abs(node.value) >= 1e15:
                    raise ToolExecutionError("Float literal magnitude too large.")
                return Decimal(str(node.value))
            raise ToolExecutionError(
                f"Unsupported literal type {type(node.value).__name__}: only numbers allowed."
            )

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            fn = _BIN_OPS.get(op_type)
            if fn is None:
                raise ToolExecutionError(f"Operator {op_type.__name__} is not supported.")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if op_type is ast.Div and right == 0:
                raise ToolExecutionError("Division by zero is not allowed.")
            try:
                out = fn(left, right)
            except (InvalidOperation, OverflowError, DivisionByZero) as exc:
                raise ToolExecutionError(f"Arithmetic failed: {type(exc).__name__}") from None
            if not out.is_finite():
                raise ToolExecutionError("Operation produced a non-finite value.")
            return out

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            fn = _UNARY_OPS.get(op_type)
            if fn is None:
                raise ToolExecutionError(f"Operator {op_type.__name__} is not supported.")
            return fn(self._eval_node(node.operand))

        # Anything else is rejected by allowlist, not by try/except.
        if isinstance(
            node,
            (
                ast.Call,
                ast.Attribute,
                ast.Subscript,
                ast.BoolOp,
                ast.Compare,
                ast.Lambda,
                ast.IfExp,
                ast.NamedExpr,
            ),
        ):
            raise ToolExecutionError(
                f"{type(node).__name__} is not allowed (no functions/attributes/comparisons/logic)."
            )
        if isinstance(node, ast.Name):
            raise ToolExecutionError("Variables are not allowed; use plain numbers.")
        if isinstance(
            node,
            (
                ast.List,
                ast.Tuple,
                ast.Set,
                ast.Dict,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        ):
            raise ToolExecutionError("Collections and comprehensions are not allowed.")
        raise ToolExecutionError(f"Unsupported syntax: {type(node).__name__}")
