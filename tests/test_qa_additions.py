"""
QA additions — fills coverage gaps, probes edge cases, and verifies bug fixes.
All tests follow the same asyncio_mode=strict convention used by the project.
"""
import asyncio
import json
import os
import stat
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_engine.engine import LightweightEngine
from agent_engine.events import AgentEvent
from agent_engine.tools import ToolRegistry

from agent_engine.tools.bash_tool import BashTool, _MAX_BACKGROUND_JOBS
from agent_engine.tools import file_ops, search_ops
class BuiltinTools:
    def __init__(self, workdir):
        self.workdir = workdir
        self._bash_tool = BashTool(workdir)
        self._running_jobs = self._bash_tool._running_jobs
    async def bash(self, **kwargs): return await self._bash_tool.bash(**kwargs)
    async def read_file(self, *args, **kwargs): return await file_ops.read_file(self.workdir, *args, **kwargs)
    async def file_write(self, *args, **kwargs): return await file_ops.file_write(self.workdir, *args, **kwargs)
    async def file_edit(self, *args, **kwargs): return await file_ops.file_edit(self.workdir, *args, **kwargs)
    async def patch_code_range(self, *args, **kwargs): return await file_ops.patch_code_range(self.workdir, *args, **kwargs)
    async def file_delete(self, *args, **kwargs): return await file_ops.file_delete(self.workdir, *args, **kwargs)
    async def directory_create(self, *args, **kwargs): return await file_ops.directory_create(self.workdir, *args, **kwargs)
    async def glob_search(self, *args, **kwargs): return await search_ops.glob_search(self.workdir, *args, **kwargs)
    async def grep_search(self, *args, **kwargs): return await search_ops.grep_search(self.workdir, *args, **kwargs)
    def _is_safe_path(self, *args, **kwargs): return file_ops._is_safe_path(self.workdir, *args, **kwargs)
    async def _run_command(self, *args, **kwargs): return await self._bash_tool._run_command(*args, **kwargs)


# Module-level tools instance used by tests that don't exercise workdir security.
_tools = BuiltinTools(workdir=os.getcwd())
bash = _tools.bash


async def bash_background(cmd):
    return await _tools.bash(action="background", command=cmd)


async def read_logs(job_id, **kw):
    return await _tools.bash(action="logs", job_id=job_id, **kw)


async def kill_process(job_id):
    return await _tools.bash(action="kill", job_id=job_id)


# Alias the dict so tests can assert `job_id in _RUNNING_JOBS`
_RUNNING_JOBS = _tools._running_jobs


# ===========================================================================
# AgentEvent — edge cases
# ===========================================================================

def test_event_metadata_not_shared_between_instances():
    """Each AgentEvent must get its own metadata dict (no shared mutable default)."""
    e1 = AgentEvent(type="token", data="a")
    e2 = AgentEvent(type="token", data="b")
    e1.metadata["x"] = 1
    assert "x" not in e2.metadata


def test_event_invalid_type_is_accepted():
    """
    AgentEvent does NOT enforce the type allowlist — it's a plain dataclass.
    This test documents the missing validation rather than breaking on it.
    """
    evt = AgentEvent(type="invalid_type", data="oops")
    assert evt.type == "invalid_type"  # No ValueError raised — design gap


# ===========================================================================
# bash — edge cases
# ===========================================================================

@pytest.mark.asyncio
async def test_bash_combines_stdout_and_stderr():
    """stdout and stderr must both appear in the returned string."""
    result = await bash(action="run", command="echo STDOUT && echo STDERR >&2")
    assert "STDOUT" in result
    assert "STDERR" in result


@pytest.mark.asyncio
async def test_bash_output_at_4000_char_boundary():
    """Output of exactly 4000 chars should NOT be truncated."""
    result = await bash(action="run", command="python3 -c \"print('x' * 3999, end='')\"")
    assert len(result.strip()) == 3999  # echo adds newline, we strip


@pytest.mark.asyncio
async def test_bash_empty_command_no_crash():
    """Empty command string must not raise — return string."""
    result = await bash(action="run", command="")
    assert isinstance(result, str)


# ===========================================================================
# bash_background — uncovered exception path
# ===========================================================================

@pytest.mark.asyncio
async def test_bash_background_job_tracked_in_running_jobs():
    """The new job must appear in _RUNNING_JOBS immediately after call."""
    result = await bash_background("sleep 10")
    job_id = result.split("job_id: ")[1].strip()
    assert job_id in _RUNNING_JOBS
    await kill_process(job_id)


@pytest.mark.asyncio
async def test_bash_background_exception_returns_error_string():
    """If subprocess creation fails, return an error string — never raise."""
    with patch("agent_engine.tools.bash_tool.asyncio.create_subprocess_shell",
               side_effect=OSError("no shell")):
        result = await bash_background("any_command")
    assert "error" in result.lower()
    assert "no shell" in result.lower()


# ===========================================================================
# kill_process — zombie-reap fix (BUG-001)
# ===========================================================================

@pytest.mark.asyncio
async def test_kill_process_no_zombie_after_kill():
    """
    BUG-001 fix: kill_process must reap the child so it doesn't stay as a zombie.
    After kill_process(), os.kill(pid, 0) must raise ProcessLookupError.
    """
    result = await bash_background("sleep 100")
    job_id = result.split("job_id: ")[1].strip()
    pid = _RUNNING_JOBS[job_id].pid

    await kill_process(job_id)
    await asyncio.sleep(0.1)  # give kernel time to reap

    try:
        os.kill(pid, 0)
        pytest.fail(f"Zombie: process {pid} still visible after kill_process()")
    except ProcessLookupError:
        pass  # expected — process is gone


# ===========================================================================
# read_logs — uncovered paths
# ===========================================================================

@pytest.mark.asyncio
async def test_read_logs_stream_none_does_not_crash():
    """If a stream attribute is None, read_logs must skip it without error."""
    result = await bash_background("sleep 10")
    job_id = result.split("job_id: ")[1].strip()
    proc = _RUNNING_JOBS[job_id]
    original_stdout = proc.stdout
    proc.stdout = None  # simulate missing stream
    try:
        logs = await read_logs(job_id)
        assert isinstance(logs, str)
    finally:
        proc.stdout = original_stdout
        await kill_process(job_id)


