"""Lightweight planner: brief objective preview before the loop starts.

Not a second LLM: a heuristic summary used only for the [PLAN] trace line, so
there is no hidden chain-of-thought exposure and no extra cost.
"""

from __future__ import annotations

TaskText = str


def plan_preview(task: TaskText) -> str:
    """One-line objective: first sentence, trimmed deterministically."""
    text = " ".join(task.split())
    for sep in (". ", "? ", "! ", "\n"):
        if sep in text:
            text = text.split(sep)[0]
            break
    return text[:140]
