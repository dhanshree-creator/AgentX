"""Pydantic tool-calling conversation state, provider-agnostic."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolCallRequest(BaseModel):
    """One tool invocation requested by the model, parsed from provider payload."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Provider-assigned tool call id (must round-trip)")
    name: str = Field(..., description="Model-chosen registered tool name")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result of one real tool execution (success or structured failure)."""

    model_config = ConfigDict(frozen=True)

    call_id: str = Field(..., description="Must match the ToolCallRequest.id")
    name: str
    ok: bool
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    duration_ms: float | None = None
    attempt: int = 1

    def to_provider_content(self) -> str:
        """Serialize for the tool-result message returned to the provider."""
        return json.dumps(
            {"name": self.name, "ok": self.ok, "data": self.data, "error": self.error},
            default=str,
        )


class AssistantMessage(BaseModel):
    """Model message, possibly containing tool calls (provider-agnostic)."""

    content: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)


class ToolMessage(BaseModel):
    """Tool result message returned to the model."""

    call_id: str
    name: str
    ok: bool
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    duration_ms: float | None = None
    attempt: int = 1


class UserMessage(BaseModel):
    """User message with the task text."""

    content: str


TraceKind = Literal[
    "plan",
    "llm_request",
    "llm_response",
    "tool_call",
    "safety",
    "result",
    "verify",
    "final",
    "error",
]


class TraceEvent(BaseModel):
    """One structured trace record (used for /trace and benchmark reporting)."""

    ts: float
    kind: TraceKind
    task_id: str
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    ok: bool | None = None
    detail: str = ""
    data: Any = None


class VerificationResult(BaseModel):
    """Deterministic post-run verification, independent of model claims."""

    ok: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class RunResult(BaseModel):
    """Outcome of one bounded agent run (loop.py)."""

    status: Literal["completed", "failed", "budget_limit", "cancelled"]
    final_answer: str = ""
    turns: int = 0
    tool_calls_made: int = 0
    tool_calls_rejected: int = 0
    tool_errors: int = 0
    retries: int = 0
    errors: list[str] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    verification: VerificationResult | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    duration_s: float = 0.0
    user_task: str = ""
