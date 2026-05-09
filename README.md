# agent_engine

A lightweight, async, event-driven Python library for running ReAct AI agents — embeddable in any async web backend.

## Why?

Building AI agents in Python shouldn't require a framework. Existing solutions (LangChain, LlamaIndex) carry hundreds of dependencies, force synchronous patterns incompatible with FastAPI, and bury you in abstractions. `agent_engine` is different:

- **~700 lines of stdlib + two dependencies** (`openai`, `mcp`) — nothing else.
- **Fully async** — every tool, every LLM call, every file read is `await`-able. Drop it straight into FastAPI with zero blocking.
- **Event-driven streaming** — the engine is an async generator yielding typed `AgentEvent` objects. Pipe tokens to WebSockets, SSE, or a terminal with the same three lines of code.
- **Native MCP support** — connect to any Model Context Protocol server (databases, APIs, filesystems) in two lines. The lifecycle (connect → use → disconnect) is handled for you.

## Quick Start

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...        # or OPENROUTER_API_KEY
export AGENT_MODEL=gpt-4o           # optional, defaults to gpt-4o
```

```python
import asyncio
from agent_engine.engine import LightweightEngine

async def main():
    engine = LightweightEngine(allowed_tools=["bash", "web_fetch"])

    async for event in engine.run("What Python version is installed?"):
        if event.type == "token":
            print(event.data, end="", flush=True)
        elif event.type == "tool_start":
            print(f"\n[tool] {event.metadata['tool_name']} — {event.data}")
        elif event.type == "tool_result":
            print(f"[result] {event.data[:120]}")
        elif event.type == "done":
            print("\n✓ done")

asyncio.run(main())
```

## Features

| Feature | Description |
|---|---|
| **Streaming ReAct loop** | Async generator yielding `AgentEvent` objects — tokens, tool calls, results, errors, done |
| **21 built-in tools** | `bash`, `file_write`, `file_edit`, `glob_search`, `grep_search` (from `builtin_tools.py`), plus `web_fetch`, `web_search`, `ask_user`, `python_repl`, `sleep`, `get_time`, `manage_tasks`, `subagent`, `notebook_edit`, `git_tool`, `manage_todo`, `cron_tool`, `skill_tool`, `code_analysis`, `system_info`, `network_tool` (from `tools/`) — all async; sandboxed file I/O |
| **Auto schema generation** | Register any typed Python async function; its OpenAI tool schema is generated via `inspect` |
| **MCP integration** | Connect to stdio MCP servers; their tools are auto-registered and called transparently |
| **MCP config file** | Load multiple MCP servers from a `mcp_config.json` file via `load_mcp_config()` — no code changes needed to add or disable servers |
| **Multi-provider LLM** | One `AsyncOpenAI` client targets OpenAI, OpenRouter, vLLM, or Ollama via `base_url` |
| **History management** | Optional in-memory history with configurable length cap and system-prompt preservation |
| **Token usage tracking** | `"done"` event exposes `prompt_tokens`, `completion_tokens`, and `total_tokens` for cost estimation |
| **Thinking model support** | Native `reasoning_content` parsing for o1/o3/DeepSeek-R1 models; `"thinking"` event type |
| **GLM reasoning support** | `z-ai/glm4.7` auto-injects `enable_thinking` chat template kwargs |
| **Ollama context detection** | When `base_url` points to Ollama, context length is auto-queried via `/api/show` and capped at 32768 |

## Installation

**Requirements:** Python 3.11+, `pip`

```bash
# From the src/ directory (this directory)
pip install -r requirements.txt
```

The only runtime dependencies are:

```
openai>=2.33.0
mcp>=1.27.0
```

## Usage

### Basic — text response

```python
engine = LightweightEngine()

async for event in engine.run("Explain asyncio in one sentence."):
    if event.type == "token":
        print(event.data, end="", flush=True)
```

### With built-in tools

```python
engine = LightweightEngine(allowed_tools=["bash", "web_search", "code_analysis"])

async for event in engine.run("Search for Python best practices and analyze the code."):
    if event.type == "token":
        print(event.data, end="", flush=True)
    elif event.type == "tool_start":
        print(f"\n→ {event.metadata['tool_name']}({event.data})")
    elif event.type == "tool_result":
        print(f"← {event.data[:200]}")
