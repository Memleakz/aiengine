import type { ServerEvent, ClientEvent } from "../types/events";

export type ConnectionStatus = "connected" | "disconnected" | "connecting";

export class WebSocketService {
  private socket: WebSocket | null = null;
  private url: string;
  private reconnectAttempts: number;
  private maxReconnectAttempts: number;
  private reconnectDelay: number;
  private eventCallback: ((event: ServerEvent) => void) | null = null;
  private statusCallback: ((status: ConnectionStatus) => void) | null = null;
  private _status: ConnectionStatus = "disconnected";

  constructor(
    url: string,
    options?: { reconnectAttempts?: number; reconnectDelay?: number }
  ) {
    this.url = url;
    this.maxReconnectAttempts = options?.reconnectAttempts ?? 3;
    this.reconnectDelay = options?.reconnectDelay ?? 5000;
    this.reconnectAttempts = 0;
  }

  async connect(isReconnect = false): Promise<void> {
    this.setStatus("connecting");
    return new Promise((resolve, reject) => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = this.url.startsWith("ws")
        ? this.url
        : `${protocol}//${window.location.host}${this.url}`;

      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        this.reconnectAttempts = 0;
        this.setStatus("connected");
        if (isReconnect) {
          this.eventCallback?.({ event: "reconnected", data: {} });
        }
        resolve();
      };

      this.socket.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data) as ServerEvent;
          this.eventCallback?.(data);
        } catch {
          console.warn("Failed to parse WebSocket message:", event.data);
        }
      };

      this.socket.onclose = () => {
        this.setStatus("disconnected");
        this.attemptReconnect();
      };

      this.socket.onerror = (error) => {
        console.error("WebSocket error:", error);
        reject(error);
      };
    });
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error("Max reconnect attempts reached");
      return;
    }

    this.reconnectAttempts++;
    console.log(
      `Reconnecting (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`
    );

    setTimeout(() => {
      this.connect(true).catch(() => {
        console.error("Reconnection failed");
      });
    }, this.reconnectDelay);
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.setStatus("disconnected");
  }

  send(command: string): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.error("WebSocket not connected");
      return;
    }

    const message: ClientEvent = {
      event: "user_command",
      data: { text: command.trim() },
    };

    this.socket.send(JSON.stringify(message));
  }

  sendSettings(settings: UpdateSettingsEvent["data"]): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.error("WebSocket not connected");
      return;
    }

    const message: UpdateSettingsEvent = {
      event: "update_settings",
      data: settings,
    };

    this.socket.send(JSON.stringify(message));
  }

  onEvent(callback: (event: ServerEvent) => void): void {
    this.eventCallback = callback;
  }

  onStatusChange(callback: (status: ConnectionStatus) => void): void {
    this.statusCallback = callback;
  }

  private setStatus(status: ConnectionStatus): void {
    this._status = status;
    this.statusCallback?.(status);
  }

  get isConnected(): boolean {
    return this._status === "connected";
  }

  get status(): ConnectionStatus {
    return this._status;
  }
}
