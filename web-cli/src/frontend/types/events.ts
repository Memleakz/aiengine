export interface UserCommandEvent {
  event: "user_command";
  data: {
    text: string;
  };
}

export interface AgentStatusEvent {
  event: "agent_status";
  data: {
    status: "thinking" | "processing" | "complete";
    message: string;
  };
}

export interface AgentToolCallEvent {
  event: "agent_tool_call";
  data: {
    tool: string;
    target: string;
  };
}

export interface AgentStreamChunkEvent {
  event: "agent_stream_chunk";
  data: {
    chunk: string;
  };
}

export interface AgentThinkingEvent {
  event: "agent_thinking";
  data: {
    chunk: string;
  };
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  reasoning_tokens: number;
}

export interface AgentCompleteEvent {
  event: "agent_complete";
  data: {
    usage?: TokenUsage;
    session_usage?: TokenUsage;
  };
}

export interface ErrorEvent {
  event: "error";
  data: {
    message: string;
  };
}

export interface ReconnectEvent {
  event: "reconnected";
  data: Record<string, never>;
}

export interface UpdateSettingsEvent {
  event: "update_settings";
  data: {
    workdir?: string;
    system_prompt?: string;
    parameters?: {
      temperature?: number;
      top_p?: number;
      max_tokens?: number;
    };
  };
}

export interface SettingsUpdatedEvent {
  event: "settings_updated";
  data: {
    updated: string[];
  };
}

export type ClientEvent = UserCommandEvent | UpdateSettingsEvent;

export type ServerEvent =
  | AgentStatusEvent
  | AgentThinkingEvent
  | AgentToolCallEvent
  | AgentStreamChunkEvent
  | AgentCompleteEvent
  | ErrorEvent
  | ReconnectEvent
  | SettingsUpdatedEvent;

export type WsEvent = ClientEvent | ServerEvent;

export interface ToolCall {
  tool: string;
  target: string;
}

export interface MessageState {
  id: string;
  type: "user" | "agent";
  content: string;
  status?: string;
  toolCalls: ToolCall[];
  isComplete: boolean;
}