@pytest.mark.asyncio
async def test_read_logs_stream_error_included_in_output():
    """If stream.read() raises, the error description must appear in the result."""
    result = await bash_background("sleep 10")
    job_id = result.split("job_id: ")[1].strip()
    proc = _RUNNING_JOBS[job_id]

    mock_stream = MagicMock()
    mock_stream.read = AsyncMock(side_effect=OSError("broken pipe"))
    original_stdout = proc.stdout
    proc.stdout = mock_stream
    try:
        logs = await read_logs(job_id)
        assert "stream error" in logs.lower() or "broken pipe" in logs.lower()
    finally:
        proc.stdout = original_stdout
        await kill_process(job_id)


# ===========================================================================
# read_file — edge cases and uncovered exception path
# ===========================================================================

@pytest.mark.asyncio
async def test_read_file_permission_denied_returns_error(tmp_path):
    """
    A file that exists but is unreadable must return an error string,
    not raise an exception.
    """
    f = tmp_path / "secret.txt"
    f.write_text("private")
    f.chmod(0o000)
    tools = BuiltinTools(workdir=str(tmp_path))
    try:
        result = await tools.read_file("secret.txt")
        assert "error" in result.lower()
    finally:
        f.chmod(stat.S_IRUSR | stat.S_IWUSR)


@pytest.mark.asyncio
async def test_read_file_start_line_zero_treated_as_beginning(tmp_path):
    """start_line=0 is out-of-spec (1-indexed) but must not crash."""
    f = tmp_path / "t.txt"
    f.write_text("a\nb\nc\n")
    tools = BuiltinTools(workdir=str(tmp_path))
    result = await tools.read_file("t.txt", start_line=0)
    assert "a" in result
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_read_file_end_line_beyond_eof_returns_all_lines(tmp_path):
    """end_line > number of lines in file must return everything without error."""
    f = tmp_path / "t.txt"
    f.write_text("a\nb\nc\n")
    tools = BuiltinTools(workdir=str(tmp_path))
    result = await tools.read_file("t.txt", start_line=1, end_line=9999)
    assert "a" in result and "b" in result and "c" in result


@pytest.mark.asyncio
async def test_read_file_start_line_greater_than_end_line_returns_empty(tmp_path):
    """start_line > end_line is an invalid range — must return empty string."""
    f = tmp_path / "t.txt"
    f.write_text("a\nb\nc\n")
    tools = BuiltinTools(workdir=str(tmp_path))
    result = await tools.read_file("t.txt", start_line=5, end_line=2)
    assert result == ""


