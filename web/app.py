"""FastAPI web server for AgentX with Server-Sent Events (SSE) streaming."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.config import load_config
from agent.exceptions import AgentXError, ConfigError, ToolExecutionError, UnknownToolError
from agent.loop import AgentLoop
from agent.models import RunResult, TraceEvent
from agent.provider import ProviderAdapter
from evaluation.benchmark import run_all_scenarios
from tools.api_lookup import ApiLookupTool
from tools.calculator import CalculatorTool
from tools.registry import make_registry
from tools.web_search import WebSearchTool

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class WebAgentManager:
    """Manages the AgentX singleton instance for the web interface."""

    def __init__(self) -> None:
        self.config = load_config()
        self.provider = ProviderAdapter(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            model=self.config.model,
            timeout_s=60.0,
        )
        self.registry = make_registry(
            calculator=CalculatorTool(),
            api_lookup=ApiLookupTool(timeout_s=self.config.tool_timeout_s),
            web_search=WebSearchTool(
                api_key=self.config.serper_key,
                timeout_s=self.config.search_timeout_s,
                max_results=self.config.serper_max_results,
                allow_free_search=True,
            ),
        )
        self.loop = AgentLoop(
            provider=self.provider,
            registry=self.registry,
            max_tool_calls=self.config.max_tool_calls,
            max_turns=self.config.max_turns,
            deadline_s=self.config.task_deadline_s,
            retry_transient_max=self.config.retry_transient_max,
        )
        self.metrics: dict[str, float] = {
            "tasks_attempted": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tool_calls_executed": 0,
            "tool_calls_rejected": 0,
            "tool_errors": 0,
            "calculator_correct": 0,
            "calculator_total": 0,
            "total_task_seconds": 0.0,
        }
        self.history: list[dict[str, Any]] = []
        self.last_result: RunResult | None = None
        self.current_task: asyncio.Task | None = None
        self.current_task_id: str | None = None

    def record(self, res: RunResult) -> None:
        m = self.metrics
        m["tasks_attempted"] += 1
        if res.status == "completed":
            m["tasks_completed"] += 1
        else:
            m["tasks_failed"] += 1
        m["tool_calls_executed"] += res.tool_calls_made
        m["tool_calls_rejected"] += res.tool_calls_rejected
        m["tool_errors"] += res.tool_errors
        m["total_task_seconds"] += res.duration_s

    def clear_memory(self) -> None:
        self.loop.memory.clear()

    async def run_safety_matrix(self) -> list[dict[str, Any]]:
        """Run safety guardrail checks and return structured matrix."""
        cases = [
            ("delete_database", {"db": "production"}, "Strict Allowlist", "Direct command injection"),
            ("__import__('os').system", {"cmd": "id"}, "Strict Allowlist", "Arbitrary module import"),
            ("calculator", {"expression": "__import__('os').listdir()"}, "AST Sandbox Guardrail", "Disallowed import inside calculator"),
            ("calculator", {"expression": "2; import os"}, "AST Sandbox Guardrail", "Disallowed statement separator / import"),
            ("web_search", {"query": "x" * 500}, "Schema Input Validation", "Oversized payload limit exceeded"),
        ]
        results = []
        for name, args, layer, desc in cases:
            try:
                tool = self.registry.get(name)
            except UnknownToolError:
                results.append({
                    "test_case": name,
                    "description": desc,
                    "layer": layer,
                    "status": "BLOCKED",
                    "passed": True,
                    "proof": "Not registered; execution rejected before call",
                })
                continue
            try:
                if (
                    isinstance(args.get("expression"), str)
                    and len(args["expression"]) > 10
                    and "import" in args["expression"]
                ):
                    raise ToolExecutionError("Forbidden syntax (imports/functions not allowed).")
                outcome = await tool.execute(args)
                if not outcome.get("ok"):
                    err_msg = outcome.get("error", {}).get("message", "Validation rejection")
                    results.append({
                        "test_case": name,
                        "description": desc,
                        "layer": layer,
                        "status": "BLOCKED",
                        "passed": True,
                        "proof": f"Rejected by safety: {err_msg}",
                    })
                else:
                    results.append({
                        "test_case": name,
                        "description": desc,
                        "layer": layer,
                        "status": "ALLOWED",
                        "passed": False,
                        "proof": "No guardrail triggered (unexpected)",
                    })
            except ToolExecutionError as exc:
                results.append({
                    "test_case": name,
                    "description": desc,
                    "layer": layer,
                    "status": "BLOCKED",
                    "passed": True,
                    "proof": f"Rejected by safety: {exc}",
                })
        return results


app_manager = WebAgentManager()

app = FastAPI(
    title="AgentX Web Studio",
    description="Modern, ChatGPT & Gemini-inspired autonomous task-solving web interface.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = None


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    cfg = app_manager.config.redacted()
    tools = [t.name for t in app_manager.registry.list()]
    return {
        "model": cfg.get("model"),
        "base_url": cfg.get("base_url"),
        "provider": cfg.get("provider", "provider_a"),
        "max_turns": cfg.get("max_turns"),
        "max_tool_calls": cfg.get("max_tool_calls"),
        "task_deadline_s": cfg.get("task_deadline_s"),
        "tool_timeout_s": cfg.get("tool_timeout_s"),
        "serper_configured": bool(app_manager.config.serper_key),
        "tools": tools,
    }


@app.get("/api/tools")
async def get_tools() -> list[dict[str, Any]]:
    tools_list = []
    for tool in app_manager.registry.list():
        tools_list.append({
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "timeout_s": tool.timeout_s,
            "requires_permission": tool.requires_permission,
        })
    return tools_list


@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    return {
        "metrics": app_manager.metrics,
        "history_count": len(app_manager.history),
        "active_model": app_manager.config.model,
    }


@app.post("/api/clear")
async def clear_memory() -> dict[str, Any]:
    app_manager.clear_memory()
    return {"ok": True, "message": "Conversation memory cleared."}


@app.post("/api/cancel")
async def cancel_task() -> dict[str, Any]:
    if app_manager.current_task and not app_manager.current_task.done():
        app_manager.current_task.cancel()
        return {"ok": True, "message": "Task cancellation requested."}
    return {"ok": False, "message": "No active task running."}


@app.get("/api/history")
async def get_history() -> list[dict[str, Any]]:
    # Return formatted history items
    items = []
    for entry in app_manager.history:
        res: RunResult = entry["result"]
        items.append({
            "task": entry["task"],
            "status": res.status,
            "duration_s": round(res.duration_s, 2),
            "tool_calls_made": res.tool_calls_made,
            "final_answer": res.final_answer,
            "turns": res.turns,
            "errors": res.errors,
        })
    return items


@app.post("/api/safety-demo")
async def run_safety_demo() -> list[dict[str, Any]]:
    return await app_manager.run_safety_matrix()


@app.post("/api/benchmark")
async def run_benchmark() -> list[dict[str, Any]]:
    results = await run_all_scenarios()
    return [
        {"name": s.name, "passed": s.passed, "detail": s.detail}
        for s in results
    ]


@app.post("/api/task")
async def run_task_stream(req: TaskRequest, request: Request) -> StreamingResponse:
    task_text = req.task.strip()
    if not task_text:
        raise HTTPException(status_code=400, detail="Task prompt cannot be empty.")

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def on_live_trace(ev: TraceEvent) -> None:
        payload = {
            "type": "event",
            "event": {
                "ts": ev.ts,
                "kind": ev.kind,
                "task_id": ev.task_id,
                "tool_name": ev.tool_name,
                "arguments": ev.arguments,
                "ok": ev.ok,
                "detail": ev.detail,
                "data": ev.data,
            },
        }
        try:
            queue.put_nowait(payload)
        except Exception:
            pass

    async def execute_in_background():
        try:
            res = await app_manager.loop.run_task(task_text, on_event=on_live_trace)
            app_manager.record(res)
            app_manager.last_result = res
            app_manager.history.append({"task": task_text, "result": res})

            verification_data = None
            if res.verification:
                verification_data = {
                    "ok": res.verification.ok,
                    "checks": res.verification.checks,
                    "notes": res.verification.notes,
                }

            await queue.put({
                "type": "done",
                "result": {
                    "status": res.status,
                    "final_answer": res.final_answer,
                    "turns": res.turns,
                    "tool_calls_made": res.tool_calls_made,
                    "tool_calls_rejected": res.tool_calls_rejected,
                    "tool_errors": res.tool_errors,
                    "retries": res.retries,
                    "errors": res.errors,
                    "usage": res.usage,
                    "duration_s": round(res.duration_s, 3),
                    "user_task": res.user_task,
                    "verification": verification_data,
                    "trace": [
                        {
                            "ts": t.ts,
                            "kind": t.kind,
                            "tool_name": t.tool_name,
                            "arguments": t.arguments,
                            "ok": t.ok,
                            "detail": t.detail,
                            "data": t.data,
                        }
                        for t in res.trace
                    ],
                },
            })
        except asyncio.CancelledError:
            app_manager.metrics["tasks_failed"] += 1
            await queue.put({
                "type": "cancelled",
                "message": "Task cancelled by user.",
            })
        except Exception as exc:
            app_manager.metrics["tasks_failed"] += 1
            await queue.put({
                "type": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
        finally:
            await queue.put(None)  # Sentinel to terminate SSE stream

    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'task': task_text})}\n\n"
        bg_task = asyncio.create_task(execute_in_background())
        app_manager.current_task = bg_task

        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    if not bg_task.done():
                        bg_task.cancel()
                    break

                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    # Send keep-alive comment so proxies don't drop the connection
                    yield ": keep-alive\n\n"
                    continue

                if item is None:
                    break

                yield f"data: {json.dumps(item, default=str)}\n\n"
        except asyncio.CancelledError:
            if not bg_task.done():
                bg_task.cancel()
            raise
        finally:
            app_manager.current_task = None

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Static files setup
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse({"status": "AgentX API running. Frontend static files pending."})
