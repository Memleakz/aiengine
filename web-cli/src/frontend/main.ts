import { WebSocketService, ConnectionStatus } from "./services/websocket";
import { MessageFeed, AgentMessageHandle } from "./components/messageFeed";
import { InputArea } from "./components/inputArea";
import type { ServerEvent, AgentStatusEvent, AgentToolCallEvent, AgentStreamChunkEvent, AgentCompleteEvent } from "./types/events";

const messageFeedContainer = document.getElementById("message-feed") as HTMLElement;
const userInput = document.getElementById("user-input") as HTMLTextAreaElement;
const sendButton = document.getElementById("send-button") as HTMLButtonElement;
const stopButton = document.getElementById("stop-button") as HTMLButtonElement;
const connectionStatusDot = document.getElementById("connection-status-dot") as HTMLElement;
const connectionStatusText = document.getElementById("connection-status-text") as HTMLElement;
const loadingOverlay = document.getElementById("loading-overlay") as HTMLElement;
const currentWorkdirDisplay = document.getElementById("current-workdir") as HTMLElement;

const MAX_INPUT_LENGTH = 10000;

// Use environment variable for the backend URL, fallback to current host
// In production with different ports, set VITE_API_BASE_URL=http://aitest.mitfolketing.dk:8000
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || "";
// Ensure WS_URL correctly points to /ws even if API_BASE_URL is set
let WS_URL: string;
if (API_BASE_URL) {
  const base = API_BASE_URL.replace(/^http/, "ws");
  WS_URL = base.endsWith("/") ? `${base}ws` : `${base}/ws`;
} else {
  WS_URL = "/ws";
}

const wsService = new WebSocketService(WS_URL, {
  reconnectAttempts: 3,
  reconnectDelay: 5000,
});

const messageFeed = new MessageFeed(messageFeedContainer);
const inputArea = new InputArea(userInput, sendButton);

let currentAgentMessage: AgentMessageHandle | null = null;
let isProcessing = false;

function setProcessingState(processing: boolean) {
  isProcessing = processing;
  if (processing) {
    sendButton.classList.add("hidden");
    stopButton.classList.remove("hidden");
    inputArea.disable();
  } else {
    sendButton.classList.remove("hidden");
    stopButton.classList.add("hidden");
    inputArea.enable();
  }
}

stopButton.addEventListener("click", () => {
  if (isProcessing && wsService.isConnected) {
    wsService.socket?.send(JSON.stringify({ event: "stop" }));
    stopButton.classList.add("hidden"); // Optimistically hide it
    messageFeed.addSystemBanner("Stop signal sent. Terminating execution...");
  }
});

// --- Settings Modal Elements ---
const settingsButton = document.getElementById("settings-button") as HTMLButtonElement;
const turnIn = document.getElementById("turn-in") as HTMLElement;
const turnOut = document.getElementById("turn-out") as HTMLElement;
const turnThink = document.getElementById("turn-think") as HTMLElement;
const turnTotal = document.getElementById("turn-total") as HTMLElement;
const sessionIn = document.getElementById("session-in") as HTMLElement;
const sessionOut = document.getElementById("session-out") as HTMLElement;
const sessionThink = document.getElementById("session-think") as HTMLElement;
const sessionTotal = document.getElementById("session-total") as HTMLElement;
const settingsModal = document.getElementById("settings-modal") as HTMLElement;
const closeSettings = document.getElementById("close-settings") as HTMLButtonElement;
const settingsForm = document.getElementById("settings-form") as HTMLFormElement;

const settingWorkdir = document.getElementById("setting-workdir") as HTMLInputElement;
const settingSystemPrompt = document.getElementById("setting-system-prompt") as HTMLTextAreaElement;
const settingTemperature = document.getElementById("setting-temperature") as HTMLInputElement;
const settingTopP = document.getElementById("setting-top-p") as HTMLInputElement;
const settingMaxTokens = document.getElementById("setting-max-tokens") as HTMLInputElement;
const settingShowDebug = document.getElementById("setting-show-debug") as HTMLInputElement;
const settingAdaptiveTools = document.getElementById("setting-adaptive-tools") as HTMLInputElement;
const settingCompileCheck = document.getElementById("setting-compile-check") as HTMLInputElement;

let showDebug = false;