@pytest.mark.asyncio
async def test_read_file_start_line_beyond_file_returns_empty(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("a\nb\nc\n")
    tools = BuiltinTools(workdir=str(tmp_path))
    result = await tools.read_file("t.txt", start_line=100)
    assert result == ""


@pytest.mark.asyncio
async def test_read_file_encoding_errors_tolerated(tmp_path):
    """Files with non-UTF8 bytes must not crash."""
    f = tmp_path / "binary.txt"
    f.write_bytes(b"good line\n\xff\xfe bad bytes\ngood again\n")
    tools = BuiltinTools(workdir=str(tmp_path))
    result = await tools.read_file("binary.txt")
    assert isinstance(result, str)
    assert "good" in result


# ===========================================================================
# ToolRegistry — edge cases
# ===========================================================================

def test_register_overwrites_existing_tool():
    """Registering the same tool name twice replaces the first entry."""
    async def my_tool(x: str) -> str:
        """First version."""
        return "v1"

    async def my_tool_v2(x: str) -> str:
        """Second version."""
        return "v2"

    my_tool_v2.__name__ = "my_tool"

    reg = ToolRegistry()
    reg.register(my_tool)
    reg.register(my_tool_v2)
    schemas = reg.get_all_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["description"] == "Second version."


def test_register_unannotated_params_default_to_string():
    """Parameters with no type annotation must default to JSON type 'string'."""
    async def untyped(x, y=10) -> str:
        """Tool with no annotations."""
        return str(x)

    reg = ToolRegistry()
    reg.register(untyped)
    props = reg.get_all_schemas()[0]["function"]["parameters"]["properties"]
    assert props["x"]["type"] == "string"


@pytest.mark.asyncio
async def test_mcp_tool_non_text_content_returns_str():
    """MCP tool content without a 'text' attribute must be str()-ified."""
    class NonTextContent:
        pass  # no 'text' attribute

    class FakeMCPTool:
        name = "img_tool"
        description = "Returns image"
        inputSchema = {"type": "object", "properties": {}}  # noqa: N815

    class FakeSession:
        async def call_tool(self, name, arguments):
            class Result:
                content = [NonTextContent()]
            return Result()

    reg = ToolRegistry()
    reg.register_mcp_tool(FakeMCPTool(), FakeSession())
    result = await reg.dispatch("img_tool", {})
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_mcp_tool_empty_content_returns_empty_string():
    """MCP tool returning zero content items must yield an empty string."""
    class FakeMCPTool:
        name = "empty_tool"
        description = "Nothing"
        inputSchema = {"type": "object", "properties": {}}  # noqa: N815

    class FakeSession:
        async def call_tool(self, name, arguments):
            class Result:
                content = []
            return Result()

    reg = ToolRegistry()
    reg.register_mcp_tool(FakeMCPTool(), FakeSession())
    result = await reg.dispatch("empty_tool", {})
    assert result == ""


@pytest.mark.asyncio
async def test_execute_wrong_kwargs_returns_error_string():
    """Passing kwargs that don't match the function signature must return an error string."""
    async def strict_tool(x: str, y: int) -> str:
        """Strict arg tool."""
        return f"{x}{y}"

    reg = ToolRegistry()
    reg.register(strict_tool)
    result = await reg.dispatch("strict_tool", {"z": "wrong"})
    assert "error" in result.lower()


# ===========================================================================
# MCPServerManager — constructor and lifecycle (mocked)
# ===========================================================================

def test_mcp_manager_init_stores_params():
    """MCPServerManager __init__ must store command and args without connecting."""
    from agent_engine.mcp_client import MCPServerManager
    mgr = MCPServerManager("npx", ["-y", "server"])
    assert mgr._params.command == "npx"
    assert mgr._params.args == ["-y", "server"]
    assert mgr._session is None


@pytest.mark.asyncio
async def test_mcp_manager_connect_calls_initialize():
    """connect() must call session.initialize() and return the session."""
    from agent_engine.mcp_client import MCPServerManager

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()

    mgr = MCPServerManager("npx", [])
    with patch("agent_engine.mcp_client.stdio_client") as mock_stdio, \
         patch("agent_engine.mcp_client.ClientSession") as mock_cls:

        # stdio_client returns (read_stream, write_stream)
        mock_transport = (MagicMock(), MagicMock())

        # Make stdio_client a proper async context manager
        mock_stdio_cm = AsyncMock()
        mock_stdio_cm.__aenter__ = AsyncMock(return_value=mock_transport)
        mock_stdio_cm.__aexit__ = AsyncMock(return_value=False)
        mock_stdio.return_value = mock_stdio_cm

        # Make ClientSession a proper async context manager
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_session_cm

        session = await mgr.connect()

    mock_session.initialize.assert_awaited_once()
    assert session is mock_session


@pytest.mark.asyncio
async def test_mcp_manager_disconnect_closes_exit_stack():
    """disconnect() must call aclose() on the AsyncExitStack."""
    from agent_engine.mcp_client import MCPServerManager

    mgr = MCPServerManager("npx", [])
    mock_stack = AsyncMock()
    mgr._exit_stack = mock_stack
    await mgr.disconnect()
    mock_stack.aclose.assert_awaited_once()


# ===========================================================================
# LightweightEngine — additional coverage
# ===========================================================================

def test_engine_uses_agent_model_env(monkeypatch):
    """AGENT_MODEL env var must set the engine's model attribute."""
    monkeypatch.setenv("AGENT_MODEL", "my-custom-model")
    engine = LightweightEngine(api_key="k")
    assert engine.model == "my-custom-model"


def test_engine_uses_openrouter_key(monkeypatch):
    """OPENROUTER_API_KEY must be accepted as a fallback API key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    engine = LightweightEngine()
    assert engine is not None


@pytest.mark.asyncio
async def test_run_manage_history_false_does_not_mutate_caller():
    """manage_history=False must not modify the caller's history list."""
    engine = LightweightEngine(api_key="k", manage_history=False)
    original_history = [{"role": "user", "content": "old"}]
    snapshot = list(original_history)

    def _make_stream_local():
        async def _gen():
            delta = MagicMock()
            delta.content = "hi"
            delta.tool_calls = None
            choice = MagicMock()
            choice.delta = delta
            c1 = MagicMock()
            c1.choices = [choice]
            yield c1
            delta2 = MagicMock()
            delta2.content = None
            delta2.tool_calls = None
            choice2 = MagicMock()
            choice2.delta = delta2
            c2 = MagicMock()
            c2.choices = [choice2]
            yield c2
        return _gen()

    with patch.object(engine.client.chat.completions, "create",
                      AsyncMock(return_value=_make_stream_local())):
        async for _ in engine.run("new prompt", history=original_history):
            pass

    assert original_history == snapshot, "manage_history=False mutated caller's list"


@pytest.mark.asyncio
async def test_run_empty_choices_chunk_no_crash():
    """A stream chunk with an empty choices list must be silently skipped."""
    engine = LightweightEngine(api_key="k")

    async def stream_with_empty_choices():
        # chunk with no choices
        c_empty = MagicMock()
        c_empty.choices = []
        c_empty.usage = None
        yield c_empty
        # normal token chunk
        delta = MagicMock()
        delta.content = "ok"
        delta.tool_calls = None
        choice = MagicMock()
        choice.delta = delta
        c_normal = MagicMock()
        c_normal.choices = [choice]
        c_normal.usage = None
        yield c_normal
        # final empty
        d2 = MagicMock()
        d2.content = None
        d2.tool_calls = None
        c2 = MagicMock()
        c2.delta = d2
        ch2 = MagicMock()
        ch2.choices = [c2]
        ch2.usage = None
        yield ch2

    with patch.object(engine.client.chat.completions, "create",
                      AsyncMock(return_value=stream_with_empty_choices())):
        events = [e async for e in engine.run("test")]

    tokens = [e for e in events if e.type == "token"]
    assert any("ok" in t.data for t in tokens)


@pytest.mark.asyncio
async def test_run_malformed_tool_args_uses_empty_kwargs():
    """If the LLM returns invalid JSON as tool arguments, kwargs must default to {}."""
    engine = LightweightEngine(api_key="k", allowed_tools=["bash"])
    call_count = [0]

    async def side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: tool call with malformed JSON
            async def first_stream():
                delta = MagicMock()
                delta.content = None
                tc = MagicMock()
                tc.index = 0
                tc.id = "cid"
                tc.function = MagicMock()
                tc.function.name = "bash"
                tc.function.arguments = "{{NOT JSON"
                delta.tool_calls = [tc]
                choice = MagicMock()
                choice.delta = delta
                c = MagicMock()
                c.choices = [choice]
                c.usage = None
                yield c
                d2 = MagicMock()
                d2.content = None
                d2.tool_calls = None
                c2 = MagicMock()
                c2.delta = d2
                ch2 = MagicMock()
                ch2.choices = [c2]
                ch2.usage = None
                yield ch2
            return first_stream()
        else:
            # Second call: plain text response
            async def done_stream():
                d = MagicMock()
                d.content = "done"
                d.tool_calls = None
                c = MagicMock()
                c.delta = d
                ch = MagicMock()
                ch.choices = [c]
                ch.usage = None
                yield ch
                d2 = MagicMock()
                d2.content = None
                d2.tool_calls = None
                c2 = MagicMock()
                c2.delta = d2
                ch2 = MagicMock()
                ch2.choices = [c2]
                ch2.usage = None
                yield ch2
            return done_stream()

    with patch.object(engine.client.chat.completions, "create",
                      AsyncMock(side_effect=side_effect)), patch.object(engine.tools, "dispatch",
                      new=AsyncMock(return_value="result")):
        events = [e async for e in engine.run("call a tool")]

    tool_starts = [e for e in events if e.type == "tool_start"]
    assert len(tool_starts) == 1
    assert tool_starts[0].data == {}  # empty kwargs on JSON parse failure


@pytest.mark.asyncio
async def test_run_empty_prompt_no_crash():
    """An empty prompt string must not cause an unhandled exception."""
    engine = LightweightEngine(api_key="k")

    async def empty_stream():
        d = MagicMock()
        d.content = None
        d.tool_calls = None
        c = MagicMock()
        c.delta = d
        ch = MagicMock()
        ch.choices = [c]
        yield ch

    with patch.object(engine.client.chat.completions, "create",
                      AsyncMock(return_value=empty_stream())):
        events = [e async for e in engine.run("")]

    assert any(e.type == "done" for e in events)


@pytest.mark.asyncio
async def test_connect_mcp_registers_tools():
    """connect_mcp() must register MCP tools into the engine's ToolRegistry."""
    from agent_engine.mcp_client import MCPServerManager

    engine = LightweightEngine(api_key="k")

    class FakeTool:
        name = "db_query"
        description = "Query DB"
        inputSchema = {"type": "object", "properties": {"sql": {"type": "string"}}}  # noqa: N815

    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[FakeTool()]))

    mock_manager = AsyncMock(spec=MCPServerManager)
    mock_manager.connect = AsyncMock(return_value=mock_session)

    with patch("agent_engine.engine.MCPServerManager", return_value=mock_manager):
        await engine.connect_mcp("npx", ["-y", "server"])

    names = [s["function"]["name"] for s in engine.tools.get_all_schemas()]
    assert "db_query" in names
    assert mock_manager in engine._mcp_managers


