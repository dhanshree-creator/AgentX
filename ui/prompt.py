"""Interactive terminal prompt powered by prompt_toolkit with Claude Code aesthetics."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.styles import Style

from ui.console import console

COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show available commands and keyboard shortcuts"),
    ("/tools", "Inspect registered tools, limits, and schemas"),
    ("/trace", "Detailed execution timeline of latest task"),
    ("/stats", "Session metrics (success rate, latency, tool calls)"),
    ("/model", "Active model details, endpoint, and safety limits"),
    ("/history", "List tasks executed in this session"),
    ("/clear", "Clear task-local conversation memory"),
    ("/benchmark", "Run offline acceptance benchmark suite"),
    ("/safety-demo", "Run live guardrail misuse tests"),
    ("/exit", "Exit the AgentX CLI"),
    ("/quit", "Exit the AgentX CLI"),
]


class SlashCommandCompleter(Completer):
    """Auto-completion for slash commands with rich descriptions."""

    def get_completions(
        self, document: Document, complete_event: Any
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        for cmd, desc in COMMANDS:
            if cmd.lower().startswith(text.lower()):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display=cmd,
                    display_meta=desc,
                )


_CLAUDE_STYLE = Style.from_dict(
    {
        "prompt-box": "#E58B58 bold",
        "prompt-agent": "#E58B58 bold",
        "prompt-model": "#8A99A6 italic",
        "prompt-arrow": "#E58B58 bold",
        "completion-menu.completion": "bg:#1E1E2E #CDD6F4",
        "completion-menu.completion.current": "bg:#45475A #FFFFFF bold",
        "completion-menu.meta": "bg:#181825 #A6ADC8",
        "auto-suggestion": "#6C7086 italic",
    }
)


class ClaudePromptSession:
    """Manages prompt_toolkit session with persistent history and autocomplete."""

    def __init__(self, model_name: str = "", history_dir: str = "logs") -> None:
        self.model_name = model_name
        self.history_dir = history_dir
        self._session: PromptSession[str] | None = None
        self._init_session()

    def _init_session(self) -> None:
        try:
            os.makedirs(self.history_dir, exist_ok=True)
            history_path = os.path.join(self.history_dir, ".agentx_history")
            history = FileHistory(history_path)
        except OSError:
            history = InMemoryHistory()

        try:
            self._session = PromptSession(
                history=history,
                style=_CLAUDE_STYLE,
                completer=SlashCommandCompleter(),
                auto_suggest=AutoSuggestFromHistory(),
                complete_while_typing=True,
            )
        except Exception:
            self._session = None

    def _get_prompt_tokens(self) -> list[tuple[str, str]]:
        short_model = self.model_name.split("/")[-1] if self.model_name else "glm-5.3"
        return [
            ("class:prompt-box", "╭─ "),
            ("class:prompt-agent", "AgentX"),
            ("class:prompt-model", f" ‹{short_model}›"),
            ("", "\n"),
            ("class:prompt-arrow", "╰─❯ "),
        ]

    async def prompt_async(self) -> str:
        """Asynchronously prompt user for input using prompt_toolkit."""
        if self._session is not None:
            try:
                return await self._session.prompt_async(
                    self._get_prompt_tokens(),
                    style=_CLAUDE_STYLE,
                    completer=SlashCommandCompleter(),
                    auto_suggest=AutoSuggestFromHistory(),
                )
            except (KeyboardInterrupt, EOFError):
                raise
            except Exception:
                pass

        return console.input("[bold #E58B58]agentx ❯ [/bold #E58B58]")

    def prompt(self) -> str:
        """Prompt user for input using prompt_toolkit or fallback to console.input."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            return console.input("[bold #E58B58]agentx ❯ [/bold #E58B58]")

        if self._session is not None:
            try:
                return self._session.prompt(
                    self._get_prompt_tokens(),
                    style=_CLAUDE_STYLE,
                    completer=SlashCommandCompleter(),
                    auto_suggest=AutoSuggestFromHistory(),
                )
            except (KeyboardInterrupt, EOFError):
                raise
            except Exception:
                pass

        return console.input("[bold #E58B58]agentx ❯ [/bold #E58B58]")