// Initialize working directory from localStorage
const savedWorkdir = localStorage.getItem("ai_kanban_workdir");
if (savedWorkdir) {
  if (settingWorkdir) settingWorkdir.value = savedWorkdir;
  if (currentWorkdirDisplay) currentWorkdirDisplay.textContent = savedWorkdir;
}

// Load adaptive_tools and compile_check from localStorage
if (settingAdaptiveTools) {
  const savedAdaptive = localStorage.getItem("ai_kanban_adaptive_tools");
  settingAdaptiveTools.checked = savedAdaptive !== "false"; // default to true
}
if (settingCompileCheck) {
  const savedCompile = localStorage.getItem("ai_kanban_compile_check");
  settingCompileCheck.checked = savedCompile !== "false"; // default to true
}

// --- Flow Modal Elements ---
const flowButton = document.getElementById("flow-button") as HTMLButtonElement;
const flowModal = document.getElementById("flow-modal") as HTMLElement;
const closeFlow = document.getElementById("close-flow") as HTMLButtonElement;
const flowInitialPrompt = document.getElementById("flow-initial-prompt") as HTMLTextAreaElement;
const flowAgentsList = document.getElementById("flow-agents-list") as HTMLElement;
const addAgentButton = document.getElementById("add-agent-button") as HTMLButtonElement;
const startFlowButton = document.getElementById("start-flow-button") as HTMLButtonElement;
const flowStepper = document.getElementById("flow-stepper") as HTMLElement;
const flowStepperContent = document.getElementById("flow-stepper-content") as HTMLElement;

const savedFlowsSelect = document.getElementById("saved-flows-select") as HTMLSelectElement;
const saveFlowBtn = document.getElementById("save-flow-btn") as HTMLButtonElement;
const deleteFlowBtn = document.getElementById("delete-flow-btn") as HTMLButtonElement;

let agentCount = 0;

function createAgentConfig(name: string = "", prompt: string = "") {
  agentCount++;
  const id = `agent-${agentCount}`;
  const div = document.createElement("div");
  div.className = "flow-agent-item";
  div.id = id;
  div.innerHTML = `
    <div class="flow-agent-header">
      <input type="text" class="flow-agent-title-input" placeholder="Agent Name (e.g. Planner)" value="${name}">
      <div style="display: flex; gap: 8px; align-items: center;">
         <select class="load-persona-select input-textarea" style="width: 120px; padding: 2px; font-size: 11px; min-height: 24px; border-radius: 4px; background: var(--color-surface1);">
            <option value="">Load Persona</option>
         </select>
         <button type="button" class="save-persona-btn" style="background:transparent; border:none; color:var(--color-blue); cursor:pointer; font-size: 14px;" title="Save Persona">💾</button>
         <button type="button" class="remove-agent-btn" onclick="document.getElementById('${id}').remove()">×</button>
      </div>
    </div>
    <textarea class="flow-agent-prompt-input" rows="2" placeholder="System prompt for this agent...">${prompt}</textarea>
  `;
  flowAgentsList.appendChild(div);
  
  const select = div.querySelector('.load-persona-select') as HTMLSelectElement;
  const saveBtn = div.querySelector('.save-persona-btn') as HTMLButtonElement;
  const nameInput = div.querySelector('.flow-agent-title-input') as HTMLInputElement;
  const promptInput = div.querySelector('.flow-agent-prompt-input') as HTMLTextAreaElement;

  function updatePersonaDropdown() {
    const saved = JSON.parse(localStorage.getItem("ai_kanban_personas") || "{}");
    select.innerHTML = '<option value="">Load Persona</option>';
    for (const p in saved) {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      select.appendChild(opt);
    }
  }

  updatePersonaDropdown();
  
  select.addEventListener('change', () => {
    if (select.value) {
      const saved = JSON.parse(localStorage.getItem("ai_kanban_personas") || "{}");
      if (saved[select.value]) {
        nameInput.value = select.value;
        promptInput.value = saved[select.value];
      }
      select.value = ""; // reset
    }
  });

  saveBtn.addEventListener('click', () => {
    const pName = nameInput.value.trim();
    const pPrompt = promptInput.value.trim();
    if (!pName || !pPrompt) {
      alert("Please enter a name and prompt before saving the persona.");
      return;
    }
    const saved = JSON.parse(localStorage.getItem("ai_kanban_personas") || "{}");
    saved[pName] = pPrompt;
    localStorage.setItem("ai_kanban_personas", JSON.stringify(saved));
    
    document.querySelectorAll('.load-persona-select').forEach((el: any) => {
        const val = el.value;
        const savedAll = JSON.parse(localStorage.getItem("ai_kanban_personas") || "{}");
        el.innerHTML = '<option value="">Load Persona</option>';
        for (const p in savedAll) {
          const opt = document.createElement("option");
          opt.value = p;
          opt.textContent = p;
          el.appendChild(opt);
        }
        el.value = val;
    });
  });
}

