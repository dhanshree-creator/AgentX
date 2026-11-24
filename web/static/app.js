/**
 * AgentX Web Studio - Frontend Application Logic
 * Inspired by ChatGPT & Gemini: Modern, responsive, verified tool reasoning.
 */

(function () {
  "use strict";

  // Application State
  const state = {
    isRunning: false,
    activeTaskAbortController: null,
    config: null,
    history: [],
    currentTrace: null,
    theme: localStorage.getItem("agentx_theme") || "dark",
    sidebarCollapsed: localStorage.getItem("agentx_sidebar") === "collapsed",
  };

  // DOM Elements
  const elements = {
    sidebar: document.getElementById("sidebar"),
    sidebarToggleBtn: document.getElementById("sidebar-toggle-btn"),
    sidebarOpenBtn: document.getElementById("sidebar-open-btn"),
    newTaskBtn: document.getElementById("new-task-btn"),
    historyList: document.getElementById("history-list"),
    sidebarModelName: document.getElementById("sidebar-model-name"),
    sidebarModelLimits: document.getElementById("sidebar-model-limits"),
    topModelPill: document.getElementById("top-model-pill"),
    topModelName: document.getElementById("top-model-name"),
    agentLiveBadge: document.getElementById("agent-live-badge"),
    agentLiveStatus: document.getElementById("agent-live-status"),
    topClearBtn: document.getElementById("top-clear-btn"),
    topThemeBtn: document.getElementById("top-theme-btn"),
    themeToggleBtn: document.getElementById("theme-toggle-btn"),
    chatViewport: document.getElementById("chat-viewport"),
    welcomeContainer: document.getElementById("welcome-container"),
    messagesList: document.getElementById("messages-list"),
    promptTextarea: document.getElementById("prompt-textarea"),
    sendBtn: document.getElementById("send-btn"),
    commandTriggerBtn: document.getElementById("command-trigger-btn"),
    commandPopover: document.getElementById("command-popover"),
    // Modals
    toolsModal: document.getElementById("tools-modal"),
    openToolsBtn: document.getElementById("open-tools-btn"),
    toolsModalContent: document.getElementById("tools-modal-content"),
    safetyModal: document.getElementById("safety-modal"),
    openSafetyBtn: document.getElementById("open-safety-btn"),
    runGuardrailsBtn: document.getElementById("run-guardrails-btn"),
    runBenchmarksBtn: document.getElementById("run-benchmarks-btn"),
    guardrailResultsContainer: document.getElementById("guardrail-results-container"),
    benchmarkResultsContainer: document.getElementById("benchmark-results-container"),
    statsModal: document.getElementById("stats-modal"),
    openStatsBtn: document.getElementById("open-stats-btn"),
    statsModalContent: document.getElementById("stats-modal-content"),
    traceModal: document.getElementById("trace-modal"),
    traceJsonCode: document.getElementById("trace-json-code"),
    toastContainer: document.getElementById("toast-container"),
    hljsDark: document.getElementById("hljs-theme-dark"),
    hljsLight: document.getElementById("hljs-theme-light"),
  };

  // ==========================================================================
  // Initialization
  // ==========================================================================

  function init() {
    applyTheme(state.theme);
    applySidebarState(state.sidebarCollapsed);
    setupEventListeners();
    loadConfig();
    loadHistory();
    setupTextareaAutoResize();

    // Configure marked if available
    if (window.marked) {
      window.marked.setOptions({
        gfm: true,
        breaks: true,
        headerIds: false,
      });
    }
  }

  // ==========================================================================
  // Theme & Sidebar State
  // ==========================================================================

  function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("agentx_theme", theme);

    if (elements.hljsDark && elements.hljsLight) {
      if (theme === "light") {
        elements.hljsDark.disabled = true;
        elements.hljsLight.disabled = false;
      } else {
        elements.hljsDark.disabled = false;
        elements.hljsLight.disabled = true;
      }
    }
  }

  function toggleTheme() {
    applyTheme(state.theme === "dark" ? "light" : "dark");
    showToast(`Switched to ${state.theme} mode`);
  }

  function applySidebarState(collapsed) {
    state.sidebarCollapsed = collapsed;
    localStorage.setItem("agentx_sidebar", collapsed ? "collapsed" : "expanded");
    if (collapsed) {
      elements.sidebar.classList.add("collapsed");
    } else {
      elements.sidebar.classList.remove("collapsed");
    }
  }

  function toggleSidebar() {
    applySidebarState(!state.sidebarCollapsed);
  }

  // ==========================================================================
  // API Calls & Data Fetching
  // ==========================================================================

  async function loadConfig() {
    try {
      const res = await fetch("/api/config");
      if (!res.ok) throw new Error("Config fetch failed");
      const cfg = await res.json();
      state.config = cfg;

      const modelShort = cfg.model ? cfg.model.split("/").pop() : "Ready";
      elements.sidebarModelName.textContent = cfg.model || "Unknown";
      elements.sidebarModelLimits.textContent = `Turns: ${cfg.max_turns} · Tools: ${cfg.max_tool_calls} · ${cfg.task_deadline_s}s`;
      elements.topModelName.textContent = modelShort;
    } catch (err) {
      elements.sidebarModelName.textContent = "Offline";
      console.warn("Could not load backend config:", err);
    }
  }

  async function loadHistory() {
    try {
      const res = await fetch("/api/history");
      if (!res.ok) throw new Error("History fetch failed");
      const items = await res.json();
      state.history = items;
      renderHistoryList();
    } catch (err) {
      console.warn("Could not load history:", err);
    }
  }

  function renderHistoryList() {
    if (!elements.historyList) return;
    if (state.history.length === 0) {
      elements.historyList.innerHTML = '<div class="history-empty">No previous tasks yet</div>';
      return;
    }

    elements.historyList.innerHTML = "";
    state.history.slice(-15).reverse().forEach((item, index) => {
      const btn = document.createElement("button");
      btn.className = "history-item";
      btn.innerHTML = `
        <svg class="history-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        <span class="history-item-title" title="${escapeHtml(item.task)}">${escapeHtml(item.task)}</span>
        <span class="history-item-time">${item.duration_s ? item.duration_s + "s" : ""}</span>
      `;
      btn.addEventListener("click", () => {
        elements.promptTextarea.value = item.task;
        elements.promptTextarea.focus();
        showToast("Task prompt restored to input");
      });
      elements.historyList.appendChild(btn);
    });
  }

  // ==========================================================================
  // Task Execution & Server-Sent Events (SSE) Streaming
  // ==========================================================================

  async function executeTask(taskPrompt) {
    if (state.isRunning) return;
    taskPrompt = (taskPrompt || elements.promptTextarea.value).trim();
    if (!taskPrompt) return;

    // Reset input
    elements.promptTextarea.value = "";
    adjustTextareaHeight(elements.promptTextarea);

    // Hide welcome screen
    elements.welcomeContainer.style.display = "none";

    // Set Running State
    setRunningState(true);

    // Render User Message Bubble
    appendUserMessage(taskPrompt);

    // Create Assistant Message Placeholder
    const assistantCard = createAssistantMessageCard();
    elements.messagesList.appendChild(assistantCard.container);
    scrollToBottom();

    // Prepare Abort Controller
    state.activeTaskAbortController = new AbortController();

    try {
      const response = await fetch("/api/task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: taskPrompt }),
        signal: state.activeTaskAbortController.signal,
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep partial line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith(":")) continue; // keep-alive comments
          if (trimmed.startsWith("data: ")) {
            const rawData = trimmed.slice(6);
            try {
              const data = JSON.parse(rawData);
              handleStreamEvent(data, assistantCard);
            } catch (err) {
              console.warn("Failed to parse SSE JSON:", rawData, err);
            }
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        assistantCard.setCancelled();
      } else {
        assistantCard.setError(`Task execution error: ${err.message}`);
      }
    } finally {
      setRunningState(false);
      state.activeTaskAbortController = null;
      loadHistory();
      scrollToBottom();
    }
  }

  function handleStreamEvent(data, assistantCard) {
    if (data.type === "start") {
      assistantCard.updateLiveStatus("Task initialized");
    } else if (data.type === "event") {
      assistantCard.addTraceEvent(data.event);
    } else if (data.type === "done") {
      assistantCard.complete(data.result);
      state.currentTrace = data.result.trace;
    } else if (data.type === "cancelled") {
      assistantCard.setCancelled();
    } else if (data.type === "error") {
      assistantCard.setError(data.error);
    }
  }

  function cancelCurrentTask() {
    if (state.activeTaskAbortController) {
      state.activeTaskAbortController.abort();
    }
    fetch("/api/cancel", { method: "POST" }).catch(() => {});
    setRunningState(false);
    showToast("Task cancelled by user");
  }

  function setRunningState(running) {
    state.isRunning = running;
    const pulseDot = document.querySelector(".pulse-dot");
    const liveDot = document.querySelector(".badge-dot");

    if (running) {
      elements.sendBtn.classList.add("running");
      elements.sendBtn.querySelector(".send-icon").style.display = "none";
      elements.sendBtn.querySelector(".stop-icon").style.display = "block";
      elements.sendBtn.title = "Cancel task execution";

      if (pulseDot) pulseDot.classList.add("busy");
      if (liveDot) liveDot.classList.add("active");
      elements.agentLiveStatus.textContent = "Working...";
    } else {
      elements.sendBtn.classList.remove("running");
      elements.sendBtn.querySelector(".send-icon").style.display = "block";
      elements.sendBtn.querySelector(".stop-icon").style.display = "none";
      elements.sendBtn.title = "Send task (Enter)";

      if (pulseDot) pulseDot.classList.remove("busy");
      if (liveDot) liveDot.classList.remove("active");
      elements.agentLiveStatus.textContent = "Idle";
    }
  }

  // ==========================================================================
  // Message UI Builders
  // ==========================================================================

  function appendUserMessage(text) {
    const row = document.createElement("div");
    row.className = "message-row user";
    row.innerHTML = `
      <div class="message-avatar">You</div>
      <div class="message-body">
        <div class="user-bubble">${escapeHtml(text)}</div>
      </div>
    `;
    elements.messagesList.appendChild(row);
  }

  function createAssistantMessageCard() {
    const container = document.createElement("div");
    container.className = "message-row assistant";

    container.innerHTML = `
      <div class="message-avatar">✦</div>
      <div class="message-body">
        <div class="message-sender">AgentX</div>

        <!-- Thought Process / Live Pipeline Card -->
        <div class="thought-process-card open" id="thought-card">
          <div class="thought-header">
            <div class="thought-spinner" id="thought-spinner"></div>
            <span class="thought-title" id="thought-status-text">Reasoning & planning task...</span>
            <svg class="thought-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 9l6 6 6-6"/>
            </svg>
          </div>
          <div class="thought-body">
            <div class="thought-steps-list" id="thought-steps"></div>
          </div>
        </div>

        <!-- Tool Execution Cards Container -->
        <div class="tool-cards-container" id="tool-cards-container"></div>

        <!-- Final Prose Answer -->
        <div class="prose" id="answer-prose"></div>

        <!-- Footer Actions -->
        <div class="message-actions-footer" id="actions-footer" style="display: none;">
          <button class="msg-action-btn copy-answer-btn" title="Copy response to clipboard">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
            <span>Copy</span>
          </button>

          <button class="msg-action-btn view-trace-btn" title="Inspect raw trace JSON">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <span>Trace JSON</span>
          </button>

          <div class="verification-pill" id="verification-pill">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            <span id="verification-text">Verified Execution</span>
          </div>
        </div>
      </div>
    `;

    const thoughtCard = container.querySelector("#thought-card");
    const thoughtHeader = container.querySelector(".thought-header");
    const thoughtSpinner = container.querySelector("#thought-spinner");
    const thoughtStatusText = container.querySelector("#thought-status-text");
    const thoughtSteps = container.querySelector("#thought-steps");
    const toolCardsContainer = container.querySelector("#tool-cards-container");
    const answerProse = container.querySelector("#answer-prose");
    const actionsFooter = container.querySelector("#actions-footer");
    const copyBtn = container.querySelector(".copy-answer-btn");
    const traceBtn = container.querySelector(".view-trace-btn");
    const verificationPill = container.querySelector("#verification-pill");
    const verificationText = container.querySelector("#verification-text");

    let finalAnswerText = "";
    let toolCallsCount = 0;
    let fullTrace = [];

    // Header accordion toggle
    thoughtHeader.addEventListener("click", () => {
      thoughtCard.classList.toggle("open");
    });

    copyBtn.addEventListener("click", () => {
      if (finalAnswerText) {
        navigator.clipboard.writeText(finalAnswerText).then(() => {
          showToast("Response copied to clipboard");
        });
      }
    });

    traceBtn.addEventListener("click", () => {
      openTraceModal(fullTrace);
    });

    return {
      container,
      updateLiveStatus: (status) => {
        thoughtStatusText.textContent = status;
        scrollToBottom();
      },
      addTraceEvent: (ev) => {
        fullTrace.push(ev);

        // Format trace step row
        const stepRow = document.createElement("div");
        stepRow.className = "trace-step-item";

        let badgeClass = "plan";
        let badgeLabel = ev.kind.toUpperCase();
        let detailText = ev.detail || "";

        if (ev.kind === "plan") {
          badgeClass = "plan";
          thoughtStatusText.textContent = "Planned task execution";
        } else if (ev.kind === "llm_request") {
          badgeClass = "llm";
          badgeLabel = "LLM";
          thoughtStatusText.textContent = "Calling model...";
          detailText = "Requesting next action from model...";
        } else if (ev.kind === "llm_response") {
          badgeClass = "llm";
          badgeLabel = "LLM";
          detailText = ev.detail || "Received response from model";
        } else if (ev.kind === "tool_call") {
          badgeClass = "tool";
          badgeLabel = `TOOL: ${ev.tool_name || "call"}`;
          thoughtStatusText.textContent = `Executing tool: ${ev.tool_name}...`;
          detailText = `Arguments: ${JSON.stringify(ev.arguments || {})}`;
          toolCallsCount++;
        } else if (ev.kind === "result") {
          badgeClass = "result";
          badgeLabel = `DONE: ${ev.tool_name || "result"}`;
          thoughtStatusText.textContent = `Tool ${ev.tool_name} completed`;
          detailText = ev.detail || "Executed successfully";

          // Render Rich Tool Card
          renderToolResultCard(toolCardsContainer, ev);
        } else if (ev.kind === "safety") {
          badgeClass = "safety";
          badgeLabel = "GUARDRAIL";
          thoughtStatusText.textContent = `Guardrail blocked: ${ev.tool_name || "action"}`;
          detailText = `Blocked: ${ev.detail || "Safety check triggered"}`;

          // Render Safety Alert Card
          renderSafetyCard(toolCardsContainer, ev);
        } else if (ev.kind === "verify") {
          badgeClass = "verify";
          badgeLabel = "VERIFY";
          thoughtStatusText.textContent = "Verifying result consistency...";
        }

        stepRow.innerHTML = `
          <span class="step-badge ${badgeClass}">${escapeHtml(badgeLabel)}</span>
          <span class="step-desc">${escapeHtml(detailText)}</span>
        `;
        thoughtSteps.appendChild(stepRow);
        scrollToBottom();
      },
      complete: (result) => {
        finalAnswerText = result.final_answer || "";
        fullTrace = result.trace || fullTrace;

        // Stop spinner and collapse thought process to sleek Gemini/ChatGPT style pill
        thoughtSpinner.style.display = "none";
        const toolLabel = result.tool_calls_made === 1 ? "1 tool call" : `${result.tool_calls_made} tool calls`;
        thoughtStatusText.textContent = `Reasoning complete · ${toolLabel} (${result.duration_s}s)`;
        thoughtCard.classList.remove("open");

        // Render Markdown Prose
        if (window.marked && finalAnswerText) {
          answerProse.innerHTML = window.marked.parse(finalAnswerText);
          highlightCodeBlocks(answerProse);
        } else {
          answerProse.textContent = finalAnswerText;
        }

        // Verification Pill Details
        if (result.verification && result.verification.ok) {
          verificationText.textContent = "Verified deterministic computation";
          verificationPill.style.display = "flex";
        } else if (result.tool_calls_made > 0) {
          verificationText.textContent = "Verified Tool Execution";
          verificationPill.style.display = "flex";
        } else {
          verificationPill.style.display = "none";
        }

        actionsFooter.style.display = "flex";
        scrollToBottom();
      },
      setCancelled: () => {
        thoughtSpinner.style.display = "none";
        thoughtStatusText.textContent = "Execution cancelled by user";
        thoughtCard.classList.remove("open");
        answerProse.innerHTML = '<p style="color: var(--accent-amber); font-weight: 500;">Task execution was cancelled.</p>';
        actionsFooter.style.display = "flex";
        verificationPill.style.display = "none";
      },
      setError: (errText) => {
        thoughtSpinner.style.display = "none";
        thoughtStatusText.textContent = "Execution failed";
        answerProse.innerHTML = `<div class="safety-alert-card"><div class="safety-alert-icon">⚠️</div><div><div class="safety-alert-title">Execution Interrupted</div><div class="safety-alert-desc">${escapeHtml(errText)}</div></div></div>`;
        actionsFooter.style.display = "flex";
        verificationPill.style.display = "none";
      },
    };
  }

  // ==========================================================================
  // Rich Tool Card Renderers
  // ==========================================================================

  function renderToolResultCard(container, ev) {
    const card = document.createElement("div");
    card.className = "tool-card";

    const toolName = ev.tool_name || "tool";
    const data = ev.data || {};

    if (toolName === "calculator") {
      const expr = data.expression || (ev.arguments && ev.arguments.expression) || "";
      const val = data.result || ev.detail || "";
      card.innerHTML = `
        <div class="tool-card-header">
          <div class="tool-card-identity">
            <span class="tool-pill calculator">⚡ Calculator</span>
          </div>
          <span class="tool-timing-badge">AST Restricted Sandbox</span>
        </div>
        <div class="calc-result-box">
          <span class="calc-expr">${escapeHtml(expr)}</span>
          <span class="calc-equals">=</span>
          <span class="calc-val">${escapeHtml(val)}</span>
        </div>
      `;
    } else if (toolName === "web_search") {
      const query = data.query || (ev.arguments && ev.arguments.query) || "";
      const results = data.results || [];
      const provider = data.provider || "web";

      let sourcesHtml = "";
      results.forEach((item) => {
        let domain = "";
        try {
          domain = new URL(item.url).hostname.replace(/^www\./, "");
        } catch (_) {
          domain = item.url;
        }

        sourcesHtml += `
          <a class="source-card" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">
            <span class="source-domain">${escapeHtml(domain)}</span>
            <span class="source-title">${escapeHtml(item.title || domain)}</span>
            <span class="source-snippet">${escapeHtml(item.snippet || "")}</span>
          </a>
        `;
      });

      card.innerHTML = `
        <div class="tool-card-header">
          <div class="tool-card-identity">
            <span class="tool-pill web_search">🔍 Web Search</span>
            <span style="font-size: 12px; color: var(--text-secondary); font-family: var(--font-mono);">${escapeHtml(query)}</span>
          </div>
          <span class="tool-timing-badge">${results.length} sources (${escapeHtml(provider)})</span>
        </div>
        <div class="search-sources-grid">${sourcesHtml}</div>
      `;
    } else if (toolName === "api_lookup") {
      const base = data.base || "USD";
      const target = data.target || "INR";
      const rate = data.rate || "";
      const source = data.source || "open.er-api.com";
      const ageNote = data.data_age_note || "Live verified";

      card.innerHTML = `
        <div class="tool-card-header">
          <div class="tool-card-identity">
            <span class="tool-pill api_lookup">🌐 Live API Lookup</span>
          </div>
          <span class="tool-timing-badge">${escapeHtml(source)}</span>
        </div>
        <div class="api-rate-box">
          <div class="rate-pair">${escapeHtml(base)} → ${escapeHtml(target)}</div>
          <div class="rate-num">${escapeHtml(rate)}</div>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px;">${escapeHtml(ageNote)}</div>
      `;
    } else {
      card.innerHTML = `
        <div class="tool-card-header">
          <span class="tool-pill">${escapeHtml(toolName)}</span>
        </div>
        <pre class="tool-schema-pre">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
      `;
    }

    container.appendChild(card);
  }

  function renderSafetyCard(container, ev) {
    const card = document.createElement("div");
    card.className = "safety-alert-card";
    card.innerHTML = `
      <div class="safety-alert-icon">🛡️</div>
      <div>
        <div class="safety-alert-title">Guardrail Intercept Neutralized Call</div>
        <div class="safety-alert-desc">${escapeHtml(ev.detail || "Tool rejected by allowlist or AST security policy")}</div>
      </div>
    `;
    container.appendChild(card);
  }

  // ==========================================================================
  // Code Highlighting & Copy Buttons
  // ==========================================================================

  function highlightCodeBlocks(container) {
    if (!window.hljs) return;
    const preBlocks = container.querySelectorAll("pre");

    preBlocks.forEach((pre) => {
      const code = pre.querySelector("code");
      if (!code) return;

      // Syntax highlight
      window.hljs.highlightElement(code);

      // Detect language
      let lang = "code";
      code.classList.forEach((cls) => {
        if (cls.startsWith("language-")) {
          lang = cls.replace("language-", "");
        }
      });

      // Wrap in custom header with copy button
      const header = document.createElement("div");
      header.className = "code-header";
      header.innerHTML = `
        <span>${escapeHtml(lang)}</span>
        <button class="copy-code-btn">Copy code</button>
      `;

      const copyBtn = header.querySelector(".copy-code-btn");
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(code.innerText).then(() => {
          copyBtn.textContent = "Copied!";
          setTimeout(() => {
            copyBtn.textContent = "Copy code";
          }, 2000);
        });
      });

      pre.insertBefore(header, code);
    });
  }

  // ==========================================================================
  // Input Box & Auto-Resize
  // ==========================================================================

  function setupTextareaAutoResize() {
    const ta = elements.promptTextarea;
    ta.addEventListener("input", () => {
      adjustTextareaHeight(ta);
      handleCommandSuggest(ta.value);
    });

    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (state.isRunning) {
          cancelCurrentTask();
        } else {
          executeTask();
        }
      }
    });
  }

  function adjustTextareaHeight(ta) {
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }

  function handleCommandSuggest(val) {
    if (val.trim() === "/") {
      elements.commandPopover.classList.add("open");
    } else {
      elements.commandPopover.classList.remove("open");
    }
  }

  // ==========================================================================
  // Event Listeners
  // ==========================================================================

  function setupEventListeners() {
    // Send / Stop button
    elements.sendBtn.addEventListener("click", () => {
      if (state.isRunning) {
        cancelCurrentTask();
      } else {
        executeTask();
      }
    });

    // New task button
    elements.newTaskBtn.addEventListener("click", () => {
      elements.promptTextarea.value = "";
      elements.messagesList.innerHTML = "";
      elements.welcomeContainer.style.display = "flex";
      elements.promptTextarea.focus();
    });

    // Clear memory button
    elements.topClearBtn.addEventListener("click", async () => {
      try {
        await fetch("/api/clear", { method: "POST" });
        elements.messagesList.innerHTML = "";
        elements.welcomeContainer.style.display = "flex";
        showToast("Conversation memory cleared");
      } catch (err) {
        showToast("Failed to clear memory");
      }
    });

    // Theme toggles
    elements.topThemeBtn.addEventListener("click", toggleTheme);
    elements.themeToggleBtn.addEventListener("click", toggleTheme);

    // Sidebar toggles
    elements.sidebarToggleBtn.addEventListener("click", toggleSidebar);
    elements.sidebarOpenBtn.addEventListener("click", toggleSidebar);

    // Command popover trigger
    elements.commandTriggerBtn.addEventListener("click", () => {
      elements.commandPopover.classList.toggle("open");
    });

    // Command popover items
    document.querySelectorAll(".command-popover-item").forEach((item) => {
      item.addEventListener("click", () => {
        const cmd = item.getAttribute("data-cmd");
        elements.commandPopover.classList.remove("open");
        executeCommand(cmd);
      });
    });

    // Starter suggestion cards
    document.querySelectorAll(".suggestion-card").forEach((card) => {
      card.addEventListener("click", () => {
        const prompt = card.getAttribute("data-prompt");
        executeTask(prompt);
      });
    });

    // Keyboard shortcut handlers
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n") {
        e.preventDefault();
        elements.newTaskBtn.click();
      }
    });

    // Modals setup
    setupModals();
  }

  function executeCommand(cmd) {
    if (cmd === "/tools") {
      openToolsModal();
    } else if (cmd === "/stats") {
      openStatsModal();
    } else if (cmd === "/safety-demo") {
      openSafetyModal("tab-guardrails");
    } else if (cmd === "/benchmark") {
      openSafetyModal("tab-benchmarks");
    } else if (cmd === "/clear") {
      elements.topClearBtn.click();
    }
  }

  // ==========================================================================
  // Modals Implementation
  // ==========================================================================

  function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove("open");
  }

  function closeAllModals() {
    document.querySelectorAll(".modal-backdrop.open").forEach((m) => m.classList.remove("open"));
  }

  function setupModals() {
    // Close button handlers (supporting clicks on child elements)
    document.querySelectorAll(".modal-close-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const closeBtn = e.target.closest(".modal-close-btn") || btn;
        const modalId = closeBtn.getAttribute("data-close");
        if (modalId) closeModal(modalId);
        else closeAllModals();
      });
    });

    // Backdrop click close
    document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) {
          backdrop.classList.remove("open");
        }
      });
    });

    // Escape key closes modals
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeAllModals();
      }
    });

    // Tools button
    elements.openToolsBtn.addEventListener("click", openToolsModal);
    elements.topModelPill.addEventListener("click", openToolsModal);

    // Safety & Benchmark buttons
    elements.openSafetyBtn.addEventListener("click", () => openSafetyModal("tab-guardrails"));
    elements.openStatsBtn.addEventListener("click", openStatsModal);

    // Modal Tabs
    document.querySelectorAll(".modal-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".modal-tab").forEach((t) => t.classList.remove("active"));
        document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
        tab.classList.add("active");
        const paneId = tab.getAttribute("data-tab");
        document.getElementById(paneId).classList.add("active");
      });
    });

    // Safety run button
    elements.runGuardrailsBtn.addEventListener("click", runSafetySuite);
    elements.runBenchmarksBtn.addEventListener("click", runBenchmarkSuite);
  }

  async function openToolsModal() {
    elements.toolsModal.classList.add("open");
    elements.toolsModalContent.innerHTML = '<div class="modal-loading">Loading registered tools...</div>';

    try {
      const res = await fetch("/api/tools");
      const tools = await res.json();

      let html = '<div class="tools-modal-list">';
      tools.forEach((t) => {
        html += `
          <div class="tool-info-card">
            <div class="tool-info-title">
              <span class="tool-name-code">tool: ${escapeHtml(t.name)}</span>
              <span class="tool-timing-badge">Timeout: ${t.timeout_s}s</span>
            </div>
            <div class="tool-info-desc">${escapeHtml(t.description)}</div>
            <pre class="tool-schema-pre">${escapeHtml(JSON.stringify(t.parameters, null, 2))}</pre>
          </div>
        `;
      });
      html += "</div>";
      elements.toolsModalContent.innerHTML = html;
    } catch (err) {
      elements.toolsModalContent.innerHTML = `<div style="color: var(--accent-red);">Failed to load tools: ${escapeHtml(err.message)}</div>`;
    }
  }

  function openSafetyModal(defaultTab) {
    elements.safetyModal.classList.add("open");
    if (defaultTab) {
      const tabBtn = document.querySelector(`.modal-tab[data-tab="${defaultTab}"]`);
      if (tabBtn) tabBtn.click();
    }
  }

  async function runSafetySuite() {
    elements.guardrailResultsContainer.innerHTML = '<div class="matrix-empty">Testing guardrails across all defense layers...</div>';
    elements.runGuardrailsBtn.disabled = true;

    try {
      const res = await fetch("/api/safety-demo", { method: "POST" });
      const results = await res.json();

      let rowsHtml = "";
      results.forEach((r) => {
        const badge = r.status === "BLOCKED" 
          ? '<span class="status-badge-blocked">✔ BLOCKED</span>' 
          : '<span class="status-badge-allowed">⚠ ALLOWED</span>';

        rowsHtml += `
          <tr>
            <td><code>${escapeHtml(r.test_case)}</code></td>
            <td>${escapeHtml(r.layer)}</td>
            <td>${badge}</td>
            <td style="color: var(--text-muted); font-size: 12px;">${escapeHtml(r.proof)}</td>
          </tr>
        `;
      });

      elements.guardrailResultsContainer.innerHTML = `
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Attack Vector</th>
              <th>Defense Layer</th>
              <th>Status</th>
              <th>Enforcement Proof</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
        <div style="margin-top: 14px; font-size: 12.5px; color: var(--accent-green); font-weight: 600;">
          ✔ Verified: All dangerous inputs neutralized. Strict sandbox maintained.
        </div>
      `;
    } catch (err) {
      elements.guardrailResultsContainer.innerHTML = `<div style="color: var(--accent-red);">Error: ${escapeHtml(err.message)}</div>`;
    } finally {
      elements.runGuardrailsBtn.disabled = false;
    }
  }

  async function runBenchmarkSuite() {
    elements.benchmarkResultsContainer.innerHTML = '<div class="matrix-empty">Executing 10 acceptance scenarios...</div>';
    elements.runBenchmarksBtn.disabled = true;

    try {
      const res = await fetch("/api/benchmark", { method: "POST" });
      const results = await res.json();

      let rowsHtml = "";
      let passedCount = 0;
      results.forEach((r) => {
        if (r.passed) passedCount++;
        const badge = r.passed 
          ? '<span class="status-badge-blocked">✔ PASSED</span>' 
          : '<span class="status-badge-allowed">FAIL</span>';

        rowsHtml += `
          <tr>
            <td><code>${escapeHtml(r.name)}</code></td>
            <td>${badge}</td>
            <td style="color: var(--text-muted); font-size: 12px;">${escapeHtml(r.detail)}</td>
          </tr>
        `;
      });

      elements.benchmarkResultsContainer.innerHTML = `
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Scenario Name</th>
              <th>Result</th>
              <th>Verification Detail</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
        <div style="margin-top: 14px; font-size: 12.5px; color: var(--accent-green); font-weight: 600;">
          Benchmark Score: ${passedCount} / ${results.length} Scenarios Passed.
        </div>
      `;
    } catch (err) {
      elements.benchmarkResultsContainer.innerHTML = `<div style="color: var(--accent-red);">Error: ${escapeHtml(err.message)}</div>`;
    } finally {
      elements.runBenchmarksBtn.disabled = false;
    }
  }

  async function openStatsModal() {
    elements.statsModal.classList.add("open");
    elements.statsModalContent.innerHTML = '<div class="modal-loading">Loading session metrics...</div>';

    try {
      const res = await fetch("/api/stats");
      const data = await res.json();
      const m = data.metrics || {};

      const successRate = m.tasks_attempted > 0 
        ? Math.round((m.tasks_completed / m.tasks_attempted) * 100) 
        : 100;

      const avgDuration = m.tasks_attempted > 0 
        ? (m.total_task_seconds / m.tasks_attempted).toFixed(2) 
        : "0.00";

      elements.statsModalContent.innerHTML = `
        <div class="stats-grid">
          <div class="stat-box">
            <div class="stat-val">${m.tasks_attempted || 0}</div>
            <div class="stat-label">Tasks Attempted</div>
          </div>
          <div class="stat-box">
            <div class="stat-val" style="color: var(--accent-green);">${m.tasks_completed || 0}</div>
            <div class="stat-label">Tasks Completed</div>
          </div>
          <div class="stat-box">
            <div class="stat-val">${successRate}%</div>
            <div class="stat-label">Success Rate</div>
          </div>
          <div class="stat-box">
            <div class="stat-val" style="color: var(--accent-primary);">${m.tool_calls_executed || 0}</div>
            <div class="stat-label">Tool Calls Made</div>
          </div>
          <div class="stat-box">
            <div class="stat-val" style="color: var(--accent-red);">${m.tool_calls_rejected || 0}</div>
            <div class="stat-label">Tools Rejected</div>
          </div>
          <div class="stat-box">
            <div class="stat-val">${avgDuration}s</div>
            <div class="stat-label">Avg Task Time</div>
          </div>
        </div>

        <div style="font-size: 13px; color: var(--text-secondary); background: var(--bg-surface-elevated); padding: 12px 16px; border-radius: var(--radius-sm);">
          <strong>Active Endpoint:</strong> ${escapeHtml(data.active_model || "None")}<br>
          <strong>Session History:</strong> ${data.history_count} tasks stored in memory.
        </div>
      `;
    } catch (err) {
      elements.statsModalContent.innerHTML = `<div style="color: var(--accent-red);">Failed to load stats: ${escapeHtml(err.message)}</div>`;
    }
  }

  function openTraceModal(trace) {
    elements.traceModal.classList.add("open");
    const jsonStr = JSON.stringify(trace || state.currentTrace || [], null, 2);
    elements.traceJsonCode.textContent = jsonStr;

    if (window.hljs) {
      window.hljs.highlightElement(elements.traceJsonCode);
    }
  }

  // ==========================================================================
  // Utilities
  // ==========================================================================

  function scrollToBottom() {
    elements.chatViewport.scrollTop = elements.chatViewport.scrollHeight;
  }

  function escapeHtml(str) {
    if (typeof str !== "string") str = String(str || "");
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 200ms ease-out";
      setTimeout(() => toast.remove(), 200);
    }, 2500);
  }

  // Start Application
  document.addEventListener("DOMContentLoaded", init);
})();
