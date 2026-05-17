import asyncio
import functools
import json
import os
import re
from collections.abc import AsyncGenerator, Callable

from openai import NOT_GIVEN, AsyncOpenAI


from agent_engine.events import AgentEvent
from agent_engine.mcp_client import MCPServerManager
from agent_engine.persistence import TraceLogger
import uuid
from agent_engine.tools import (
    ToolRegistry,
    ask_user,
    bash_tool,
    code_analysis,
    cron_tool,
    file_ops,
    get_time,
    git_tool,
    manage_tasks,
    manage_todo,
    network_tool,
    notebook_edit,
    python_repl,
    search_ops,
    skill_tool,
    sleep,
    subagent,
    system_info,
    web_fetch,
    web_search,
)

_THINK_TAG_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_BUILTIN_TOOL_NAMES = frozenset(("bash", "read_file", "file_write", "file_edit", "file_delete", "directory_create", "glob_search", "grep_search", "web_fetch", "web_search", "ask_user", "python_repl", "sleep", "get_time", "manage_tasks", "subagent", "notebook_edit", "git_tool", "manage_todo", "cron_tool", "skill_tool", "code_analysis", "system_info", "network_tool"))


class LightweightEngine:
    def __init__(
        self,
        model: str = None,
        api_key: str = None,
        base_url: str = None,
        manage_history: bool = True,
        max_history_length: int = 40,
        max_iterations: int = 20,
        allowed_tools: list[str] = None,
        workdir: str | None = None,
        system_prompt: str | None = "You are a helpful AI coding assistant.",
        load_local_instructions: bool = True,
        extra_completion_kwargs: dict | None = None,
        max_retries: int = 3,
        max_reasoning_tokens: int = 8192,
        debug: bool | None = None,
    ) -> None:
        self.model = model or os.getenv("AGENT_MODEL", "gpt-4o")
        self.manage_history = manage_history
        self.history = []
        self.max_history_length = max_history_length
        self.max_iterations = max_iterations
        self.max_reasoning_tokens = max_reasoning_tokens
        self.load_local_instructions = load_local_instructions
        if workdir:
            self.workdir = os.path.abspath(workdir)
        else:
            self.workdir = os.path.abspath(os.getenv("AGENT_WORKDIR") or os.getcwd())
        self.system_prompt = system_prompt
        self.extra_completion_kwargs = extra_completion_kwargs or {}
        self.max_retries = max_retries
        if debug is not None:
            self.debug = debug
        else:
            self.debug = os.getenv("AGENT_DEBUG", "false").lower() in ("true", "1", "yes")
        self._is_running = False
        self._subscribers: list[asyncio.Queue[AgentEvent]] = []
        
        # Persistence & Usage
        self.session_id = str(uuid.uuid4())
        self.session_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
        log_dir = os.path.join(self.workdir, "logs")
        self.logger = TraceLogger(os.path.join(log_dir, "agent_traces.db"))

        if self.model == "z-ai/glm4.7":
            # Inject required kwargs for the GLM reasoning model
            self.extra_completion_kwargs.setdefault("max_tokens", 16384)
            self.extra_completion_kwargs.setdefault("extra_body", {
                "chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}
            })

        _base = (base_url or os.getenv("AGENT_BASE_URL", "")).rstrip("/")
        _is_ollama = "11434" in _base or _base.endswith("/ollama") or "ollama" in _base.lower()
        if _is_ollama:
            _ollama_host = "/".join(_base.split("/")[:3])  # e.g. http://127.0.0.1:11434
            _native_ctx = self._query_ollama_context(_ollama_host, self.model)
            _use_ctx = min(_native_ctx, 32768)
            self.extra_completion_kwargs.setdefault("max_tokens", _use_ctx)
            
            # OpenAI compatibility layer uses options.num_ctx for native Ollama context window size
            existing_body = self.extra_completion_kwargs.get("extra_body", {})
            if "options" not in existing_body:
                existing_body["options"] = {}
            existing_body["options"]["num_ctx"] = _use_ctx
            self.extra_completion_kwargs["extra_body"] = existing_body

        resolved_key = (
            api_key
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        resolved_base_url = base_url or os.getenv("AGENT_BASE_URL")

        if not resolved_key:
            # Fallback for local execution (e.g. Ollama)
            resolved_key = "dummy-ollama-key"
            if not resolved_base_url:
                resolved_base_url = "http://127.0.0.1:11434/v1"

        self.client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=resolved_base_url,
        )

        self.tools = ToolRegistry()
        self._mcp_managers: list[MCPServerManager] = []

        if allowed_tools:
            self.bash_tool_instance = bash_tool.BashTool(workdir=self.workdir)
            def bind_workdir(fn: Callable) -> Callable:
                @functools.wraps(fn)
                async def wrapper(*args, **kwargs):
                    return await fn(*args, workdir=self.workdir, **kwargs)
                return wrapper

            tool_method_map = {
                "bash": self.bash_tool_instance.bash,
                "read_file": bind_workdir(file_ops.read_file),
                "file_write": bind_workdir(file_ops.file_write),
                "file_edit": bind_workdir(file_ops.file_edit),
                "patch_code_range": bind_workdir(file_ops.patch_code_range),
                "file_delete": bind_workdir(file_ops.file_delete),

                "directory_create": bind_workdir(file_ops.directory_create),
                "glob_search": bind_workdir(search_ops.glob_search),
                "grep_search": bind_workdir(search_ops.grep_search),
                "web_fetch": web_fetch,
                "web_search": web_search,
                "ask_user": ask_user,
                "python_repl": python_repl,
                "sleep": sleep,
                "get_time": get_time,
                "manage_tasks": bind_workdir(manage_tasks),
                "subagent": bind_workdir(subagent),
                "notebook_edit": bind_workdir(notebook_edit),
                "git_tool": bind_workdir(git_tool),
                "manage_todo": bind_workdir(manage_todo),
                "cron_tool": cron_tool,
                "skill_tool": bind_workdir(skill_tool),
                "code_analysis": bind_workdir(code_analysis),
                "system_info": system_info,
                "network_tool": network_tool,
            }
            for tool_name in allowed_tools:
                if tool_name not in tool_method_map:
                    raise ValueError(f"Unknown built-in tool: '{tool_name}'")
                self.tools.register(tool_method_map[tool_name])

    def subscribe(self, queue: asyncio.Queue[AgentEvent] = None) -> asyncio.Queue[AgentEvent]:
        """Subscribe to engine events. Returns a queue that will receive all yielded AgentEvents."""
        if queue is None:
            queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[AgentEvent]) -> None:
        """Unsubscribe a queue from engine events."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def _broadcast(self, event: AgentEvent, should_log: bool = True) -> None:
        """Internal: broadcast an event to all subscribers and log it if requested."""
        if should_log:
            self.logger.log_event(self.session_id, event.type, event.data, event.metadata)
        for queue in self._subscribers:
            queue.put_nowait(event)

    def set_system_prompt(self, new_prompt: str) -> None:
        """Update the agent's system prompt. Takes effect on the next run() call."""
        self.system_prompt = new_prompt

    def set_workdir(self, new_workdir: str) -> None:
        """Update the working directory for the engine and its builtin tools."""
        self.workdir = os.path.abspath(new_workdir)
        if hasattr(self, "bash_tool_instance"):
            self.bash_tool_instance.workdir = self.workdir

    def update_completion_kwargs(self, **kwargs) -> None:
        """Update model parameters like temperature, top_p, max_tokens, etc."""
        self.extra_completion_kwargs.update(kwargs)

    def set_debug(self, enabled: bool) -> None:
        """Enable or disable diagnostic debug output."""
        self.debug = enabled

    def _unwrap_tool_args(self, tool_name: str, kwargs: Any) -> dict:
        """Multi-pass unwrapping to handle common model hallucinations/double-JSON/list-wrapping."""
        for _ in range(4):  # One extra pass for deep nesting
            if not isinstance(kwargs, dict):
                if isinstance(kwargs, list) and len(kwargs) > 0:
                    if isinstance(kwargs[0], dict):
                        kwargs = kwargs[0]
                        continue
                    elif isinstance(kwargs[0], str) and tool_name == "bash":
                        kwargs = {"command": kwargs[0]}
                        continue
                if isinstance(kwargs, str):
                    s = kwargs.strip()
                    if s.startswith(('{', '[')):
                        try:
                            kwargs = json.loads(s)
                            continue
                        except: pass
                    if tool_name == "bash":
                        kwargs = {"command": s}
                        continue
                break

            if len(kwargs) == 1:
                key = next(iter(kwargs))
                val = kwargs[key]
                
                # Unwrap nested dict
                if isinstance(val, dict):
                    kwargs = val
                    continue
                
                # Handle "command": ["ls", "-l"] or "args": ["ls", "-l"]
                if key in ("command", "args", "arguments", "parameters") and isinstance(val, list):
                    cmd_str = " ".join(str(v) for v in val)
                    kwargs = {"command": cmd_str}
                    continue

                # Handle "parameters": {"command": "..."}
                if key in ("parameters", "args", "kwargs") and isinstance(val, dict):
                    kwargs = val
                    continue

                # Handle string values that might be encoded JSON or pseudo-YAML
                if isinstance(val, str):
                    s = val.strip()
                    # JSON check
                    if s.startswith(('{', '[')):
                        try:
                            inner = json.loads(s)
                            if isinstance(inner, dict):
                                kwargs = inner
                                continue
                            if isinstance(inner, list) and tool_name == "bash":
                                kwargs = {"command": " ".join(str(v) for v in inner)}
                                continue
                        except: pass
                    
                    # Pseudo-YAML check (e.g. "args: [...]")
                    for prefix in ("args:", "command:", "parameters:", "kwargs:"):
                        if s.lower().startswith(prefix):
                            inner_s = s[len(prefix):].strip()
                            if inner_s.startswith(('{', '[')):
                                try:
                                    inner_p = json.loads(inner_s)
                                    if isinstance(inner_p, list):
                                        kwargs = {"command": " ".join(str(v) for v in inner_p)}
                                    else:
                                        kwargs = inner_p if isinstance(inner_p, dict) else {"command": str(inner_p)}
                                    break
                                except: pass
                            kwargs = {"command": inner_s}
                            break
                    else:
                        # No prefix found, but if it was the only key and tool is bash, maybe it's just the command
                        if key in ("args", "parameters", "kwargs") and tool_name == "bash":
                            kwargs = {"command": s}
                            continue
                    
                    if kwargs != {key: val}: continue
            
            # Handle mixed case: {"command": "...", "args": [...]}
            if "args" in kwargs and "command" not in kwargs and tool_name == "bash":
                val = kwargs["args"]
                if isinstance(val, list):
                    kwargs = {"command": " ".join(str(v) for v in val)}
                    continue

            # Handle "kwargs": "..." where it should be a key-value or empty
            if len(kwargs) == 1 and next(iter(kwargs)) == "kwargs" and isinstance(kwargs["kwargs"], str):
                if tool_name == "bash":
                    kwargs = {"command": kwargs["kwargs"]}
                    continue
                else:
                    # For other tools, 'kwargs' as a string is likely a hallucination of the argument block itself
                    # If it's not a dict, we probably want an empty dict for tools that take no args
                    kwargs = {}
                    break

            break
        return kwargs if isinstance(kwargs, dict) else {}

    def _get_effective_system_prompt(self) -> tuple[str | None, list[str]]:
        """Combine base system prompt with local agent instructions if they exist."""
        prompt = self.system_prompt or ""
        diagnostics = []

        if not self.load_local_instructions:
            diagnostics.append("Automatic loading of local instructions (agent.md) is disabled.")
            return (prompt if prompt else None), diagnostics
        
        # Look for agent instructions in workdir and CWD
        # Support multiple filenames: agents.md, agent.md, AGENTS.md
        candidates = ["agents.md", "agent.md", "AGENTS.md"]
        search_dirs = []
        if hasattr(self, "workdir") and self.workdir:
            search_dirs.append(self.workdir)
        
        # Add CWD if it's different from workdir
        cwd = os.getcwd()
        if cwd not in search_dirs:
            search_dirs.append(cwd)
            
        local_instr = ""
        found_path = None
        
        diagnostics.append(f"Searching for agent instructions in: {search_dirs}")
        
        for d in search_dirs:
            for cand in candidates:
                path = os.path.join(d, cand)
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            if content:
                                local_instr = content
                                found_path = path
                                break
                    except Exception as e:
                        diagnostics.append(f"Error reading {path}: {e}")
            if local_instr:
                break
                
        if local_instr:
            diagnostics.append(f"Found agent instructions at: {found_path}")
            if prompt:
                prompt += "\n\n"
            prompt += local_instr
        else:
            diagnostics.append("No local agent instructions (agents.md/agent.md) found.")
            
        return (prompt if prompt else None), diagnostics

    @staticmethod
    def _query_ollama_context(ollama_host: str, model_name: str, default: int = 32768) -> int:
        import urllib.request
        try:
            payload = json.dumps({"name": model_name}).encode()
            req = urllib.request.Request(
                f"{ollama_host}/api/show",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
            model_info = data.get("model_info", {})
            for key, val in model_info.items():
                if key.endswith(".context_length") and isinstance(val, int):
                    return val
        except Exception:
            pass
        return default

    @staticmethod
    def _rescue_html_json(raw: str) -> dict | None:
        result_chars: list[str] = []
        i = 0
        in_string = False
        escape_next = False
        depth = 0
        while i < len(raw):
            ch = raw[i]
            if escape_next:
                result_chars.append(ch)
                escape_next = False
                i += 1
                continue
            if ch == '\\':
                result_chars.append(ch)
                escape_next = True
                i += 1
                continue
            if ch == '"':
                if not in_string:
                    in_string = True
                    result_chars.append(ch)
                    i += 1
                    continue
                else:
                    rest = raw[i + 1:]
                    stripped = rest.lstrip()
                    # Close the string if followed by JSON structural chars OR at end of input
                    if not stripped or stripped[0] in (',', '}', ']', ':'):
                        in_string = False
                        result_chars.append(ch)
                        i += 1
                        continue
                    else:
                        result_chars.append('\\"')
                        i += 1
                        continue
            if in_string:
                if ch == '\n':
                    result_chars.append('\\n')
                elif ch == '\t':
                    result_chars.append('\\t')
                elif ch == '\r':
                    result_chars.append('\\r')
                else:
                    result_chars.append(ch)
                i += 1
                continue
            if not in_string:
                if ch in ('{', '['):
                    depth += 1
                elif ch in ('}', ']'):
                    depth -= 1
            result_chars.append(ch)
            i += 1
        repaired = ''.join(result_chars)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            if in_string:
                try:
                    return json.loads(repaired + '"' + ('}' * depth))
                except json.JSONDecodeError:
                    pass
            for d in range(depth, 0, -1):
                try:
                    return json.loads(repaired + ('}' * d))
                except json.JSONDecodeError:
                    pass
            return None

    async def load_mcp_config(self, config_path: str = "mcp_config.json") -> None:
        """Load and connect enabled MCP servers from a JSON config file.

        Expected schema::

            {
              "mcp_servers": {
                "<name>": {"command": str, "args": list[str], "enabled": bool}
              }
            }
        """
        resolved_path = config_path
        if not os.path.isabs(resolved_path):
            # Try relative to CWD
            if not os.path.exists(resolved_path):
                # Try relative to workdir
                workdir_cand = os.path.join(self.workdir, resolved_path)
                if os.path.exists(workdir_cand):
                    resolved_path = workdir_cand
                else:
                    # Try relative to the package source directory (where mcp_config.json usually lives)
                    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    pkg_cand = os.path.join(pkg_dir, resolved_path)
                    if os.path.exists(pkg_cand):
                        resolved_path = pkg_cand

        try:
            with open(resolved_path) as f:
                raw = f.read()
        except FileNotFoundError:
            print(f"Warning: MCP config file '{config_path}' not found. Running without MCPs.")
            return

        try:
            config = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid MCP config JSON: {exc}") from exc

        servers = config.get("mcp_servers", {})
        for name, details in servers.items():
            if not details.get("enabled"):
                continue
            try:
                if "auto_init" in details:
                    await self.connect_mcp(
                        command=details["command"],
                        args=details["args"],
                        auto_init=details["auto_init"]
                    )
                else:
                    await self.connect_mcp(
                        command=details["command"],
                        args=details["args"]
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"Error connecting MCP '{name}': {exc}")

    async def connect_mcp(self, command: str, args: list[str], auto_init: list[dict] | dict | None = None) -> None:
        manager = MCPServerManager(command, args)
        try:
            session = await manager.connect()
            result = await session.list_tools()
            for tool in result.tools:
                self.tools.register_mcp_tool(tool, session, workdir_getter=lambda: self.workdir)
            self._mcp_managers.append(manager)

            # Process auto-initialization calls if configured
            if auto_init:
                calls = [auto_init] if isinstance(auto_init, dict) else auto_init
                for call in calls:
                    tool_name = call.get("tool")
                    tool_args = call.get("arguments", {})
                    # Dynamically resolve ${workdir} placeholders
                    resolved_args = {}
                    for k, v in tool_args.items():
                        if isinstance(v, str) and v == "${workdir}":
                            resolved_args[k] = self.workdir
                        else:
                            resolved_args[k] = v
                    
                    if tool_name:
                        print(f"  Auto-initializing MCP tool '{tool_name}'...")
                        init_res = await self._execute_tool(tool_name, resolved_args)
                        print(f"  Auto-init response: {init_res[0]}")
        except Exception:
            # If initialization fails (e.g., server crashes or times out), we MUST
            # cleanly disconnect to prevent the AsyncExitStack from being garbage
            # collected while active. GC'ing an active anyio task group will cause
            # a catastrophic 'Attempted to exit cancel scope in a different task' crash.
            await manager.disconnect()
            raise


    async def close(self) -> None:
        self._is_running = False
        managers = list(self._mcp_managers)
        self._mcp_managers.clear()
        for manager in reversed(managers):
            # We explicitly reverse the shutdown order (LIFO) because AnyIO relies
            # on strict cancel-scope nesting. If we shut down in FIFO order, the
            # inner scopes would be disconnected out of order, raising exceptions
            # and leaking task cancellations into the event loop.
            try:
                await manager.disconnect()
            except BaseException:
                pass



    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit, ensuring resources are freed."""
        await self.close()

    async def _execute_tool(self, name: str, args: dict, timeout: int = 30) -> tuple[str, bool]:
        """Execute a tool with timeout and output capping, returning (result_string, is_truncated)."""
        # Hard cap for storage in message history — keeps context tokens low.
        # read_file gets a generous cap; bash/search tools get a tighter one.
        _HISTORY_CAP = 16_000
        _VERBOSE_TOOLS = {"read_file", "web_fetch", "get_ast", "get_symbols", "run_query", "analyze_project"}  # tools that intentionally produce long output
        is_truncated = False
        try:
            result = await asyncio.wait_for(self.tools.dispatch(name, args), timeout=timeout)
            result_str = str(result)
            cap = 100_000 if name in _VERBOSE_TOOLS else _HISTORY_CAP
            if len(result_str) > cap:
                is_truncated = True
                result_str = result_str[:cap] + f"\n\n[Output truncated at {cap:,} chars — use targeted queries to get more]"
            return result_str, is_truncated

        except TimeoutError:
            return f"Error: Tool '{name}' timed out after {timeout}s.", False
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}", False

    async def run(
        self,
        prompt: str,
        history: list = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        self._is_running = True
        if self.manage_history:
            if history is not None:
                self.history = history  # work with caller's list directly
            working_messages = self.history
        else:
            working_messages = list(history) if history else []

        system_role = "developer" if self.model.startswith(("o1", "o3")) else "system"

        if self.manage_history and len(working_messages) > self.max_history_length:
            has_system = bool(working_messages) and working_messages[0].get("role") in ("system", "developer")
            if has_system:
                system_msg = working_messages[0]
                tail = working_messages[-(self.max_history_length - 1):]
                working_messages.clear()
                working_messages.append(system_msg)
                working_messages.extend(tail)
            else:
                tail = working_messages[-self.max_history_length:]
                working_messages.clear()
                working_messages.extend(tail)

        effective_prompt, diagnostics = self._get_effective_system_prompt()
        if self.debug:
            for diag in diagnostics:
                ev = AgentEvent(type="system", data=f"[DEBUG] {diag}")
                self._broadcast(ev)
                yield ev

        if effective_prompt:
            if working_messages and working_messages[0].get("role") in ("system", "developer"):
                working_messages[0] = {**working_messages[0], "content": effective_prompt, "role": system_role}
            else:
                working_messages.insert(0, {"role": system_role, "content": effective_prompt})

        working_messages.append({"role": "user", "content": prompt})
        schemas = self.tools.get_all_schemas()
        tools_param = schemas if schemas else NOT_GIVEN

        run_usage = None
        iteration = 0
        while self._is_running:
            iteration += 1
            if iteration > self.max_iterations:
                ev = AgentEvent(type="system", data=f"[WARN] Max iterations ({self.max_iterations}) reached. Stopping.")
                self._broadcast(ev)
                yield ev
                break

            ev = AgentEvent(type="system", data=f"Requesting completion (iter {iteration}/{self.max_iterations})...")
            self._broadcast(ev)
            yield ev

            create_kwargs = {
                "model": self.model,
                "messages": working_messages,
                "tools": tools_param,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if self.extra_completion_kwargs:
                create_kwargs.update(self.extra_completion_kwargs)

            # Retry logic for OpenAI API
            stream = None
            last_err = None
            for attempt in range(self.max_retries + 1):
                try:
                    stream = await self.client.chat.completions.create(**create_kwargs)
                    break
                except Exception as e:
                    import openai
                    is_retryable = isinstance(e, (openai.RateLimitError, openai.InternalServerError, openai.APIStatusError))
                    # APIStatusError is retryable if code is 503 or 502
                    if isinstance(e, openai.APIStatusError):
                        if e.status_code == 400 and "does not support tools" in str(e).lower():
                            msg = f"Model '{self.model}' does not support tool calling."
                            if "ollama" in str(self.client.base_url).lower():
                                msg += f" (Hint: Try 'ollama pull {self.model}' to ensure you have the latest version with tool support, or update Ollama to 0.3.0+)"
                            ev = AgentEvent(type="system", data=f"{msg} Retrying without tools...")
                            self._broadcast(ev)
                            yield ev
                            create_kwargs["tools"] = NOT_GIVEN
                            continue
                        elif e.status_code not in (502, 503):
                            is_retryable = False

                    if is_retryable and attempt < self.max_retries:
                        delay = (2 ** attempt) + 1
                        ev = AgentEvent(type="system", data=f"API Error ({e}). Retrying in {delay}s (attempt {attempt+1}/{self.max_retries})...", metadata={"retry_count": attempt+1})
                        self._broadcast(ev)
                        yield ev
                        await asyncio.sleep(delay)
                    else:
                        last_err = e
                        break

            if not self._is_running:
                break

            if not stream:
                ev = AgentEvent(type="error", data=f"API Error after {self.max_retries} retries: {str(last_err)}")
                self._broadcast(ev)
                yield ev
                break

            text_content = ""
            tool_call_accumulator: dict[int, dict] = {}
            run_usage = None
            in_think_block = False

            stream_buffer = ""
            local_reasoning_chars = 0
            async for chunk in stream:
                if not self._is_running:
                    break
                if chunk.usage:
                    u = chunk.usage
                    details = getattr(u, "completion_tokens_details", None)
                    reasoning_tokens = getattr(details, "reasoning_tokens", 0) if details else 0
                    
                    run_usage = {
                        "prompt_tokens": u.prompt_tokens,
                        "completion_tokens": u.completion_tokens,
                        "total_tokens": u.total_tokens,
                        "reasoning_tokens": reasoning_tokens,
                    }
                    # Accumulate session usage
                    self.session_usage["prompt_tokens"] += u.prompt_tokens
                    self.session_usage["completion_tokens"] += u.completion_tokens
                    self.session_usage["total_tokens"] += u.total_tokens
                    self.session_usage["reasoning_tokens"] = self.session_usage.get("reasoning_tokens", 0) + reasoning_tokens
                    continue
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue
                reasoning = (
                    getattr(delta, "reasoning_content", None) or 
                    getattr(delta, "reasoning", None) or 
                    getattr(delta, "thought", None)
                )
                if reasoning:
                    local_reasoning_chars += len(reasoning)
                    ev = AgentEvent(type="thinking", data=reasoning)
                    self._broadcast(ev, should_log=False)
                    yield ev
                if delta.content:
                    # Append new content to the buffer
                    stream_buffer += delta.content
                    
                    start_tags = ["<think>", "<|think|>", "<thought>", "<|thought|>"]
                    end_tags = ["</think>", "<|/think|>", "</thought>", "|>", "]]>"]
                    
                    while stream_buffer:
                        if not in_think_block:
                            # Look for any start tag
                            best_tag = None
                            best_pos = -1
                            for tag in start_tags:
                                pos = stream_buffer.find(tag)
                                if pos != -1 and (best_pos == -1 or pos < best_pos):
                                    best_pos = pos
                                    best_tag = tag
                            
                            if best_tag:
                                # Found a start tag!
                                before = stream_buffer[:best_pos]
                                if before:
                                    text_content += before
                                    ev = AgentEvent(type="token", data=before)
                                    self._broadcast(ev, should_log=False)
                                    yield ev
                                in_think_block = True
                                stream_buffer = stream_buffer[best_pos + len(best_tag):]
                                continue
                            else:
                                # No start tag found. Yield most of the buffer but keep enough to catch a partial tag.
                                if len(stream_buffer) > 12:
                                    to_yield = stream_buffer[:-12]
                                    text_content += to_yield
                                    ev = AgentEvent(type="token", data=to_yield)
                                    self._broadcast(ev, should_log=False)
                                    yield ev
                                    stream_buffer = stream_buffer[-12:]
                                break
                        else:
                            # Currently in a thinking block, look for any end tag
                            best_tag = None
                            best_pos = -1
                            for tag in end_tags:
                                pos = stream_buffer.find(tag)
                                if pos != -1 and (best_pos == -1 or pos < best_pos):
                                    best_pos = pos
                                    best_tag = tag
                            
                            if best_tag:
                                # Found an end tag!
                                thought = stream_buffer[:best_pos]
                                if thought:
                                    local_reasoning_chars += len(thought)
                                    ev = AgentEvent(type="thinking", data=thought)
                                    self._broadcast(ev, should_log=False)
                                    yield ev
                                in_think_block = False
                                stream_buffer = stream_buffer[best_pos + len(best_tag):]
                                continue
                            else:
                                # No end tag yet. Yield most of the thinking content.
                                if len(stream_buffer) > 12:
                                    to_yield = stream_buffer[:-12]
                                    
                                    # Sanity check: if reasoning tokens (approx) exceed limit, stop.
                                    # We use character count as a proxy (4 chars/token).
                                    approx_reasoning_tokens = self.session_usage.get("reasoning_tokens", 0) + (local_reasoning_chars + len(to_yield)) // 4
                                    if approx_reasoning_tokens > self.max_reasoning_tokens:
                                        ev = AgentEvent(type="system", data=f"[ERROR] Reasoning token limit ({self.max_reasoning_tokens}) exceeded. Stopping.")
                                        self._broadcast(ev)
                                        yield ev
                                        self._is_running = False
                                        break

                                    local_reasoning_chars += len(to_yield)
                                    ev = AgentEvent(type="thinking", data=to_yield)
                                    self._broadcast(ev, should_log=False)
                                    yield ev
                                    stream_buffer = stream_buffer[-12:]
                                break
                
                # Ensure the buffer is cleared at the end of the stream
                if not delta.content and stream_buffer:
                    if in_think_block:
                        local_reasoning_chars += len(stream_buffer)
                        ev = AgentEvent(type="thinking", data=stream_buffer)
                    else:
                        text_content += stream_buffer
                        ev = AgentEvent(type="token", data=stream_buffer)
                    self._broadcast(ev, should_log=False)
                    yield ev
                    stream_buffer = ""

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_accumulator:
                            tool_call_accumulator[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name or "" if tc.function else "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_call_accumulator[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_call_accumulator[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_call_accumulator[idx]["arguments"] += tc.function.arguments

            if local_reasoning_chars > 0:
                estimated_reasoning = local_reasoning_chars // 4
                if run_usage:
                    if not run_usage.get("reasoning_tokens"):
                        run_usage["reasoning_tokens"] = estimated_reasoning
                        self.session_usage["reasoning_tokens"] = self.session_usage.get("reasoning_tokens", 0) + estimated_reasoning
                else:
                    run_usage = {
                        "prompt_tokens": 0,
                        "completion_tokens": estimated_reasoning,
                        "total_tokens": estimated_reasoning,
                        "reasoning_tokens": estimated_reasoning,
                    }
                    self.session_usage["reasoning_tokens"] = self.session_usage.get("reasoning_tokens", 0) + estimated_reasoning
                    self.session_usage["completion_tokens"] = self.session_usage.get("completion_tokens", 0) + estimated_reasoning
                    self.session_usage["total_tokens"] = self.session_usage.get("total_tokens", 0) + estimated_reasoning

            if not self._is_running:
                break

            if tool_call_accumulator:
                tool_calls_block = []
                to_execute = []
                for acc in tool_call_accumulator.values():
                    call_id = acc["id"]
                    tool_name = acc["name"]
                    raw_args_str = acc["arguments"]
                    decoder = json.JSONDecoder()
                    pos = 0
                    found_any = False
                    while pos < len(raw_args_str):
                        while pos < len(raw_args_str) and raw_args_str[pos] not in ('{', '['):
                            pos += 1
                        if pos >= len(raw_args_str):
                            break
                        try:
                            obj, next_pos = decoder.raw_decode(raw_args_str, pos)
                            to_execute.append({"id": call_id, "name": tool_name, "kwargs": obj, "sub_idx": len(to_execute)})
                            found_any = True
                            while next_pos < len(raw_args_str) and raw_args_str[next_pos].isspace():
                                next_pos += 1
                            pos = next_pos
                        except json.JSONDecodeError:
                            remaining = raw_args_str[pos:].strip()
                            rescued = self._rescue_html_json(remaining)
                            if rescued:
                                to_execute.append({"id": call_id, "name": tool_name, "kwargs": rescued, "sub_idx": len(to_execute)})
                                found_any = True
                            break
                    if not found_any:
                        to_execute.append({"id": call_id, "name": tool_name, "kwargs": {}, "sub_idx": 0, "error": True})

                for i, item in enumerate(to_execute):
                    unique_id = f"{item['id']}_{i}" if len(to_execute) > 1 else item['id']
                    item["final_id"] = unique_id
                    tool_calls_block.append({
                        "id": unique_id,
                        "type": "function",
                        "function": {"name": item["name"], "arguments": json.dumps(item["kwargs"])},
                    })
                working_messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls_block})

                # Parallel Tool Execution
                event_queue = asyncio.Queue()
                self.subscribe(event_queue)
                
                async def run_one_tool(item: dict):
                    call_id = item["final_id"]
                    tool_name = item["name"]
                    kwargs = self._unwrap_tool_args(tool_name, item["kwargs"])

                    original_name = tool_name
                    # Shims & Rerouting
                    if "command" in kwargs and tool_name != "bash":
                        tool_name = "bash"
                    elif "content" in kwargs and tool_name not in ("file_write", "file_edit"):
                        if "filepath" not in kwargs:
                            c_low = kwargs["content"].lower()
                            if "<!doctype html" in c_low or "<html" in c_low:
                                kwargs["filepath"] = "index.html"
                            elif "body {" in c_low or "color:" in c_low:
                                kwargs["filepath"] = "style.css"
                            else:
                                kwargs["filepath"] = "generated_file.txt"
                        tool_name = "file_write"
                    elif "old_string" in kwargs and tool_name != "file_edit":
                        tool_name = "file_edit"
                    elif "filepath" in kwargs and "content" not in kwargs and "command" not in kwargs:
                        # Legitimate tools that use 'filepath' should not be rerouted to bash.
                        # Only reroute if the tool name is unknown or explicitly 'bash' without an action.
                        known_file_tools = ("read_file", "file_write", "file_edit", "file_delete", "patch_code_range")
                        if tool_name not in known_file_tools:
                            if tool_name != "bash":
                                tool_name = "bash"
                                kwargs["action"] = "read"
                            elif kwargs.get("action") != "read":
                                kwargs["action"] = "read"


                    if tool_name != original_name:
                        self._broadcast(AgentEvent(type="system", data=f"[SHIM] Rerouted {original_name}→{tool_name}"))

                    # Tool Start
                    target_preview = ""
                    if tool_name in ("bash", "file_write", "file_edit", "read_file"):
                        target_preview = kwargs.get("command") or kwargs.get("path") or kwargs.get("filepath") or ""
                    
                    self._broadcast(AgentEvent(
                        type="tool_start", 
                        data=kwargs, 
                        metadata={"tool_name": tool_name, "call_id": call_id, "target": target_preview}
                    ))

                    # Execution
                    if item.get("error"):
                        result_str = "Error: Tool call arguments could not be parsed as JSON."
                        is_truncated = False
                    else:
                        result_str, is_truncated = await self._execute_tool(tool_name, kwargs)

                    # Tool Result
                    self._broadcast(AgentEvent(
                        type="tool_result", 
                        data=result_str, 
                        metadata={
                            "tool_name": tool_name, 
                            "call_id": call_id,
                            "is_truncated": is_truncated
                        }
                    ))
                    return {"role": "tool", "tool_call_id": call_id, "content": result_str}

                try:
                    # Group tools by name to ensure sequential execution for the same tool
                    # (Avoids race conditions in SQL, file ops, etc.)
                    groups: dict[str, list[dict]] = {}
                    for item in to_execute:
                        # We need to resolve the tool name first to group correctly
                        temp_kwargs = self._unwrap_tool_args(item["name"], item["kwargs"])
                        resolved_name = item["name"]
                        if "command" in temp_kwargs and resolved_name != "bash":
                            resolved_name = "bash"
                        # ... other shims could go here, but bash is the most common one
                        
                        if resolved_name not in groups:
                            groups[resolved_name] = []
                        groups[resolved_name].append(item)

                    async def run_group(tool_items: list[dict]):
                        for item in tool_items:
                            if not self._is_running:
                                break
                            result_msg = await run_one_tool(item)
                            working_messages.append(result_msg)
                            nonlocal pending_count
                            pending_count -= 1

                    # Start groups in parallel
                    pending_count = len(to_execute)
                    group_tasks = [asyncio.create_task(run_group(items)) for items in groups.values()]
                    
                    # Wait for all groups to complete while yielding events from the queue
                    while pending_count > 0 or not event_queue.empty():
                        # Yield all currently available events
                        try:
                            while not event_queue.empty():
                                yield event_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        
                        if pending_count == 0:
                            break
                            
                        # Wait a bit or wait for any group to finish a step
                        await asyncio.sleep(0.05)
                    
                    # Ensure all group tasks are actually finished/cleaned up
                    if group_tasks:
                        await asyncio.gather(*group_tasks, return_exceptions=True)
                finally:
                    self.unsubscribe(event_queue)

                if not self._is_running:
                    break
                continue
            else:
                if text_content:
                    working_messages.append({"role": "assistant", "content": text_content})
                    # Log the full assistant message once after streaming tokens
                    self._broadcast(AgentEvent(type="assistant_message", data=text_content))
                break

        self._is_running = False
        ev = AgentEvent(
            type="done", 
            data="Run complete", 
            metadata={
                "final_history": working_messages, 
                "usage": run_usage,
                "session_usage": self.session_usage
            }
        )
        self._broadcast(ev)
        yield ev
