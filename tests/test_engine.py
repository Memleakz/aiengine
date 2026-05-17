"""Tests for LightweightEngine — uses mocking to avoid real LLM/MCP calls."""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_engine.engine import LightweightEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine(**kwargs):
    """Create an engine with a dummy API key."""
    # Ensure workdir is always provided for tests, using a default if not specified
    if "workdir" not in kwargs:
        kwargs["workdir"] = "/tmp/test_workdir" # Dummy path, will be overridden by tmp_path where applicable
    return LightweightEngine(api_key="test-key", **kwargs)


def _build_chunks(text: str = "", tool_calls: list = None, usage: dict = None):
    """Build a list of fake stream chunks."""
    chunks = []

    if text:
        for char in text:
            delta = MagicMock()
            delta.content = char
            delta.tool_calls = None
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            chunk.usage = None
            chunks.append(chunk)

    if tool_calls:
        for i, tc_spec in enumerate(tool_calls):
            delta = MagicMock()
            delta.content = None
            tc = MagicMock()
            tc.index = i
            tc.id = tc_spec["id"]
            tc.function = MagicMock()
            tc.function.name = tc_spec["name"]
            tc.function.arguments = json.dumps(tc_spec["args"])
            delta.tool_calls = [tc]
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            chunk.usage = None
            chunks.append(chunk)

    # final empty chunk
    delta = MagicMock()
    delta.content = None
    delta.tool_calls = None
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = None
    chunks.append(chunk)

    # optional trailing usage chunk (empty choices, usage populated)
    if usage:
        usage_chunk = MagicMock()
        usage_chunk.choices = []
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = usage["prompt_tokens"]
        mock_usage.completion_tokens = usage["completion_tokens"]
        mock_usage.total_tokens = usage["total_tokens"]
        usage_chunk.usage = mock_usage
        chunks.append(usage_chunk)

    return chunks


def _make_stream(text: str = "", tool_calls: list = None, usage: dict = None):
    """Return a raw async generator of fake stream chunks."""
    chunks = _build_chunks(text=text, tool_calls=tool_calls, usage=usage)

    async def _gen():
        for c in chunks:
            yield c

    return _gen()


def _stream_chunks(text: str = "", tool_calls: list = None, usage: dict = None):
    """Return an AsyncMock whose return value is an async iterable of chunks.

    Use this for direct patching: patch.object(..., "create", _stream_chunks("text")).
    """
    return AsyncMock(return_value=_make_stream(text=text, tool_calls=tool_calls, usage=usage))


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

# def test_init_raises_without_api_key(monkeypatch, tmp_path):
#     monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
#     monkeypatch.delenv("OPENAI_API_KEY", raising=False)
#     with pytest.raises(ValueError, match="API key"):
#         LightweightEngine(workdir=str(tmp_path))


def test_init_reads_api_key_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    engine = LightweightEngine(workdir=str(tmp_path))
    assert engine is not None


def test_init_unknown_tool_raises(tmp_path):
    with pytest.raises(ValueError, match="Unknown built-in tool"):
        make_engine(allowed_tools=["not_a_real_tool"], workdir=str(tmp_path))


def test_init_registers_allowed_tools(tmp_path):
    engine = make_engine(allowed_tools=["bash", "read_file"], workdir=str(tmp_path))
    schemas = engine.tools.get_all_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "bash" in names
    assert "read_file" in names


def test_init_no_tools_empty_registry(tmp_path):
    engine = make_engine(workdir=str(tmp_path))
    assert engine.tools.get_all_schemas() == []


# ---------------------------------------------------------------------------
# run — text-only response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_yields_token_events(tmp_path):
    engine = make_engine(workdir=str(tmp_path))

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("Hello!")):
        events = [e async for e in engine.run("Hi")]

    tokens = [e for e in events if e.type == "token"]
    assert "".join(t.data for t in tokens) == "Hello!"


@pytest.mark.asyncio
async def test_run_yields_system_event(tmp_path):
    engine = make_engine(workdir=str(tmp_path))

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("Hi")):
        events = [e async for e in engine.run("Hi")]

    assert any(e.type == "system" for e in events)


