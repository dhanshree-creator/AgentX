"""Test suite for the 4 core AgentX test cases."""

import pytest
import httpx
from tools.calculator import CalculatorTool
from tools.api_lookup import ApiLookupTool
from tools.web_search import WebSearchTool
from tools.registry import ToolRegistry, make_registry
from agent.exceptions import ToolExecutionError, UnknownToolError


@pytest.mark.asyncio
async def test_case_1_calculator():
    """Test Case 1: Pure AST Mathematical Evaluation (125 * 48 = 6000)."""
    calc = CalculatorTool()
    res = await calc.run({"expression": "125 * 48"})
    assert res["result"] == "6000"

    # Verify AST blocks arbitrary code injection
    with pytest.raises(ToolExecutionError):
        await calc.run({"expression": "__import__('os').system('dir')"})


@pytest.mark.asyncio
async def test_case_2_currency_lookup(monkeypatch):
    """Test Case 2: Currency Exchange Rate API Lookup."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": "success",
                "time_last_update_unix": 1700000000,
                "rates": {"INR": 86.82, "EUR": 0.92},
            },
        )

    import tools.api_lookup as api_mod
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        api_mod.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_client(transport=httpx.MockTransport(handler), **{k: v for k, v in kwargs.items() if k not in ("timeout", "transport")})
    )

    api = ApiLookupTool()
    res = await api.run({"base": "USD", "target": "INR"})
    assert res["base"] == "USD"
    assert res["target"] == "INR"
    assert res["rate_number"] == "86.82"


@pytest.mark.asyncio
async def test_case_3_web_search(monkeypatch):
    """Test Case 3: Live Web Search with Untrusted Notice & SSRF Protection."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organic": [
                    {"title": "Everest Elevation", "link": "https://example.com/everest", "snippet": "8848.86 meters"},
                ]
            },
        )

    import tools.web_search as ws_mod
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        ws_mod.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_client(transport=httpx.MockTransport(handler), **{k: v for k, v in kwargs.items() if k not in ("timeout", "transport")})
    )

    search = WebSearchTool(api_key="mock-key")
    res = await search.run({"query": "Mount Everest height meters", "num_results": 1})
    assert len(res["results"]) == 1
    assert res["results"][0]["snippet"] == "8848.86 meters"
    assert "untrusted_content_notice" in res


@pytest.mark.asyncio
async def test_case_4_safety_guardrail_intercept():
    """Test Case 4: 4-Layer Safety Firewall blocks unauthorized tools."""
    calc = CalculatorTool()
    search = WebSearchTool(api_key="mock-key")
    api = ApiLookupTool()
    registry = make_registry(calc, search, api)

    # Allowed tools exist
    assert registry.is_registered("calculator")
    assert registry.is_registered("api_lookup")
    assert registry.is_registered("web_search")

    # Unauthorized tools are rejected at Layer 1 Allowlist Gate
    assert not registry.is_registered("delete_database")
    assert not registry.is_registered("execute_shell")

    with pytest.raises(UnknownToolError):
        registry.get("delete_database")
