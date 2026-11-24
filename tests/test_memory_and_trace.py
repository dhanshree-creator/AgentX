"""Memory trimming, redaction, and planner preview tests."""

from agent.memory import TaskMemory
from agent.metrics import redact
from agent.models import ToolMessage
from agent.planner import plan_preview


def test_memory_trims_oldest_but_keeps_anchor():
    m = TaskMemory(max_messages=4)
    m.set_user_task("anchor task")
    for i in range(10):
        m.append(ToolMessage(call_id=f"c{i}", name="calculator", ok=True))
    assert m.messages[0].content == "anchor task"
    assert len(m.messages) <= 4


def test_memory_clear():
    m = TaskMemory()
    m.set_user_task("x")
    m.clear()
    assert m.user_task == "" and m.messages == []


def test_user_truncation():
    m = TaskMemory(max_user_chars=50)
    m.set_user_task("x" * 200)
    assert m.messages[-1].content.endswith("...[truncated]")
    assert len(m.messages[-1].content) <= 65


def test_redact_secrets():
    obj = {"api_key": "sk-123", "nested": {"token": "abc", "ok": 1}, "list": [{"password": "p"}]}
    safe = redact(obj)
    assert safe["api_key"] == "***redacted***"
    assert safe["nested"]["token"] == "***redacted***"
    assert safe["nested"]["ok"] == 1
    assert safe["list"][0]["password"] == "***redacted***"


def test_plan_preview_first_sentence():
    assert plan_preview("Get the rate. Then calculate. Extra.").startswith("Get the rate")
    assert len(plan_preview("x" * 500)) <= 140