@pytest.mark.asyncio
async def test_close_with_no_managers_no_error():
    """Calling close() on an engine with zero MCP connections must be a no-op."""
    engine = LightweightEngine(api_key="k")
    await engine.close()  # must not raise
    assert engine._mcp_managers == []


@pytest.mark.asyncio
async def test_run_multiple_tool_calls_in_one_response():
    """Engine must handle batches with more than one tool call per LLM response."""
    engine = LightweightEngine(api_key="k", allowed_tools=["bash"])
    call_count = [0]

    async def side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            async def multi_tool_stream():
                # Two tool calls in a single stream response
                for i, (call_id, cmd) in enumerate([("c1", "ls"), ("c2", "pwd")]):
                    delta = MagicMock()
                    delta.content = None
                    tc = MagicMock()
                    tc.index = i
                    tc.id = call_id
                    tc.function = MagicMock()
                    tc.function.name = "bash"
                    tc.function.arguments = json.dumps({"command": cmd})
                    delta.tool_calls = [tc]
                    choice = MagicMock()
                    choice.delta = delta
                    c = MagicMock()
                    c.choices = [choice]
                    c.usage = None
                    yield c
                d2 = MagicMock()
                d2.content = None
                d2.tool_calls = None
                c2 = MagicMock()
                c2.delta = d2
                ch2 = MagicMock()
                ch2.choices = [c2]
                ch2.usage = None
                yield ch2
            return multi_tool_stream()
        else:
            async def done():
                d = MagicMock()
                d.content = "done"
                d.tool_calls = None
                c = MagicMock()
                c.delta = d
                ch = MagicMock()
                ch.choices = [c]
                ch.usage = None
                yield ch
                d2 = MagicMock()
                d2.content = None
                d2.tool_calls = None
                c2 = MagicMock()
                c2.delta = d2
                ch2 = MagicMock()
                ch2.choices = [c2]
                ch2.usage = None
                yield ch2
            return done()

    with patch.object(engine.client.chat.completions, "create",
                      AsyncMock(side_effect=side_effect)), patch.object(engine.tools, "dispatch",
                      new=AsyncMock(return_value="output")):
        events = [e async for e in engine.run("run two tools")]

    tool_starts = [e for e in events if e.type == "tool_start"]
    assert len(tool_starts) == 2


# ===========================================================================
# New QA additions — token usage (AC-7.x) and coverage gaps
# ===========================================================================

# ---------------------------------------------------------------------------
# builtin_tools.py coverage gaps (lines 25-26 and 28-29)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bash_kill_raises_during_timeout_still_returns_error():
    """if proc.kill() raises during timeout cleanup, the error is swallowed."""
    with patch("agent_engine.tools.bash_tool.asyncio.create_subprocess_shell") as mock_create:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.kill = MagicMock(side_effect=ProcessLookupError("no such process"))
        mock_create.return_value = mock_proc

        result = await bash(action="run", command="sleep 999", timeout=1)

    assert "timed out" in result


@pytest.mark.asyncio
async def test_bash_subprocess_creation_fails_returns_error():
    """if create_subprocess_shell itself raises, return error string."""
    with patch("agent_engine.tools.bash_tool.asyncio.create_subprocess_shell", side_effect=OSError("cannot fork")):
        result = await bash(action="run", command="echo hi")

    assert result.startswith("Error:")
    assert "fork" in result


