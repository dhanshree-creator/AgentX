"""Interactive REPL commands with Claude Code styling (/help, /tools, /trace, /stats, /model, /history, /clear, /benchmark, /safety-demo, /exit)."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table

from evaluation.benchmark import run_all_scenarios
from ui.console import (
    _COLORS,
    _LABELS,
    console,
    render_history,
    render_model_info,
    render_run_result,
    render_stats,
    tool_table,
)


def _run_async(coro: Any) -> Any:
    """Run a coroutine even when an event loop is already running (REPL context)."""
    import asyncio as _asyncio

    try:
        running = _asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is None:
        return _asyncio.run(coro)
    import concurrent.futures as _cf

    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, coro).result()


class CommandHandlers:
    """Binds CLI commands to the app context (loop, registry, metrics, trace)."""

    def __init__(self, app: Any):
        self.app = app

    def handle(self, raw: str) -> bool:
        """Handle a /command; return False when the REPL should exit."""
        cmd, _, rest = raw.partition(" ")
        cmd = cmd.strip().lower()
        rest = rest.strip()

        if cmd in ("/exit", "/quit", "/q"):
            console.print("\n[bold #E58B58]Session ended.[/bold #E58B58] [dim]Goodbye![/dim]\n")
            return False

        if cmd in ("/help", "/?"):
            self._help()
        elif cmd == "/tools":
            tool_table(self.app.registry.list())
        elif cmd == "/trace":
            self._trace()
        elif cmd == "/stats":
            self._stats()
        elif cmd == "/model":
            self._model()
        elif cmd == "/history":
            self._history()
        elif cmd in ("/clear", "/cls"):
            self.app.loop.memory.clear()
            console.print(
                Panel(
                    "[bold green]✔[/bold green] Conversation memory cleared. Ready for next task.",
                    border_style="dim",
                    expand=False,
                )
            )
            console.print()
        elif cmd == "/benchmark":
            self._benchmark(rest)
        elif cmd == "/safety-demo":
            self._safety_demo()
        else:
            console.print(
                f"[bold red]Unknown command:[/bold red] [yellow]{cmd}[/yellow]. Type [bold cyan]/help[/bold cyan] for commands."
            )
            console.print()
        return True

    def _help(self) -> None:
        t = Table(
            title="[bold #E58B58]AgentX Command Palette[/bold #E58B58]",
            border_style="#E58B58",
            header_style="bold cyan",
            expand=False,
        )
        t.add_column("Category", style="dim", width=16)
        t.add_column("Command", style="bold #E58B58", width=16)
        t.add_column("Description", style="bright_white")

        t.add_row("Exploration", "/tools", "Inspect registered tools, limits, and schemas")
        t.add_row("", "/model", "View active model name, endpoint, and safety limits")
        t.add_row("", "/help", "Show this categorized command reference")
        t.add_section()

        t.add_row("Inspection", "/trace", "Detailed step-by-step trace of latest task run")
        t.add_row("", "/stats", "Session metrics (success rate, latency, token usage)")
        t.add_row("", "/history", "List tasks executed in current session")
        t.add_section()

        t.add_row("Testing", "/benchmark", "Run 10 offline acceptance test scenarios")
        t.add_row("", "/safety-demo", "Run live guardrail misuse tests against safety engine")
        t.add_section()

        t.add_row("Session", "/clear", "Clear task-local conversation memory")
        t.add_row("", "/exit, /quit", "Exit the AgentX CLI")

        console.print(t)
        console.print(
            "[dim]Shortcuts: [/dim][bold cyan]Tab[/bold cyan] [dim]autocomplete[/dim]  [dim]•[/dim]  "
            "[bold cyan]↑/↓[/bold cyan] [dim]history[/dim]  [dim]•[/dim]  "
            "[bold cyan]Ctrl+C[/bold cyan] [dim]cancel task[/dim]  [dim]•[/dim]  "
            "[bold cyan]Ctrl+D[/bold cyan] [dim]exit[/dim]"
        )
        console.print()

    def _model(self) -> None:
        render_model_info(self.app.config.redacted())

    def _history(self) -> None:
        history = getattr(self.app, "history", [])
        render_history(history)

    def _trace(self) -> None:
        res = self.app.last_result
        if res is None:
            console.print("[dim yellow]No task has been executed yet in this session.[/dim yellow]")
            console.print()
            return

        t = Table(
            title=f"[bold #E58B58]Task Execution Trace ({res.status.upper()})[/bold #E58B58]",
            border_style="#E58B58",
            header_style="bold cyan",
            expand=False,
        )
        t.add_column("Step", style="dim", width=6, justify="right")
        t.add_column("Kind", style="bold", width=14)
        t.add_column("Tool / Target", style="cyan", width=18)
        t.add_column("Details", style="bright_white", ratio=1)

        for idx, ev in enumerate(res.trace, 1):
            kind = _LABELS.get(ev.kind, ev.kind.upper())
            color = _COLORS.get(ev.kind, "white")
            detail = ev.detail or ""
            if len(detail) > 160:
                detail = detail[:157] + "..."
            tool_name = ev.tool_name or "-"
            t.add_row(str(idx), f"[{color}]{kind}[/{color}]", tool_name, detail)

        console.print(t)
        render_run_result(res)

    def _stats(self) -> None:
        render_stats(self.app.metrics)

    def _benchmark(self, rest: str) -> None:
        """Offline benchmark of 10 acceptance scenarios (no LLM, no network)."""
        console.print("[dim]Running acceptance benchmark scenarios...[/dim]")
        results = _run_async(run_all_scenarios())

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        rate = (passed / total * 100.0) if total else 0.0

        t = Table(
            title="[bold #E58B58]Acceptance Benchmark Suite[/bold #E58B58]",
            border_style="#E58B58",
            header_style="bold cyan",
        )
        t.add_column("Scenario", style="bold white", width=26)
        t.add_column("Status", width=12)
        t.add_column("Verification Detail", style="dim")

        for r in results:
            badge = "[green]✔ PASS[/green]" if r.passed else "[red]✖ FAIL[/red]"
            t.add_row(r.name, badge, r.detail or "Passed all assertions")

        console.print(t)
        score_color = "green" if passed == total else "yellow" if passed > 0 else "red"
        console.print(
            f"  [bold {score_color}]● Result: {passed}/{total} scenarios passed ({rate:.0f}%)[/bold {score_color}]"
        )
        console.print()

    def _safety_demo(self) -> None:
        """Queue the async safety demo to run on the REPL's live event loop."""
        self.app.pending_async = "/safety-demo"
