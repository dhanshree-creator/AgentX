"""Session metrics helpers and opt-in JSONL trace persistence.

Nothing is written unless AGENTX_LOG_JSONL is explicitly enabled; when enabled,
traces go to AGENTX_LOG_DIR (default logs/), never containing API keys.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

REDACT_KEYS = {"api_key", "authorization", "x-api-key", "serper_key", "token", "password", "secret"}


def redact(obj: Any) -> Any:
    """Deep-redact secret-looking keys from JSON-safe structures."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in REDACT_KEYS:
                out[k] = "***redacted***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def save_trace_jsonl(result, log_dir: str, enabled: bool = True) -> str | None:
    """Append one JSONL line with the run summary to logs/agentx-traces.jsonl."""
    if not enabled:
        return None
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "agentx-traces.jsonl")
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": result.status,
        "duration_s": round(result.duration_s, 2),
        "turns": result.turns,
        "tool_calls_made": result.tool_calls_made,
        "tool_calls_rejected": result.tool_calls_rejected,
        "tool_errors": result.tool_errors,
        "usage": redact(result.usage),
        "user_task": result.user_task[:200],
        "final_answer": (result.final_answer or "")[:400],
        "verification_ok": result.verification.ok if result.verification else None,
        "trace": [json.loads(ev.model_dump_json()) for ev in result.trace],
    }
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(redact(record), default=str) + "\n")
    except OSError:
        return None
    return path
