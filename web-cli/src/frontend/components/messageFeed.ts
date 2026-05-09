import { MarkdownRenderer } from "./renderer";
import type { ToolCall } from "../types/events";

export interface AgentMessageHandle {
  setStatus(status: string): void;
  appendThinking(chunk: string): void;
  addToolCall(tool: string, target: string): void;
  addToolResult(tool: string, output: string, truncated: boolean): void;
  getRenderer(): MarkdownRenderer;
  markComplete(): void;
  markAsInterrupted(reason: string): void;
}

export class MessageFeed {
  private container: HTMLElement;
  private messages: Map<string, HTMLElement> = new Map();
  private viewLatestBtn: HTMLElement | null = null;
  private scrollThreshold = 100;

  constructor(container: HTMLElement) {
    this.container = container;
    this.setupScrollListener();
  }

  private setupScrollListener(): void {
    this.container.addEventListener("scroll", () => {
      this.updateViewLatestVisibility();
    });
  }

  private isNearBottom(): boolean {
    return (
      this.container.scrollHeight -
        this.container.scrollTop -
        this.container.clientHeight <
      this.scrollThreshold
    );
  }

  private updateViewLatestVisibility(): void {
    if (this.isNearBottom()) {
      this.hideViewLatestButton();
    } else {
      this.showViewLatestButton();
    }
  }

  private showViewLatestButton(): void {
    if (this.viewLatestBtn) return;

    this.viewLatestBtn = document.createElement("button");
    this.viewLatestBtn.className = "view-latest-btn";
    this.viewLatestBtn.innerHTML = "View latest ▼";
    this.viewLatestBtn.addEventListener("click", () => {
      this.scrollToBottom(true);
    });

    this.container.parentElement?.appendChild(this.viewLatestBtn);
  }

  private hideViewLatestButton(): void {
    if (this.viewLatestBtn) {
      this.viewLatestBtn.remove();
      this.viewLatestBtn = null;
    }
  }

  addUserMessage(text: string): void {
    this.hideEmptyState();
    const messageDiv = document.createElement("div");
    messageDiv.className = "message user-message";
    messageDiv.setAttribute("role", "listitem");

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = text;

    messageDiv.appendChild(bubble);
    this.container.appendChild(messageDiv);
    this.scrollToBottom(true);
  }