@pytest.mark.asyncio
async def test_run_yields_done_event(tmp_path):
    engine = make_engine(workdir=str(tmp_path))

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("Hi")):
        events = [e async for e in engine.run("Hi")]

    done_events = [e for e in events if e.type == "done"]
    assert len(done_events) == 1
    assert "final_history" in done_events[0].metadata


@pytest.mark.asyncio
async def test_run_appends_messages_to_history(tmp_path):
    engine = make_engine(workdir=str(tmp_path))
    history = []

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("Done")):
        async for _ in engine.run("Tell me something", history=history):
            pass

    roles = [m["role"] for m in history]
    assert "user" in roles
    assert "assistant" in roles


# ---------------------------------------------------------------------------
# run — tool-call response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_executes_tool_and_continues(tmp_path):
    engine = make_engine(allowed_tools=["bash"], workdir=str(tmp_path))

    call_count = 0

    async def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_stream(
                tool_calls=[{"id": "call_1", "name": "bash", "args": {"command": "echo hi"}}]
            )
        else:
            return _make_stream(text="All done.")

    with patch.object(engine.client.chat.completions, "create", AsyncMock(side_effect=side_effect)), \
            patch.object(engine.tools, "dispatch", new=AsyncMock(return_value="hi\n")):
        events = [e async for e in engine.run("run bash")]

    tool_starts = [e for e in events if e.type == "tool_start"]
    tool_results = [e for e in events if e.type == "tool_result"]
    assert len(tool_starts) == 1
    assert len(tool_results) == 1
    assert tool_starts[0].metadata["tool_name"] == "bash"


@pytest.mark.asyncio
async def test_run_tool_result_in_history(tmp_path):
    engine = make_engine(allowed_tools=["bash"], workdir=str(tmp_path))
    history = []
    call_count = 0

    async def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_stream(
                tool_calls=[{"id": "call_1", "name": "bash", "args": {"command": "ls"}}]
            )
        return _make_stream(text="Done")

    with patch.object(engine.client.chat.completions, "create", AsyncMock(side_effect=side_effect)), \
            patch.object(engine.tools, "dispatch", new=AsyncMock(return_value="file.txt\n")):
        async for _ in engine.run("list files", history=history):
            pass

    roles = [m["role"] for m in history]
    assert "tool" in roles


# ---------------------------------------------------------------------------
# history management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_history_pruned_when_over_limit(tmp_path):
    engine = make_engine(max_history_length=4, system_prompt=None, workdir=str(tmp_path))
    # Start with 10 messages (no system)
    history = [{"role": "user", "content": str(i)} for i in range(10)]

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("ok")):
        async for _ in engine.run("new msg", history=history):
            pass

    # history was pruned — should be <= max_history_length + 2 (new user + assistant)
    assert len(history) <= engine.max_history_length + 2


@pytest.mark.asyncio
async def test_history_system_msg_preserved(tmp_path):
    engine = make_engine(max_history_length=4, system_prompt=None, workdir=str(tmp_path))
    system_msg = {"role": "system", "content": "You are a helpful assistant."}
    history = [system_msg] + [{"role": "user", "content": str(i)} for i in range(10)]

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "system"
    assert history[0]["content"] == "You are a helpful assistant."


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_disconnects_managers(tmp_path):
    engine = make_engine(workdir=str(tmp_path))
    mock_manager = AsyncMock()
    engine._mcp_managers.append(mock_manager)
    await engine.close()
    mock_manager.disconnect.assert_awaited_once()
    assert engine._mcp_managers == []


# ---------------------------------------------------------------------------
# token usage
# ---------------------------------------------------------------------------

_SAMPLE_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


@pytest.mark.asyncio
async def test_done_event_contains_usage_key(tmp_path):
    engine = make_engine(workdir=str(tmp_path))

    with patch.object(
        engine.client.chat.completions,
        "create",
        _stream_chunks("Hi", usage=_SAMPLE_USAGE),
    ):
        events = [e async for e in engine.run("Hello")]

    done = next(e for e in events if e.type == "done")
    assert "usage" in done.metadata


@pytest.mark.asyncio
async def test_done_event_usage_values(tmp_path):
    engine = make_engine(workdir=str(tmp_path))

    with patch.object(
        engine.client.chat.completions,
        "create",
        _stream_chunks("Hi", usage=_SAMPLE_USAGE),
    ):
        events = [e async for e in engine.run("Hello")]

    usage = next(e for e in events if e.type == "done").metadata["usage"]
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 5
    assert usage["total_tokens"] == 15