```

Available built-in tool names (21 total):
`bash`, `file_write`, `file_edit`, `glob_search`, `grep_search`, `web_fetch`, `web_search`, `ask_user`, `python_repl`, `sleep`, `get_time`, `manage_tasks`, `subagent`, `notebook_edit`, `git_tool`, `manage_todo`, `cron_tool`, `skill_tool`, `code_analysis`, `system_info`, `network_tool`

> **Security note:** `bash`, `file_write`, `file_edit`, `glob_search`, and `grep_search` execute arbitrary commands or file operations. Setting
> `workdir` constrains only their *starting directory* — they are **not** OS-level sandboxed.
> File operations enforce strict workdir containment (blocks `..` traversal and symlink escapes).
> Never expose these tools to untrusted user input without additional safeguards.

### The `bash` tool — unified action interface

The `bash` built-in tool dispatches via an `action` parameter:

| Action | Description | Required args |
|---|---|---|
| `"run"` (default) | Execute a shell command synchronously | `command` |
| `"background"` | Start a command without waiting; returns `job_id` | `command` |
| `"logs"` | Read buffered output from a background job | `job_id`; optional `tail_lines` (default 100) |
| `"kill"` | Terminate a background job | `job_id` |
| `"read"` | Read a file's contents (alias for `read_file`) | `filepath`; optional `start_line`, `end_line` |

### With an MCP server

```python
import asyncio
from agent_engine.engine import LightweightEngine

async def main():
    engine = LightweightEngine(allowed_tools=["bash"])

    await engine.connect_mcp(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sqlite", "--db", "./mydb.db"]
    )

    try:
        async for event in engine.run("Create a users table and insert a test row."):
            if event.type == "token":
                print(event.data, end="", flush=True)
    finally:
        await engine.close()

asyncio.run(main())
```

### Loading MCPs from a config file

```json
{
  "mcp_servers": {
    "sqlite": {
      "command": "npx",
      "args": ["-y", "mcp-sqlite", "--db", "./my_database.db"],
      "enabled": true
    }
  }
}
```

```python
engine = LightweightEngine(allowed_tools=["bash"])
await engine.load_mcp_config("mcp_config.json")
try:
    async for event in engine.run("List the tables."):
        if event.type == "token":
            print(event.data, end="", flush=True)
finally:
    await engine.close()
```

**Error handling:** missing file → warning + continues; `"enabled": false` → skipped; server connect fail → non-fatal; bad JSON → raises `ValueError`.

### With persistent conversation history

```python
history = []

async for event in engine.run("My name is Alice.", history=history):
    pass

async for event in engine.run("What is my name?", history=history):
    if event.type == "token":
        print(event.data, end="", flush=True)
# → "Your name is Alice."
```

### With directory sandboxing

```python
engine = LightweightEngine(
    allowed_tools=["bash", "file_write", "glob_search"],
    workdir="./my_project",
)
```

`workdir` defaults to `os.getcwd()`. File operations (`file_write`, `file_edit`, `glob_search`, `grep_search`) enforce strict containment — `..` traversal and symlink escapes are blocked.

### With dynamic system prompts

```python
engine = LightweightEngine(system_prompt="You are a frontend developer.")

async for event in engine.run("Scaffold a new component."):
    if event.type == "token":
        print(event.data, end="", flush=True)

engine.set_system_prompt("You are a strict security auditor.")

async for event in engine.run("Review the login handler."):
    if event.type == "token":
        print(event.data, end="", flush=True)
```

### Reading token usage

```python
async for event in engine.run(prompt):
    if event.type == "token":
        print(event.data, end="", flush=True)
    elif event.type == "done":
        usage = event.metadata.get("usage") or {}
        print(f"\n📊 {usage.get('prompt_tokens')} in | {usage.get('completion_tokens')} out")
```

### Embedding in FastAPI

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from agent_engine.engine import LightweightEngine
import json

app = FastAPI()
engine = LightweightEngine(allowed_tools=["bash"])

@app.get("/chat")
async def chat(prompt: str):
    async def event_stream():
        async for event in engine.run(prompt):
            yield f"data: {json.dumps({'type': event.type, 'data': str(event.data)})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

## Configuration

| Parameter | Env var fallback | Default | Description |
|---|---|---|---|
| `model` | `AGENT_MODEL` | `"gpt-4o"` | LLM model name |
| `api_key` | `OPENROUTER_API_KEY`, then `OPENAI_API_KEY` | — | API key (required) |
| `base_url` | `AGENT_BASE_URL` | `None` | Override LLM endpoint |
| `manage_history` | — | `True` | Mutate the passed-in `history` list on each `run()` |
| `max_history_length` | — | `40` | Max messages kept; oldest non-system messages pruned |
| `max_iterations` | — | `20` | Max ReAct iterations before stopping |
| `allowed_tools` | — | `None` | List of built-in tool names to register; `None` = no tools |
| `workdir` | — | `os.getcwd()` | Root directory for the sandbox |
| `system_prompt` | — | `"You are a helpful AI coding assistant."` | System message; `None` = no injection |
| `extra_completion_kwargs` | — | `{}` | Extra kwargs passed to OpenAI completion API |

### Provider examples

```python
# OpenRouter
engine = LightweightEngine(model="anthropic/claude-3-5-sonnet", api_key="sk-or-...", base_url="https://openrouter.ai/api/v1")

