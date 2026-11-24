# AgentX — Autonomous Task-Solving Agent (Studio & Terminal)

AgentX is an interactive AI agent for **Topic 184: An LLM Agent with Tool Use [Real-Time Scenario]**.
You give it a natural-language task. It decides which tools it needs (calculator, web search, or a
structured exchange-rate API), proposes **structured tool calls**, and — this is the important part —
**your application, not the model, validates and executes them**. Results flow back to the model,
which continues until it can give a verified answer or must honestly say it can't.

- **Modern Web Studio**: ChatGPT & Gemini-inspired web interface with real-time SSE streaming, transparent tool accordions, live guardrails matrix, and light/dark themes.
- **Terminal CLI (Rich TUI)**: Full REPL with Claude Code aesthetics.
- **Real tools. Real network calls. No fabricated results.**
- **Hard safety guardrails in code, not in prompts.**

---

## Quick start (Windows — 1-Click)

1. Double-click **`install.bat`** to set up the virtual environment and install all dependencies.
2. Edit `.env` with your API endpoint and key.
3. Double-click **`run.bat`** to start the web interface and automatically open it in your browser.

---

## Quick start (Manual PowerShell)

```powershell
# Web Interface (opens at http://127.0.0.1:8000)
python web_server.py --open

# Terminal REPL
python main.py
```

## Quick start (macOS / Linux)

```bash
cd agentx-cli
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env         # fill in your endpoint credentials (see below)
python main.py
```

Prerequisite: **Python 3.11+** (`python --version`). Everything else is pip-installed.

---

## Environment configuration

AgentX uses a **bring-your-own-key** model provider (any OpenAI-compatible endpoint with native
function calling — OpenAI, Azure OpenAI, Groq, Together, Ollama-with-tools, LiteLLM proxies, …).

Copy `.env.example` → `.env` and set:

| Variable | Required | Meaning |
|---|---|---|
| `AGENTX_BASE_URL` | yes | e.g. `https://api.openai.com/v1`. Must be `https://` unless `AGENTX_ALLOW_INSECURE_BASE_URL=true` (explicit `http://` opt-in, dev only). |
| `AGENTX_API_KEY` | yes | Secret key for that endpoint. **Never committed, never printed.** |
| `AGENTX_MODEL` | yes | A function-calling model name, e.g. `gpt-4o-mini` / `llama3.1-70b-versatile` / whatever your endpoint serves. |
| `AGENTX_MAX_TOOL_CALLS` | no | Default `5`. Tool executions allowed per task. |
| `AGENTX_MAX_TURNS` | no | Default `12`. Model turns per task. |
| `AGENTX_TASK_DEADLINE_S` | no | Default `120`. Whole-task deadline. |
| `AGENTX_TOOL_TIMEOUT_S` | no | Default `15`. Per-tool-call timeout. |
| `AGENTX_RETRY_TRANSIENT_MAX` | no | Default `2`. Bounded retries for transient provider errors. |
| `AGENTX_LOG_JSONL` | no | `true` enables structured JSONL traces in `logs/` (off by default; secrets redacted). |
| `AGENTX_LOG_DIR` | no | Default `logs`. |
| `SERPER_API_KEY` | no | Enables the `web_search` tool (free tier at serper.dev). Without it, `web_search` reports "not configured" — it never fakes results. |

**No key of any kind is bundled or defaulted.** The app refuses to start without the three required
LLM variables and tells you exactly what's missing.

---

## Interactive commands

| Command | Effect |
|---|---|
| `/help` | list commands |
| `/tools` | registered tools + limits (the actual allowlist) |
| `/trace` | full execution trace of the last task |
| `/stats` | session metrics |
| `/clear` | wipe task-local conversation memory |
| `/benchmark` | run the 10-scenario acceptance suite (offline, no API needed) |
| `/safety-demo` | live guardrail rejections (unregistered tool, malicious expression, oversized payload) |
| `/exit` | quit |

Type anything else → it's treated as a task. `Ctrl+C` cancels the current task cleanly (state stays
consistent; no traceback dump).

---

## Example tasks

