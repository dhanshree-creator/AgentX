"""Tests for the Claude Code styled terminal user interface and commands."""

from __future__ import annotations

import time

from prompt_toolkit.document import Document

from agent.models import RunResult, TraceEvent, VerificationResult
from tools.calculator import CalculatorTool
from tools.registry import ToolRegistry
from ui.commands import CommandHandlers
from ui.console import (
    render_final_answer,
    render_history,
    render_model_info,
    render_run_result,
    render_stats,
    safety_violation,
    startup_panel,
    task_header,
    tool_table,
    trace_line,
)
from ui.prompt import ClaudePromptSession, SlashCommandCompleter


def test_startup_panel_renders():
    config = {
        "model": "z-ai/glm-5.3",
        "provider": "provider_a",
        "base_url": "https://example.com/v1",
        "max_turns": 12,
        "max_tool_calls": 5,
        "task_deadline_s": 120.0,
        "serper_key": "***set***",
    }
    startup_panel(config, ["calculator", "api_lookup"])


def test_task_header_renders():
    task_header("Calculate 25 * 4 and format nicely")


def test_trace_line_all_kinds():
    events = [
        TraceEvent(ts=time.time(), kind="plan", task_id="t1", detail="Plan detail"),
        TraceEvent(ts=time.time(), kind="llm_request", task_id="t1"),
        TraceEvent(ts=time.time(), kind="llm_response", task_id="t1", detail="finish_reason=stop tool_calls=1"),
        TraceEvent(
            ts=time.time(),
            kind="tool_call",
            task_id="t1",
            tool_name="calculator",
            arguments={"expression": "12 * 12"},
        ),
        TraceEvent(ts=time.time(), kind="safety", task_id="t1", ok=True, detail="allowlist ok"),
        TraceEvent(ts=time.time(), kind="safety", task_id="t1", ok=False, detail="blocked"),
        TraceEvent(ts=time.time(), kind="result", task_id="t1", ok=True, detail="144"),
        TraceEvent(ts=time.time(), kind="result", task_id="t1", ok=False, detail="calc failed"),
        TraceEvent(ts=time.time(), kind="verify", task_id="t1", ok=True, detail="all checks pass"),
        TraceEvent(ts=time.time(), kind="error", task_id="t1", detail="Unexpected failure"),
        TraceEvent(ts=time.time(), kind="final", task_id="t1", detail="Done"),
    ]
    for ev in events:
        trace_line(ev)


def test_render_final_answer():
    render_final_answer("### Result\nHere is a code block:\n```python\nprint(42)\n```")
    render_final_answer("")  # handles empty gracefully


def test_render_run_result():
    res = RunResult(
        status="completed",
        final_answer="42",
        turns=2,
        tool_calls_made=1,
        tool_calls_rejected=0,
        tool_errors=0,
        retries=0,
        errors=[],
        trace=[],
        verification=VerificationResult(
            ok=True,
            checks=[{"check": "result_valid", "ok": True}],
            notes="Passed verification",
        ),
        usage={"total_tokens": 320},
        duration_s=1.2,
        user_task="Test task",
    )
    render_run_result(res)


def test_tool_table():
    calc = CalculatorTool()
    reg = ToolRegistry()
    reg.register(
        name=calc.name,
        description=calc.description,
        parameters=calc.schema(),
        args_model=calc.args_model(),
        executor_run=calc.run,
        timeout_s=15.0,
    )
    tool_table(reg.list())


def test_render_stats():
    metrics = {
        "tasks_attempted": 5,
        "tasks_completed": 4,
        "tasks_failed": 1,
        "tool_calls_executed": 7,
        "tool_calls_rejected": 1,
        "tool_errors": 0,
        "calculator_correct": 3,
        "calculator_total": 3,
        "total_task_seconds": 12.5,
    }
    render_stats(metrics)


def test_render_history():
    render_history([])
    sample_result = RunResult(
        status="completed",
        final_answer="Answer",
        turns=1,
        tool_calls_made=2,
        tool_calls_rejected=0,
        tool_errors=0,
        retries=0,
        errors=[],
        trace=[],
        duration_s=0.8,
        user_task="Task sample",
    )
    render_history([{"task": "Calculate square root", "result": sample_result}])


def test_render_model_info():
    render_model_info(
        {
            "model": "z-ai/glm-5.3",
            "provider": "provider_a",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "max_turns": 12,
            "max_tool_calls": 5,
            "tool_timeout_s": 15.0,
            "task_deadline_s": 120.0,
            "retry_transient_max": 2,
            "serper_key": None,
        }
    )


def test_safety_violation():
    safety_violation("Dangerous shell invocation blocked.")


class DummyApp:
    def __init__(self):
        calc = CalculatorTool()
        reg = ToolRegistry()
        reg.register(
            name=calc.name,
            description=calc.description,
            parameters=calc.schema(),
            args_model=calc.args_model(),
            executor_run=calc.run,
            timeout_s=15.0,
        )
        self.registry = reg
        self.metrics = {
            "tasks_attempted": 1,
            "tasks_completed": 1,
            "tasks_failed": 0,
            "tool_calls_executed": 1,
            "tool_calls_rejected": 0,
            "tool_errors": 0,
            "calculator_correct": 1,
            "calculator_total": 1,
            "total_task_seconds": 0.5,
        }
        self.last_result = RunResult(
            status="completed",
            final_answer="Done",
            turns=1,
            tool_calls_made=1,
            tool_calls_rejected=0,
            tool_errors=0,
            retries=0,
            errors=[],
            trace=[TraceEvent(ts=time.time(), kind="plan", task_id="t1", detail="Plan")],
            duration_s=0.5,
            user_task="Test",
        )
        self.history = [{"task": "Test", "result": self.last_result}]
        self.config = type(
            "Config",
            (),
            {
                "redacted": lambda self: {
                    "model": "glm-5.3",
                    "provider": "provider_a",
                    "base_url": "https://example.com",
                    "max_turns": 12,
                    "max_tool_calls": 5,
                    "tool_timeout_s": 15.0,
                    "task_deadline_s": 120.0,
                    "retry_transient_max": 2,
                    "serper_key": None,
                }
            },
        )()
        self.loop = type(
            "Loop",
            (),
            {"memory": type("Memory", (), {"clear": lambda self: None})()},
        )()
        self.pending_async = None


def test_command_handlers():
    app = DummyApp()
    handlers = CommandHandlers(app)

    assert handlers.handle("/help") is True
    assert handlers.handle("/tools") is True
    assert handlers.handle("/trace") is True
    assert handlers.handle("/stats") is True
    assert handlers.handle("/model") is True
    assert handlers.handle("/history") is True
    assert handlers.handle("/clear") is True
    assert handlers.handle("/benchmark") is True
    assert handlers.handle("/safety-demo") is True
    assert app.pending_async == "/safety-demo"
    assert handlers.handle("/unknown_cmd") is True
    assert handlers.handle("/exit") is False
    assert handlers.handle("/quit") is False


def test_completer_and_prompt():
    completer = SlashCommandCompleter()
    doc = Document("/h")
    completions = list(completer.get_completions(doc, None))
    cmds = [c.text for c in completions]
    assert "/help" in cmds
    assert "/history" in cmds

    session = ClaudePromptSession(model_name="z-ai/glm-5.3")
    tokens = session._get_prompt_tokens()
    assert any("AgentX" in t[1] for t in tokens)
