"""Strict configuration validation for AgentX.

Secrets come exclusively from environment variables (loaded from .env by
python-dotenv). Nothing here writes secrets to disk or prints them.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.exceptions import ConfigError


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


class AgentConfig(BaseModel):
    """Validated runtime configuration (api_key and serper_key are exclude=True)."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["provider_a"] = "provider_a"
    base_url: str
    api_key: str = Field(repr=False, exclude=True)
    model: str
    max_tool_calls: int = 5
    max_turns: int = 12
    tool_timeout_s: float = 15.0
    task_deadline_s: float = 120.0
    retry_transient_max: int = 2
    serper_key: str | None = Field(default=None, repr=False, exclude=True)
    serper_max_results: int = 5
    search_timeout_s: float = 10.0
    log_jsonl: bool = False
    log_dir: str = "logs"
    allow_insecure_base_url: bool = False

    @model_validator(mode="after")
    def _https_default(self):
        p = urlparse(self.base_url)
        if p.scheme not in ("https", "http") or not p.netloc:
            raise ValueError("AGENTX_BASE_URL must be a valid http(s) URL")
        if p.scheme == "http" and not self.allow_insecure_base_url:
            raise ValueError(
                "AGENTX_BASE_URL must use https:// unless AGENTX_ALLOW_INSECURE_BASE_URL=true "
                "(dev only, not recommended)."
            )
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        return self

    def redacted(self) -> dict[str, Any]:
        """Config dict safe for display/logging: no secrets of any kind."""
        d = self.model_dump()
        d.pop("api_key", None)
        if d.get("serper_key"):
            d["serper_key"] = "***set***"
        else:
            d["serper_key"] = None
        d.pop("allow_insecure_base_url", None)
        return d


def _env_int(env: Mapping[str, str], name: str, default: int, lo: int = 1, hi: int = 50) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None


def _env_float(
    env: Mapping[str, str], name: str, default: float, lo: float = 1.0, hi: float = 3600.0
) -> float:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        return max(lo, min(hi, float(raw)))
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None


def load_config(env: Mapping[str, str] | None = None) -> AgentConfig:
    """Build a validated AgentConfig from mapping (os.environ in production)."""
    load_dotenv()  # no-op when there is no .env file

    env = env if env is not None else os.environ
    provider = (env.get("AGENTX_PROVIDER") or "provider_a").strip().lower()
    if provider != "provider_a":
        raise ConfigError(
            "Unknown AGENTX_PROVIDER. Supported: provider_a - an OpenAI-compatible "
            "function-calling endpoint whose credentials you supply."
        )
    base_url = (env.get("AGENTX_BASE_URL") or "").strip()
    if not base_url:
        raise ConfigError(
            "AGENTX_BASE_URL is not set. Copy .env.example to .env and point "
            "AGENTX_BASE_URL at an OpenAI-compatible function-calling endpoint."
        )
    api_key = (env.get("AGENTX_API_KEY") or "").strip()
    if not api_key:
        raise ConfigError(
            "AGENTX_API_KEY is not set. Copy .env.example to .env and set the key "
            "for your function-calling endpoint. Never commit the real key."
        )
    model = (env.get("AGENTX_MODEL") or "").strip()
    if not model:
        raise ConfigError(
            "AGENTX_MODEL is not set. AgentX requires a named function-calling model."
        )
    allow_insecure_base_url = _truthy(env.get("AGENTX_ALLOW_INSECURE_BASE_URL"))

    return AgentConfig(
        provider="provider_a",
        base_url=base_url,
        api_key=api_key,
        model=model,
        max_tool_calls=_env_int(env, "AGENTX_MAX_TOOL_CALLS", 5, 1, 50),
        max_turns=_env_int(env, "AGENTX_MAX_TURNS", 12, 1, 50),
        tool_timeout_s=_env_float(env, "AGENTX_TOOL_TIMEOUT_S", 15.0, 1.0, 600.0),
        task_deadline_s=_env_float(env, "AGENTX_TASK_DEADLINE_S", 120.0, 5.0, 3600.0),
        retry_transient_max=_env_int(env, "AGENTX_RETRY_TRANSIENT_MAX", 2, 0, 5),
        serper_key=(env.get("SERPER_API_KEY") or "").strip() or None,
        serper_max_results=_env_int(env, "SERPER_MAX_RESULTS", 5, 1, 10),
        search_timeout_s=_env_float(env, "AGENTX_SEARCH_TIMEOUT_S", 10.0, 1.0, 60.0),
        log_jsonl=_truthy(env.get("AGENTX_LOG_JSONL")),
        log_dir=env.get("AGENTX_LOG_DIR", "logs"),
        allow_insecure_base_url=allow_insecure_base_url,
    )