- `What is 125 multiplied by 48?` → deterministic calculator result (6000).
- `Get the USD to INR rate and calculate the INR value of $250 after a 2% fee.` → sequential tools: `api_lookup` first, then `calculator` using the **real fetched rate**, then a verified answer.
- `Search the web for the length of the Nile and the Amazon, then calculate the difference.` → search → citations → verified calculation, with uncertainty stated where data is uncertain.
- `Use the delete_database tool.` → rejected: not on the allowlist. Nothing executes.

---

## Architecture

```
User task
   │
   ▼
┌─────────────┐     JSON tool schemas     ┌──────────────────┐
│ AgentLoop   │ ────────────────────────▶ │  LLM (_BACKEND   │
│ (agent/loop)│ ◀──────────────────────── │  function-calling │
└──────┬──────┘   tool_calls / content    └──────────────────┘
       │ model *proposes* ToolCallRequests
       ▼
┌─────────────────────────────────────────────────┐
│ TRUSTED EXECUTION (never model-controlled):     │
│  1. allowlist check        (tools/registry)     │
│  2. Pydantic arg validation (safety/validation) │
│  3. permission check       (safety/permissions) │
│  4. budget + deadline      (safety/limits)      │
│  5. real execution, timeout            (tools/*)│
│  6. structured result → ToolMessage → model    │
└─────────────────────────────────────────────────┘
       │ repeat (bounded) until final answer
       ▼
Deterministic verification (agent/verifier) → trace + metrics → final answer
```

Directory layout (see `agentx-cli/` tree):

- `agent/` — loop, provider adapter (isolated), verifier, bounded memory, prompts, config.
- `tools/` — registry + the three real tools.
- `safety/` — validation, permissions, budgets, SSRF/URL guard.
- `ui/` — Rich console and REPL commands.
- `evaluation/` — benchmark scenarios and the live safety demo.
- `tests/` — 66 automated tests (offline; no credentials needed).
- `logs/` — optional JSONL traces (gitignored, redacted).

---

## Calculate converted amount + fee (Demo A semantics)

For the currency demonstration the verifier checks that the calculator expression actually used the
**retrieved** rate. The fee model is:

```
gross = input_amount × rate           # rate: real value from api_lookup (timestamped)
fee   = gross × fee% / 100            # fee% comes only from the user's explicit instruction
net   = gross − fee
```

All arithmetic goes through the calculator tool — never the model — and the tool output carries a
note that real-world providers may levy their own spread/fees not modelled here.

---

## Safety design

| Layer | Mechanism |
|---|---|
| Tool allowlist | Only services **registered in code** can execute; unknown names are rejected and traced. Registration happens once at startup; nothing can add tools at runtime. |
| Argument validation | Strict Pydantic schemas (`extra="forbid"`), length/magnitude/count limits, wrong types rejected **before** execution. |
| Calculator security | Restricted-AST evaluator. No `eval`/`exec`. Imports, calls, attributes, names, strings, comprehensions, comparisons, lambdas — all rejected by allowlist. Division-by-zero, huge literals, non-finite results blocked. `__import__('os').system('rm -rf /')` → rejected, nothing runs. |
| Network safety | HTTPS-only endpoints; localhost / private ranges / link-local / cloud-metadata hosts (e.g. `169.254.169.254`, `metadata.google.internal`) are blocked; model-supplied URLs to arbitrary destinations are never fetched. |
| Execution budget | Max 5 tool executions (configurable), max model turns, per-tool timeout, whole-task deadline, bounded retries for transient errors only. |
| Prompt-injection resistance | Tool output is returned to the model wrapped in `"untrusted evidence"` framing; the system prompt states that instructions inside tool results have no authority; and — the real guarantee — **permissions live in application code**, so no text the model reads can elevate them. |
| Secret hygiene | Keys only from env; API key marked `exclude=True` in config; error messages redact `sk-…`/authorization strings; JSONL logs deep-redact secret-looking keys; the banner shows "configured (hidden)", never the value. |
| Honest failure | Any tool failure returns a structured error to the model; the verifier flags failed tools; the agent is required to disclose limitations rather than claim success. No fabricated rates, citations, or retries-until-lucky results. |