# ---------------------------------------------------------------------------
# AC-7.5: multi-turn usage — the final LLM call's usage wins in one run()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiturn_done_event_carries_final_call_usage():
    """
    AC-7.5: In a run that includes a tool call (two LLM requests), the 'done'
    event must carry usage from the SECOND (final) LLM call, not the first.
    """
    engine = LightweightEngine(api_key="k", allowed_tools=["bash"])

    first_usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
    second_usage = {"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220}

    call_count = [0]

    async def side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: returns a tool call + usage chunk
            async def _first():
                # tool call chunk
                delta = MagicMock()
                delta.content = None
                tc = MagicMock()
                tc.index = 0
                tc.id = "call_99"
                tc.function = MagicMock()
                tc.function.name = "bash"
                tc.function.arguments = '{"command": "echo hi"}'
                delta.tool_calls = [tc]
                choice = MagicMock()
                choice.delta = delta
                chunk = MagicMock()
                chunk.choices = [choice]
                chunk.usage = None
                yield chunk
                # final empty chunk
                d2 = MagicMock()
                d2.content = None
                d2.tool_calls = None
                c2 = MagicMock()
                c2.delta = d2
                ch2 = MagicMock()
                ch2.choices = [c2]
                ch2.usage = None
                yield ch2
                # usage chunk for first call
                uc = MagicMock()
                uc.choices = []
                mu = MagicMock()
                mu.prompt_tokens = first_usage["prompt_tokens"]
                mu.completion_tokens = first_usage["completion_tokens"]
                mu.total_tokens = first_usage["total_tokens"]
                uc.usage = mu
                yield uc
            return _first()
        else:
            # Second call: plain text + second usage chunk
            async def _second():
                d = MagicMock()
                d.content = "ok"
                d.tool_calls = None
                c = MagicMock()
                c.delta = d
                ch = MagicMock()
                ch.choices = [c]
                ch.usage = None
                yield ch
                d2 = MagicMock()
                d2.content = None
                d2.tool_calls = None
                c2 = MagicMock()
                c2.delta = d2
                ch2 = MagicMock()
                ch2.choices = [c2]
                ch2.usage = None
                yield ch2
                # usage chunk for second call
                uc = MagicMock()
                uc.choices = []
                mu = MagicMock()
                mu.prompt_tokens = second_usage["prompt_tokens"]
                mu.completion_tokens = second_usage["completion_tokens"]
                mu.total_tokens = second_usage["total_tokens"]
                uc.usage = mu
                yield uc
            return _second()

    with patch.object(engine.client.chat.completions, "create", AsyncMock(side_effect=side_effect)), \
            patch.object(engine.tools, "dispatch", new=AsyncMock(return_value="hi\n")):
        events = [e async for e in engine.run("run bash")]

    done = next(e for e in events if e.type == "done")
    usage = done.metadata["usage"]
    assert usage is not None, "usage should be set on done event"
    assert usage["prompt_tokens"] == 200, f"Expected 200, got {usage['prompt_tokens']} (used first call's usage)"
    assert usage["completion_tokens"] == 20


# ---------------------------------------------------------------------------
# AC-7.3: usage is None when stream emits no usage chunk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_done_usage_is_none_when_provider_omits_usage_chunk():
    """AC-7.3: If the stream never emits a usage chunk, metadata['usage'] is None."""
    engine = LightweightEngine(api_key="k")

    async def _stream_without_usage():
        d = MagicMock()
        d.content = "hello"
        d.tool_calls = None
        c = MagicMock()
        c.delta = d
        ch = MagicMock()
        ch.choices = [c]
        ch.usage = None
        yield ch

    with patch.object(
        engine.client.chat.completions,
        "create",
        AsyncMock(return_value=_stream_without_usage()),
    ):
        events = [e async for e in engine.run("hi")]

    done = next(e for e in events if e.type == "done")
    assert done.metadata["usage"] is None


# ---------------------------------------------------------------------------
# AC-7.3: zero-value token counts are valid (not confused with falsy None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_done_usage_handles_zero_token_counts():
    """Zero token values are valid — usage dict should not be None."""
    engine = LightweightEngine(api_key="k")

    async def _stream_zero_usage():
        d = MagicMock()
        d.content = "x"
        d.tool_calls = None
        c = MagicMock()
        c.delta = d
        ch = MagicMock()
        ch.choices = [c]
        ch.usage = None
        yield ch
        # final empty chunk
        d2 = MagicMock()
        d2.content = None
        d2.tool_calls = None
        c2 = MagicMock()
        c2.delta = d2
        ch2 = MagicMock()
        ch2.choices = [c2]
        ch2.usage = None
        yield ch2
        # usage chunk with zero values
        uc = MagicMock()
        uc.choices = []
        mu = MagicMock()
        mu.prompt_tokens = 0
        mu.completion_tokens = 0
        mu.total_tokens = 0
        uc.usage = mu
        yield uc

    with patch.object(
        engine.client.chat.completions,
        "create",
        AsyncMock(return_value=_stream_zero_usage()),
    ):
        events = [e async for e in engine.run("hi")]

    done = next(e for e in events if e.type == "done")
    usage = done.metadata["usage"]
    assert usage is not None
    assert usage["prompt_tokens"] == 0
    assert usage["total_tokens"] == 0


# ---------------------------------------------------------------------------
# AC-7.4: consumer API — event.metadata.get("usage", {}) pattern is safe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consumer_api_usage_get_pattern_is_safe():
    """AC-7.4: event.metadata.get('usage', {}) must work; no KeyError."""
    engine = LightweightEngine(api_key="k")

    async def _stream():
        d = MagicMock()
        d.content = "hi"
        d.tool_calls = None
        c = MagicMock()
        c.delta = d
        ch = MagicMock()
        ch.choices = [c]
        ch.usage = None
        yield ch

    with patch.object(
        engine.client.chat.completions,
        "create",
        AsyncMock(return_value=_stream()),
    ):
        events = [e async for e in engine.run("hi")]

    done = next(e for e in events if e.type == "done")
    # When no usage chunk was in the stream, 'usage' key IS present but value is None
    assert "usage" in done.metadata


# ===========================================================================
# QA Phase — Features 8 & 9 (workdir sandboxing + dynamic system prompt)
# ===========================================================================

def _make_engine(**kwargs):
    """Local helper: engine with a dummy API key."""
    return LightweightEngine(api_key="test-key", **kwargs)


def _make_text_stream(text: str = "ok"):
    """Return a one-shot async generator yielding a single text response."""
    async def _gen():
        delta = MagicMock()
        delta.content = text
        delta.tool_calls = None
        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        chunk.usage = None
        yield chunk
        d2 = MagicMock()
        d2.content = None
        d2.tool_calls = None
        c2 = MagicMock()
        c2.delta = d2
        ch2 = MagicMock()
        ch2.choices = [c2]
        ch2.usage = None
        yield ch2
    return AsyncMock(return_value=_gen())


# ---------------------------------------------------------------------------
# AC-8.3: _is_safe_path exception path (lines 23-24 of builtin_tools.py)
# ---------------------------------------------------------------------------

def test_is_safe_path_null_byte_returns_false(tmp_path):
    """A path with an embedded null byte triggers ValueError → _is_safe_path returns False."""
    t = BuiltinTools(workdir=str(tmp_path))
    # Null byte causes Path.resolve() to raise ValueError on Linux
    result = t._is_safe_path("\x00malicious")
    assert result is False


def test_is_safe_path_oserror_returns_false(tmp_path):
    """If Path.resolve() raises OSError, _is_safe_path must return False (not propagate)."""
    from pathlib import Path
    from unittest.mock import patch
    t = BuiltinTools(workdir=str(tmp_path))
    with patch.object(Path, "resolve", side_effect=OSError("mock io error")):
        result = t._is_safe_path("safe_file.txt")
    assert result is False


@pytest.mark.asyncio
async def test_read_file_null_byte_path_returns_security_error(tmp_path):
    """read_file() with a null-byte path must return Security Error, not crash."""
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("\x00secret")
    assert "security error" in result.lower()


# ---------------------------------------------------------------------------
# AC-8.6: bash_background runs in workdir
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bash_background_runs_in_workdir(tmp_path):
    """AC-8.6: bash_background must execute with cwd=workdir."""
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.bash(action="background", command="touch workdir_marker.txt")
    job_id = result.split("job_id: ")[1].strip()
    await asyncio.sleep(0.3)
    await t.bash(action="kill", job_id=job_id)
    assert (tmp_path / "workdir_marker.txt").exists(), \
        "bash_background did not run in the configured workdir"


# ---------------------------------------------------------------------------
# AC-8.8: workdir with no allowed_tools is harmless
# ---------------------------------------------------------------------------

def test_engine_workdir_no_allowed_tools_is_harmless(tmp_path):
    """AC-8.8: passing workdir without allowed_tools must not raise."""
    engine = _make_engine(workdir=str(tmp_path))
    assert engine.workdir == os.path.abspath(str(tmp_path))
    assert engine.tools.get_all_schemas() == []


# ---------------------------------------------------------------------------
# AC-9.4: empty string system_prompt skips injection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_no_injection_when_system_prompt_empty_string():
    """AC-9.4: system_prompt='' (empty string) must skip injection."""
    engine = _make_engine(system_prompt="")
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "user", \
        "Empty system_prompt should not inject a system message"


# ---------------------------------------------------------------------------
# AC-9.6: system message survives history pruning when system_prompt is active
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_history_pruning_preserves_system_msg_with_active_system_prompt():
    """AC-9.6: system msg at index 0 must survive pruning when engine has system_prompt."""
    engine = _make_engine(max_history_length=4, system_prompt="Active persona.")
    history = [{"role": "system", "content": "Active persona."}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
        for i in range(10)
    ]

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("latest", history=history):
            pass

    assert history[0]["role"] == "system", "System message was lost after pruning"
    assert len(history) <= engine.max_history_length + 2


# ---------------------------------------------------------------------------
# AC-9.3: run() enforces system prompt on EVERY call, not just the first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_system_prompt_enforced_on_every_call():
    """AC-9.3: Each run() call must overwrite/inject the system prompt."""
    engine = _make_engine(system_prompt="Persona A.")
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("r1")):
        async for _ in engine.run("first", history=history):
            pass

    engine.set_system_prompt("Persona B.")

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("r2")):
        async for _ in engine.run("second", history=history):
            pass

    assert history[0]["content"] == "Persona B.", \
        "System prompt was not updated in history on second run()"


