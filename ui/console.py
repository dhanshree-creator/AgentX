"""Rich terminal rendering with Claude Code aesthetics: start banner, task trace, panels, and Markdown."""

from __future__ import annotations

import platform
import sys
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent.models import RunResult, TraceEvent

console = Console(legacy_windows=False)

APP_NAME = "AgentX"
APP_VERSION = "1.0.0"

_COLORS = {
    "plan": "cyan",
    "llm_request": "magenta",
    "llm_response": "magenta",
    "tool_call": "yellow",
    "safety": "red",
    "result": "green",
    "verify": "blue",
    "final": "green",
    "error": "red",
}

_LABELS = {
    "plan": "PLAN",
    "llm_request": "LLM",
    "llm_response": "LLM",
    "tool_call": "TOOL CALL",
    "safety": "SAFETY",
    "result": "RESULT",
    "verify": "VERIFY",
    "final": "FINAL",
    "error": "ERROR",
}


def startup_panel(config_redacted: dict[str, Any], tools: list[str]) -> None:
    """Claude Code styled welcome banner with model, tools, and shortcuts."""
    model_name = str(config_redacted.get("model", "unknown"))
    provider = str(config_redacted.get("provider", "provider_a"))
    base_url = str(config_redacted.get("base_url", "unknown"))
    serper = config_redacted.get("serper_key")
    search_status = (
        "[bold green]Connected[/bold green] [dim](Serper.dev)[/dim]"
        if serper
        else "[bold green]Connected[/bold green] [dim](DuckDuckGo Free)[/dim]"
    )

    header_table = Table.grid(padding=(0, 2))
    header_table.add_row(
        f"[bold #E58B58]● {APP_NAME}[/bold #E58B58] [dim]v{APP_VERSION}[/dim]",
        "[bold #8A99A6]Autonomous Task-Solving Agent CLI[/bold #8A99A6]",
    )

    info_grid = Table.grid(padding=(0, 3))
    info_grid.add_row(
        "[bold cyan]Model[/bold cyan]",
        f"[bold white]{model_name}[/bold white] [dim]({provider})[/dim]",
        "[bold cyan]Web Search[/bold cyan]",
        search_status,
    )
    info_grid.add_row(
        "[bold cyan]Endpoint[/bold cyan]",
        f"[dim]{base_url}[/dim]",
        "[bold cyan]Guardrails[/bold cyan]",
        "[bold green]Active[/bold green] [dim](strict allowlist)[/dim]",
    )
    info_grid.add_row(
        "[bold cyan]Active Tools[/bold cyan]",
        f"[bright_white]{', '.join(tools)}[/bright_white]",
        "[bold cyan]Execution Limits[/bold cyan]",
        f"[dim]turns={config_redacted.get('max_turns')} · tools={config_redacted.get('max_tool_calls')} · deadline={config_redacted.get('task_deadline_s')}s[/dim]",
    )
    info_grid.add_row(
        "[bold cyan]Runtime[/bold cyan]",
        f"[dim]Python {sys.version.split()[0]} on {platform.system()}[/dim]",
        "",
        "",
    )

    content = Table.grid(padding=(1, 0))
    content.add_row(header_table)
    content.add_row(info_grid)

    console.print()
    console.print(
        Panel(
            content,
            border_style="#E58B58",
            padding=(1, 2),
            expand=False,
            title="[bold #E58B58] Claude-Style CLI [/bold #E58B58]",
            subtitle="[dim]Type a task or /help · Tab for completion[/dim]",
        )
    )
    console.print()


def task_header(task: str) -> None:
    """Claude Code styled task initiation card."""
    console.print()
    content = Text()
    content.append("❯ ", style="bold #E58B58")
    content.append(task.strip(), style="bold white")

    console.print(
        Panel(
            content,
            title="[bold #E58B58]Task[/bold #E58B58]",
            border_style="#E58B58",
            expand=False,
            padding=(0, 2),
        )
    )
    console.print()


