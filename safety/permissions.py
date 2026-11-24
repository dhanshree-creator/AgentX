"""Permission checks (allowlist-first). Consequential tools need approval."""

from __future__ import annotations

from typing import Any

from agent.exceptions import SafetyLimitError


def check_permission(tool: Any, approved: set[str]) -> None:
    """Raise SafetyLimitError if the tool requires permission not yet granted."""
    if getattr(tool, "requires_permission", False) and getattr(tool, "name", "") not in approved:
        label = getattr(tool, "permission_label", "") or "approval"
        raise SafetyLimitError(
            f"Tool {getattr(tool, 'name', '?')!r} requires human approval ({label}), "
            "which was not granted. Ask the user and do not retry automatically."
        )