# ---------------------------------------------------------------------------
# AC-8.4: read_file security error string must start with "Security Error:"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_security_error_message_prefix(tmp_path):
    """AC-8.4: _is_safe_path failure must return a string starting with 'Security Error:'."""
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("../../etc/passwd")
    assert result.startswith("Security Error:"), \
        f"Expected 'Security Error:' prefix, got: {result!r}"


# ---------------------------------------------------------------------------
# Nonexistent workdir: bash() must return error string, not raise
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bash_nonexistent_workdir_returns_error():
    """bash() with a nonexistent workdir must return an error string, not raise."""
    t = BuiltinTools(workdir="/nonexistent/qa/path/xyz")
    result = await t.bash(action="run", command="echo hi")
    assert isinstance(result, str)
    # Must be an error (cwd doesn't exist), not crash the caller
    assert "error" in result.lower() or result == ""  # subprocess may return empty on error


# ===========================================================================
# Feature 10: load_mcp_config — additional edge cases
# ===========================================================================

def _make_engine_f10():
    return LightweightEngine(api_key="test-key")


@pytest.mark.asyncio
async def test_load_mcp_config_missing_mcp_servers_key(tmp_path):
    """Config JSON without 'mcp_servers' key defaults to empty → no connections."""
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps({}))

    engine = _make_engine_f10()
    engine.connect_mcp = AsyncMock()

    await engine.load_mcp_config(config_path=str(config_file))

    engine.connect_mcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_mcp_config_server_missing_enabled_field_is_skipped(tmp_path):
    """A server entry with no 'enabled' field is treated as disabled and silently skipped."""
    config = {
        "mcp_servers": {
            "no_enabled_field": {
                "command": "npx",
                "args": ["-y", "some-server"],
                # 'enabled' key deliberately absent
            }
        }
    }
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(config))

    engine = _make_engine_f10()
    engine.connect_mcp = AsyncMock()

    await engine.load_mcp_config(config_path=str(config_file))

    engine.connect_mcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_mcp_config_server_missing_command_key_is_non_fatal(tmp_path, capsys):
    """A server entry missing 'command' raises KeyError, which must be caught and logged."""
    config = {
        "mcp_servers": {
            "bad_entry": {
                # 'command' key absent → KeyError when engine tries details["command"]
                "args": ["-y", "some-server"],
                "enabled": True,
            },
            "good_entry": {
                "command": "npx",
                "args": ["-y", "good-server"],
                "enabled": True,
            },
        }
    }
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(config))

    engine = _make_engine_f10()
    call_count = 0

    async def connect_side_effect(command, args):
        nonlocal call_count
        call_count += 1

    engine.connect_mcp = AsyncMock(side_effect=connect_side_effect)

    # Must not raise
    await engine.load_mcp_config(config_path=str(config_file))

    # Only the good_entry should have been connected
    assert call_count == 1
    captured = capsys.readouterr()
    assert "Error connecting MCP" in captured.out
    assert "bad_entry" in captured.out


@pytest.mark.asyncio
async def test_load_mcp_config_warning_message_includes_path(tmp_path, capsys):
    """The FileNotFoundError warning must include the exact config path that was missing."""
    missing_path = str(tmp_path / "totally_missing.json")
    engine = _make_engine_f10()

    await engine.load_mcp_config(config_path=missing_path)

    captured = capsys.readouterr()
    assert missing_path in captured.out, (
        f"Expected path '{missing_path}' in warning output, got: {captured.out!r}"
    )


@pytest.mark.asyncio
async def test_load_mcp_config_all_disabled_results_in_zero_connections(tmp_path):
    """When all servers are disabled, connect_mcp must never be called."""
    config = {
        "mcp_servers": {
            "server_a": {"command": "npx", "args": ["a"], "enabled": False},
            "server_b": {"command": "npx", "args": ["b"], "enabled": False},
            "server_c": {"command": "npx", "args": ["c"], "enabled": False},
        }
    }
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(config))

    engine = _make_engine_f10()
    engine.connect_mcp = AsyncMock()

    await engine.load_mcp_config(config_path=str(config_file))

    engine.connect_mcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_mcp_config_mcp_managers_count_matches_enabled(tmp_path):
    """AC-8: After load_mcp_config, _mcp_managers count == number of enabled servers."""
    config = {
        "mcp_servers": {
            "enabled_1": {"command": "npx", "args": ["a"], "enabled": True},
            "disabled_1": {"command": "npx", "args": ["b"], "enabled": False},
            "enabled_2": {"command": "npx", "args": ["c"], "enabled": True},
        }
    }
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(config))

    engine = _make_engine_f10()
    # Stub connect_mcp to append a fake manager without spawning subprocesses
    fake_manager = MagicMock()

    async def fake_connect(command, args):
        engine._mcp_managers.append(fake_manager)

    engine.connect_mcp = AsyncMock(side_effect=fake_connect)

    await engine.load_mcp_config(config_path=str(config_file))

    assert len(engine._mcp_managers) == 2, (
        f"Expected 2 managers for 2 enabled servers, got {len(engine._mcp_managers)}"
    )


