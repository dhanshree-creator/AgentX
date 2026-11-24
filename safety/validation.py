"""Argument validation bridge between model JSON payloads and tool schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from agent.exceptions import ToolExecutionError


def validate_arguments(tool_name: str, args_model: type[BaseModel], raw: Any) -> dict[str, Any]:
    """Strict Pydantic validation; extra/wrong fields are rejected before execution."""
    if not isinstance(raw, dict):
        raise ToolExecutionError("Tool arguments must be a JSON object.")
    try:
        model = args_model.model_validate(raw)
    except ValidationError as exc:
        errs = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc']) or 'payload'}: {e['msg']}"
            for e in exc.errors()[:4]
        )
        raise ToolExecutionError(f"Invalid arguments for {tool_name!r}: {errs}") from None
    return model.model_dump()


def validate_registry_alignment(
    tool_name: str, schema: dict[str, Any], args_model: type[BaseModel]
) -> None:
    """At registration: schema property names must match the args model fields."""
    schema_props = set((schema.get("properties") or {}).keys())
    model_fields = set(getattr(args_model, "model_fields", {}).keys())
    if schema_props != model_fields:
        raise ToolExecutionError(
            f"Tool {tool_name!r} schema/model field mismatch: {sorted(schema_props ^ model_fields)}"
        )
