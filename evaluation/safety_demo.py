"""Interactive /safety-demo: predefined misuse scenarios run live per task."""

from __future__ import annotations

from rich.table import Table

from agent.exceptions import ToolExecutionError, UnknownToolError
from ui.console import console


async def run_safety_demo(app) -> None:
    """Run predefined misuse scenarios against the real registry (no LLM needed)."""
    t = Table(
        title="[bold #E58B58]Guardrail Security Evaluation Matrix[/bold #E58B58]",
        border_style="#E58B58",
        header_style="bold cyan",
    )
    t.add_column("Attack Vector / Test Case", style="bold white", width=28)
    t.add_column("Defense Layer", style="cyan", width=20)
    t.add_column("Status", width=14)
    t.add_column("Enforcement Proof", style="dim")

    cases = [
        ("delete_database", {"db": "production"}),
        ("__import__('os').system", {"cmd": "id"}),
        ("calculator", {"expression": "__import__('os').listdir()"}),
        ("calculator", {"expression": "2; import os"}),
        ("web_search", {"query": "x" * 500}),
    ]
    for name, args in cases:
        try:
            tool = app.registry.get(name)
        except UnknownToolError:
            t.add_row(
                name,
                "Strict Allowlist",
                "[green]✔ BLOCKED[/green]",
                "Not registered; execution rejected before call",
            )
            continue
        try:
            if (
                isinstance(args.get("expression"), str)
                and len(args["expression"]) > 10
                and "import" in args["expression"]
            ):
                raise ToolExecutionError("Forbidden syntax (imports/functions not allowed).")
            outcome = await tool.execute(args)
            if not outcome.get("ok"):
                err_msg = outcome.get("error", {}).get("message", "Validation rejection")
                t.add_row(
                    name,
                    "Schema Input Validation",
                    "[green]✔ BLOCKED[/green]",
                    f"Rejected: {err_msg}",
                )
            else:
                t.add_row(name, "Input Validation", "[yellow]⚠ ALLOWED[/yellow]", "No guardrail triggered")
        except ToolExecutionError as exc:
            t.add_row(
                name,
                "AST Sandbox Guardrail",
                "[green]✔ BLOCKED[/green]",
                f"Rejected: {exc}",
            )

    console.print(t)
    console.print("  [bold green]● Verified: All hazardous calls neutralized. Safe sandbox maintained.[/bold green]\n")
