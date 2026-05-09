# AI Engine Web CLI

A modern, web-based chat interface for the AI agent engine that resembles OpenCode's chat UI with rich markdown rendering, code block syntax highlighting, and real-time status indicators.

## Why?

Traditional terminal emulators lack visual feedback for AI agent interactions. The Web CLI provides:
- Rich markdown rendering with proper formatting
- Syntax-highlighted code blocks with copy buttons
- Visual status badges showing what the agent is doing (thinking, processing tool calls)
- Real-time streaming of agent responses via WebSocket
- Auto-expanding input area with keyboard shortcuts

## Features

| Feature | Description |
|---|---|
| **Real-time WebSocket communication** | Bidirectional event-driven protocol with the AI engine |
| **Streaming markdown rendering** | Incremental parsing via `marked` with live DOM updates |
| **Code block syntax highlighting** | 190+ languages via `highlight.js` with Catppuccin Mocha theme |
| **Copy buttons on code blocks** | One-click clipboard copy with language label |
| **Agent status indicators** | Animated badges for thinking, processing, and complete states |
| **Tool call visualization** | Displays tool name and target for each agent tool execution |
| **Auto-expanding input area** | Grows vertically as you type (max 168px), Enter to send, Shift+Enter for newline |
| **Connection status management** | Visual dot indicator with 3-attempt auto-reconnect (5s intervals) |
| **Catppuccin Mocha theme** | Dark theme with CSS custom properties for consistent design tokens |
| **Responsive design** | Works on desktop and mobile with reduced motion support |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- `agent_engine` package available (from parent `src/` directory)

### Backend (FastAPI)

```bash
cd src/web-cli
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.backend.main:app --reload --port 8000
```

### Frontend (Vite + TypeScript)

In a separate terminal:

```bash
cd src/web-cli
npm install
npm run dev
```

Open http://localhost:3000 in your browser. The frontend proxies API requests to the backend at port 8000.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (Vite + TypeScript)                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ InputArea    │  │ MessageFeed  │  │ MarkdownRenderer │  │
│  │ (textarea)   │  │ (DOM mgr)    │  │ (marked + hljs)  │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         └─────────────────┴───────────────────┘            │
│                      WebSocketService                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ WebSocket (/ws)
┌───────────────────────────▼─────────────────────────────────┐
│  FastAPI Backend (Uvicorn, port 8000)                       │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │ main.py              │  │ engine_bridge.py             │ │
│  │ - WebSocket endpoint │  │ - AgentEvent → WS event map  │ │
│  │ - Static file serve  │  │ - _extract_target helper     │ │
│  └──────────┬───────────┘  └──────────────┬───────────────┘ │
│             └─────────────────────────────┘                 │
│                        LightweightEngine                     │
│                     (from agent_engine)                      │
└─────────────────────────────────────────────────────────────┘
```

## WebSocket Protocol

### Client → Server

```json
{
  "event": "user_command",
  "data": {
    "text": "Your command here"
  }
}
```

### Server → Client

| Event | When | Data |
|---|---|---|
| `agent_status` | Agent starts thinking or processing | `{ "status": "thinking" \| "processing", "message": "..." }` |
| `agent_tool_call` | Agent executes a tool | `{ "tool": "tool_name", "target": "target_file" }` |
| `agent_stream_chunk` | Agent streams text/code | `{ "chunk": "text content" }` |
| `agent_complete` | Agent finishes processing | `{}` (empty payload) |
| `error` | Server or engine error | `{ "message": "Error description" }` |

### HTTP Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the frontend `index.html` |
| `GET` | `/health` | Returns `{ "status": "ok", "engine_available": bool }` |
| `WebSocket` | `/ws` | Main WebSocket endpoint for command execution |

## Engine Event Mapping

The `engine_bridge.py` module translates `AgentEvent` types from the engine into WebSocket protocol events:

| AgentEvent.type | WebSocket event | Data mapping |
|---|---|---|
| `"token"` | `agent_stream_chunk` | `data` → `chunk` |
| `"thinking"` | `agent_status` | `data` → `message`, `status: "thinking"` |
| `"tool_start"` | `agent_tool_call` | `metadata.tool_name` → `tool`, `data` → `target` (extracted via `_extract_target`) |
| `"tool_result"` | *(ignored)* | Not forwarded to client |
| `"system"` | `agent_status` | `data` → `message`, `status: "processing"` |
| `"done"` | `agent_complete` | Empty payload |
| `"error"` | `error` | `data` → `message` |

### Target Extraction (`_extract_target`)

For `tool_start` events, the `_extract_target` function extracts a human-readable target from the tool call data:

1. If `data` is a dict, checks keys in priority order: `filepath`, `target`, `file`, `path`, `command`
2. If none match, returns the first key name
3. If `data` is a string, returns it directly
4. Returns `"unknown"` as fallback for empty/None values

## Directory Structure

```
src/web-cli/
├── .venv/                          # Python virtual environment
├── node_modules/                   # Frontend dependencies
├── package.json                    # Frontend: Vite, TS, Tailwind, marked, highlight.js
├── requirements.txt                # Backend: fastapi[standard], uvicorn[standard]
├── tsconfig.json                   # TypeScript: ES2020, strict mode
├── vite.config.ts                  # Vite: root=src/frontend, proxy to backend
├── tailwind.config.js              # Tailwind: Catppuccin Mocha theme extension
├── src/
│   ├── frontend/
│   │   ├── index.html              # Entry HTML with module script
│   │   ├── style.css               # Custom CSS: design tokens, animations, components
│   │   ├── main.ts                 # Application entry: DOM wiring, event loop
│   │   ├── types/
│   │   │   └── events.ts           # TypeScript interfaces for WebSocket events
│   │   ├── services/
│   │   │   └── websocket.ts        # WebSocket connection manager with reconnect logic
│   │   └── components/
│   │       ├── renderer.ts         # Markdown + code block rendering engine
│   │       ├── messageFeed.ts      # Message feed DOM manager (scroll, append)
│   │       └── inputArea.ts        # Auto-expanding textarea with keyboard shortcuts
│   └── backend/
│       ├── main.py                 # FastAPI app: WebSocket endpoint, static file serving
│       └── engine_bridge.py        # Engine event translator (AgentEvent → WS protocol)
└── tests/
    ├── test_backend.py             # Backend WebSocket endpoint tests
    ├── test_engine_bridge.py       # Event translation unit tests
    └── test_qa_additions.py        # Edge case and coverage tests