def trace_line(ev: TraceEvent) -> None:
    """Renders a single trace event in Claude Code activity feed style."""
    if ev.kind == "plan":
        console.print(f"  [bold #E58B58]✦ Plan:[/bold #E58B58] [dim]{ev.detail}[/dim]")
    elif ev.kind == "llm_request":
        console.print("  [bold #C084FC]✦ Model:[/bold #C084FC] [dim]Thinking and generating action...[/dim]")
    elif ev.kind == "llm_response":
        detail = ev.detail
        if "tool_calls=" in detail:
            tc_count = detail.split("tool_calls=")[-1].strip()
            console.print(f"  [bold #C084FC]✦ Model:[/bold #C084FC] [dim]Proposing {tc_count} tool call(s)[/dim]")
        else:
            console.print("  [bold #C084FC]✦ Model:[/bold #C084FC] [dim]Generated response[/dim]")
    elif ev.kind == "tool_call":
        tool_icon = _tool_icon(ev.tool_name or "")
        args_str = _short_args(ev.arguments)
        console.print(f"  [bold cyan]╭─ {tool_icon} Tool: {ev.tool_name}[/bold cyan]")
        if args_str:
            console.print(f"  [bold cyan]│[/bold cyan]  [dim]Arguments:[/dim] [bright_white]{args_str}[/bright_white]")
    elif ev.kind == "safety":
        if ev.ok:
            console.print(f"  [bold cyan]│[/bold cyan]  [bold green]🛡️ Guardrail:[/bold green] [green]Approved[/green] [dim]({ev.detail})[/dim]")
        else:
            console.print(f"  [bold cyan]│[/bold cyan]  [bold red]🛡️ Guardrail:[/bold red] [bold red]REJECTED[/bold red] - [red]{ev.detail}[/red]")
    elif ev.kind == "result":
        if ev.ok:
            console.print(f"  [bold cyan]╰─ ➔[/bold cyan] [bold green]✔ Result:[/bold green] [bright_white]{ev.detail}[/bright_white]")
            if ev.tool_name == "web_search" and isinstance(ev.data, dict):
                results = ev.data.get("results") or []
                for idx, item in enumerate(results, 1):
                    title = item.get("title", "Untitled").strip()
                    url = item.get("url", "").strip()
                    snippet = (item.get("snippet") or "").strip()
                    if len(snippet) > 160:
                        snippet = snippet[:157] + "..."
                    console.print(f"     [bold #E58B58]{idx}.[/bold #E58B58] [bold white]{title}[/bold white]")
                    if snippet:
                        console.print(f"        [dim]{snippet}[/dim]")
                    if url:
                        console.print(f"        [dim underline #38BDF8]{url}[/dim underline #38BDF8]")
        else:
            console.print(f"  [bold cyan]╰─ ➔[/bold cyan] [bold red]✖ Failed:[/bold red] [red]{ev.detail}[/red]")
        console.print()
    elif ev.kind == "verify":
        icon = "[bold green]✔[/bold green]" if ev.ok else "[bold yellow]⚠[/bold yellow]"
        verdict = "[green]Passed[/green]" if ev.ok else "[yellow]Issues found[/yellow]"
        console.print(f"  [bold #38BDF8]◈ Verification:[/bold #38BDF8] {icon} {verdict} [dim]{ev.detail}[/dim]")
        console.print()
    elif ev.kind == "error":
        console.print(f"  [bold red]✖ Error:[/bold red] [red]{ev.detail}[/red]")
        console.print()
    elif ev.kind == "final":
        pass  # Rendered cleanly in render_final_answer


def render_final_answer(answer: str) -> None:
    """Render assistant final response in a rich Markdown card."""
    if not answer.strip():
        return

    md = Markdown(answer.strip(), code_theme="monokai")
    console.print(
        Panel(
            md,
            title=f"[bold #E58B58] {APP_NAME} [/bold #E58B58]",
            border_style="#E58B58",
            expand=False,
            padding=(1, 2),
        )
    )
    console.print()


