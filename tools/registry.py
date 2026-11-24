"""Central, explicit tool registry.

Only explicitly registered tools can execute. The model never picks an
unregistered tool or reaches internals via dynamic imports or attribute lookup.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from agent.exceptions import ToolExecutionError, UnknownToolError
from safety.validation import validate_arguments, validate_registry_alignment


def _is_bound_method(func) -> bool:
    return getattr(func, "__self__", None) is not None


class RegisteredTool:
    """One registered tool: name, schema, validated executor, limits, permission flag."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        args_model: type[BaseModel],
        executor_run,
        timeout_s: float = 10.0,
        requires_permission: bool = False,
        permission_label: str = "",
    ):
        if not (name.isidentifier() and name.islower() and 3 <= len(name) <= 40):
            raise ToolExecutionError(f"Illegal tool name: {name!r}")
        self.name = name
        self.description = description
        self.parameters = parameters
        self.args_model = args_model
        self._executor_run = executor_run
        self.timeout_s = timeout_s
        self.requires_permission = requires_permission
        self.permission_label = permission_label
        validate_registry_alignment(name, parameters, args_model)

    async def run_args(self, validated: dict[str, Any]) -> dict[str, Any]:
        """Run the tool entrypoint. Convention: free-function executors that need a
        pydantic model declare it as an annotation; everything else gets a dict."""
        import inspect

        sig = None
        try:
            sig = inspect.signature(self._executor_run)
        except (ValueError, TypeError):
            sig = None
        wants_model = False
        if sig is not None:
            params = list(sig.parameters.values())
            if (
                len(params) == 1
                and not _is_bound_method(self._executor_run)
                and params[0].annotation is not inspect.Parameter.empty
            ):
                if isinstance(params[0].annotation, type) and issubclass(
                    params[0].annotation, BaseModel
                ):
                    wants_model = True
        if wants_model:
            return await self._executor_run(self.args_model(**validated))
        return await self._executor_run(validated)

    async def execute(self, raw_args: Any) -> dict[str, Any]:
        """Validate then execute. Always returns a structured success/error dict."""
        try:
            args = validate_arguments(self.name, self.args_model, raw_args)
        except ToolExecutionError as exc:
            return {"ok": False, "error": {"type": "validation", "message": str(exc)}, "data": None}
        try:
            data = await asyncio.wait_for(self.run_args(args), timeout=self.timeout_s)
            return {"ok": True, "data": data, "error": None}
        except ToolExecutionError as exc:
            return {"ok": False, "error": {"type": "execution", "message": str(exc)}, "data": None}
        except TimeoutError:
            return {
                "ok": False,
                "error": {"type": "timeout", "message": f"Timed out after {self.timeout_s}s."},
                "data": None,
            }
        except Exception as exc:
            # Never leak stack traces or secrets back to the model.
            return {
                "ok": False,
                "error": {"type": "runtime", "message": f"{type(exc).__name__}: {exc}"},
                "data": None,
            }


class ToolRegistry:
    """Explicit allowlist of tools; only registration-time contents ever execute."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        args_model: type[BaseModel],
        executor_run,
        timeout_s: float = 10.0,
        requires_permission: bool = False,
        permission_label: str = "",
    ) -> RegisteredTool:
        if name.lower() in self._tools:
            raise ToolExecutionError(f"Tool {name!r} already registered")
        tool = RegisteredTool(
            name=name.lower(),
            description=description,
            parameters=parameters,
            args_model=args_model,
            executor_run=executor_run,
            timeout_s=timeout_s,
            requires_permission=requires_permission,
            permission_label=permission_label,
        )
        self._tools[name.lower()] = tool
        return tool

    def get(self, name: str) -> RegisteredTool:
        tool = self._tools.get((name or "").strip().lower())
        if tool is None:
            raise UnknownToolError(f"Tool {name!r} is not registered on this agent")
        return tool

    def is_registered(self, name: str) -> bool:
        return (name or "").strip().lower() in self._tools

    def list(self) -> list[RegisteredTool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]


def make_registry(calculator: Any, web_search: Any, api_lookup: Any) -> ToolRegistry:
    """Build the default read-only registry: calculator, web_search, api_lookup."""
    registry = ToolRegistry()
    registry.register(
        name=calculator.name,
        description=calculator.description,
        parameters=calculator.schema(),
        args_model=calculator.args_model(),
        executor_run=calculator.run,
        timeout_s=15.0,
    )
    registry.register(
        name=web_search.name,
        description=web_search.description,
        parameters=web_search.schema(),
        args_model=web_search.args_model(),
        executor_run=web_search.run,
        timeout_s=20.0,
    )
    registry.register(
        name=api_lookup.name,
        description=api_lookup.description,
        parameters=api_lookup.schema(),
        args_model=api_lookup.args_model(),
        executor_run=api_lookup.run,
        timeout_s=20.0,
    )
    return registry
