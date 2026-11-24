"""api_lookup and web_search tests with mocked HTTP transport (no network)."""

import httpx
import pytest

from agent.exceptions import ToolExecutionError
from tools.api_lookup import ApiLookupTool
from tools.web_search import WebSearchTool


def _transport(handler) -> httpx.AsyncBaseTransport:
    return httpx.MockTransport(handler)


def _patch_asyncclient(monkeypatch, transport):
    import tools.api_lookup as api_mod
    import tools.web_search as ws_mod

    real_client = httpx.AsyncClient

    def _client_patched(*args, **kwargs):
        kwargs.pop("timeout", None)
        kwargs.pop("transport", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(api_mod.httpx, "AsyncClient", _client_patched)
    monkeypatch.setattr(ws_mod.httpx, "AsyncClient", _client_patched)


@pytest.mark.asyncio
async def test_api_lookup_success(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/USD")
        return httpx.Response(
            200,
            json={
                "result": "success",
                "time_last_update_unix": 1700000000,
                "rates": {"INR": 83.2, "EUR": 0.91},
            },
        )

    _patch_asyncclient(monkeypatch, _transport(handler))
    tool = ApiLookupTool()
    res = await tool.run({"base": "usd", "target": "inr"})
    assert res["base"] == "USD" and res["target"] == "INR"
    assert res["rate_number"] == "83.2"
    assert res["retrieved_at_utc"].endswith("Z")
    assert res["provider_updated_at_utc"] is not None


@pytest.mark.asyncio
async def test_api_lookup_missing_currency(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rates": {"EUR": 0.91}})

    _patch_asyncclient(monkeypatch, _transport(handler))
    tool = ApiLookupTool()
    with pytest.raises(ToolExecutionError) as ei:
        await tool.run({"base": "USD", "target": "INR"})
    assert "No rate available" in str(ei.value)


@pytest.mark.asyncio
async def test_api_lookup_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    _patch_asyncclient(monkeypatch, _transport(handler))
    tool = ApiLookupTool()
    with pytest.raises(ToolExecutionError) as ei:
        await tool.run({"base": "USD", "target": "INR"})
    assert "503" in str(ei.value)


@pytest.mark.asyncio
async def test_api_lookup_malformed_json(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    _patch_asyncclient(monkeypatch, _transport(handler))
    tool = ApiLookupTool()
    with pytest.raises(ToolExecutionError):
        await tool.run({"base": "USD", "target": "INR"})


@pytest.mark.asyncio
async def test_api_lookup_invalid_currency_args():
    tool = ApiLookupTool()
    with pytest.raises(ToolExecutionError):
        await tool.run({"base": "USDD", "target": "INR"})
    with pytest.raises(ToolExecutionError):
        await tool.run({"base": "12", "target": "IN!"})


# ---- web_search ----


@pytest.mark.asyncio
async def test_search_requires_key():
    tool = WebSearchTool(api_key=None)
    with pytest.raises(ToolExecutionError) as ei:
        await tool.run({"query": "test"})
    assert "SERPER_API_KEY" in str(ei.value)


@pytest.mark.asyncio
async def test_search_success(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "google.serper.dev"
        assert request.headers.get("x-api-key") == "fake-key"
        return httpx.Response(
            200,
            json={
                "organic": [
                    {"title": "A", "link": "https://a.example/1", "snippet": "first"},
                    {"title": "B", "link": "https://b.example/2", "snippet": "second"},
                ]
            },
        )

    import tools.web_search as ws_mod

    real_client = httpx.AsyncClient

    def _client(**kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=_transport(handler), **kwargs)

    monkeypatch.setattr(ws_mod.httpx, "AsyncClient", _client)
    tool = WebSearchTool(api_key="fake-key")
    res = await tool.run({"query": "unit testing", "num_results": 2})
    assert len(res["results"]) == 2
    assert res["results"][0]["url"] == "https://a.example/1"
    assert "untrusted_content_notice" in res


@pytest.mark.asyncio
async def test_search_rate_limit_structured_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited"})

    import tools.web_search as ws_mod

    real_client = httpx.AsyncClient

    def _client(**kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=_transport(handler), **kwargs)

    monkeypatch.setattr(ws_mod.httpx, "AsyncClient", _client)
    tool = WebSearchTool(api_key="fake-key")
    with pytest.raises(ToolExecutionError) as ei:
        await tool.run({"query": "anything"})
    assert "429" in str(ei.value)


@pytest.mark.asyncio
async def test_search_filters_private_urls(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organic": [
                    {"title": "Meta", "link": "https://169.254.169.254/latest", "snippet": "x"},
                    {"title": "OK", "link": "https://fine.example/ok", "snippet": "y"},
                ]
            },
        )

    import tools.web_search as ws_mod

    real_client = httpx.AsyncClient

    def _client(**kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=_transport(handler), **kwargs)

    monkeypatch.setattr(ws_mod.httpx, "AsyncClient", _client)
    tool = WebSearchTool(api_key="fake-key")
    res = await tool.run({"query": "test"})
    urls = [r["url"] for r in res["results"]]
    assert all(not u.startswith("https://169.") for u in urls)
    assert "https://fine.example/ok" in urls


@pytest.mark.asyncio
async def test_search_timeout(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    import tools.web_search as ws_mod

    real_client = httpx.AsyncClient

    def _client(**kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=_transport(handler), **kwargs)

    monkeypatch.setattr(ws_mod.httpx, "AsyncClient", _client)
    tool = WebSearchTool(api_key="fake-key")
    with pytest.raises(ToolExecutionError) as ei:
        await tool.run({"query": "slow query"})
    assert "timed out" in str(ei.value)
