"""Deterministic verifier: checks tool evidence, independent of model claims."""

from __future__ import annotations

from typing import Any

from agent.memory import TaskMemory
from agent.models import AssistantMessage, ToolMessage, VerificationResult


def verify_run(memory: TaskMemory, trace: list, task_id: str) -> VerificationResult:
    """Deterministic checks over the just-finished run's tool messages."""
    checks: list[dict[str, Any]] = []
    tool_msgs = [m for m in memory.messages if isinstance(m, ToolMessage)]
    ok_all = True
    notes: list[str] = []

    # Check 1: every executed tool call has a matching tool result (id round-trip).
    call_ids = [
        tc.id for m in memory.messages if isinstance(m, AssistantMessage) for tc in m.tool_calls
    ]
    result_ids = [m.call_id for m in tool_msgs]
    if call_ids:
        if sorted(call_ids) == sorted(result_ids):
            checks.append({"check": "tool_call_result_pairing", "ok": True})
        else:
            ok_all = False
            notes.append("Some tool calls lack a matching tool result (context handoff issue).")
            checks.append({"check": "tool_call_result_pairing", "ok": False})

    # Check 2: calculations must visibly use retrieved API values when both ran.
    calc_msgs = [m for m in tool_msgs if m.name == "calculator" and m.ok]
    api_msgs = [m for m in tool_msgs if m.name == "api_lookup" and m.ok]
    if calc_msgs and api_msgs:
        rate = None
        for m in api_msgs:
            data = m.data or {}
            rate = data.get("rate_number") or data.get("rate")
            if rate:
                break
        exprs = [
            str((m.data or {}).get("expression") or "")
            for m in calc_msgs
            if isinstance(m.data, dict)
        ]
        if rate and any(_digits(rate) in _digits(e) for e in exprs):
            checks.append({"check": "calculator_uses_api_rate", "ok": True})
        else:
            ok_all = False
            notes.append(
                "Calculator expression did not visibly include the retrieved rate; "
                "final numbers may not be evidence-backed."
            )
            checks.append({"check": "calculator_uses_api_rate", "ok": False})

    # Check 3: failures are surfaced, never hidden.
    if any(not m.ok for m in tool_msgs):
        notes.append("At least one tool failed; the final answer must state that limitation.")
        checks.append({"check": "any_tool_failed_flagged", "ok": True})

    # Check 4: search-enabled runs should have citable URLs.
    search_msgs = [m for m in tool_msgs if m.name == "web_search" and m.ok]
    if search_msgs:
        urls = [
            r.get("url")
            for m in search_msgs
            for r in ((m.data or {}).get("results") or [])
            if isinstance(r, dict)
        ]
        checks.append({"check": "search_urls_available", "ok": bool(urls), "url_count": len(urls)})
        if not urls:
            ok_all = False
            notes.append("Search ran but returned no usable URLs for citation.")

    return VerificationResult(
        ok=ok_all,
        checks=checks,
        notes=" ".join(notes) if notes else "All applicable deterministic checks passed.",
    )


def _digits(text: Any) -> str:
    return "".join(ch for ch in str(text or "") if ch.isdigit())
