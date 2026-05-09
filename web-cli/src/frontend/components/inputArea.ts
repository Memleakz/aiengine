export class InputArea {
  private textarea: HTMLTextAreaElement;
  private sendButton: HTMLButtonElement;
  private sendCallback: ((text: string) => void) | null = null;

  constructor(textarea: HTMLTextAreaElement, sendButton: HTMLButtonElement) {
    this.textarea = textarea;
    this.sendButton = sendButton;
    this.setupEventListeners();
  }

  private setupEventListeners(): void {
    this.textarea.addEventListener("input", () => this.autoResize());
    this.textarea.addEventListener("keydown", (e: KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }
    });

    this.sendButton.addEventListener("click", () => {
      this.handleSend();
    });
  }

  private autoResize(): void {
    this.textarea.style.height = "auto";
    const maxHeight = 168;
    this.textarea.style.height = `${Math.min(
      this.textarea.scrollHeight,
      maxHeight
    )}px`;
  }

  private handleSend(): void {
    const text = this.textarea.value.trim();
    if (text && this.sendCallback) {
      this.sendCallback(text);
      this.clear();
    }
  }

  onSend(callback: (text: string) => void): void {
    this.sendCallback = callback;
  }

  enable(): void {
    this.textarea.disabled = false;
    this.sendButton.disabled = false;
    this.textarea.classList.remove("disabled");
    this.sendButton.classList.remove("disabled");
  }

  disable(): void {
    this.textarea.disabled = true;
    this.sendButton.disabled = true;
    this.textarea.classList.add("disabled");
    this.sendButton.classList.add("disabled");
  }

  clear(): void {
    this.textarea.value = "";
    this.autoResize();
  }

  focus(): void {
    this.textarea.focus();
  }
}