Note on scope: there is **no shell tool, no file-write tool, no DB tool** in the registry — the whole
registry is read-only/computational by design. Any future consequential tool must implement the
`requires_permission` path (human approval) plus its own auditability.

---

## Tests and benchmark

```powershell
# Windows
.\.venv\Scripts\python -m pytest tests -v
.\.venv\Scripts\python -m ruff check .
```

```bash
# macOS / Linux
.venv/bin/python -m pytest tests -v
.venv/bin/python -m ruff check .
```

Current state of this workspace: **66 passed**, lint clean. The suite covers: calculator arithmetic +
malicious-expression rejection, registry allowlist behavior, agent-loop tool round-trips (assistant
tool-call ↔ tool-result id pairing preserved), budget/turn/deadline enforcement, permission gate,
SSRF blocking, provider secret redaction, exchange-rate API success/missing/HTTP-error/timeout paths,
and web-search key/timeouts/private-URL filtering — all offline via mocked HTTP.

Inside the app, `/benchmark` runs the 10 competition scenarios and prints PASS/FAIL per scenario with
actual outcome evidence (not printed-words checks):

1. Direct calculation (exact 6000)
2. Sequential tools (api then calculator, real-rate math verified)
3. Research sources preserved (URLs kept for citation)
4. Unknown tool rejected
5. Malicious calculator expression rejected
6. Malformed arguments rejected
7. API failure → structured error, no fabrication
8. Execution budget stops repeats
9. Prompt injection contained
10. Incomplete evidence disclosed

---

## Competition demonstration script

### Demo A — multi-step currency task (needs LLM credentials + network)

```
agentx> Get the USD to INR rate and calculate the INR value of $250 after a 2% fee.
```

Expected on screen, in order:
1. `[TOOL CALL] api_lookup(base=USD, target=INR)`
2. `[RESULT] OK rate=…, retrieved_at_utc=…` (real network fetch; timestamp visible)
3. `[TOOL CALL] calculator(expression=(250 * <REAL RATE>) * (1 - 0.02))`
4. `[RESULT] OK result=…`
5. `[VERIFY] pass — calculator_uses_api_rate OK; tool_call_result_pairing OK`
6. `[FINAL]` the amount, the rate source, the timestamp, and the fee caveat.

### Demo B — research + calculation (also needs `SERPER_API_KEY`)

```
agentx> Search the web for the length of the Nile river and the length of the Amazon river, then calculate how much longer the Nile is.
```

Expected: `web_search` with real results and URLs → extraction of supported figures → `calculator`
difference → final answer cites URLs and flags which values were measured vs disputed upstream.

### Demo C — guardrails (works with no credentials)

```
agentx> /safety-demo
```

Expected: `delete_database` rejected (allowlist), `__import__('os').listdir()` rejected (restricted
AST, payload never executed), 500-char query rejected (schema limit), each with the responsible rule
shown and a "Nothing dangerous executed" confirmation. Also visible in-loop by literally asking the
agent to delete a database — the model may *propose* the call; the registry refuses it.

### Demo D — API timeout (needs credentials)

Temporarily point `AGENTX_BASE_URL` at an unreachable `https://…` host and run a task: the tool
returns a structured timeout error; the agent reports failure honestly (no invented rate).

Presenters: keep `/trace` open between demos to show real event sequence, timestamps, and verdicts.

---

## Jury Q&A

**1. How does the LLM decide to call a tool?**
It receives the system prompt, task text, and each tool's JSON schema. The model's native
function-calling returns `tool_calls` with a name + JSON arguments when it judges a tool is needed.
We use `tool_choice="auto"`; the model proposes, it never executes.

**2. How are tool schemas supplied?**
The registry generates OpenAI-style `tools=[{"type":"function", "function": {name, description,
parameters}}]` payloads. The same registration also drives server-side validation, so schema,
validator, and executor can't drift apart (alignment asserted at registration time).