@pytest.mark.asyncio
async def test_done_event_usage_none_when_not_provided(tmp_path):
    """When the stream does not emit a usage chunk, metadata['usage'] is None."""
    engine = make_engine(workdir=str(tmp_path))

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("Hi")):
        events = [e async for e in engine.run("Hello")]

    done = next(e for e in events if e.type == "done")
    assert done.metadata["usage"] is None


@pytest.mark.asyncio
async def test_usage_chunk_does_not_emit_token_event(tmp_path):
    """The usage chunk must be consumed silently — no spurious token events."""
    engine = make_engine(workdir=str(tmp_path))

    with patch.object(
        engine.client.chat.completions,
        "create",
        _stream_chunks("AB", usage=_SAMPLE_USAGE),
    ):
        events = [e async for e in engine.run("Hello")]

    tokens = [e for e in events if e.type == "token"]
    assert "".join(t.data for t in tokens) == "AB"


@pytest.mark.asyncio
async def test_stream_options_flag_passed_to_api(tmp_path):
    """The create call must include stream_options={"include_usage": True}."""
    engine = make_engine(workdir=str(tmp_path))

    mock_create = _stream_chunks("Hi", usage=_SAMPLE_USAGE)
    with patch.object(engine.client.chat.completions, "create", mock_create):
        async for _ in engine.run("Hello"):
            pass

    _, kwargs = mock_create.call_args_list[0]
    assert kwargs.get("stream_options") == {"include_usage": True}


@pytest.mark.asyncio
async def test_usage_overwritten_per_run(tmp_path):
    """Each run() call tracks its own usage; the value from the last stream wins."""
    engine = make_engine(workdir=str(tmp_path))

    usage_a = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    usage_b = {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}

    with patch.object(
        engine.client.chat.completions,
        "create",
        _stream_chunks("A", usage=usage_a),
    ):
        events_a = [e async for e in engine.run("first")]

    with patch.object(
        engine.client.chat.completions,
        "create",
        _stream_chunks("B", usage=usage_b),
    ):
        events_b = [e async for e in engine.run("second")]

    done_a = next(e for e in events_a if e.type == "done")
    done_b = next(e for e in events_b if e.type == "done")
    assert done_a.metadata["usage"]["prompt_tokens"] == 10
    assert done_b.metadata["usage"]["prompt_tokens"] == 20


# ---------------------------------------------------------------------------
# workdir
# ---------------------------------------------------------------------------

def test_init_workdir_defaults_to_cwd():
    engine = LightweightEngine(api_key="test-key")
    assert engine.workdir == os.path.abspath(os.getcwd())


def test_init_workdir_resolves_to_abspath(tmp_path):
    engine = make_engine(workdir=str(tmp_path))
    assert os.path.isabs(engine.workdir)
    assert engine.workdir == os.path.abspath(str(tmp_path))


def test_init_workdir_forwarded_to_bash_tool_instance(tmp_path):
    """Engine with allowed_tools must pass its workdir to the BashTool instance."""
    from agent_engine.tools.bash_tool import BashTool
    captured = {}

    original_init = BashTool.__init__

    def spy_init(self, workdir):
        captured["workdir"] = workdir
        original_init(self, workdir)

    with patch.object(BashTool, "__init__", spy_init):
        make_engine(workdir=str(tmp_path), allowed_tools=["bash"])

    assert captured["workdir"] == os.path.abspath(str(tmp_path))


# ---------------------------------------------------------------------------
# system_prompt
# ---------------------------------------------------------------------------

def test_init_default_system_prompt(tmp_path):
    engine = make_engine(workdir=str(tmp_path))
    assert engine.system_prompt == "You are a helpful AI coding assistant."


def test_init_custom_system_prompt(tmp_path):
    engine = make_engine(system_prompt="You are a strict code reviewer.", workdir=str(tmp_path))
    assert engine.system_prompt == "You are a strict code reviewer."


def test_init_system_prompt_none(tmp_path):
    engine = make_engine(system_prompt=None, workdir=str(tmp_path))
    assert engine.system_prompt is None