# Local Ollama (context length auto-detected, capped at 32768)
engine = LightweightEngine(model="llama3", api_key="ollama", base_url="http://localhost:11434/v1")

# vLLM
engine = LightweightEngine(model="mistralai/Mistral-7B-Instruct-v0.2", api_key="EMPTY", base_url="http://localhost:8000/v1")

# GLM reasoning model (thinking auto-enabled)
engine = LightweightEngine(model="z-ai/glm4.7", api_key="...", base_url="https://open.bigmodel.cn/api/paas/v4/")
```

## Development

### Running tests

```bash
cd src/
pip install pytest pytest-asyncio
pytest tests/ -v
```

### Project structure

```
agent_engine/
├── __init__.py        # Public surface: LightweightEngine, AgentEvent
├── events.py          # AgentEvent dataclass
├── builtin_tools.py   # BuiltinTools class (workdir-scoped) + unified bash/file/glob/grep tools
├── mcp_client.py      # MCPServerManager — MCP stdio subprocess lifecycle
├── engine.py          # LightweightEngine — ReAct loop as async generator
└── tools/             # 16 modular tool implementations + __init__.py + registry.py (ToolRegistry)
    ├── ask_user.py
    ├── code_analysis.py
    ├── cron_tool.py
    ├── get_time.py
    ├── git_tool.py
    ├── manage_tasks.py
    ├── network_tool.py
    ├── notebook_edit.py
    ├── python_repl.py
    ├── registry.py
    ├── skill_tool.py
    ├── sleep.py
    ├── subagent.py
    ├── system_info.py
    ├── todo_tool.py
    ├── web_fetch.py
    ├── web_search.py
    └── __init__.py
tests/
├── test_events.py
├── test_builtin_tools.py
├── test_tools.py
├── test_engine.py
└── test_qa_additions.py
```

### Registering a custom tool

```python
async def search_web(query: str, max_results: int = 5) -> str:
    """Search the web and return top results as plain text."""
    return results

engine = LightweightEngine()
engine.tools.register(search_web)
```

The schema is derived automatically from the function signature via `inspect`.

### Dependency graph (no circular imports)

```
events  ←  builtin_tools  ←  mcp_client  ←  tools/registry  ←  engine
           ↑
            └── tools/ (16 modular tools)
```

## Architecture

The engine implements the [ReAct](https://arxiv.org/abs/2210.03629) (Reasoning + Acting) pattern:

```
User prompt → LLM call (streaming) → text only? → yield "done"
                                   → tool call? → yield "tool_start" → execute → yield "tool_result" → loop
```

**Event types emitted:**

| Event type | When | `data` |
|---|---|---|
| `"system"` | Before each LLM call | Status string |
| `"token"` | Each streamed text chunk | Token string |
| `"thinking"` | Model outputs reasoning (o1/o3/DeepSeek-R1/GLM) | Reasoning content string |
| `"tool_start"` | Before tool execution | Parsed args dict |
| `"tool_result"` | After tool execution | Result string |
| `"error"` | On LLM/tool failure | Error message |
| `"done"` | Loop complete | `"Run complete"`; `metadata["final_history"]`; `metadata["usage"]` |

## Web CLI

A production-ready web interface for interacting with the AI engine in real time.

- **Authentication**: Session-based auth with admin password.
- **Isolation**: Strict `AGENT_WORKDIR` and environment filtering.
- **Tech Stack**: FastAPI backend, Vite + TS frontend.

```bash
cd web-cli
uvicorn src.backend.main:app --reload --port 8000
```

Open http://localhost:3000. 

> **Production Note**: For a secure production setup using dedicated system users, systemd, and **automated vhost provisioning (Nginx/Apache)**, see the **[Deployment Guide](../DEPLOYMENT_GUIDE.md)**.

See `web-cli/README.md` for full details.

## License

MIT
