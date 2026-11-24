"""Tool registry allowlist tests."""

import pytest

from agent.exceptions import ToolExecutionError, UnknownToolError
from tools.calculator import CalculatorTool
from tools.registry import ToolRegistry


def _tiny_tool():
    from pydantic import BaseModel

    class Args(BaseModel):
        x: int

    async def run(args: Args):
        return {"x2": args.x * 2}

    return {
        "name": "adder",
        "description": "adds",
        "parameters": {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
            "additionalProperties": False,
        },
        "args_model": Args,
        "executor_run": run,
        "timeout_s": 5.0,
    }


def test_register_and_get():
    reg = ToolRegistry()
    reg.register(**_tiny_tool())
    assert reg.is_registered("adder")
    assert reg.get("Adder").name == "adder"  # case-insensitive lookup
    assert not reg.is_registered("other")


def test_duplicate_registration_rejected():
    reg = ToolRegistry()
    reg.register(**_tiny_tool())
    with pytest.raises(ToolExecutionError):
        reg.register(**_tiny_tool())


def test_unknown_tool_rejected():
    reg = ToolRegistry()
    with pytest.raises(UnknownToolError):
        reg.get("delete_database")


def test_schema_shape():
    reg = ToolRegistry()
    reg.register(**_tiny_tool())
    schemas = reg.schemas()
    assert schemas[0]["type"] == "function"
    fn = schemas[0]["function"]
    assert fn["name"] == "adder"
    assert "x" in fn["parameters"]["properties"]


@pytest.mark.asyncio
async def test_execute_success_and_validation():
    reg = ToolRegistry()
    reg.register(**_tiny_tool())
    tool = reg.get("adder")
    ok = await tool.execute({"x": 21})
    assert ok["ok"] and ok["data"]["x2"] == 42
    bad = await tool.execute({"x": "not-int"})
    assert not bad["ok"] and bad["error"]["type"] == "validation"


def test_make_registry_default_tools():
    from tools.api_lookup import ApiLookupTool
    from tools.web_search import WebSearchTool

    reg = ToolRegistry()
    reg.register(
        name=CalculatorTool().name,
        description=CalculatorTool().description,
        parameters=CalculatorTool().schema(),
        args_model=CalculatorTool().args_model(),
        executor_run=CalculatorTool().run,
    )
    reg.register(
        name=ApiLookupTool().name,
        description=ApiLookupTool().description,
        parameters=ApiLookupTool().schema(),
        args_model=ApiLookupTool().args_model(),
        executor_run=ApiLookupTool().run,
    )
    reg.register(
        name=WebSearchTool(api_key=None).name,
        description=WebSearchTool(api_key=None).description,
        parameters=WebSearchTool(api_key=None).schema(),
        args_model=WebSearchTool(api_key=None).args_model(),
        executor_run=WebSearchTool(api_key=None).run,
    )
    names = {t.name for t in reg.list()}
    assert names == {"calculator", "api_lookup", "web_search"}
