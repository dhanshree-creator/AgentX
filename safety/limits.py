"""Execution-budget enforcement: max tool calls, max turns, task deadline."""

from __future__ import annotations

import time

from agent.exceptions import SafetyLimitError


class Budget:
    """Tracks execution budget for one agent task."""

    def __init__(self, max_tool_calls: int = 5, max_turns: int = 12, deadline_s: float = 120.0):
        self.max_tool_calls = max_tool_calls
        self.max_turns = max_turns
        self.deadline_s = deadline_s
        self.started = time.monotonic()
        self.tool_calls_executed = 0
        self.tool_calls_rejected = 0
        self.turns = 0

    def check_turn(self, next_turn_index: int) -> None:
        if next_turn_index + 1 > self.max_turns:
            raise SafetyLimitError(
                f"Model-turn budget exhausted ({self.max_turns} turns). Task stopped for safety."
            )

    def claim_tool_call(self) -> None:
        """Reserve a slot before executing a tool."""
        if self.tool_calls_executed + 1 > self.max_tool_calls:
            raise SafetyLimitError(
                f"Tool-call budget exhausted ({self.max_tool_calls} executions per task). "
                "Repeated identical failing calls cannot consume the whole budget."
            )
        self.tool_calls_executed += 1

    def remaining_tool_calls(self) -> int:
        return max(0, self.max_tool_calls - self.tool_calls_executed)

    def seconds_left(self) -> float:
        return max(0.0, self.deadline_s - (time.monotonic() - self.started))

    def check_deadline(self) -> None:
        if self.seconds_left() <= 0.0:
            raise SafetyLimitError(
                f"Task deadline exceeded ({self.deadline_s:.0f}s). Task stopped for safety."
            )

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started