  createAgentMessage(): AgentMessageHandle {
    this.hideEmptyState();
    const id = `msg-${Date.now()}`;
    const messageDiv = document.createElement("div");
    messageDiv.id = id;
    messageDiv.className = "message agent-message";
    messageDiv.setAttribute("role", "listitem");

    const header = document.createElement("div");
    header.className = "agent-header";
    header.innerHTML = '<span class="agent-icon">🤖</span><span class="agent-label">Agent</span>';

    const statusBadge = document.createElement("div");
    statusBadge.className = "status-badge";
    statusBadge.setAttribute("aria-live", "polite");

    const toolCallsContainer = document.createElement("div");
    toolCallsContainer.className = "tool-calls-container";

    const markdownContainer = document.createElement("div");
    markdownContainer.className = "markdown-content";

    const thoughtContainer = document.createElement("div");
    thoughtContainer.className = "thought-container hidden";
    thoughtContainer.innerHTML = `
      <div class="thought-header">
        <span class="thought-icon">🧠</span>
        <span class="thought-label">Thought Process</span>
        <button class="thought-toggle">[Show]</button>
      </div>
      <div class="thought-content"></div>
    `;

    const thoughtContent = thoughtContainer.querySelector(".thought-content") as HTMLElement;
    const thoughtToggle = thoughtContainer.querySelector(".thought-toggle") as HTMLButtonElement;
    
    thoughtToggle.addEventListener("click", () => {
      const isVisible = thoughtContainer.classList.toggle("expanded");
      thoughtToggle.textContent = isVisible ? "[Hide]" : "[Show]";
      this.scrollToBottom(true);
    });

    messageDiv.appendChild(header);
    messageDiv.appendChild(statusBadge);
    messageDiv.appendChild(thoughtContainer);
    messageDiv.appendChild(toolCallsContainer);
    messageDiv.appendChild(markdownContainer);
    this.container.appendChild(messageDiv);
    this.messages.set(id, messageDiv);

    const renderer = new MarkdownRenderer(markdownContainer);

    return {
      setStatus: (status: string) => {
        const isActive = ["thinking", "requesting", "processing", "iter"].some(s => status.toLowerCase().includes(s));
        statusBadge.textContent = isActive ? "" : status;
        statusBadge.classList.remove("status-complete");
        if (isActive) {
          statusBadge.classList.add("status-thinking");
        } else {
          statusBadge.classList.remove("status-thinking");
        }
      },
      appendThinking: (chunk: string) => {
        thoughtContainer.classList.remove("hidden");
        thoughtContent.textContent += chunk;
        this.scrollToBottom(true);
      },
      addToolCall: (tool: string, target: string) => {
        const toolDiv = document.createElement("div");
        toolDiv.className = "tool-call";
        
        const isLong = target.length > 60 || target.includes("\n");
        
        toolDiv.innerHTML = `
          <div class="tool-call-header">
            <span class="tool-icon">⚙️</span>
            <span class="tool-name">${tool}</span>
            ${isLong ? '<button class="tool-args-toggle">[Details]</button>' : `<span class="tool-args-preview">: ${target}</span>`}
          </div>
          ${isLong ? `<div class="tool-args-content hidden"><pre><code>${target}</code></pre></div>` : ""}
        `;
        
        if (isLong) {
          const toggle = toolDiv.querySelector(".tool-args-toggle") as HTMLButtonElement;
          const content = toolDiv.querySelector(".tool-args-content") as HTMLElement;
          toggle.addEventListener("click", () => {
            const isVisible = content.classList.toggle("hidden");
            toggle.textContent = isVisible ? "[Details]" : "[Hide]";
            this.scrollToBottom(true);
          });
        }
        
        toolCallsContainer.appendChild(toolDiv);
        this.scrollToBottom(true);
      },
      addToolResult: (tool: string, output: string, truncated: boolean) => {
        const resultDiv = document.createElement("div");
        resultDiv.className = "tool-result";

        const toggleBtn = document.createElement("button");
        toggleBtn.className = "tool-result-toggle";
        toggleBtn.textContent = "[View Output]";

        const contentDiv = document.createElement("div");
        contentDiv.className = "tool-result-content hidden";

        const pre = document.createElement("pre");
        pre.className = "tool-output-pre";
        pre.textContent = output;
        contentDiv.appendChild(pre);

        if (truncated) {
          const warning = document.createElement("div");
          warning.className = "truncation-warning";
          warning.textContent = "⚠️ Output truncated (50k character limit)";
          contentDiv.appendChild(warning);
        }

        toggleBtn.addEventListener("click", () => {
          const isHidden = contentDiv.classList.toggle("hidden");
          toggleBtn.textContent = isHidden ? "[View Output]" : "[Hide Output]";
          this.scrollToBottom(true);
        });

        resultDiv.appendChild(toggleBtn);
        resultDiv.appendChild(contentDiv);
        toolCallsContainer.appendChild(resultDiv);
        this.scrollToBottom(true);
      },
      getRenderer: () => renderer,
      markComplete: () => {
        statusBadge.textContent = "✓ Complete";
        statusBadge.classList.remove("status-thinking");
        statusBadge.classList.add("status-complete");
        setTimeout(() => {
          statusBadge.style.opacity = "0";
          setTimeout(() => statusBadge.remove(), 300);
        }, 2000);
      },
      markAsInterrupted: (reason: string) => {
        statusBadge.textContent = `Interrupted: ${reason}`;
        statusBadge.classList.remove("status-thinking", "status-complete");
        statusBadge.classList.add("status-interrupted");
      },
    };
  }

  scrollToBottom(smooth: boolean = true): void {
    requestAnimationFrame(() => {
      if (smooth) {
        this.container.scrollTo({
          top: this.container.scrollHeight,
          behavior: "smooth",
        });
      } else {
        this.container.scrollTop = this.container.scrollHeight;
      }
    });
  }

  showEmptyState(): void {
    if (this.container.querySelector(".empty-state")) return;

    const emptyState = document.createElement("div");
    emptyState.className = "empty-state";
    emptyState.innerHTML = `
      <div class="empty-icon">🤖</div>
      <h2 class="empty-title">AI Agent Interface</h2>
      <p class="empty-subtitle">Start a conversation by typing a command below.</p>
    `;
    this.container.appendChild(emptyState);
  }

  hideEmptyState(): void {
    const emptyState = this.container.querySelector(".empty-state");
    if (emptyState) {
      emptyState.remove();
    }
  }

  addErrorBanner(message: string): void {
    const banner = document.createElement("div");
    banner.className = "error-banner";
    banner.innerHTML = `
      <span class="error-icon">⚠️</span>
      <span class="error-text">${message}</span>
    `;
    this.container.appendChild(banner);
    this.scrollToBottom(true);
  }

  addSystemBanner(message: string): void {
    const banner = document.createElement("div");
    banner.className = "system-banner";
    banner.innerHTML = `
      <span class="system-icon">ℹ️</span>
      <span class="system-text">${message}</span>
    `;
    this.container.appendChild(banner);
    this.scrollToBottom(true);
  }
}
