"""Bounded, task-local conversation memory.

No database. Nothing is persisted to disk. Secrets and tool payloads are never
stored beyond the lifetime of one task unless JSONL logging is explicitly enabled.
"""

from __future__ import annotations

from agent.models import AssistantMessage, ToolMessage, UserMessage

MAX_MESSAGES = 60  # hard cap so even long tasks cannot grow unbounded
MAX_USER_CHARS = 8000


class TaskMemory:
    """Keeps the current task's messages and trims the oldest beyond a cap."""

    def __init__(self, max_messages: int = MAX_MESSAGES, max_user_chars: int = MAX_USER_CHARS):
        self.max_messages = max_messages
        self.max_user_chars = max_user_chars
        self.user_task: str = ""
        self.messages: list[AssistantMessage | ToolMessage | UserMessage] = []

    def set_user_task(self, text: str) -> None:
        if len(text) > self.max_user_chars:
            text = text[: self.max_user_chars] + "...[truncated]"
        self.user_task = text
        self.messages.append(UserMessage(content=text))

    def append(self, msg: AssistantMessage | ToolMessage | UserMessage) -> None:
        self.messages.append(msg)
        while len(self.messages) > self.max_messages:
            # Keep the task anchor (user task) and drop the oldest non-anchor message.
            self.messages.pop(1)

    def clear(self) -> None:
        self.user_task = ""
        self.messages.clear()

    def to_provider_messages(self) -> list[AssistantMessage | ToolMessage | UserMessage]:
        return self.messages
