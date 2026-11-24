"""Agent loop tests using a scripted fake provider (no network, no API key)."""

from __future__ import annotations

import json

import pytest

from agent.exceptions import ProviderError
from agent.loop import AgentLoop
from tools.calculator import CalculatorTool
from tools.registry import ToolRegistry


class FakeProvider:
    """Scripted responses, mimicking OpenAI-compatible tool-calling payload shape."""

    def __init__(self, script: list[dict]):
        self.script = list(script)
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None, tool_choice="auto", temperature=0.0):
        self.calls.append(json.loads(json.dumps(messages)))
        resp = self.script.pop(0)
        return {
            "content": resp.get("content"),
            "tool_calls": [
                {"id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]}
                for tc in resp.get("tool_calls") or []
            ],
            "usage": resp.get("usage", {}),
            "finish_reason": resp.get(
                "finish_reason", "tool_calls" if resp.get("tool_calls") else "stop"
            ),
        }


def make_registry_min() -> ToolRegistry:
    calc = CalculatorTool()
    reg = ToolRegistry()
    reg.register(
        name=calc.name,
        description=calc.description,
        parameters=calc.schema(),
        args_model=calc.args_model(),
        executor_run=calc.run,
        timeout_s=5.0,
    )
    return reg


@pytest.mark.asyncio
async def test_single_turn_no_tool():
    provider = FakeProvider([{"content": "Hello, task done.", "tool_calls": []}])
    loop = AgentLoop(provider, make_registry_min(), max_tool_calls=3, max_turns=3, deadline_s=30)
    res = await loop.run_task("Say hello")
    assert res.status == "completed"
    assert res.final_answer == "Hello, task done."


@pytest.mark.asyncio
async def test_tool_call_round_trip():
    provider = FakeProvider(
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "c1", "name": "calculator", "arguments": {"expression": "6 * 7"}}
                ],
            },
            {"content": "42", "tool_calls": []},
        ]
    )
    loop = AgentLoop(provider, make_registry_min(), max_tool_calls=3, max_turns=4, deadline_s=30)
    res = await loop.run_task("Multiply 6 by 7 with the calculator.")
    assert res.status == "completed"
    assert res.tool_calls_made == 1
    # Second request must contain assistant tool_calls + matching tool result.
    second = provider.calls[1]
    assistant = [m for m in second if m.get("role") == "assistant" and m.get("tool_calls")]
    toolmsg = [m for m in second if m.get("role") == "tool"]
    assert assistant and assistant[0]["tool_calls"][0]["id"] == "c1"
    assert toolmsg and toolmsg[0]["tool_call_id"] == "c1"
    assert "42" in json.dumps(toolmsg[0]["content"])


@pytest.mark.asyncio
async def test_unknown_tool_rejected_gracefully():
    provider = FakeProvider(
        [
            {
                "content": None,
                "tool_calls": [{"id": "c1", "name": "delete_database", "arguments": {}}],
            },
            {"content": "Cannot help with that.", "tool_calls": []},
        ]
    )
    loop = AgentLoop(provider, make_registry_min(), max_tool_calls=3, max_turns=4, deadline_s=30)
    res = await loop.run_task("Delete everything.")
    assert res.status == "completed"
    assert res.tool_calls_rejected == 1 and res.tool_calls_made == 0


@pytest.mark.asyncio
async def test_tool_budget_stops_run():
    provider = FakeProvider(
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": f"c{i}", "name": "calculator", "arguments": {"expression": "1+1"}}
                ],
            }
            for i in range(10)
        ]
    )
    loop = AgentLoop(provider, make_registry_min(), max_tool_calls=2, max_turns=8, deadline_s=60)
    res = await loop.run_task("Loop tools.")
    # Two executions succeed; third claim hits the budget limit -> controlled failure.
    assert res.status == "failed" and res.tool_calls_made == 2
    assert any(
        "budget" in e.lower()
        for e in res.errors + [t.detail for t in res.trace if t.kind == "safety"]
    )


@pytest.mark.asyncio
async def test_turn_budget_enforced():
    class EndlessProvider(FakeProvider):
        def chat(self, messages, tools=None, tool_choice="auto", temperature=0.0):
            return {
                "content": None,
                "tool_calls": [
                    {"id": "x", "name": "calculator", "arguments": {"expression": "1+1"}}
                ],
                "usage": {},
                "finish_reason": "tool_calls",
            }

    loop = AgentLoop(
        EndlessProvider([]), make_registry_min(), max_tool_calls=50, max_turns=3, deadline_s=60
    )
    res = await loop.run_task("loop forever")
    assert res.status == "failed" and res.turns <= 3


@pytest.mark.asyncio
async def test_provider_error_recorded_no_fabrication():
    class BoomProvider:
        def chat(self, *a, **kw):
            raise ProviderError("503 service unavailable")

    loop = AgentLoop(
        BoomProvider(), make_registry_min(), max_tool_calls=3, max_turns=3, deadline_s=30
    )
    res = await loop.run_task("anything")
    assert res.status == "failed"
    assert "503" in res.final_answer
    assert res.verification is not None