def render_run_result(res: RunResult) -> None:
    """Claude Code styled summary pill for task completion."""
    status_color = "green" if res.status == "completed" else "red" if res.status == "failed" else "yellow"
    status_badge = f"[bold {status_color}]● {res.status.upper()}[/bold {status_color}]"

    tokens = res.usage.get("total_tokens", 0) if res.usage else 0
    token_str = f"  [dim]•[/dim]  [bold cyan]{tokens:,}[/bold cyan] [dim]tokens[/dim]" if tokens else ""

    summary_text = (
        f"{status_badge}  [dim]•[/dim]  "
        f"[bold white]{res.duration_s:.1f}s[/bold white] [dim]elapsed[/dim]  [dim]•[/dim]  "
        f"[bold white]{res.turns}[/bold white] [dim]turn(s)[/dim]  [dim]•[/dim]  "
        f"[bold white]{res.tool_calls_made}[/bold white] [dim]tool call(s)[/dim]"
        f"{token_str}"
    )

    console.print(
        Panel(
            Text.from_markup(summary_text),
            border_style="dim",
            expand=False,
            padding=(0, 2),
        )
    )

    if res.verification and res.verification.checks:
        v = res.verification
        v_title = "[bold green]✔ All verification checks passed[/bold green]" if v.ok else "[bold yellow]⚠ Verification noticed discrepancies[/bold yellow]"
        v_table = Table.grid(padding=(0, 2))
        v_table.add_row(v_title)
        for c in v.checks:
            mark = "[green]✔[/green]" if c.get("ok") else "[red]✖[/red]"
            v_table.add_row(f"  {mark} [dim]{c.get('check')}[/dim]")
        if v.notes:
            v_table.add_row(f"  [dim italic]{v.notes}[/dim italic]")
        console.print(Panel(v_table, border_style="dim", expand=False, padding=(0, 2)))

    console.print()


def tool_table(registry_list: list[Any]) -> None:
    """Claude Code styled tool inspection table."""
    t = Table(
        title="[bold #E58B58]Registered Tools (Strict Allowlist)[/bold #E58B58]",
        border_style="#E58B58",
        header_style="bold cyan",
        show_lines=True,
    )
    t.add_column("Tool", style="bold white", width=18)
    t.add_column("Timeout", style="cyan", justify="right", width=10)
    t.add_column("Security", style="green", width=14)
    t.add_column("Description", style="dim", ratio=1)

    for tool in registry_list:
        icon = _tool_icon(tool.name)
        t.add_row(
            f"{icon} {tool.name}",
            f"{tool.timeout_s:.0f}s",
            "[green]✔ Allowlisted[/green]",
            tool.description.strip(),
        )
    console.print(t)
    console.print()


def render_stats(metrics: dict[str, Any]) -> None:
    """Claude Code styled analytics dashboard."""
    attempted = metrics.get("tasks_attempted", 0)
    completed = metrics.get("tasks_completed", 0)
    failed = metrics.get("tasks_failed", 0)
    success_rate = (completed / attempted * 100.0) if attempted else 0.0

    meter_width = 16
    filled = int(meter_width * (success_rate / 100.0))
    meter = f"[green]{'█' * filled}[/green][dim]{'░' * (meter_width - filled)}[/dim]"

    t = Table(
        title="[bold #E58B58]Session Performance Dashboard[/bold #E58B58]",
        border_style="#E58B58",
        header_style="bold cyan",
    )
    t.add_column("Metric", style="bold white", width=24)
    t.add_column("Value", style="bright_white", width=22)
    t.add_column("Details", style="dim")

    t.add_row("Tasks Attempted", str(attempted), "Total user requests")
    t.add_row("Tasks Completed", f"[green]{completed}[/green]", "Finished successfully")
    t.add_row("Tasks Failed", f"[red]{failed}[/red]", "Errors or budget limits")
    t.add_row("Success Rate", f"{success_rate:.1f}%  {meter}", "Task completion ratio")
    t.add_row(
        "Tool Calls Executed",
        str(metrics.get("tool_calls_executed", 0)),
        "Successful tool calls",
    )
    t.add_row(
        "Tool Calls Blocked",
        f"[yellow]{metrics.get('tool_calls_rejected', 0)}[/yellow]",
        "Guardrail interventions",
    )
    t.add_row("Tool Failures", f"[red]{metrics.get('tool_errors', 0)}[/red]", "Tool execution exceptions")

    calc_total = metrics.get("calculator_total", 0)
    calc_correct = metrics.get("calculator_correct", 0)
    calc_str = f"{calc_correct}/{calc_total}" if calc_total else "n/a"
    t.add_row("Calculator Precision", calc_str, "Deterministic math verification")

    total_secs = metrics.get("total_task_seconds", 0.0)
    avg_secs = (total_secs / attempted) if attempted else 0.0
    t.add_row("Average Duration", f"{avg_secs:.1f}s", "Mean response latency")
    t.add_row("Total Session Time", f"{total_secs:.1f}s", "Cumulative execution time")

    console.print(t)
    console.print()