function updateFlowDropdown() {
  const saved = JSON.parse(localStorage.getItem("ai_kanban_flows") || "{}");
  savedFlowsSelect.innerHTML = '<option value="">-- Load Saved Flow --</option>';
  for (const f in saved) {
    const opt = document.createElement("option");
    opt.value = f;
    opt.textContent = f;
    savedFlowsSelect.appendChild(opt);
  }
}
updateFlowDropdown();

savedFlowsSelect.addEventListener('change', () => {
  const fName = savedFlowsSelect.value;
  if (!fName) return;
  const saved = JSON.parse(localStorage.getItem("ai_kanban_flows") || "{}");
  const flow = saved[fName];
  if (flow) {
    flowInitialPrompt.value = flow.initial_prompt || "";
    flowAgentsList.innerHTML = "";
    if (flow.agents && flow.agents.length > 0) {
      for (const a of flow.agents) {
        createAgentConfig(a.name, a.system_prompt);
      }
    }
  }
});

saveFlowBtn.addEventListener('click', () => {
  const fName = prompt("Enter a name for this Flow:");
  if (!fName) return;
  const initialPrompt = flowInitialPrompt.value.trim();
  const agents = [];
  for (const child of Array.from(flowAgentsList.children)) {
    const nameInput = child.querySelector(".flow-agent-title-input") as HTMLInputElement;
    const promptInput = child.querySelector(".flow-agent-prompt-input") as HTMLTextAreaElement;
    if (nameInput.value.trim() || promptInput.value.trim()) {
      agents.push({
        name: nameInput.value.trim(),
        system_prompt: promptInput.value.trim()
      });
    }
  }
  const saved = JSON.parse(localStorage.getItem("ai_kanban_flows") || "{}");
  saved[fName] = { initial_prompt: initialPrompt, agents };
  localStorage.setItem("ai_kanban_flows", JSON.stringify(saved));
  updateFlowDropdown();
  savedFlowsSelect.value = fName;
});

deleteFlowBtn.addEventListener('click', () => {
  const fName = savedFlowsSelect.value;
  if (!fName) return;
  if (confirm(`Delete saved flow "${fName}"?`)) {
    const saved = JSON.parse(localStorage.getItem("ai_kanban_flows") || "{}");
    delete saved[fName];
    localStorage.setItem("ai_kanban_flows", JSON.stringify(saved));
    updateFlowDropdown();
  }
});

flowButton.addEventListener("click", () => {
  if (flowAgentsList.children.length === 0) {
    createAgentConfig("Planner", "You are the planner. Outline the steps to complete the task.");
    createAgentConfig("Developer", "You are the developer. Implement the plan provided by the planner.");
  }
  flowModal.classList.add("show");
});

closeFlow.addEventListener("click", () => {
  flowModal.classList.remove("show");
});

addAgentButton.addEventListener("click", () => {
  createAgentConfig();
});

startFlowButton.addEventListener("click", () => {
  const initialPrompt = flowInitialPrompt.value.trim();
  if (!initialPrompt) {
    alert("Please provide an initial task request.");
    return;
  }
  
  const agents = [];
  for (const child of Array.from(flowAgentsList.children)) {
    const nameInput = child.querySelector(".flow-agent-title-input") as HTMLInputElement;
    const promptInput = child.querySelector(".flow-agent-prompt-input") as HTMLTextAreaElement;
    if (nameInput.value.trim() && promptInput.value.trim()) {
      agents.push({
        name: nameInput.value.trim(),
        system_prompt: promptInput.value.trim()
      });
    }
  }
  
  if (agents.length === 0) {
    alert("Please configure at least one agent step.");
    return;
  }
  
  flowModal.classList.remove("show");
  messageFeed.addUserMessage(`[Flow Started] ${initialPrompt}`);
  
  wsService.socket?.send(JSON.stringify({
    event: "run_flow",
    data: { initial_prompt: initialPrompt, agents }
  }));
  
  setProcessingState(true);
});

