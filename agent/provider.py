"""Provider adapter for OpenAI-compatible structured tool calling.

Isolates provider-specific SDK usage behind a narrow interface so an alternative
compatible provider can be added later without touching the agent loop. Uses the
real `openai` SDK function-calling path - no fake/manual JSON printing.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from agent.exceptions import ProviderError


def _is_tool_not_found_error(exc: Exception) -> bool:
    """Return True when the provider signals it doesn't support function calling.

    NVIDIA NIM and some other providers return HTTP 404 with a body like:
      {"status": 404, "title": "Not Found",
       "detail": "Function '<uuid>': Not found for account '<id>'"}
    We detect this by checking for status_code 404 and the word 'Function'
    in the response body, which is distinct from a normal 404 (e.g. wrong URL).
    """
    # openai SDK wraps HTTP errors as openai.NotFoundError (status_code=404)
    status = getattr(exc, "status_code", None)
    if status != 404:
        return False
    body = str(getattr(exc, "body", "") or "") + str(exc)
    return "Function" in body or "function" in body


class ProviderAdapter:
    """Wraps an OpenAI-compatible client (real chat.completions tool calling).

    When the provider returns a 404 indicating that function/tool calling is not
    supported for the configured model, the adapter automatically retries the
    request without tools so the model can answer directly.
    """

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 60.0):
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)
        self.model = model
        # Set to False the first time a tool-calling 404 is detected so we stop
        # sending tools on every subsequent request for this session.
        self._tools_supported: bool = True

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Send one chat request. Returns a normalised response dict.

        Normalised keys: content (str | None), tool_calls (list of ToolCallRequest-eligible dicts:
        {"id": str, "name": str, "arguments": dict}), usage (dict), finish_reason (str|None).
        Raises ProviderError on failure with a short, safe description (no secrets).

        If the provider does not support function calling (HTTP 404 "Function not found"),
        the request is automatically retried without tools and a plain text answer is returned.
        """
        # If we already know tools aren't supported, skip sending them.
        effective_tools = tools if self._tools_supported else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }
        if effective_tools:
            kwargs["tools"] = effective_tools
            kwargs["tool_choice"] = tool_choice
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            # Detect provider-side "function calling not supported" (404 Function not found)
            # and transparently fall back to a plain no-tools request.
            if tools and _is_tool_not_found_error(exc):
                self._tools_supported = False
                fallback_kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 2048,
                }
                try:
                    resp = self._client.chat.completions.create(**fallback_kwargs)
                except Exception as fallback_exc:
                    raise ProviderError(self._describe(fallback_exc)) from None
            else:
                raise ProviderError(self._describe(exc)) from None

        if not getattr(resp, "choices", None):
            raise ProviderError("Provider returned no choices (empty response).")

        choice = resp.choices[0]
        msg = choice.message
        content = getattr(msg, "content", None)
        raw_calls = getattr(msg, "tool_calls", None) or []

        tool_calls = []
        for tc in raw_calls:
            fn = getattr(tc, "function", None)
            if fn is None or not getattr(tc, "id", None):
                continue
            args_raw = getattr(fn, "arguments", "") or "{}"
            try:
                import json

                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
            except json.JSONDecodeError:
                # Keep raw; the safety layer will reject invalid args with a structured error.
                args = {"__invalid_json__": args_raw[:500]}
            tool_calls.append({"id": tc.id, "name": fn.name, "arguments": args})

        usage = {}
        if getattr(resp, "usage", None):
            u = resp.usage
            usage = {
                "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                "total_tokens": getattr(u, "total_tokens", 0) or 0,
            }
        return {
            "content": content,
            "tool_calls": tool_calls,
            "usage": usage,
            "finish_reason": getattr(choice, "finish_reason", None),
        }

    @staticmethod
    def _describe(exc: Exception) -> str:
        """Short, secret-free provider error description."""
        text = str(exc)
        for token in ("api_key", "sk-", "bearer ", "authorization"):
            low = text.lower()
            if token in low:
                idx = low.find(token)
                text = text[: max(0, idx - 20)] + "...[redacted]"
                break
        if len(text) > 300:
            text = text[:300] + "..."
        name = type(exc).__name__
        return f"{name}: {text}"