def render_history(history: list[dict[str, Any]]) -> None:
    """Renders table of tasks run in current session."""
    if not history:
        console.print("[dim]No tasks have been executed in this session yet.[/dim]")
        console.print()
        return

    t = Table(
        title="[bold #E58B58]Session Task History[/bold #E58B58]",
        border_style="#E58B58",
        header_style="bold cyan",
    )
    t.add_column("#", justify="right", style="dim", width=4)
    t.add_column("Task", style="bold white", ratio=1)
    t.add_column("Status", width=12)
    t.add_column("Duration", justify="right", width=10)
    t.add_column("Tools", justify="right", width=8)

    for i, item in enumerate(history, 1):
        task_text = item.get("task", "")
        if len(task_text) > 60:
            task_text = task_text[:57] + "..."
        res: RunResult = item.get("result")
        status_badge = "[green]Completed[/green]" if res.status == "completed" else f"[red]{res.status}[/red]"
        t.add_row(
            str(i),
            task_text,
            status_badge,
            f"{res.duration_s:.1f}s",
            str(res.tool_calls_made),
        )

    console.print(t)
    console.print()


def render_model_info(config_redacted: dict[str, Any]) -> None:
    """Claude Code styled model inspection card."""
    t = Table.grid(padding=(0, 2))
    t.add_row("[bold cyan]Model:[/bold cyan]", f"[bold white]{config_redacted.get('model')}[/bold white]")
    t.add_row("[bold cyan]Provider:[/bold cyan]", str(config_redacted.get("provider")))
    t.add_row("[bold cyan]Base URL:[/bold cyan]", str(config_redacted.get("base_url")))
    t.add_row("[bold cyan]Max Turns:[/bold cyan]", str(config_redacted.get("max_turns")))
    t.add_row("[bold cyan]Max Tool Calls:[/bold cyan]", str(config_redacted.get("max_tool_calls")))
    t.add_row("[bold cyan]Tool Timeout:[/bold cyan]", f"{config_redacted.get('tool_timeout_s')}s")
    t.add_row("[bold cyan]Task Deadline:[/bold cyan]", f"{config_redacted.get('task_deadline_s')}s")
    t.add_row("[bold cyan]Max Retries:[/bold cyan]", str(config_redacted.get("retry_transient_max")))
    t.add_row(
        "[bold cyan]Web Search Key:[/bold cyan]",
        "[green]Configured[/green]" if config_redacted.get("serper_key") else "[dim]Not set[/dim]",
    )

    console.print(
        Panel(
            t,
            title="[bold #E58B58]Model & Environment Configuration[/bold #E58B58]",
            border_style="#E58B58",
            expand=False,
            padding=(1, 2),
        )
    )
    console.print()


def safety_violation(message: str) -> None:
    """Display safety violation guardrail warning."""
    console.print(f"[bold red]🛡️ [SAFETY][/bold red] [red]{message}[/red]")


def _tool_icon(name: str) -> str:
    if "calc" in name:
        return "⚡"
    if "search" in name:
        return "🌐"
    if "api" in name or "lookup" in name:
        return "💱"
    return "🔧"


def _short_args(args: dict[str, Any] | None) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 80:
            s = s[:77] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)[:200]