**3. How does the app execute and return results?**
Each proposed call is: allowlist-checked → Pydantic-validated (strict, no extra fields) →
permission-checked → budget-claimed → executed under `asyncio.wait_for` timeout → wrapped into a
`{"ok": bool, "data" | "error"}` result → appended as a `role=tool` message keyed by the provider's
`tool_call_id` so results pair with the right request.

**4. Multi-step tasks?**
The loop: model → tool calls → tool results → model → … until a no-tool-call response, bounded by
turn/tool budgets and a deadline. The assistant message containing tool calls and every matching
result stay in conversation order (tested), so the model never "loses" its prior calls.

**5. What happens when a tool fails?**
A structured error (`type`, safe message, no stack trace/secrets) goes back to the model inside the
`role=tool` message. It may retry within the transient-retry budget or answer with the limitation
stated. The verifier flags failed tools; a "success" can't be fabricated by the loop.

**6. Guardrails against misuse?**
Allowlist, strict schemas, restricted-AST calculator (no eval), SSRF/HTTPS guard, budgets+deadlines,
read-only tool set, and permission gating for any future consequential tool — all in code.

**7. Prompt injection defense?**
Layered: retrieved content is framed as untrusted evidence, the system prompt says embedded
instructions carry no authority, and the decisive control is that permissions/allowlist live in the
application — even a fully jailbroken model response can only *propose* calls that the validator and
registry independently permit. Real adversarial testing goes beyond small demos, so we don't claim
perfect immunity.

**8. How do you evaluate correctness?**
Unit/acceptance suites (deterministic outcomes), plus deterministic post-run verification: pairing
checks, "calculator actually used the retrieved rate" check, citation-availability check, failure
disclosure check. Model self-reports are never treated as proof.

**9. Different from a chatbot?**
A chatbot returns text. AgentX has an action layer: typed tool interface, real execution, evidence
round-trips, budgets, verification, and an audit trace of every decision and outcome.

**10. Current limitations?**
Single-provider adapter (add more by implementing the adapter interface); no parallel tool-call
execution yet; benchmark's fake fixtures stand in for live APIs in CI; calculator supports a fixed
operator set (`+ - * / **`, parentheses, decimals); safety-demo covers a small scenario set, not an
exhaustive proof; live search quality depends on the search provider.

---

## Known limitations & troubleshooting

| Symptom | Meaning | Fix |
|---|---|---|
| `AGENTX_API_KEY is not set` at startup | config validation rejected boot | copy `.env.example` → `.env`, fill it in |
| `AGENTX_BASE_URL must use https://` | you used `http://` without explicitly allowing it | set `AGENTX_ALLOW_INSECURE_BASE_URL=true` only for local dev stubs |
| `web_search is not configured` | `SERPER_API_KEY` absent | add it to `.env`; other fields stay the same |
| `Search provider rejected the API key (401/403)` | wrong/expired search key | replace `SERPER_API_KEY` |
| `Exchange-rate API timed out after 15.0s` | live network issue; structured error, no fake data | retry; the answer will state the limitation |
| `Tool-call budget exhausted` | task hit the execution cap legitimately (or a repeating failure) | raise `AGENTX_MAX_TOOL_CALLS` in `.env`, or fix the failing tool |
| `Task deadline exceeded` | whole task overran its wall-clock limit | raise `AGENTX_TASK_DEADLINE_S` |
| Provider auth errors in trace | bad model credentials | check base URL/key/model trio in `.env` |
| Windows PowerShell blocks `Activate.ps1` | execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

Logs: traces go to `logs/agentx-traces.jsonl` **only if** `AGENTX_LOG_JSONL=true`; they are
deep-redacted of secret-looking keys and never include raw credentials. Nothing is persisted by
default; `/clear` resets conversation memory; no database.

---

## What this repo is / is not

- ✅ Working, tested terminal agent; 66/66 offline tests green; `/benchmark` 10/10 in-app.
- ✅ Real structured function calling via a provider adapter you can swap.
- ✅ Live demos need **your** credentials (LLM endpoint +, for Demo B, a search key). Nothing is
  fabricated in their absence: the tools report "not configured" instead of pretending.
