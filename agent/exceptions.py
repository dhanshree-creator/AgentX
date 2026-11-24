"""Orthogonal, well-named exceptions for AgentX."""

from __future__ import annotations


class AgentXError(Exception):
    """Base class for all AgentX errors."""


class ConfigError(AgentXError):
    """Invalid or missing configuration (bad / missing env vars)."""


class ToolExecutionError(AgentXError):
    """A tool ran but failed (bad args or runtime failure)."""


class UnknownToolError(AgentXError):
    """Tool name not in the registry allowlist."""


class SafetyLimitError(AgentXError):
    """Budget, deadline, permission, or policy limit exceeded."""


class ProviderError(AgentXError):
    """Errors from the LLM provider (auth, rate limit, malformed, network)."""


class TokenBudgetExceeded(AgentXError):
    """Retried model calls exhausted the token budget without a final answer."""