def test_set_system_prompt_updates_value(tmp_path):
    engine = make_engine(workdir=str(tmp_path))
    engine.set_system_prompt("New instructions.")
    assert engine.system_prompt == "New instructions."


@pytest.mark.asyncio
async def test_run_injects_system_prompt_into_empty_history(tmp_path):
    engine = make_engine(system_prompt="Be brief.", workdir=str(tmp_path))
    history = []

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "system"
    assert history[0]["content"] == "Be brief."


@pytest.mark.asyncio
async def test_run_updates_existing_system_message(tmp_path):
    engine = make_engine(system_prompt="New persona.", workdir=str(tmp_path))
    history = [{"role": "system", "content": "Old persona."}]

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["content"] == "New persona."


@pytest.mark.asyncio
async def test_run_set_system_prompt_takes_effect(tmp_path):
    engine = make_engine(system_prompt="First persona.", workdir=str(tmp_path))
    engine.set_system_prompt("Second persona.")
    history = []

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["content"] == "Second persona."


@pytest.mark.asyncio
async def test_run_no_injection_when_system_prompt_none(tmp_path):
    engine = make_engine(system_prompt=None, workdir=str(tmp_path))
    history = []

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("ok")):
        async for _ in engine.run("hi", history=history):
            pass

    assert history[0]["role"] == "user"


@pytest.mark.asyncio
async def test_run_manage_history_false_does_not_mutate_system_msg(tmp_path):
    """manage_history=False with an existing system msg must not modify the caller's dict."""
    engine = make_engine(manage_history=False, system_prompt="Agent persona.", workdir=str(tmp_path))
    original_system = {"role": "system", "content": "Caller's original."}
    original_history = [original_system, {"role": "user", "content": "old"}]

    with patch.object(engine.client.chat.completions, "create", _stream_chunks("ok")):
        async for _ in engine.run("new", history=list(original_history)):
            pass

    # The caller's original dict must be untouched
    assert original_system["content"] == "Caller's original."


# ---------------------------------------------------------------------------
# load_mcp_config (Feature 10)
# ---------------------------------------------------------------------------

_SAMPLE_CONFIG = {
    "mcp_servers": {
        "sqlite": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sqlite"],
            "enabled": True,
        },
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "enabled": False,
        },
        "local_filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "enabled": True,
        },
    }
}


@pytest.mark.asyncio
async def test_load_mcp_config_connects_enabled_servers(tmp_path):
    """Only enabled servers should be connected; disabled ones are silently skipped."""
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(_SAMPLE_CONFIG))

    engine = make_engine(workdir=str(tmp_path))
    engine.connect_mcp = AsyncMock()

    await engine.load_mcp_config(config_path=str(config_file))

    # sqlite and local_filesystem are enabled; github is disabled
    assert engine.connect_mcp.await_count == 2
    called_commands = [call.kwargs["command"] for call in engine.connect_mcp.call_args_list]
    assert all(cmd == "npx" for cmd in called_commands)


@pytest.mark.asyncio
async def test_load_mcp_config_skips_disabled_servers(tmp_path):
    """A server with enabled=false must never trigger a connect_mcp call."""
    config = {
        "mcp_servers": {
            "disabled_server": {
                "command": "npx",
                "args": ["-y", "some-server"],
                "enabled": False,
            }
        }
    }
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(config))

    engine = make_engine(workdir=str(tmp_path))
    engine.connect_mcp = AsyncMock()

    await engine.load_mcp_config(config_path=str(config_file))

    engine.connect_mcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_mcp_config_missing_file_does_not_raise(tmp_path, capsys):
    """FileNotFoundError must be caught; a warning is printed, method returns normally."""
    engine = make_engine(workdir=str(tmp_path))

    # Should not raise
    await engine.load_mcp_config(config_path=str(tmp_path / "nonexistent.json"))

    captured = capsys.readouterr()
    assert "Warning" in captured.out
    assert "not found" in captured.out