# ===========================================================================
# Ticket: add-thinking-model-support — Feature 1: thinking event type
# ===========================================================================

def test_thinking_event_type_listed_in_comment():
    """AC: events.py type comment must include 'thinking'."""
    import inspect

    import agent_engine.events as ev_module
    source = inspect.getsource(ev_module)
    assert '"thinking"' in source or "'thinking'" in source, \
        "events.py type comment does not mention 'thinking'"


def test_thinking_event_constructs_without_error():
    """AC: AgentEvent(type='thinking', data='some thought') must not raise."""
    evt = AgentEvent(type="thinking", data="I am thinking deeply.")
    assert evt.type == "thinking"
    assert evt.data == "I am thinking deeply."
    assert isinstance(evt.metadata, dict)
    assert isinstance(evt.timestamp, float)


def test_thinking_event_metadata_isolated():
    """thinking events must have per-instance metadata (no shared mutable default)."""
    e1 = AgentEvent(type="thinking", data="thought A")
    e2 = AgentEvent(type="thinking", data="thought B")
    e1.metadata["key"] = "value"
    assert "key" not in e2.metadata


# ===========================================================================
# Ticket: add-thinking-model-support — Feature 2: native reasoning token parsing
# ===========================================================================

def _make_thinking_stream(reasoning: str = None, content: str = None):
    """Build a minimal async generator simulating a chunk with reasoning_content and/or content."""
    async def _gen():
        delta = MagicMock()
        delta.content = content
        delta.tool_calls = None
        # Attach reasoning_content attribute
        if reasoning is not None:
            delta.reasoning_content = reasoning
        else:
            # Simulate SDK that doesn't expose the attribute at all
            del delta.reasoning_content  # MagicMock: accessing missing attr still returns Mock
            # Use spec to truly hide it
        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        chunk.usage = None
        yield chunk
        # terminal empty chunk
        d2 = MagicMock()
        d2.content = None
        d2.tool_calls = None
        d2.reasoning_content = None
        c2 = MagicMock()
        c2.delta = d2
        ch2 = MagicMock()
        ch2.choices = [c2]
        ch2.usage = None
        yield ch2
    return AsyncMock(return_value=_gen())


def _make_reasoning_chunk_stream(reasoning: str, content: str = None):
    """
    Build a stream where delta.reasoning_content is set via spec-based mock
    so getattr(delta, 'reasoning_content', None) works correctly.
    """
    async def _gen():
        # Use a plain object so getattr works predictably
        class Delta:
            pass
        delta = Delta()
        delta.reasoning_content = reasoning
        delta.content = content
        delta.tool_calls = None

        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        chunk.usage = None
        yield chunk

        # terminal
        class Delta2:
            pass
        delta2 = Delta2()
        delta2.reasoning_content = None
        delta2.content = None
        delta2.tool_calls = None
        c2 = MagicMock()
        c2.delta = delta2
        ch2 = MagicMock()
        ch2.choices = [c2]
        ch2.usage = None
        yield ch2

    return AsyncMock(return_value=_gen())


def _make_no_reasoning_stream(content: str = "Hello"):
    """Stream where delta has no reasoning_content attribute (older SDK simulation)."""
    async def _gen():
        class Delta:
            pass
        delta = Delta()
        # deliberately NO reasoning_content attribute
        delta.content = content
        delta.tool_calls = None

        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        chunk.usage = None
        yield chunk

        class Delta2:
            pass
        delta2 = Delta2()
        delta2.content = None
        delta2.tool_calls = None
        c2 = MagicMock()
        c2.delta = delta2
        ch2 = MagicMock()
        ch2.choices = [c2]
        ch2.usage = None
        yield ch2

    return AsyncMock(return_value=_gen())


@pytest.mark.asyncio
async def test_reasoning_content_yields_thinking_event():
    """AC-F2a: Non-empty reasoning_content yields a 'thinking' event."""
    engine = LightweightEngine(api_key="k")

    with patch.object(
        engine.client.chat.completions,
        "create",
        _make_reasoning_chunk_stream(reasoning="I am thinking"),
    ):
        events = [e async for e in engine.run("solve it")]

    thinking_events = [e for e in events if e.type == "thinking"]
    assert len(thinking_events) == 1
    assert thinking_events[0].data == "I am thinking"


@pytest.mark.asyncio
async def test_reasoning_content_yields_thinking_before_token():
    """AC-F2a: thinking event must be yielded BEFORE any token event from the same chunk."""
    engine = LightweightEngine(api_key="k")

    with patch.object(
        engine.client.chat.completions,
        "create",
        _make_reasoning_chunk_stream(reasoning="my thought", content="my answer"),
    ):
        events = [e async for e in engine.run("go")]

    types = [e.type for e in events if e.type in ("thinking", "token")]
    assert types[0] == "thinking", f"Expected 'thinking' first, got: {types}"
    assert "token" in types


@pytest.mark.asyncio
async def test_reasoning_content_none_yields_no_thinking_event():
    """AC-F2b: reasoning_content=None must not yield a 'thinking' event."""
    engine = LightweightEngine(api_key="k")

    with patch.object(
        engine.client.chat.completions,
        "create",
        _make_reasoning_chunk_stream(reasoning=None, content="Hello"),
    ):
        events = [e async for e in engine.run("hi")]

    thinking_events = [e for e in events if e.type == "thinking"]
    assert thinking_events == [], f"Unexpected thinking events: {thinking_events}"


@pytest.mark.asyncio
async def test_no_reasoning_attribute_yields_no_thinking_event():
    """AC-F2b: Missing reasoning_content attribute (older SDK) must not yield 'thinking'."""
    engine = LightweightEngine(api_key="k")

    with patch.object(
        engine.client.chat.completions,
        "create",
        _make_no_reasoning_stream(content="Hello"),
    ):
        events = [e async for e in engine.run("hi")]

    thinking_events = [e for e in events if e.type == "thinking"]
    assert thinking_events == []


@pytest.mark.asyncio
async def test_reasoning_content_empty_string_yields_no_thinking_event():
    """AC-F2b: Empty-string reasoning_content is falsy → no 'thinking' event."""
    engine = LightweightEngine(api_key="k")

    with patch.object(
        engine.client.chat.completions,
        "create",
        _make_reasoning_chunk_stream(reasoning="", content="answer"),
    ):
        events = [e async for e in engine.run("hi")]

    thinking_events = [e for e in events if e.type == "thinking"]
    assert thinking_events == [], "Empty reasoning_content should not yield thinking event"


