"""Calculator tests: arithmetic correctness plus security rejections."""

import pytest

from agent.exceptions import ToolExecutionError
from tools.calculator import CalculatorTool


@pytest.fixture()
def calc() -> CalculatorTool:
    return CalculatorTool()


@pytest.mark.asyncio
async def test_basic_add_mul(calc):
    res = await calc.run({"expression": "125 * 48"})
    assert res["result"] == "6000"


@pytest.mark.asyncio
async def test_parentheses_and_decimals(calc):
    res = await calc.run({"expression": "(250 * 84.5) * (1 - 0.02)"})
    # Exact decimal arithmetic: 21125 * 0.98 = 20702.5
    assert res["result"] == "20702.5"


@pytest.mark.asyncio
async def test_unary_minus(calc):
    res = await calc.run({"expression": "-5 + 3"})
    assert res["result"] == "-2"


@pytest.mark.asyncio
async def test_division(calc):
    res = await calc.run({"expression": "100 / 4"})
    assert res["result"] == "25"


@pytest.mark.asyncio
async def test_division_by_zero_rejected(calc):
    with pytest.raises(ToolExecutionError):
        await calc.run({"expression": "1 / 0"})


@pytest.mark.asyncio
async def test_reject_import_exec_call(calc):
    for expr in (
        "__import__('os').system('id')",
        "eval('2+2')",
        "exec('x=1')",
        "open('/etc/passwd')",
        "__builtins__",
    ):
        with pytest.raises(ToolExecutionError):
            await calc.run({"expression": expr})


@pytest.mark.asyncio
async def test_reject_variables_and_attributes(calc):
    for expr in ("x + 1", "os.getcwd", "a.b", "f'{1+1}'"):
        with pytest.raises(ToolExecutionError):
            await calc.run({"expression": expr})


@pytest.mark.asyncio
async def test_reject_strings_and_bool(calc):
    for expr in ("'1' + '2'", "True + 1"):
        with pytest.raises(ToolExecutionError):
            await calc.run({"expression": expr})


@pytest.mark.asyncio
async def test_reject_comparison_and_boolops(calc):
    for expr in ("1 < 2", "1 and 2", "1 if 2 else 3"):
        with pytest.raises(ToolExecutionError):
            await calc.run({"expression": expr})


@pytest.mark.asyncio
async def test_reject_oversized_literal(calc):
    big = "9" * 40
    with pytest.raises(ToolExecutionError):
        await calc.run({"expression": f"{big} + 1"})


@pytest.mark.asyncio
async def test_reject_extra_fields(calc):
    with pytest.raises(ToolExecutionError):
        await calc.run({"expression": "1+1", "evil": "payload"})


@pytest.mark.asyncio
async def test_reject_non_string_expression(calc):
    with pytest.raises(ToolExecutionError):
        await calc.run({"expression": 123})


@pytest.mark.asyncio
async def test_malformed_syntax_rejected(calc):
    with pytest.raises(ToolExecutionError):
        await calc.run({"expression": "1 + + +"})


@pytest.mark.asyncio
async def test_small_power_allowed(calc):
    res = await calc.run({"expression": "2 ** 3"})
    assert res["result"] == "8"


@pytest.mark.asyncio
async def test_fractional_power_rejected(calc):
    with pytest.raises(ToolExecutionError):
        await calc.run({"expression": "4 ** 0.5"})