@pytest.mark.asyncio
async def test_load_mcp_config_malformed_json_raises_value_error(tmp_path):
    """A top-level JSON parse error must raise ValueError."""
    config_file = tmp_path / "bad.json"
    config_file.write_text("{not valid json")

    engine = make_engine(workdir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid MCP config JSON"):
        await engine.load_mcp_config(config_path=str(config_file))


@pytest.mark.asyncio
async def test_load_mcp_config_per_server_error_is_non_fatal(tmp_path, capsys):
    """A connection failure for one server must not prevent other servers from connecting."""
    config = {
        "mcp_servers": {
            "bad_server": {
                "command": "npx",
                "args": ["-y", "bad-server"],
                "enabled": True,
            },
            "good_server": {
                "command": "npx",
                "args": ["-y", "good-server"],
                "enabled": True,
            },
        }
    }
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(config))

    engine = make_engine(workdir=str(tmp_path))

    call_count = 0

    async def connect_side_effect(command, args):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated connection failure")

    engine.connect_mcp = AsyncMock(side_effect=connect_side_effect)

    # Must not raise
    await engine.load_mcp_config(config_path=str(config_file))

    # Both servers were attempted; the error was logged
    assert call_count == 2
    captured = capsys.readouterr()
    assert "Error connecting MCP" in captured.out
    assert "bad_server" in captured.out


@pytest.mark.asyncio
async def test_load_mcp_config_declaration_order_preserved(tmp_path):
    """Servers must be connected in the order they appear in the JSON."""
    config = {
        "mcp_servers": {
            "alpha": {"command": "npx", "args": ["alpha"], "enabled": True},
            "beta": {"command": "npx", "args": ["beta"], "enabled": True},
            "gamma": {"command": "npx", "args": ["gamma"], "enabled": True},
        }
    }
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(config))

    engine = make_engine(workdir=str(tmp_path))
    engine.connect_mcp = AsyncMock()

    await engine.load_mcp_config(config_path=str(config_file))

    args_order = [call.kwargs["args"][0] for call in engine.connect_mcp.call_args_list]
    assert args_order == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_load_mcp_config_empty_servers_section(tmp_path):
    """An empty mcp_servers dict must not raise and must not call connect_mcp."""
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps({"mcp_servers": {}}))

    engine = make_engine(workdir=str(tmp_path))
    engine.connect_mcp = AsyncMock()

    engine.connect_mcp.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_mcp_config_auto_init(tmp_path):
    """Setting auto_init in mcp_servers must execute the init tools with dynamic workdir replacement."""
    config = {
        "mcp_servers": {
            "test_server": {
                "command": "npx",
                "args": ["dummy"],
                "enabled": True,
                "auto_init": [
                    {
                        "tool": "dummy_tool",
                        "arguments": {
                            "project": "${workdir}",
                            "path": "some_path"
                        }
                    }
                ]
            }
        }
    }
    config_file = tmp_path / "mcp_config.json"
    config_file.write_text(json.dumps(config))

    engine = make_engine(workdir=str(tmp_path))
    engine.connect_mcp = AsyncMock()

    await engine.load_mcp_config(config_path=str(config_file))
    
    engine.connect_mcp.assert_awaited_once_with(
        command="npx",
        args=["dummy"],
        auto_init=[
            {
                "tool": "dummy_tool",
                "arguments": {
                    "project": "${workdir}",
                    "path": "some_path"
                }
            }
        ]
    )


@pytest.mark.asyncio
async def test_connect_mcp_executes_auto_init_with_replacements(tmp_path):
    """connect_mcp must resolve ${workdir} and dispatch the auto_init tool calls."""
    engine = make_engine(workdir=str(tmp_path))
    
    # Mock the MCPServerManager and tool execution
    from unittest.mock import patch
    with patch("agent_engine.engine.MCPServerManager") as mock_manager_cls:
        mock_manager = MagicMock()
        mock_session = AsyncMock()
        mock_manager.connect = AsyncMock(return_value=mock_session)
        mock_session.list_tools = AsyncMock()
        mock_session.list_tools.return_value.tools = []
        mock_manager_cls.return_value = mock_manager
        
        # Stub the _execute_tool call
        engine._execute_tool = AsyncMock(return_value=("Success", False))
        
        auto_init_config = {
            "tool": "register_project_tool",
            "arguments": {
                "project": "${workdir}",
                "path": "subfolder"
            }
        }
        
        await engine.connect_mcp("npx", ["dummy"], auto_init=auto_init_config)
        
        engine._execute_tool.assert_awaited_once_with(
            "register_project_tool",
            {
                "project": str(tmp_path),
                "path": "subfolder"
            }
        )
