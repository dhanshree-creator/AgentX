"""Test suite for AgentX Web API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


def test_root_serves_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AgentX" in resp.text
    assert "ChatGPT & Gemini-inspired" in resp.text or "Autonomous Task-Solving" in resp.text


def test_api_config():
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "model" in data
    assert "tools" in data
    assert "calculator" in data["tools"]
    assert "api_lookup" in data["tools"]
    assert "web_search" in data["tools"]


def test_api_tools():
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) == 3
    names = {t["name"] for t in tools}
    assert names == {"calculator", "api_lookup", "web_search"}


def test_api_stats():
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert "metrics" in stats
    assert "tasks_attempted" in stats["metrics"]


def test_api_clear():
    resp = client.post("/api/clear")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True


def test_api_safety_demo():
    resp = client.post("/api/safety-demo")
    assert resp.status_code == 200
    cases = resp.json()
    assert len(cases) == 5
    for case in cases:
        assert case["passed"] is True
        assert case["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_api_benchmark():
    resp = client.post("/api/benchmark")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 10
    passed = [r for r in results if r["passed"]]
    assert len(passed) == 10


def test_api_task_empty_rejected():
    resp = client.post("/api/task", json={"task": "   "})
    assert resp.status_code == 400