settingsButton.addEventListener("click", () => {
  settingsModal.classList.add("show");
});

closeSettings.addEventListener("click", () => {
  settingsModal.classList.remove("show");
});

settingsModal.addEventListener("click", (e) => {
  if (e.target === settingsModal) {
    settingsModal.classList.remove("show");
  }
});

settingsForm.addEventListener("submit", (e) => {
  e.preventDefault();
  
  showDebug = settingShowDebug.checked;

  const adaptive = settingAdaptiveTools ? settingAdaptiveTools.checked : true;
  const compile = settingCompileCheck ? settingCompileCheck.checked : true;

  const settings = {
    workdir: settingWorkdir.value || undefined,
    system_prompt: settingSystemPrompt.value || undefined,
    adaptive_tools: adaptive,
    compile_check: compile,
    parameters: {
      temperature: parseFloat(settingTemperature.value),
      top_p: parseFloat(settingTopP.value),
      max_tokens: parseInt(settingMaxTokens.value, 10),
    }
  };
  
  wsService.sendSettings(settings);
  
  if (settings.workdir) {
    localStorage.setItem("ai_kanban_workdir", settings.workdir);
    if (currentWorkdirDisplay) currentWorkdirDisplay.textContent = settings.workdir;
  }

  localStorage.setItem("ai_kanban_adaptive_tools", adaptive.toString());
  localStorage.setItem("ai_kanban_compile_check", compile.toString());

  settingsModal.classList.remove("show");
  // Banner only on manual save
  messageFeed.addSystemBanner(`Settings applied${showDebug ? " (Debug ON)" : ""}.`);
});

let initialSettingsSynced = false;

wsService.onStatusChange((status: ConnectionStatus) => {
  updateConnectionStatus(status);
  
  if (status === "connected") {
    const workdir = localStorage.getItem("ai_kanban_workdir");
    const adaptive = localStorage.getItem("ai_kanban_adaptive_tools") !== "false";
    const compile = localStorage.getItem("ai_kanban_compile_check") !== "false";
    
    const initialSettings: any = {};
    if (workdir) {
      initialSettings.workdir = workdir;
    }
    initialSettings.adaptive_tools = adaptive;
    initialSettings.compile_check = compile;
    
    wsService.sendSettings(initialSettings);
  } else if (status === "disconnected") {
    initialSettingsSynced = false;
  }
});

wsService.onEvent((event: ServerEvent) => {
  handleServerEvent(event);
});

inputArea.onSend((text: string) => {
  if (!isProcessing && wsService.isConnected) {
    const sanitizedText = sanitizeInput(text);
    if (sanitizedText.length > MAX_INPUT_LENGTH) {
      messageFeed.addErrorBanner("Message too long (max 10000 characters)");
      return;
    }
    messageFeed.addUserMessage(sanitizedText);
    wsService.send(sanitizedText);
    setProcessingState(true);
    currentAgentMessage = messageFeed.createAgentMessage();
    currentAgentMessage.setStatus("Thinking...");
  }
});

function handleServerEvent(event: ServerEvent): void {
  switch (event.event) {
    case "agent_status":
      handleAgentStatus(event.data);
      break;
    case "agent_thinking":
      handleAgentThinking(event.data);
      break;
    case "agent_tool_call":
      handleAgentToolCall(event.data);
      break;
    case "agent_tool_done":
      handleAgentToolDone(event.data);
      break;
    case "agent_stream_chunk":
      handleAgentStreamChunk(event.data);
      break;
    case "agent_complete":
      handleAgentComplete(event.data);
      break;
    case "reconnected":
      handleReconnect();
      break;
    case "error":
      handleError(event.data);
      break;
    case "validation_error":
      handleValidationError(event.data);
      break;
    case "settings_updated":
      handleSettingsUpdated(event.data);
      break;
    case "flow_start":
      handleFlowStart(event.data);
      break;
    case "flow_step_start":
      handleFlowStepStart(event.data);
      break;
    case "flow_step_complete":
      handleFlowStepComplete(event.data);
      break;
    case "flow_complete":
      handleFlowComplete(event.data);
      break;
  }
}

