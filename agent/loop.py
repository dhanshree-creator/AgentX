"""Bounded agent loop: model proposes tool calls; app validates and executes them."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any

from agent.exceptions import AgentXError, SafetyLimitError, UnknownToolError
from agent.memory import TaskMemory
from agent.models import (
    AssistantMessage,
    RunResult,
    ToolCallRequest,
    ToolMessage,
    TraceEvent,
    UserMessage,
    VerificationResult,
)
from agent.prompts import SYSTEM_PROMPT
from agent.provider import ProviderAdapter
from safety.limits import Budget
from tools.registry import ToolRegistry

MAX_TOOL_MESSAGE_CHARS = 12000  # cap each tool payload sent back to the model


class TraceList(list):
    """List that dispatches new items to an optional event callback."""

    def __init__(self, callback: Callable[[TraceEvent], None] | None = None) -> None:
        super().__init__()
        self._callback = callback

    def append(self, item: Any) -> None:
        super().append(item)
        if self._callback is not None:
            try:
                self._callback(item)
            except Exception:
                pass


class AgentLoop:
    def __init__(
        self,
        provider: ProviderAdapter,
        registry: ToolRegistry,
        max_tool_calls: int = 5,
        max_turns: int = 12,
        deadline_s: float = 120.0,
        retry_transient_max: int = 2,
    ):
        self.provider = provider
        self.registry = registry
        self.memory = TaskMemory()
        self.budget_kwargs = dict(
            max_tool_calls=max_tool_calls,
            max_turns=max_turns,
            deadline_s=deadline_s,
        )
        self.retry_transient_max = retry_transient_max

    # ---- public ----
    async def run_task(
        self,
        task: str,
        on_event: Callable[[TraceEvent], None] | None = None,
    ) -> RunResult:
        task_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        trace: list[TraceEvent] = TraceList(on_event)
        budget = Budget(**self.budget_kwargs)
        errors: list[str] = []
        tool_calls_made = 0
        tool_calls_rejected = 0
        tool_errors = 0
        retries = 0
        usage: dict[str, int] = {}
        verification: VerificationResult | None = None
        status = "failed"
        final_answer = ""

        self.memory.clear()
        self.memory.set_user_task(task)
        trace.append(
            TraceEvent(ts=time.time(), kind="plan", task_id=task_id, detail=f"Task: {task[:120]}")
        )

        try:
            while True:
                budget.check_turn(budget.turns)
                budget.check_deadline()
                budget.turns += 1

                trace.append(TraceEvent(ts=time.time(), kind="llm_request", task_id=task_id))
                resp = await self._call_model_with_retries(
                    self._build_messages(), self.registry.schemas(), trace, task_id
                )
                retries += max(0, resp["retry_count"])
                if resp.get("usage"):
                    for k, v in resp["usage"].items():
                        usage[k] = usage.get(k, 0) + int(v)
                trace.append(
                    TraceEvent(
                        ts=time.time(),
                        kind="llm_response",
                        task_id=task_id,
                        detail=f"finish_reason={resp.get('finish_reason')} tool_calls={len(resp['tool_calls'])}",
                    )
                )

                content = resp.get("content")
                tool_calls = [ToolCallRequest.model_validate(tc) for tc in resp["tool_calls"]]
                self.memory.append(AssistantMessage(content=content, tool_calls=tool_calls))

                if not tool_calls:
                    final_answer = (content or "").strip() or "(model returned an empty answer)"
                    trace.append(
                        TraceEvent(
                            ts=time.time(), kind="final", task_id=task_id, detail=final_answer[:200]
                        )
                    )
                    status = "completed"
                    verification = self._verify()
                    break

                for tc in tool_calls:
                    if budget.seconds_left() <= 0:
                        raise SafetyLimitError("Task deadline exceeded while executing tool calls.")
                    outcome = await self._execute_tool_call(tc, task_id, trace, budget)
                    if outcome["ok"]:
                        tool_calls_made += 1
                    elif outcome["phase"] == "pre-execution":
                        tool_calls_rejected += 1
                    else:
                        tool_errors += 1
                    self.memory.append(
                        ToolMessage(
                            call_id=tc.id,
                            name=tc.name,
                            ok=outcome["result"]["ok"],
                            data=outcome["result"].get("data"),
                            error=outcome["result"].get("error"),
                            duration_ms=outcome.get("duration_ms"),
                            attempt=outcome.get("attempt", 1),
                        )
                    )
        except Exception as exc:
            status = "failed"
            detail = _safe_err(exc)
            errors.append(detail)
            trace.append(TraceEvent(ts=time.time(), kind="error", task_id=task_id, detail=detail))
            final_answer = (
                f"Task stopped by a controlled error: {detail}. No tool result was fabricated."
            )
            verification = VerificationResult(
                ok=False,
                checks=[],
                notes="Run aborted; verification not applicable.",
            )

        duration = time.monotonic() - started
        return RunResult(
            status=status,
            final_answer=final_answer,
            turns=budget.turns,
            tool_calls_made=tool_calls_made,
            tool_calls_rejected=tool_calls_rejected,
            tool_errors=tool_errors,
            retries=retries,
            errors=errors,
            trace=list(trace),
            verification=verification,
            usage=usage,
            duration_s=duration,
            user_task=task,
        )

    # ---- internals ----
    def _build_messages(self) -> list[dict[str, Any]]:
        """Serialise task memory to provider message dicts.

        Critical invariant: the assistant message that requested tool calls and
        each matching tool result (with its call id) are both present, in order.
        """
        msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in self.memory.to_provider_messages():
            if isinstance(m, UserMessage):
                msgs.append({"role": "user", "content": m.content})
            elif isinstance(m, AssistantMessage):
                entry: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
                if m.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": _dump_args(tc.arguments)},
                        }
                        for tc in m.tool_calls
                    ]
                msgs.append(entry)
            else:  # ToolMessage
                payload = json.dumps({"ok": m.ok, "data": m.data, "error": m.error}, default=str)
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": m.call_id,
                        "content": _clip(payload, MAX_TOOL_MESSAGE_CHARS),
                    }
                )
        return msgs

    async def _call_model_with_retries(self, messages, tools, trace, task_id) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, self.retry_transient_max + 2):
            try:
                import asyncio

                resp = await asyncio.to_thread(
                    self.provider.chat,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
                resp["retry_count"] = attempt - 1
                return resp
            except SafetyLimitError:
                raise
            except AgentXError as exc:
                last_exc = exc
                trace.append(
                    TraceEvent(
                        ts=time.time(),
                        kind="error",
                        task_id=task_id,
                        detail=f"provider attempt {attempt}: {_safe_err(exc)}",
                    )
                )
        raise last_exc or AgentXError("provider call failed")

    async def _execute_tool_call(
        self, tc: ToolCallRequest, task_id, trace, budget
    ) -> dict[str, Any]:
        """Validate, authorize, and execute one tool call. Returns an outcome dict."""
        trace.append(
            TraceEvent(
                ts=time.time(),
                kind="tool_call",
                task_id=task_id,
                tool_name=tc.name,
                arguments=tc.arguments,
            )
        )
        try:
            tool = self.registry.get(tc.name)
        except UnknownToolError as exc:
            budget.tool_calls_rejected += 1
            trace.append(
                TraceEvent(
                    ts=time.time(),
                    kind="safety",
                    task_id=task_id,
                    tool_name=tc.name,
                    ok=False,
                    detail=str(exc),
                )
            )
            return _pre_exec_rejection("unknown_tool", str(exc))

        from safety.permissions import check_permission

        try:
            check_permission(tool, approved=set())
        except SafetyLimitError as exc:
            budget.tool_calls_rejected += 1
            trace.append(
                TraceEvent(
                    ts=time.time(),
                    kind="safety",
                    task_id=task_id,
                    tool_name=tc.name,
                    ok=False,
                    detail=str(exc),
                )
            )
            return _pre_exec_rejection("permission", str(exc))

        try:
            budget.claim_tool_call()
        except SafetyLimitError as exc:
            trace.append(
                TraceEvent(
                    ts=time.time(),
                    kind="safety",
                    task_id=task_id,
                    tool_name=tc.name,
                    ok=False,
                    detail=str(exc),
                )
            )
            return _pre_exec_rejection("budget", str(exc))

        started = time.monotonic()
        result = await tool.execute(tc.arguments)
        duration_ms = (time.monotonic() - started) * 1000.0
        trace.append(
            TraceEvent(
                ts=time.time(),
                kind="result",
                task_id=task_id,
                tool_name=tc.name,
                ok=bool(result["ok"]),
                detail=_short_err(result["error"])
                if not result["ok"]
                else _summarize(result.get("data")),
                data=result.get("data"),
            )
        )
        return {
            "ok": result["ok"],
            "phase": "executed",
            "result": result,
            "duration_ms": duration_ms,
            "attempt": 1,
        }

    def _verify(self) -> VerificationResult:
        from agent.verifier import verify_run

        return verify_run(self.memory, [], "")


def _pre_exec_rejection(error_type: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "phase": "pre-execution",
        "result": {"ok": False, "error": {"type": error_type, "message": message}, "data": None},
        "duration_ms": 0.0,
        "attempt": 1,
    }


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _dump_args(args: dict[str, Any]) -> str:
    return json.dumps(args, default=str)


def _short_err(err: dict[str, Any] | None) -> str:
    if not err:
        return "unknown error"
    return f"[{err.get('type', 'error')}] {err.get('message', '')}"


def _summarize(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    keys = ["result", "rate", "query", "retrieved_at_utc"]
    parts = [f"{k}={data[k]}" for k in keys if k in data]
    if isinstance(data.get("results"), list):
        parts.append(f"results={len(data['results'])}")
    return ", ".join(parts)


def _safe_err(exc: BaseException) -> str:
    """Short, secret-free error description for traces and final answers."""
    text = str(exc)
    low = text.lower()
    for token in ("api_key", "sk-", "bearer ", "authorization:"):
        if token in low:
            idx = low.find(token)
            return f"{type(exc).__name__}: {text[: max(0, idx - 20)].strip()}...[redacted]"
    if len(text) > 300:
        text = text[:300] + "..."
    return f"{type(exc).__name__}: {text}"
