import { marked } from "marked";
import hljs from "highlight.js";

export class MarkdownRenderer {
  private container: HTMLElement;
  private rawContent: string = "";
  private lastRenderedLength: number = 0;
  private renderTimeout: number | null = null;

  constructor(container: HTMLElement) {
    this.container = container;
  }

  append(chunk: string): void {
    this.rawContent += chunk;
    if (this.renderTimeout) {
      clearTimeout(this.renderTimeout);
    }
    this.renderTimeout = window.setTimeout(() => {
      this.renderIncremental();
      this.renderTimeout = null;
    }, 100);
  }

  flush(): void {
    if (this.renderTimeout) {
      clearTimeout(this.renderTimeout);
      this.renderTimeout = null;
    }
    this.renderIncremental();
  }

  reset(): void {
    this.rawContent = "";
    this.lastRenderedLength = 0;
    this.container.innerHTML = "";
    if (this.renderTimeout) {
      clearTimeout(this.renderTimeout);
      this.renderTimeout = null;
    }
  }

  getContent(): string {
    return this.rawContent;
  }

  private renderIncremental(): void {
    const newContent = this.rawContent.slice(this.lastRenderedLength);
    if (!newContent) return;

    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = marked.parse(newContent) as string;

    while (tempDiv.firstChild) {
      this.container.appendChild(tempDiv.firstChild);
    }

    this.container.querySelectorAll("pre code:not(.hljs)").forEach((block) => {
      hljs.highlightElement(block as HTMLElement);
    });

    this.addCopyButtonsToNewNodes(tempDiv);

    this.lastRenderedLength = this.rawContent.length;
  }

  private addCopyButtonsToNewNodes(tempDiv: HTMLElement): void {
    this.container.querySelectorAll("pre:not(.has-copy-button)").forEach((pre) => {
      const button = document.createElement("button");
      button.className = "copy-button";
      button.textContent = "Copy";
      button.setAttribute("aria-label", "Copy code to clipboard");

      button.addEventListener("click", async () => {
        const code = pre.querySelector("code");
        if (code) {
          await navigator.clipboard.writeText(code.textContent || "");
          button.textContent = "Copied!";
          button.classList.add("copied");
          setTimeout(() => {
            button.textContent = "Copy";
            button.classList.remove("copied");
          }, 2000);
        }
      });

      const header = document.createElement("div");
      header.className = "code-header";

      const codeBlock = pre.querySelector("code");
      const lang = codeBlock?.className
        .replace("hljs language-", "")
        .replace("language-", "")
        .toUpperCase() || "CODE";

      const langLabel = document.createElement("span");
      langLabel.className = "code-lang";
      langLabel.textContent = lang;

      header.appendChild(langLabel);
      header.appendChild(button);
      pre.insertBefore(header, pre.firstChild);
      pre.classList.add("has-copy-button");
    });
  }
}
