"""AgentX CLI entry point. Terminal-only interactive REPL with Claude Code aesthetics."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from rich.panel import Panel
from rich.text import Text

from agent.config import load_config
from agent.exceptions import AgentXError, ConfigError
from agent.loop import AgentLoop
from agent.provider import ProviderAdapter
from tools.api_lookup import ApiLookupTool
from tools.calculator import CalculatorTool
from tools.registry import make_registry
from tools.web_search import WebSearchTool
from ui.commands import CommandHandlers
from ui.console import (  # noqa: F401
    _COLORS,
    _LABELS,
    console,
    render_final_answer,
    render_run_result,
    startup_panel,
    task_header,
    tool_table,
    trace_line,
)
from ui.prompt import ClaudePromptSession

MAX_PROMPT_CHARS = 8000

try:
    from agent.metrics import save_trace_jsonl

    _HAS_LOGGING = True
except ImportError:  # pragma: no cover
    _HAS_LOGGING = False


class AgentXApp:
    """Wires config, provider, registry, loop, metrics, and CLI together."""

    def __init__(self) -> None:
        self.config = load_config()
        self.provider = ProviderAdapter(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            model=self.config.model,
            timeout_s=60.0,
        )
        self.registry = make_registry(
            calculator=CalculatorTool(),
            api_lookup=ApiLookupTool(timeout_s=self.config.tool_timeout_s),
            web_search=WebSearchTool(
                api_key=self.config.serper_key,
                timeout_s=self.config.search_timeout_s,
                max_results=self.config.serper_max_results,
                allow_free_search=True,
            ),
        )
        self.loop = AgentLoop(
            provider=self.provider,
            registry=self.registry,
            max_tool_calls=self.config.max_tool_calls,
            max_turns=self.config.max_turns,
            deadline_s=self.config.task_deadline_s,
            retry_transient_max=self.config.retry_transient_max,
        )
        self.metrics: dict[str, float] = {
            "tasks_attempted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tool_calls_executed": 0,
            "tool_calls_rejected": 0,
            "tool_errors": 0,
            "calculator_correct": 0,
            "calculator_total": 0,
            "total_task_seconds": 0.0,
        }
        self.history: list[dict[str, Any]] = []
        self.last_result = None
        self.pending_async: str | None = None  # /safety-demo runs on the live loop

    def record(self, res: Any) -> None:
        m = self.metrics
        m["tasks_attempted"] += 1
        if res.status == "completed":
            m["tasks_completed"] += 1
        else:
            m["tasks_failed"] += 1
        m["tool_calls_executed"] += res.tool_calls_made
        m["tool_calls_rejected"] += res.tool_calls_rejected
        m["tool_errors"] += res.tool_errors
        m["total_task_seconds"] += res.duration_s


async def run_task(app: AgentXApp, task: str) -> None:
    task_header(task)

    def on_live_trace(ev: Any) -> None:
        trace_line(ev)

    res = await app.loop.run_task(task, on_event=on_live_trace)
    app.record(res)
    app.last_result = res
    app.history.append({"task": task, "result": res})

    if _HAS_LOGGING:
        save_trace_jsonl(res, app.config.log_dir, enabled=app.config.log_jsonl)

    if res.final_answer:
        render_final_answer(res.final_answer)
    render_run_result(res)


async def amain() -> int:
    try:
        app = AgentXApp()
    except ConfigError as exc:
        console.print(
            Panel(
                Text(str(exc), style="bold red"),
                title="[bold red]Configuration Problem[/bold red]",
                border_style="red",
            )
        )
        console.print("[dim]Copy .env.example to .env and fill in your endpoint credentials.[/dim]")
        return 2

    startup_panel(app.config.redacted(), [t.name for t in app.registry.list()])

    handlers = CommandHandlers(app)
    prompt_session = ClaudePromptSession(
        model_name=app.config.model,
        history_dir=app.config.log_dir,
    )

    while True:
        try:
            raw = await prompt_session.prompt_async()
        except KeyboardInterrupt:
            console.print("\n[dim yellow]Input cancelled. Type /exit to quit.[/dim yellow]\n")
            continue
        except EOFError:
            console.print("\n[dim]Goodbye.[/dim]\n")
            return 0

        raw = raw.strip()
        if not raw:
            continue
        if len(raw) > MAX_PROMPT_CHARS:
            console.print("[bold red]Prompt too long (limit 8000 chars).[/bold red]\n")
            continue

        if raw.startswith("/"):
            try:
                if not handlers.handle(raw):
                    return 0
                if app.pending_async == "/safety-demo":
                    app.pending_async = None
                    from evaluation.safety_demo import run_safety_demo

                    await run_safety_demo(app)
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Command cancelled.[/yellow]\n")
                continue
            except Exception as exc:
                console.print(f"[bold red]Command error:[/bold red] {type(exc).__name__}: {exc}\n")
            continue

        try:
            await run_task(app, raw)
        except KeyboardInterrupt:
            console.print(
                "\n[yellow]Task cancelled by user. State is consistent; type another task or /help.[/yellow]\n"
            )
            app.metrics["tasks_failed"] += 1
        except AgentXError as exc:
            console.print(f"[bold red]Task error:[/bold red] {exc}\n")


def main() -> None:
    if "--web" in sys.argv or "-w" in sys.argv:
        from web_server import main as web_main
        web_main()
        return

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        sys.exit(asyncio.run(amain()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