```

## Frontend Components

### WebSocketService

Manages the WebSocket connection with automatic reconnection:

```typescript
const ws = new WebSocketService("/ws", {
  reconnectAttempts: 3,
  reconnectDelay: 5000,
});

await ws.connect();
ws.onEvent((event) => { /* handle server events */ });
ws.onStatusChange((status) => { /* "connected" | "disconnected" | "connecting" */ });
ws.send("your command here");
```

### MarkdownRenderer

Incremental markdown parsing with syntax highlighting:

```typescript
const renderer = new MarkdownRenderer(container);
renderer.append("## Heading\n");
renderer.append("```python\nprint('hello')\n```");
```

### MessageFeed

Manages the message list DOM:

```typescript
const feed = new MessageFeed(container);
feed.addUserMessage("Hello");
const agentMsg = feed.createAgentMessage();
agentMsg.setStatus("Thinking...");
agentMsg.addToolCall("read_file", "config.json");
agentMsg.getRenderer().append("Response text...");
agentMsg.markComplete();
```

### InputArea

Auto-expanding textarea with keyboard shortcuts:

```typescript
const input = new InputArea(textarea, sendButton);
input.onSend((text) => { /* send command */ });
input.enable();
input.disable();
input.clear();
```

## Configuration

### Backend

| Setting | Default | Description |
|---|---|---|
| Port | 8000 | FastAPI/Uvicorn listen port |
| WebSocket path | `/ws` | WebSocket endpoint |
| Engine import | `agent_engine` | Must be importable from `PYTHONPATH` |

### Frontend

| Setting | Default | Description |
|---|---|---|
| Dev server port | 3000 | Vite dev server |
| Backend proxy | `http://localhost:8000` | Vite proxy target |
| Reconnect attempts | 3 | Max WebSocket reconnect attempts |
| Reconnect delay | 5000ms | Delay between reconnect attempts |

## Development

### Running Tests

```bash
cd src/web-cli
PYTHONPATH=../.. .venv/bin/python -m pytest tests/ -v
```

All 68 tests should pass (27 original + 41 QA additions).

### TypeScript Compilation

```bash
cd src/web-cli
npx tsc --noEmit
```

### Building for Production

```bash
cd src/web-cli
npm run build
```

Output goes to `dist/` and can be served by any static file server.

## Design System

Built with Catppuccin Mocha theme tokens via CSS custom properties:

| Token | Value | Usage |
|---|---|---|
| `--color-base` | `#1e1e2e` | Page background |
| `--color-mantle` | `#181825` | Code block background |
| `--color-surface0` | `#313244` | Cards, panels |
| `--color-text` | `#cdd6f4` | Primary text |
| `--color-blue` | `#89b4fa` | User messages, accents |
| `--color-green` | `#a6e3a1` | Success states |
| `--color-red` | `#f38ba8` | Error states |
| `--color-yellow` | `#f9e2af` | Warning/connecting states |

Typography: Inter (UI), JetBrains Mono (code).

## License

MIT

## FILE CHANGE MANIFEST

MODIFIED: src/README.md
MODIFIED: src/web-cli/README.md
