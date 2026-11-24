"""Benchmark suite + verifier tests (fully offline, deterministic)."""

import pytest

from evaluation.benchmark import report_lines, run_all_scenarios


@pytest.mark.asyncio
async def test_all_scenarios_pass():
    results = await run_all_scenarios()
    failed = [r.name for r in results if not r.passed]
    assert not failed, f"failing scenarios: {failed}"
    assert len(results) == 10
    lines = report_lines(results)
    assert any("10/10" in line for line in lines)


def test_verifier_flags_failed_tools():
    from agent.memory import TaskMemory
    from agent.models import ToolMessage
    from agent.verifier import verify_run

    memory = TaskMemory()
    memory.set_user_task("task")
    memory.append(
        ToolMessage(
            call_id="c1",
            name="web_search",
            ok=False,
            error={"type": "execution", "message": "down"},
        )
    )
    vr = verify_run(memory, [], "tid")
    assert vr.notes
    assert any(c["check"] == "any_tool_failed_flagged" for c in vr.checks)


def test_verifier_pairing_check():
    from agent.memory import TaskMemory
    from agent.models import AssistantMessage, ToolCallRequest, ToolMessage
    from agent.verifier import verify_run

    memory = TaskMemory()
    memory.set_user_task("task")
    memory.append(
        AssistantMessage(
            content=None,
            tool_calls=[
                ToolCallRequest(id="c1", name="calculator", arguments={"expression": "1+1"})
            ],
        )
    )
    memory.append(ToolMessage(call_id="c1", name="calculator", ok=True, data={"result": "2"}))
    vr = verify_run(memory, [], "tid")
    pairing = [c for c in vr.checks if c["check"] == "tool_call_result_pairing"]
    assert pairing and pairing[0]["ok"] is True


def test_verifier_detects_missing_api_rate_in_calc():
    from agent.memory import TaskMemory
    from agent.models import ToolMessage
    from agent.verifier import verify_run

    memory = TaskMemory()
    memory.set_user_task("convert")
    memory.append(
        ToolMessage(call_id="a", name="api_lookup", ok=True, data={"rate_number": "84.5"})
    )
    memory.append(
        ToolMessage(
            call_id="b", name="calculator", ok=True, data={"expression": "1+1", "result": "2"}
        )
    )
    vr = verify_run(memory, [], "tid")
    check_rate = [c for c in vr.checks if c["check"] == "calculator_uses_api_rate"]
    assert check_rate and check_rate[0]["ok"] is False