function handleFlowStart(data: any): void {
  flowStepper.classList.remove("hidden");
  flowStepperContent.innerHTML = "";
  for (let i = 0; i < data.total_agents; i++) {
    const step = document.createElement("div");
    step.className = "stepper-item";
    step.id = `stepper-step-${i + 1}`;
    step.textContent = `Step ${i + 1}`;
    flowStepperContent.appendChild(step);
    
    if (i < data.total_agents - 1) {
      const sep = document.createElement("div");
      sep.className = "stepper-separator";
      sep.textContent = "➔";
      flowStepperContent.appendChild(sep);
    }
  }
}

function handleFlowStepStart(data: any): void {
  const stepEl = document.getElementById(`stepper-step-${data.step}`);
  if (stepEl) {
    stepEl.textContent = data.agent_name;
    stepEl.classList.add("active");
  }
  
  // Create a new agent message block for this agent
  currentAgentMessage = messageFeed.createAgentMessage();
  
  // We can modify the label to show the agent name
  const header = currentAgentMessage.element.querySelector('.agent-label');
  if (header) {
    header.textContent = data.agent_name;
  }
  
  currentAgentMessage.setStatus("Thinking...");
}

function handleFlowStepComplete(data: any): void {
  if (currentAgentMessage) {
    currentAgentMessage.markComplete();
    currentAgentMessage = null;
  }
  
  // Find the active step and mark it completed
  const activeSteps = flowStepperContent.querySelectorAll('.stepper-item.active');
  activeSteps.forEach(el => {
    el.classList.remove("active");
    el.classList.add("completed");
    el.textContent = `✓ ${el.textContent}`;
  });
}

function handleFlowComplete(data: any): void {
  messageFeed.addSystemBanner("Agent Flow completed successfully.");
  setProcessingState(false);
  inputArea.focus();
  setTimeout(() => {
    flowStepper.classList.add("hidden");
  }, 3000);
}

function handleAgentStatus(data: AgentStatusEvent["data"]): void {
  if (data.message.startsWith("[DEBUG]")) {
    if (showDebug) {
      messageFeed.addSystemBanner(data.message);
    }
    return;
  }
  if (currentAgentMessage) {
    currentAgentMessage.setStatus(data.message);
  }
}

function handleAgentThinking(data: { chunk: string }): void {
  if (!currentAgentMessage) {
    currentAgentMessage = messageFeed.createAgentMessage();
  }
  currentAgentMessage.appendThinking(data.chunk);
}

function handleAgentToolCall(data: AgentToolCallEvent["data"]): void {
  if (currentAgentMessage) {
    currentAgentMessage.addToolCall(data.tool, data.target);
  }
}

function handleAgentToolDone(data: { tool: string; output: string; truncated: boolean }): void {
  if (currentAgentMessage) {
    currentAgentMessage.addToolResult(data.tool, data.output, data.truncated);
  }
}

function handleAgentStreamChunk(data: any): void {
  if (!currentAgentMessage) {
    currentAgentMessage = messageFeed.createAgentMessage();
    currentAgentMessage.setStatus("Processing...");
    // Update the name if provided in the stream event (from flow logic)
    if (data.agent_name) {
      const header = currentAgentMessage.element.querySelector('.agent-label');
      if (header) header.textContent = data.agent_name;
    }
  }
  currentAgentMessage.getRenderer().append(data.chunk);
}

function handleAgentComplete(data: AgentCompleteEvent["data"]): void {
  if (currentAgentMessage) {
    currentAgentMessage.markComplete();
  }
  
  if (data.usage && data.session_usage) {
    updateStats(data.usage, data.session_usage);
  }

  currentAgentMessage = null;
  setProcessingState(false);
  inputArea.focus();
}

function updateStats(usage: TokenUsage, sessionUsage: TokenUsage): void {
  if (turnIn) turnIn.textContent = (usage.prompt_tokens || 0).toLocaleString();
  if (turnOut) turnOut.textContent = (usage.completion_tokens || 0).toLocaleString();
  if (turnThink) turnThink.textContent = (usage.reasoning_tokens || 0).toLocaleString();
  if (turnTotal) turnTotal.textContent = (usage.total_tokens || 0).toLocaleString();

  if (sessionIn) sessionIn.textContent = (sessionUsage.prompt_tokens || 0).toLocaleString();
  if (sessionOut) sessionOut.textContent = (sessionUsage.completion_tokens || 0).toLocaleString();
  if (sessionThink) sessionThink.textContent = (sessionUsage.reasoning_tokens || 0).toLocaleString();
  if (sessionTotal) sessionTotal.textContent = (sessionUsage.total_tokens || 0).toLocaleString();
}