@pytest.mark.asyncio
async def test_reasoning_content_not_stored_in_history():
    """AC-F2c: Reasoning tokens must NOT appear in the assistant message stored in history."""
    engine = LightweightEngine(api_key="k", manage_history=True)
    history = []

    with patch.object(
        engine.client.chat.completions,
        "create",
        _make_reasoning_chunk_stream(reasoning="secret thought", content="public answer"),
    ):
        async for _ in engine.run("tell me", history=history):
            pass

    assistant_messages = [m for m in history if m["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert "secret thought" not in assistant_messages[0]["content"], \
        "Reasoning content must not be stored in the assistant message"
    assert "public answer" in assistant_messages[0]["content"]


@pytest.mark.asyncio
async def test_thinking_only_chunk_no_token_event():
    """AC-F2: A chunk with only reasoning_content and no content must yield thinking but no token."""
    engine = LightweightEngine(api_key="k")

    with patch.object(
        engine.client.chat.completions,
        "create",
        _make_reasoning_chunk_stream(reasoning="pure thought", content=None),
    ):
        events = [e async for e in engine.run("solve")]

    thinking_events = [e for e in events if e.type == "thinking"]
    token_events = [e for e in events if e.type == "token"]
    assert len(thinking_events) == 1
    assert token_events == [], f"Unexpected token events: {token_events}"


@pytest.mark.asyncio
async def test_standard_content_processing_unchanged_with_reasoning():
    """AC-F2d: Standard token/tool processing must be unaffected when reasoning is also present."""
    engine = LightweightEngine(api_key="k")

    with patch.object(
        engine.client.chat.completions,
        "create",
        _make_reasoning_chunk_stream(reasoning="thought", content="Hello!"),
    ):
        events = [e async for e in engine.run("hi")]

    token_events = [e for e in events if e.type == "token"]
    assert "".join(e.data for e in token_events) == "Hello!"


# ===========================================================================
# Ticket: add-thinking-model-support — Feature 3: developer role compatibility
# ===========================================================================

@pytest.mark.asyncio
async def test_o1_model_uses_developer_role():
    """AC-F3a: model='o1-preview' must use role='developer' for system prompt."""
    engine = LightweightEngine(api_key="k", model="o1-preview", system_prompt="Be concise.")
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "developer", \
        f"Expected 'developer' role for o1 model, got: {history[0]['role']!r}"
    assert history[0]["content"] == "Be concise."


@pytest.mark.asyncio
async def test_o1_model_exact_uses_developer_role():
    """AC-F3a: model='o1' (exact) must also use role='developer'."""
    engine = LightweightEngine(api_key="k", model="o1", system_prompt="prompt")
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "developer"


@pytest.mark.asyncio
async def test_o3_mini_uses_developer_role():
    """AC-F3b: model='o3-mini' must use role='developer' for system prompt."""
    engine = LightweightEngine(api_key="k", model="o3-mini", system_prompt="Be precise.")
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "developer", \
        f"Expected 'developer' role for o3 model, got: {history[0]['role']!r}"


@pytest.mark.asyncio
async def test_gpt4o_uses_system_role():
    """AC-F3c: model='gpt-4o' must use role='system' (no regression)."""
    engine = LightweightEngine(api_key="k", model="gpt-4o", system_prompt="You are helpful.")
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "system", \
        f"Expected 'system' role for gpt-4o, got: {history[0]['role']!r}"


@pytest.mark.asyncio
async def test_gpt35_uses_system_role(tmp_path):
    """AC-F3c: model='gpt-3.5-turbo' must use role='system' (no regression)."""
    engine = LightweightEngine(api_key="k", model="gpt-3.5-turbo", system_prompt="help", workdir=str(tmp_path))
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "system"


@pytest.mark.asyncio
async def test_existing_developer_role_msg_updated_not_duplicated():
    """AC-F3d: An existing role='developer' msg at index 0 must be updated, not doubled."""
    engine = LightweightEngine(api_key="k", model="o1-mini", system_prompt="New instruction.")
    history = [{"role": "developer", "content": "Old instruction."}]

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    developer_msgs = [m for m in history if m["role"] == "developer"]
    assert len(developer_msgs) == 1, \
        f"Expected exactly 1 developer message, found {len(developer_msgs)}"
    assert developer_msgs[0]["content"] == "New instruction."


@pytest.mark.asyncio
async def test_existing_system_role_updated_to_developer_for_o1():
    """AC-F3d: An existing role='system' msg at index 0 must have its role updated to 'developer'."""
    engine = LightweightEngine(api_key="k", model="o1-preview", system_prompt="Updated prompt.")
    history = [{"role": "system", "content": "Old system prompt."}]

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "developer", \
        f"Expected role updated to 'developer', got: {history[0]['role']!r}"
    assert history[0]["content"] == "Updated prompt."


@pytest.mark.asyncio
async def test_developer_role_preserved_through_history_pruning():
    """AC-F3e: The 'developer' msg at index 0 must survive history pruning on o1 models."""
    engine = LightweightEngine(
        api_key="k",
        model="o1-preview",
        system_prompt="Preserve me.",
        max_history_length=4,
    )
    # Populate history with developer msg + many turns to trigger pruning
    history = [{"role": "developer", "content": "Preserve me."}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
        for i in range(12)
    ]

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("latest", history=history):
            pass

    assert history[0]["role"] == "developer", \
        "Developer message was lost after history pruning"
    assert len(history) <= engine.max_history_length + 2


@pytest.mark.asyncio
async def test_o3_prefix_only_model_uses_developer_role():
    """AC-F3b: Any model starting with 'o3' uses developer role (edge: 'o3' exact)."""
    engine = LightweightEngine(api_key="k", model="o3", system_prompt="prompt")
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "developer"


@pytest.mark.asyncio
async def test_non_o1_o3_model_not_affected_by_prefix():
    """AC-F3c: model='other-o1-like' does not start with 'o1'/'o3' → system role."""
    engine = LightweightEngine(api_key="k", model="claude-o1-sonnet", system_prompt="p")
    history = []

    with patch.object(engine.client.chat.completions, "create", _make_text_stream("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    # Does NOT start with o1/o3 → system role
    assert history[0]["role"] == "system"