function handleReconnect(): void {
  if (currentAgentMessage) {
    currentAgentMessage.markAsInterrupted("Connection lost");
    currentAgentMessage = null;
  }
  setProcessingState(false);
  inputArea.focus();
  messageFeed.addSystemBanner("Connection restored.");
}

function handleError(data: { message: string }): void {
  messageFeed.addErrorBanner(data.message);
  if (isProcessing) {
    setProcessingState(false);
    inputArea.focus();
  }
}

function handleValidationError(data: { message: string }): void {
  messageFeed.addErrorBanner(data.message);
}

function handleSettingsUpdated(data: { updated: string[] }): void {
  // Silent update for workdir sync unless other things changed
  if (data.updated.length === 1 && data.updated[0] === "workdir") {
    return;
  }
  messageFeed.addSystemBanner(`Settings updated successfully: ${data.updated.join(", ")}`);
}

function sanitizeInput(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.textContent || "";
}

function updateConnectionStatus(status: ConnectionStatus): void {
  if (connectionStatusDot && connectionStatusText) {
    connectionStatusDot.className = "status-dot";
    switch (status) {
      case "connected":
        connectionStatusDot.classList.add("status-connected");
        connectionStatusText.textContent = "Connected";
        if (loadingOverlay) {
          loadingOverlay.classList.add("hidden");
        }
        break;
      case "connecting":
        connectionStatusDot.classList.add("status-connecting");
        connectionStatusText.textContent = "Connecting...";
        break;
      case "disconnected":
        connectionStatusDot.classList.add("status-disconnected");
        connectionStatusText.textContent = "Disconnected";
        break;
    }
  }
}

// --- Login Modal Elements ---
const loginModal = document.getElementById("login-modal") as HTMLElement;
const loginForm = document.getElementById("login-form") as HTMLFormElement;
const loginPassword = document.getElementById("login-password") as HTMLInputElement;
const loginError = document.getElementById("login-error") as HTMLElement;

async function checkAuthStatus(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/status`);
    if (!response.ok) {
      throw new Error(`Server responded with ${response.status}`);
    }
    const data = await response.json();
    
    if (data.enabled) {
      // Lock workdir input in production mode
      if (settingWorkdir) {
        settingWorkdir.disabled = true;
        settingWorkdir.placeholder = "Locked in production mode";
        settingWorkdir.title = "Working directory cannot be changed in production mode";
        const label = settingWorkdir.parentElement?.querySelector('label');
        if (label) {
          label.textContent += " (Locked)";
        }
      }
    }

    if (data.enabled && !data.authenticated) {
      loginModal.classList.add("show");
      return false;
    }
    return true;
  } catch (error) {
    console.error("Failed to check auth status:", error);
    messageFeed.addErrorBanner("Cannot connect to server. Please ensure the backend is running and reachable.");
    if (loadingOverlay) {
      const loadingText = loadingOverlay.querySelector('.loading-text');
      if (loadingText) {
        loadingText.textContent = "Connection failed. Please check server status.";
      }
    }
    return false; // Do not proceed to WebSocket connection if auth check fails
  }
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = loginPassword.value;
  
  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    
    if (response.ok) {
      loginModal.classList.remove("show");
      loginError.classList.add("hidden");
      // Connect to WebSocket after successful login
      wsService.connect().catch(err => {
        console.error("Failed to connect after login:", err);
        messageFeed.addErrorBanner("Login successful, but failed to connect to agent.");
      });
    } else {
      loginError.classList.remove("hidden");
      loginPassword.value = "";
      loginPassword.focus();
    }
  } catch (error) {
    console.error("Login failed:", error);
    loginError.textContent = "Server error during login. Please try again.";
    loginError.classList.remove("hidden");
  }
});

document.addEventListener("DOMContentLoaded", async () => {
  messageFeed.showEmptyState();
  
  const isAuthenticated = await checkAuthStatus();
  if (isAuthenticated) {
    wsService.connect().catch((err) => {
      console.error("Failed to connect to WebSocket server:", err);
      // If we get an error, it might be due to auth even if status check passed (race condition or session expired)
      if (err.message === "Authentication required" || (err instanceof CloseEvent && err.code === 1008)) {
        loginModal.classList.add("show");
      }
    });
  }
});
