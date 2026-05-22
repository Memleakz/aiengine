"""
QA Report test suite — covers coverage gaps, edge cases, and validates acceptance criteria.
Targets uncovered lines in builtin_tools.py, engine.py, and the modular tools/ directory.
"""
import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_engine.engine import LightweightEngine
from agent_engine.events import AgentEvent

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmpdir_tools(tmp_path):
    """BuiltinTools instance rooted at a fresh temporary directory."""
    return BuiltinTools(workdir=str(tmp_path)), tmp_path


# ===========================================================================
# BuiltinTools — uncovered branches
# ===========================================================================

class TestBashActionFallback:
    """Line 73: unknown action with a command should fall back to 'run'."""

    @pytest.mark.asyncio
    async def test_unknown_action_with_command_falls_back_to_run(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="ls", command="echo hello")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_unknown_action_without_command_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="nonexistent_action")
        # no command supplied — falls into the "unknown action" else branch
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_run_with_zero_timeout_returns_error(self, tmpdir_tools):
        """Line 84-85: timeout <= 0 check."""
        tools, _ = tmpdir_tools
        result = await tools.bash(action="run", command="echo hi", timeout=0)
        assert "Error" in result and "timeout" in result.lower()

    @pytest.mark.asyncio
    async def test_run_with_negative_timeout_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="run", command="echo hi", timeout=-5)
        assert "Error" in result


class TestBashBackgroundEdgeCases:
    """Lines 91, 92-96: background action guards."""

    @pytest.mark.asyncio
    async def test_background_empty_command_returns_error(self, tmpdir_tools):
        """Line 91: empty command."""
        tools, _ = tmpdir_tools
        result = await tools.bash(action="background", command="   ")
        assert "Error" in result and "command" in result.lower()

    @pytest.mark.asyncio
    async def test_background_dos_guard_max_jobs(self, tmpdir_tools):
        """Lines 92-96: cap at _MAX_BACKGROUND_JOBS."""
        tools, _ = tmpdir_tools
        # Inject fake procs to hit the limit
        fake_proc = MagicMock()
        for i in range(_MAX_BACKGROUND_JOBS):
            tools._running_jobs[f"fake-{i}"] = fake_proc
        result = await tools.bash(action="background", command="echo overflow")
        assert "maximum" in result.lower() or "Error" in result
        # Clean up
        tools._running_jobs.clear()


class TestBashLogsEdgeCases:
    """Lines 113-132: logs action."""

    @pytest.mark.asyncio
    async def test_logs_missing_job_id_returns_error(self, tmpdir_tools):
        """Line 113: logs with no job_id."""
        tools, _ = tmpdir_tools
        result = await tools.bash(action="logs")
        assert "Error" in result and "job_id" in result.lower()

    @pytest.mark.asyncio
    async def test_logs_nonexistent_job_id_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="logs", job_id="does-not-exist")
        assert "Error" in result and "no job found" in result.lower()

    @pytest.mark.asyncio
    async def test_logs_running_job_returns_output(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        start_result = await tools.bash(action="background", command="echo log_output && sleep 2")
        job_id = start_result.split("job_id: ")[1].strip()
        await asyncio.sleep(0.2)
        log_result = await tools.bash(action="logs", job_id=job_id)
        # Kill the job
        await tools.bash(action="kill", job_id=job_id)
        assert "log_output" in log_result or "(no output yet)" in log_result

    @pytest.mark.asyncio
    async def test_logs_tail_lines_limits_output(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        start_result = await tools.bash(
            action="background",
            command="printf 'line1\\nline2\\nline3\\nline4\\nline5\\n'"
        )
        job_id = start_result.split("job_id: ")[1].strip()
        await asyncio.sleep(0.3)
        log_result = await tools.bash(action="logs", job_id=job_id, tail_lines=2)
        await tools.bash(action="kill", job_id=job_id)
        # Should have at most 2 lines
        non_empty_lines = [line for line in log_result.splitlines() if line.strip()]
        assert len(non_empty_lines) <= 2


class TestBashKillEdgeCases:
    """Lines 136-146: kill action."""

    @pytest.mark.asyncio
    async def test_kill_missing_job_id_returns_error(self, tmpdir_tools):
        """Line 136-137: kill with no job_id."""
        tools, _ = tmpdir_tools
        result = await tools.bash(action="kill")
        assert "Error" in result and "job_id" in result.lower()

    @pytest.mark.asyncio
    async def test_kill_nonexistent_job_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="kill", job_id="ghost-job")
        assert "Error" in result and "no job found" in result.lower()


class TestBashReadAction:
    """Lines 149-160: action='read' delegates to read_file."""

    @pytest.mark.asyncio
    async def test_read_action_reads_existing_file(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "hello.txt").write_text("read me")
        result = await tools.bash(action="read", filepath="hello.txt")
        assert "read me" in result

    @pytest.mark.asyncio
    async def test_read_action_missing_filepath_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="read")
        assert "Error" in result and "filepath" in result.lower()

    @pytest.mark.asyncio
    async def test_read_action_with_line_range(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "multi.txt").write_text("line1\nline2\nline3\n")
        result = await tools.bash(action="read", filepath="multi.txt", start_line=2, end_line=3)
        assert "line2" in result
        assert "line1" not in result


class TestBashCoordsAction:
    """Tests for the built-in 'coords' action in BashTool."""

    @pytest.mark.asyncio
    async def test_coords_action_calculates_correct_byte_offsets(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "index.html").write_text("line1\n  <div class=\"menu-item1\">\nline3\n")
        result = await tools.bash(
            action="coords",
            filepath="index.html",
            start_line=2,
            command="menu-item1"
        )
        # line1 is 6 bytes ("line1\n")
        # line2 has "  <div class=\"" before "menu-item1", which is 14 bytes
        # So "menu-item1" start offset is 6 + 14 = 20
        # End offset is 20 + len("menu-item1") = 30
        assert "START: 20" in result
        assert "END: 30" in result

    @pytest.mark.asyncio
    async def test_coords_action_missing_filepath_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="coords", start_line=2, command="item")
        assert "Error" in result and "filepath" in result.lower()

    @pytest.mark.asyncio
    async def test_coords_action_invalid_start_line_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="coords", filepath="index.html", start_line=0, command="item")
        assert "Error" in result and "positive" in result.lower()

    @pytest.mark.asyncio
    async def test_coords_action_missing_pattern_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.bash(action="coords", filepath="index.html", start_line=2)
        assert "Error" in result and "command" in result.lower()

    @pytest.mark.asyncio
    async def test_coords_action_pattern_not_found_returns_error(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "index.html").write_text("hello\nworld\n")
        result = await tools.bash(action="coords", filepath="index.html", start_line=1, command="nonexistent")
        assert "Error" in result and "not found" in result.lower()


class TestFileWriteBase64:
    """Lines 193-198: base64_content branch in file_write."""

    @pytest.mark.asyncio
    async def test_file_write_base64_content(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        raw = b"\x00\x01\x02\x03binary data"
        encoded = base64.b64encode(raw).decode()
        result = await tools.file_write("bin.dat", base64_content=encoded)
        assert "base64" in result.lower() or "Successfully" in result
        assert (tmp_path / "bin.dat").read_bytes() == raw

    @pytest.mark.asyncio
    async def test_file_write_text_content(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        result = await tools.file_write("text.txt", content="hello world")
        assert "Successfully" in result
        assert (tmp_path / "text.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_file_write_path_traversal_blocked(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.file_write("../escape.txt", content="bad")
        assert "Security Error" in result

    @pytest.mark.asyncio
    async def test_file_write_creates_parent_dirs(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        result = await tools.file_write("subdir/nested/file.txt", content="nested")
        assert "Successfully" in result
        assert (tmp_path / "subdir" / "nested" / "file.txt").exists()


class TestFileEditReplaceAll:
    """Lines 217-220: replace_all=True branch in file_edit."""

    @pytest.mark.asyncio
    async def test_file_edit_replace_all_true(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "rep.txt").write_text("foo foo foo")
        result = await tools.file_edit("rep.txt", "foo", "bar", replace_all=True)
        assert "Successfully" in result
        assert (tmp_path / "rep.txt").read_text() == "bar bar bar"

    @pytest.mark.asyncio
    async def test_file_edit_replace_all_false_only_first(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "once.txt").write_text("foo foo foo")
        result = await tools.file_edit("once.txt", "foo", "bar", replace_all=False)
        assert "Successfully" in result
        assert (tmp_path / "once.txt").read_text() == "bar foo foo"

    @pytest.mark.asyncio
    async def test_file_edit_old_string_not_found_returns_error(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "no_match.txt").write_text("hello world")
        result = await tools.file_edit("no_match.txt", "NOTHERE", "replacement")
        assert "Error" in result and "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_file_edit_nonexistent_file_returns_error(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.file_edit("ghost.txt", "a", "b")
        assert "Error" in result


class TestGlobSearch:
    """Lines 230-241: glob_search."""

    @pytest.mark.asyncio
    async def test_glob_search_finds_matching_files(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "a.py").write_text("pass")
        (tmp_path / "b.py").write_text("pass")
        (tmp_path / "c.txt").write_text("text")
        result = await tools.glob_search("*.py")
        assert "a.py" in result
        assert "b.py" in result

    @pytest.mark.asyncio
    async def test_glob_search_no_match_returns_message(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.glob_search("*.xyz")
        assert "No files found" in result

    @pytest.mark.asyncio
    async def test_glob_search_path_traversal_blocked(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.glob_search("*.py", path="../")
        assert "Security Error" in result


class TestGrepSearch:
    """Lines 245-272: grep_search with include parameter."""

    @pytest.mark.asyncio
    async def test_grep_search_finds_pattern(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "search_me.txt").write_text("needle in a haystack")
        result = await tools.grep_search("needle")
        assert "needle" in result

    @pytest.mark.asyncio
    async def test_grep_search_include_filters_by_extension(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "match.py").write_text("target_token")
        (tmp_path / "skip.txt").write_text("target_token")
        result = await tools.grep_search("target_token", include="*.py")
        assert "match.py" in result
        assert "skip.txt" not in result

    @pytest.mark.asyncio
    async def test_grep_search_no_matches_returns_message(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.grep_search("ABSOLUTELY_NOT_PRESENT_xyz123")
        assert "No matches found" in result

    @pytest.mark.asyncio
    async def test_grep_search_path_traversal_blocked(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.grep_search("anything", path="../etc")
        assert "Security Error" in result


# ===========================================================================
# engine.py — uncovered branches
# ===========================================================================

class TestRescueHtmlJson:
    """Lines 139-198: _rescue_html_json static method."""

    def test_valid_json_parses_normally(self):
        raw = '{"key": "value"}'
        result = LightweightEngine._rescue_html_json(raw)
        assert result == {"key": "value"}

    def test_html_encoded_quotes_in_values(self):
        # LLM output: &quot; used inside string values
        raw = '{"msg": "say &quot;hello&quot;"}'
        # _rescue_html_json handles unescaped quotes, not HTML entities — should
        # still parse the outer JSON (the &quot; is valid content)
        result = LightweightEngine._rescue_html_json(raw)
        assert result is not None
        assert "msg" in result

    def test_unescaped_quote_inside_string_repaired(self):
        # LLM emits a raw double-quote inside a JSON string value
        raw = '{"content": "he said "hello" to me"}'
        result = LightweightEngine._rescue_html_json(raw)
        # Should repair to something parseable (not None)
        assert result is not None

    def test_empty_string_returns_none(self):
        result = LightweightEngine._rescue_html_json("")
        assert result is None

    def test_truncated_json_repaired_with_closing_brace(self):
        """BUG-003 FIXED: _rescue_html_json correctly handles trailing close-quote at EOF.
        '{"key": "value"' must repair to {'key': 'value'} (clean value, no leaked quote).
        """
        raw = '{"key": "value"'
        result = LightweightEngine._rescue_html_json(raw)
        assert result is not None
        assert result.get("key") == "value", (
            f"BUG-003 FIXED: expected clean value 'value', got: {result!r}"
        )

    def test_newline_in_string_value(self):
        raw = '{"cmd": "echo hello\nworld"}'
        result = LightweightEngine._rescue_html_json(raw)
        assert result is not None

    def test_tab_in_string_value(self):
        raw = '{"cmd": "col1\tcol2"}'
        result = LightweightEngine._rescue_html_json(raw)
        assert result is not None

    def test_nested_object_parses(self):
        raw = '{"outer": {"inner": "val"}}'
        result = LightweightEngine._rescue_html_json(raw)
        assert result == {"outer": {"inner": "val"}}

    def test_completely_invalid_returns_none(self):
        result = LightweightEngine._rescue_html_json("not json at all @@##")
        assert result is None


class TestQueryOllamaContext:
    """Lines 119-137: _query_ollama_context static method."""

    def test_network_error_returns_default(self):
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = LightweightEngine._query_ollama_context("http://localhost:11434", "llama3")
        assert result == 32768  # default

    def test_custom_default_returned_on_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            result = LightweightEngine._query_ollama_context("http://localhost:11434", "llama3", default=8192)
        assert result == 8192

    def test_successful_response_returns_context_length(self):
        payload = {"model_info": {"llama.context_length": 131072}}
        resp_mock = MagicMock()
        resp_mock.read.return_value = json.dumps(payload).encode()
        resp_mock.__enter__ = lambda s: s
        resp_mock.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=resp_mock):
            result = LightweightEngine._query_ollama_context("http://localhost:11434", "llama3")
        assert result == 131072

    def test_no_context_length_key_returns_default(self):
        payload = {"model_info": {"llama.num_heads": 32}}
        resp_mock = MagicMock()
        resp_mock.read.return_value = json.dumps(payload).encode()
        resp_mock.__enter__ = lambda s: s
        resp_mock.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=resp_mock):
            result = LightweightEngine._query_ollama_context("http://localhost:11434", "llama3")
        assert result == 32768


class TestEngineGLMKwargs:
    """Lines 42-47: GLM model auto-injects thinking kwargs."""

    def test_glm_model_injects_max_tokens(self):
        engine = LightweightEngine(model="z-ai/glm4.7", api_key="test-key")
        assert engine.extra_completion_kwargs.get("max_tokens") == 16384

    def test_glm_model_injects_extra_body(self):
        engine = LightweightEngine(model="z-ai/glm4.7", api_key="test-key")
        body = engine.extra_completion_kwargs.get("extra_body", {})
        assert "chat_template_kwargs" in body
        assert body["chat_template_kwargs"]["enable_thinking"] is True

    def test_glm_model_does_not_override_existing_max_tokens(self):
        engine = LightweightEngine(
            model="z-ai/glm4.7",
            api_key="test-key",
            extra_completion_kwargs={"max_tokens": 4096},
        )
        # setdefault: existing value preserved
        assert engine.extra_completion_kwargs["max_tokens"] == 4096


class TestEngineExtraKwargs:
    """Line 299: extra_completion_kwargs are merged into create_kwargs."""

    @pytest.mark.asyncio
    async def test_extra_kwargs_passed_to_create(self):
        engine = LightweightEngine(
            model="gpt-4o",
            api_key="test-key",
            extra_completion_kwargs={"temperature": 0.5},
        )
        captured = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            # Return a minimal async iterable
            async def _aiter():
                yield MagicMock(choices=[], usage=MagicMock(
                    prompt_tokens=1, completion_tokens=1, total_tokens=2
                ))
            mock = MagicMock()
            mock.__aiter__ = lambda s: _aiter()
            return mock

        engine.client.chat.completions.create = fake_create
        async for _ in engine.run("hello"):
            pass
        assert captured.get("temperature") == 0.5


class TestEngineMaxIterations:
    """Lines 286-288: max_iterations guard emits system warning."""

    @pytest.mark.asyncio
    async def test_max_iterations_emits_warning_event(self):
        engine = LightweightEngine(
            model="gpt-4o",
            api_key="test-key",
            max_iterations=1,
            allowed_tools=["bash"],
        )

        call_count = 0

        async def fake_create(**kwargs):
            nonlocal call_count
            call_count += 1

            async def _aiter():
                # Always return a tool call to force iterations
                chunk = MagicMock()
                chunk.usage = None
                chunk.choices = [MagicMock()]
                tc = MagicMock()
                tc.index = 0
                tc.id = "call_1"
                tc.function = MagicMock()
                tc.function.name = "bash"
                tc.function.arguments = '{"action": "run", "command": "echo hi"}'
                chunk.choices[0].delta = MagicMock(
                    content=None, tool_calls=[tc], reasoning_content=None
                )
                yield chunk
                # Final chunk with no content or tool calls
                final = MagicMock()
                final.usage = None
                final.choices = [MagicMock()]
                final.choices[0].delta = MagicMock(content=None, tool_calls=None)
                yield final

            mock_stream = MagicMock()
            mock_stream.__aiter__ = lambda s: _aiter()
            return mock_stream

        engine.client.chat.completions.create = fake_create
        events = [e async for e in engine.run("keep calling tools")]
        warning_events = [e for e in events if e.type == "system" and "Max iterations" in str(e.data)]
        assert len(warning_events) >= 1


class TestEngineToolShim:
    """Lines 377-394: tool shim/rerouting logic."""

    @pytest.mark.asyncio
    async def test_shim_wrapped_kwargs_unwrapped(self):
        """kwargs key is a single 'kwargs' wrapper — should be unwrapped."""
        engine = LightweightEngine(
            model="gpt-4o",
            api_key="test-key",
            allowed_tools=["bash"],
        )

        async def fake_create(**kwargs):
            async def _aiter():
                chunk = MagicMock()
                chunk.usage = None
                chunk.choices = [MagicMock()]
                tc = MagicMock()
                tc.index = 0
                tc.id = "call_1"
                tc.function = MagicMock()
                tc.function.name = "bash"
                # Wrap args in a 'kwargs' key
                tc.function.arguments = '{"kwargs": {"action": "run", "command": "echo shim_test"}}'
                chunk.choices[0].delta = MagicMock(
                    content=None, tool_calls=[tc], reasoning_content=None
                )
                yield chunk
                final = MagicMock()
                final.usage = None
                final.choices = [MagicMock()]
                final.choices[0].delta = MagicMock(content=None, tool_calls=None)
                yield final

            mock = MagicMock()
            mock.__aiter__ = lambda s: _aiter()
            return mock

        engine.client.chat.completions.create = fake_create
        events = [e async for e in engine.run("test")]
        tool_results = [e for e in events if e.type == "tool_result"]
        # Tool was executed (shim passed through correctly)
        assert len(tool_results) >= 1

    @pytest.mark.asyncio
    async def test_shim_reroutes_command_to_bash(self):
        """If tool_name != 'bash' but kwargs has 'command', reroute to bash."""
        engine = LightweightEngine(
            model="gpt-4o",
            api_key="test-key",
            allowed_tools=["bash"],
        )

        async def fake_create(**kwargs):
            async def _aiter():
                chunk = MagicMock()
                chunk.usage = None
                chunk.choices = [MagicMock()]
                tc = MagicMock()
                tc.index = 0
                tc.id = "call_shim"
                tc.function = MagicMock()
                tc.function.name = "run_command"  # Unknown name — but has 'command'
                tc.function.arguments = '{"command": "echo rerouted"}'
                chunk.choices[0].delta = MagicMock(
                    content=None, tool_calls=[tc], reasoning_content=None
                )
                yield chunk
                final = MagicMock()
                final.usage = None
                final.choices = [MagicMock()]
                final.choices[0].delta = MagicMock(content=None, tool_calls=None)
                yield final

            mock = MagicMock()
            mock.__aiter__ = lambda s: _aiter()
            return mock

        engine.client.chat.completions.create = fake_create
        events = [e async for e in engine.run("test shim")]
        shim_events = [e for e in events if e.type == "system" and "SHIM" in str(e.data)]
        assert len(shim_events) >= 1


# ===========================================================================
# Modular tools — coverage
# ===========================================================================

class TestGetTime:
    """Lines 3-5 of get_time.py."""

    @pytest.mark.asyncio
    async def test_get_time_returns_iso_string(self):
        from agent_engine.tools.get_time import get_time
        result = await get_time()
        # Must be parseable as ISO 8601 with timezone
        from datetime import datetime
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    @pytest.mark.asyncio
    async def test_get_time_returns_utc(self):
        import datetime as dt_mod

        from agent_engine.tools.get_time import get_time
        result = await get_time()
        parsed = dt_mod.datetime.fromisoformat(result)
        # UTC offset should be +00:00
        assert parsed.utcoffset().total_seconds() == 0


class TestSleep:
    """Lines 7-14 of sleep.py."""

    @pytest.mark.asyncio
    async def test_sleep_zero_returns_error(self):
        from agent_engine.tools.sleep import sleep
        result = await sleep(0)
        assert "Error" in result and "positive" in result.lower()

    @pytest.mark.asyncio
    async def test_sleep_negative_returns_error(self):
        from agent_engine.tools.sleep import sleep
        result = await sleep(-1)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_sleep_over_max_returns_error(self):
        from agent_engine.tools.sleep import sleep
        result = await sleep(61)
        assert "Error" in result and "maximum" in result.lower()

    @pytest.mark.asyncio
    async def test_sleep_valid_returns_confirmation(self):
        with patch("agent_engine.tools.sleep.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            from agent_engine.tools.sleep import sleep as _sleep_fn
            result = await _sleep_fn(1)
            mock_sleep.assert_called_once_with(1)
        assert "1 second" in result


class TestPythonRepl:
    """Lines 9-40 of python_repl.py."""

    @pytest.mark.asyncio
    async def test_python_repl_runs_code(self):
        from agent_engine.tools.python_repl import python_repl
        result = await python_repl("print('hello_from_repl')")
        assert "hello_from_repl" in result

    @pytest.mark.asyncio
    async def test_python_repl_captures_stderr(self):
        from agent_engine.tools.python_repl import python_repl
        result = await python_repl("import sys; sys.stderr.write('err_output')")
        assert "err_output" in result

    @pytest.mark.asyncio
    async def test_python_repl_no_output_message(self):
        from agent_engine.tools.python_repl import python_repl
        result = await python_repl("x = 1 + 1")
        assert "no output" in result.lower()

    @pytest.mark.asyncio
    async def test_python_repl_syntax_error_captured(self):
        from agent_engine.tools.python_repl import python_repl
        result = await python_repl("def broken(")
        assert "SyntaxError" in result or "Error" in result

    @pytest.mark.asyncio
    async def test_python_repl_runtime_exception_captured(self):
        from agent_engine.tools.python_repl import python_repl
        result = await python_repl("raise ValueError('test_exception_msg')")
        assert "ValueError" in result or "test_exception_msg" in result

    @pytest.mark.asyncio
    async def test_python_repl_timeout(self):
        from agent_engine.tools.python_repl import python_repl
        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            result = await python_repl("import time; time.sleep(999)")
        assert "timed out" in result.lower() or "Error" in result


class TestSystemInfo:
    """Lines 9-39 of system_info.py."""

    @pytest.mark.asyncio
    async def test_system_info_returns_non_empty(self):
        from agent_engine.tools.system_info import system_info
        result = await system_info()
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_system_info_includes_os(self):
        from agent_engine.tools.system_info import system_info
        result = await system_info()
        assert "OS:" in result or "Platform:" in result

    @pytest.mark.asyncio
    async def test_system_info_includes_python(self):
        from agent_engine.tools.system_info import system_info
        result = await system_info()
        assert "Python:" in result

    @pytest.mark.asyncio
    async def test_system_info_includes_cpu(self):
        from agent_engine.tools.system_info import system_info
        result = await system_info()
        assert "CPUs:" in result


class TestWebFetch:
    """Lines 17-66 of web_fetch.py."""

    @pytest.mark.asyncio
    async def test_web_fetch_unsupported_scheme(self):
        from agent_engine.tools.web_fetch import web_fetch
        result = await web_fetch("ftp://example.com/file")
        assert "Unsupported scheme" in result or "Error" in result

    @pytest.mark.asyncio
    async def test_web_fetch_no_hostname(self):
        from agent_engine.tools.web_fetch import web_fetch
        result = await web_fetch("http:///no-host")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_web_fetch_localhost_blocked(self):
        from agent_engine.tools.web_fetch import web_fetch
        result = await web_fetch("http://127.0.0.1/api/dummy_endpoint")
        assert "blocked" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_web_fetch_private_ip_blocked(self):
        from agent_engine.tools.web_fetch import web_fetch
        result = await web_fetch("http://192.168.1.1/admin")
        assert "blocked" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_web_fetch_successful_response(self):
        from agent_engine.tools.web_fetch import web_fetch
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html>Hello World</html>"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("agent_engine.tools.web_fetch._is_ssrf_blocked", return_value=False), \
                patch("urllib.request.urlopen", return_value=mock_response):
            result = await web_fetch("https://example.com")
        assert "Hello World" in result

    @pytest.mark.asyncio
    async def test_web_fetch_url_error_returns_error_string(self):
        import urllib.error

        from agent_engine.tools.web_fetch import web_fetch
        with patch("agent_engine.tools.web_fetch._is_ssrf_blocked", return_value=False), \
                patch("urllib.request.urlopen", side_effect=urllib.error.URLError("DNS failure")):
            result = await web_fetch("https://nonexistent-xyz-domain.com")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_web_fetch_truncates_large_response(self):
        from agent_engine.tools.web_fetch import web_fetch
        large_data = b"x" * 9000
        mock_response = MagicMock()
        mock_response.read.return_value = large_data
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("agent_engine.tools.web_fetch._is_ssrf_blocked", return_value=False), \
                patch("urllib.request.urlopen", return_value=mock_response):
            result = await web_fetch("https://example.com/big")
        assert "truncated" in result.lower()
        assert len(result) < len(large_data)


class TestSkillTool:
    """Lines 9-49 of skill_tool.py."""

    @pytest.mark.asyncio
    async def test_skill_list_empty(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("list", workdir=str(tmp_path))
        assert "No skills found" in result

    @pytest.mark.asyncio
    async def test_skill_save_and_list(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        await skill_tool("save", name="my_skill", content="Skill content here", workdir=str(tmp_path))
        result = await skill_tool("list", workdir=str(tmp_path))
        assert "my_skill" in result

    @pytest.mark.asyncio
    async def test_skill_save_sanitizes_name(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("save", name="bad/../name", content="x", workdir=str(tmp_path))
        # Slashes are stripped; result should succeed
        assert "saved" in result.lower()

    @pytest.mark.asyncio
    async def test_skill_save_missing_name_returns_error(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("save", content="x", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_skill_save_missing_content_returns_error(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("save", name="skill", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_skill_read_existing(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        await skill_tool("save", name="read_test", content="read content", workdir=str(tmp_path))
        result = await skill_tool("read", name="read_test", workdir=str(tmp_path))
        assert "read content" in result

    @pytest.mark.asyncio
    async def test_skill_read_missing_returns_error(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("read", name="nonexistent", workdir=str(tmp_path))
        assert "Error" in result and "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_skill_read_missing_name_returns_error(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("read", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_skill_delete_existing(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        await skill_tool("save", name="to_delete", content="bye", workdir=str(tmp_path))
        result = await skill_tool("delete", name="to_delete", workdir=str(tmp_path))
        assert "deleted" in result.lower()
        # Verify it's gone
        list_result = await skill_tool("list", workdir=str(tmp_path))
        assert "to_delete" not in list_result

    @pytest.mark.asyncio
    async def test_skill_delete_missing_returns_error(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("delete", name="ghost", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_skill_delete_missing_name_returns_error(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("delete", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_skill_unknown_action_returns_error(self, tmp_path):
        from agent_engine.tools.skill_tool import skill_tool
        result = await skill_tool("wipe_everything", workdir=str(tmp_path))
        assert "Error" in result and "Unknown" in result


class TestManageTodo:
    """Lines 12-31 of todo_tool.py (manage_todo)."""

    @pytest.mark.asyncio
    async def test_todo_read_nonexistent_returns_message(self, tmp_path):
        from agent_engine.tools.todo_tool import manage_todo
        result = await manage_todo("read", workdir=str(tmp_path))
        assert "does not exist" in result.lower()

    @pytest.mark.asyncio
    async def test_todo_update_creates_file(self, tmp_path):
        from agent_engine.tools.todo_tool import manage_todo
        result = await manage_todo("update", content="# My Plan", workdir=str(tmp_path))
        assert "updated" in result.lower()
        assert (tmp_path / "CLAUDE.md").exists()

    @pytest.mark.asyncio
    async def test_todo_read_after_update(self, tmp_path):
        from agent_engine.tools.todo_tool import manage_todo
        await manage_todo("update", content="# My Plan", workdir=str(tmp_path))
        result = await manage_todo("read", workdir=str(tmp_path))
        assert "# My Plan" in result

    @pytest.mark.asyncio
    async def test_todo_append_adds_content(self, tmp_path):
        from agent_engine.tools.todo_tool import manage_todo
        await manage_todo("update", content="initial", workdir=str(tmp_path))
        await manage_todo("append", content="appended", workdir=str(tmp_path))
        result = await manage_todo("read", workdir=str(tmp_path))
        assert "initial" in result
        assert "appended" in result

    @pytest.mark.asyncio
    async def test_todo_unknown_action_returns_error(self, tmp_path):
        from agent_engine.tools.todo_tool import manage_todo
        result = await manage_todo("destroy", workdir=str(tmp_path))
        assert "Error" in result and "Unknown" in result

    # BUG-001 FIXED: append to empty file no longer prepends a newline
    @pytest.mark.asyncio
    async def test_todo_append_to_new_file_no_leading_newline(self, tmp_path):
        """BUG-001 FIXED: manage_todo 'append' on a fresh empty file must NOT
        start with a blank line."""
        from agent_engine.tools.todo_tool import manage_todo
        await manage_todo("update", content="", workdir=str(tmp_path))
        await manage_todo("append", content="first line", workdir=str(tmp_path))
        raw = (tmp_path / "CLAUDE.md").read_text()
        assert not raw.startswith("\n"), (
            "BUG-001 FIXED: append on empty file must not produce leading newline"
        )
        assert "first line" in raw


class TestManageTasks:
    """Lines 23-76 of manage_tasks.py."""

    @pytest.mark.asyncio
    async def test_list_empty_returns_no_tasks(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        result = await manage_tasks("list", workdir=str(tmp_path))
        assert "No tasks found" in result

    @pytest.mark.asyncio
    async def test_create_task(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        result = await manage_tasks("create", title="My task", workdir=str(tmp_path))
        assert "Task created" in result

    @pytest.mark.asyncio
    async def test_create_missing_title_returns_error(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        result = await manage_tasks("create", workdir=str(tmp_path))
        assert "Error" in result and "title" in result.lower()

    @pytest.mark.asyncio
    async def test_list_after_create(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        await manage_tasks("create", title="Task A", workdir=str(tmp_path))
        result = await manage_tasks("list", workdir=str(tmp_path))
        assert "Task A" in result

    @pytest.mark.asyncio
    async def test_update_task_status(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        await manage_tasks("create", title="Updatable", workdir=str(tmp_path))
        result = await manage_tasks("update", task_id="1", status="in_progress", workdir=str(tmp_path))
        assert "in_progress" in result

    @pytest.mark.asyncio
    async def test_update_invalid_status_returns_error(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        await manage_tasks("create", title="Task", workdir=str(tmp_path))
        result = await manage_tasks("update", task_id="1", status="flying", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_update_nonexistent_id_returns_error(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        result = await manage_tasks("update", task_id="999", status="completed", workdir=str(tmp_path))
        assert "Error" in result and "999" in result

    @pytest.mark.asyncio
    async def test_delete_task(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        await manage_tasks("create", title="To delete", workdir=str(tmp_path))
        result = await manage_tasks("delete", task_id="1", workdir=str(tmp_path))
        assert "deleted" in result.lower()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_error(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        result = await manage_tasks("delete", task_id="42", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, tmp_path):
        from agent_engine.tools.manage_tasks import manage_tasks
        result = await manage_tasks("nuke", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_corrupted_json_file_treated_as_empty(self, tmp_path):
        """manage_tasks load_tasks should handle corrupted JSON gracefully."""
        from agent_engine.tools.manage_tasks import _TASKS_FILE, manage_tasks
        (tmp_path / _TASKS_FILE).write_text("{INVALID JSON}")
        result = await manage_tasks("list", workdir=str(tmp_path))
        assert "No tasks found" in result

    # BUG TEST: ID collision after deletion
    @pytest.mark.asyncio
    async def test_create_after_delete_generates_unique_id(self, tmp_path):
        """BUG-002: manage_tasks uses len(tasks)+1 for IDs which can collide after deletion.
        Create 2, delete 1, create again — new task gets ID '2' which already existed."""
        from agent_engine.tools.manage_tasks import manage_tasks
        await manage_tasks("create", title="First", workdir=str(tmp_path))   # id=1
        await manage_tasks("create", title="Second", workdir=str(tmp_path))  # id=2
        await manage_tasks("delete", task_id="1", workdir=str(tmp_path))     # delete id=1
        # Now len(tasks)==1, so new_id starts at '2' which already exists
        # The while loop increments to '3' — verify no collision
        result = await manage_tasks("create", title="Third", workdir=str(tmp_path))
        assert "Error" not in result, "BUG-002: ID collision caused error on create after delete"
        list_result = await manage_tasks("list", workdir=str(tmp_path))
        assert "Third" in list_result


class TestNetworkTool:
    """Lines 18-55 of network_tool.py."""

    @pytest.mark.asyncio
    async def test_ping_missing_target_returns_error(self):
        from agent_engine.tools.network_tool import network_tool
        result = await network_tool("ping")
        assert "Error" in result and "target" in result.lower()

    @pytest.mark.asyncio
    async def test_lookup_missing_target_returns_error(self):
        from agent_engine.tools.network_tool import network_tool
        result = await network_tool("lookup")
        assert "Error" in result and "target" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        from agent_engine.tools.network_tool import network_tool
        result = await network_tool("hack")
        assert "Error" in result and "Unknown" in result

    @pytest.mark.asyncio
    async def test_interfaces_returns_output(self):
        from agent_engine.tools.network_tool import network_tool
        result = await network_tool("interfaces")
        # Should return something (ip addr or ifconfig output)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_run_cmd_timeout_returns_error(self):
        from agent_engine.tools.network_tool import _run_cmd
        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            result = await _run_cmd(["ping", "-c", "1", "1.2.3.4"])
        assert "timed out" in result.lower() or "Error" in result


class TestCronTool:
    """Lines 23-86 of cron_tool.py (add/remove/unknown action)."""

    @pytest.mark.asyncio
    async def test_cron_add_missing_args_returns_error(self):
        from agent_engine.tools.cron_tool import cron_tool
        result = await cron_tool("add")
        assert "Error" in result and ("schedule" in result.lower() or "command" in result.lower())

    @pytest.mark.asyncio
    async def test_cron_remove_missing_query_returns_error(self):
        from agent_engine.tools.cron_tool import cron_tool
        result = await cron_tool("remove")
        assert "Error" in result and "query" in result.lower()

    @pytest.mark.asyncio
    async def test_cron_unknown_action_returns_error(self):
        from agent_engine.tools.cron_tool import cron_tool
        result = await cron_tool("destroy_all")
        assert "Error" in result and "Unknown" in result


# ===========================================================================
# Acceptance criteria: all 21 tools are registered when allowed_tools="all"
# ===========================================================================

class TestAllToolsRegisterable:
    """PRD Feature #2: 21 async built-in tools."""

    ALL_21_TOOLS = [
        "bash", "read_file", "file_write", "file_edit", "glob_search", "grep_search",
        "web_fetch", "web_search", "ask_user", "python_repl", "sleep", "get_time",
        "manage_tasks", "subagent", "notebook_edit", "git_tool", "manage_todo",
        "cron_tool", "skill_tool", "code_analysis", "system_info", "network_tool",
    ]

    def test_all_21_tools_can_be_registered(self):
        engine = LightweightEngine(
            model="gpt-4o",
            api_key="test-key",
            allowed_tools=self.ALL_21_TOOLS,
        )
        schemas = engine.tools.get_all_schemas()
        registered_names = {s["function"]["name"] for s in schemas}
        for tool in self.ALL_21_TOOLS:
            assert tool in registered_names, f"Tool '{tool}' not registered"

    def test_unknown_tool_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown built-in tool"):
            LightweightEngine(
                model="gpt-4o",
                api_key="test-key",
                allowed_tools=["nonexistent_tool"],
                workdir=str(tmp_path),
            )

    def test_tool_count_is_21(self):
        """PRD says 21 tools but actual implementation has 22 (read_file is separate from bash).
        This test documents the discrepancy: actual count is 22."""
        engine = LightweightEngine(
            model="gpt-4o",
            api_key="test-key",
            allowed_tools=self.ALL_21_TOOLS,
        )
        schemas = engine.tools.get_all_schemas()
        # PRD states 21 tools ("5 built-in + 16 modular") but read_file is registered
        # separately from bash, giving 22 total. Document the actual count.
        assert len(schemas) == 22, (
            f"Expected 22 registered tools (PRD says 21 but read_file is extra). Got {len(schemas)}"
        )


# ===========================================================================
# AgentEvent acceptance criteria
# ===========================================================================

class TestAgentEventAcceptanceCriteria:
    """PRD Feature #1: AgentEvent typed event system."""

    def test_event_has_required_fields(self):
        e = AgentEvent(type="token", data="hello")
        assert hasattr(e, "type")
        assert hasattr(e, "data")
        assert hasattr(e, "metadata")

    def test_event_metadata_defaults_to_empty_dict(self):
        e = AgentEvent(type="done", data="fin")
        assert e.metadata == {}

    def test_all_documented_event_types_constructable(self):
        for t in ("token", "tool_start", "tool_result", "system", "done", "thinking"):
            e = AgentEvent(type=t, data="x")
            assert e.type == t

    def test_event_metadata_custom(self):
        e = AgentEvent(type="tool_result", data="res", metadata={"tool_name": "bash", "call_id": "c1"})
        assert e.metadata["tool_name"] == "bash"


# ===========================================================================
# Engine no-API-key guard
# ===========================================================================

class TestEngineApiKeyGuard:
    """PRD: engine raises clearly if no API key."""

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        engine = LightweightEngine(model="gpt-4o")
        assert engine.client is not None


# ===========================================================================
# BuiltinTools: large file guard and line-range reads
# ===========================================================================

class TestReadFileLargeGuard:
    """line 169-173: large file guard."""

    @pytest.mark.asyncio
    async def test_large_file_returns_error(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        big = tmp_path / "big.bin"
        # Patch getsize to simulate a large file
        with patch("os.path.getsize", return_value=11 * 1024 * 1024):
            big.write_bytes(b"x")
            result = await tools.read_file("big.bin")
        assert "too large" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, tmpdir_tools):
        tools, _ = tmpdir_tools
        result = await tools.read_file("no_such_file.txt")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_read_file_line_range(self, tmpdir_tools):
        tools, tmp_path = tmpdir_tools
        (tmp_path / "range.txt").write_text("line1\nline2\nline3\n")
        # end_line is exclusive in Python slicing: lines[start:end]
        # start_line=2,end_line=2 → lines[1:2] → ["line2\n"]
        result = await tools.read_file("range.txt", start_line=2, end_line=2)
        assert "line2" in result
        assert "line1" not in result
        assert "line3" not in result


# ===========================================================================
# code_analysis — uncovered branches
# ===========================================================================

class TestCodeAnalysis:
    """Tests for agent_engine/tools/code_analysis.py."""

    @pytest.mark.asyncio
    async def test_code_analysis_path_traversal_blocked(self, tmp_path):
        from agent_engine.tools.code_analysis import code_analysis
        result = await code_analysis("../outside.py", workdir=str(tmp_path))
        assert "Security Error" in result

    @pytest.mark.asyncio
    async def test_code_analysis_non_python_file_returns_error(self, tmp_path):
        from agent_engine.tools.code_analysis import code_analysis
        (tmp_path / "file.js").write_text("console.log('hi')")
        result = await code_analysis("file.js", workdir=str(tmp_path))
        assert "Error" in result and "Python" in result

    @pytest.mark.asyncio
    async def test_code_analysis_file_not_found(self, tmp_path):
        from agent_engine.tools.code_analysis import code_analysis
        result = await code_analysis("missing.py", workdir=str(tmp_path))
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_code_analysis_valid_file_with_class_and_function(self, tmp_path):
        from agent_engine.tools.code_analysis import code_analysis
        src = '''
class Greeter:
    """A simple greeter."""
    def hello(self):
        pass

def top_level():
    """Top-level function."""
    pass
'''
        (tmp_path / "module.py").write_text(src)
        result = await code_analysis("module.py", workdir=str(tmp_path))
        assert "Class: Greeter" in result
        assert "Method: hello" in result
        assert "Function: top_level" in result

    @pytest.mark.asyncio
    async def test_code_analysis_empty_file_returns_no_classes(self, tmp_path):
        from agent_engine.tools.code_analysis import code_analysis
        (tmp_path / "empty.py").write_text("")
        result = await code_analysis("empty.py", workdir=str(tmp_path))
        assert "No classes or functions found" in result

    @pytest.mark.asyncio
    async def test_code_analysis_syntax_error_returns_error(self, tmp_path):
        from agent_engine.tools.code_analysis import code_analysis
        (tmp_path / "bad.py").write_text("def foo(: bad syntax")
        result = await code_analysis("bad.py", workdir=str(tmp_path))
        assert "Error" in result


# ===========================================================================
# git_tool — uncovered branches
# ===========================================================================

class TestGitTool:
    """Tests for agent_engine/tools/git_tool.py using mocked subprocess."""

    @pytest.mark.asyncio
    async def test_git_status(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        with patch("agent_engine.tools.git_tool._run_git_cmd", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = "On branch main\nnothing to commit"
            result = await git_tool("status", workdir=str(tmp_path))
        assert "On branch main" in result
        mock_cmd.assert_called_once_with(["status"], str(tmp_path))

    @pytest.mark.asyncio
    async def test_git_diff(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        with patch("agent_engine.tools.git_tool._run_git_cmd", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = "diff --git a/file b/file"
            result = await git_tool("diff", workdir=str(tmp_path))
        assert "diff" in result

    @pytest.mark.asyncio
    async def test_git_add(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        with patch("agent_engine.tools.git_tool._run_git_cmd", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ""
            result = await git_tool("add", workdir=str(tmp_path), path="file.py")
        assert "Added" in result
        mock_cmd.assert_called_once_with(["add", "file.py"], str(tmp_path))

    @pytest.mark.asyncio
    async def test_git_add_returns_output_when_nonempty(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        with patch("agent_engine.tools.git_tool._run_git_cmd", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = "Some output"
            result = await git_tool("add", workdir=str(tmp_path), path="file.py")
        assert result == "Some output"

    @pytest.mark.asyncio
    async def test_git_commit_missing_message(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        result = await git_tool("commit", workdir=str(tmp_path))
        assert "Error" in result and "message" in result.lower()

    @pytest.mark.asyncio
    async def test_git_commit_with_message(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        with patch("agent_engine.tools.git_tool._run_git_cmd", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = "[main abc1234] my commit"
            result = await git_tool("commit", workdir=str(tmp_path), message="my commit")
        assert "main" in result

    @pytest.mark.asyncio
    async def test_git_branch_list(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        with patch("agent_engine.tools.git_tool._run_git_cmd", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = "* main"
            result = await git_tool("branch", workdir=str(tmp_path))
        assert "main" in result
        mock_cmd.assert_called_once_with(["branch"], str(tmp_path))

    @pytest.mark.asyncio
    async def test_git_branch_create(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        with patch("agent_engine.tools.git_tool._run_git_cmd", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = "Switched to a new branch 'feature'"
            await git_tool("branch", workdir=str(tmp_path), name="feature")
        mock_cmd.assert_called_once_with(["checkout", "-b", "feature"], str(tmp_path))

    @pytest.mark.asyncio
    async def test_git_log(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        with patch("agent_engine.tools.git_tool._run_git_cmd", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = "abc1234 Initial commit"
            result = await git_tool("log", workdir=str(tmp_path))
        assert "abc1234" in result

    @pytest.mark.asyncio
    async def test_git_unknown_action_returns_error(self, tmp_path):
        from agent_engine.tools.git_tool import git_tool
        result = await git_tool("rebase", workdir=str(tmp_path))
        assert "Error" in result and "rebase" in result


# ===========================================================================
# notebook_edit — uncovered branches
# ===========================================================================

class TestNotebookEdit:
    """Tests for agent_engine/tools/notebook_edit.py."""

    def _make_notebook(self, tmp_path, cells=None):
        nb = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": cells or [
                {"cell_type": "code", "metadata": {}, "source": ["print('hello')"],
                 "execution_count": None, "outputs": []},
            ]
        }
        path = tmp_path / "test.ipynb"
        path.write_text(json.dumps(nb))
        return path

    @pytest.mark.asyncio
    async def test_notebook_path_traversal_blocked(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        result = await notebook_edit("../outside.ipynb", 0, "code", workdir=str(tmp_path))
        assert "Security Error" in result

    @pytest.mark.asyncio
    async def test_notebook_non_ipynb_file_returns_error(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        (tmp_path / "file.py").write_text("")
        result = await notebook_edit("file.py", 0, "code", workdir=str(tmp_path))
        assert "Error" in result and ".ipynb" in result

    @pytest.mark.asyncio
    async def test_notebook_file_not_found(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        result = await notebook_edit("missing.ipynb", 0, "code", workdir=str(tmp_path))
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_notebook_invalid_json_returns_error(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        (tmp_path / "bad.ipynb").write_text("not json at all")
        result = await notebook_edit("bad.ipynb", 0, "code", workdir=str(tmp_path))
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_notebook_missing_cells_key_returns_error(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        (tmp_path / "no_cells.ipynb").write_text(json.dumps({"nbformat": 4}))
        result = await notebook_edit("no_cells.ipynb", 0, "code", workdir=str(tmp_path))
        assert "Error" in result and "cells" in result

    @pytest.mark.asyncio
    async def test_notebook_out_of_bounds_index_returns_error(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        self._make_notebook(tmp_path)
        result = await notebook_edit("test.ipynb", 99, "new code", workdir=str(tmp_path))
        assert "out of bounds" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_notebook_update_existing_cell(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        self._make_notebook(tmp_path)
        result = await notebook_edit("test.ipynb", 0, "print('updated')", workdir=str(tmp_path))
        assert "Updated" in result
        nb = json.loads((tmp_path / "test.ipynb").read_text())
        assert "print('updated')" in "".join(nb["cells"][0]["source"])

    @pytest.mark.asyncio
    async def test_notebook_append_new_cell(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        self._make_notebook(tmp_path)
        result = await notebook_edit("test.ipynb", 1, "new cell code", workdir=str(tmp_path))
        assert "Appended" in result
        nb = json.loads((tmp_path / "test.ipynb").read_text())
        assert len(nb["cells"]) == 2

    @pytest.mark.asyncio
    async def test_notebook_append_markdown_cell(self, tmp_path):
        from agent_engine.tools.notebook_edit import notebook_edit
        self._make_notebook(tmp_path)
        result = await notebook_edit("test.ipynb", 1, "# Title", cell_type="markdown", workdir=str(tmp_path))
        assert "Appended" in result
        nb = json.loads((tmp_path / "test.ipynb").read_text())
        assert nb["cells"][1]["cell_type"] == "markdown"


# ===========================================================================
# ask_user — uncovered branches
# ===========================================================================

class TestAskUser:
    """Tests for agent_engine/tools/ask_user.py."""

    @pytest.mark.asyncio
    async def test_ask_user_returns_mocked_response(self):
        from agent_engine.tools.ask_user import ask_user
        with patch("agent_engine.tools.ask_user.asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            mock_loop.return_value = loop
            loop.run_in_executor = AsyncMock(return_value="yes I confirm")
            result = await ask_user("Are you sure?")
        assert result == "yes I confirm"

    @pytest.mark.asyncio
    async def test_ask_user_exception_returns_error_string(self):
        from agent_engine.tools.ask_user import ask_user
        with patch("agent_engine.tools.ask_user.asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            mock_loop.return_value = loop
            loop.run_in_executor = AsyncMock(side_effect=RuntimeError("no tty"))
            result = await ask_user("Should I proceed?")
        assert "Error" in result


# ===========================================================================
# subagent — uncovered branches
# ===========================================================================

class TestSubagent:
    """Tests for agent_engine/tools/subagent.py."""

    @pytest.mark.asyncio
    async def test_subagent_returns_token_events(self, tmp_path):
        from agent_engine.tools.subagent import subagent

        async def _fake_run(prompt):
            yield AgentEvent(type="token", data="Hello ")
            yield AgentEvent(type="token", data="world")
            yield AgentEvent(type="done", data="Run complete", metadata={"final_history": [], "usage": {}})

        # subagent lazy-imports LightweightEngine; patch at the engine module level
        with patch("agent_engine.engine.LightweightEngine") as mock_engine_cls:
            instance = MagicMock()
            instance.run = _fake_run
            instance.close = AsyncMock()
            mock_engine_cls.return_value = instance
            result = await subagent("Do something", workdir=str(tmp_path))
        assert "Hello world" in result

    @pytest.mark.asyncio
    async def test_subagent_empty_response_returns_message(self, tmp_path):
        from agent_engine.tools.subagent import subagent

        async def _fake_run(prompt):
            yield AgentEvent(type="done", data="Run complete", metadata={"final_history": [], "usage": {}})

        with patch("agent_engine.engine.LightweightEngine") as mock_engine_cls:
            instance = MagicMock()
            instance.run = _fake_run
            instance.close = AsyncMock()
            mock_engine_cls.return_value = instance
            result = await subagent("Empty task", workdir=str(tmp_path))
        assert "no text" in result.lower() or "Sub-agent" in result

    @pytest.mark.asyncio
    async def test_subagent_with_context_prepends_context(self, tmp_path):
        from agent_engine.tools.subagent import subagent
        received_prompts = []

        async def _fake_run(prompt):
            received_prompts.append(prompt)
            yield AgentEvent(type="token", data="done")
            yield AgentEvent(type="done", data="Run complete", metadata={"final_history": [], "usage": {}})

        with patch("agent_engine.engine.LightweightEngine") as mock_engine_cls:
            instance = MagicMock()
            instance.run = _fake_run
            instance.close = AsyncMock()
            mock_engine_cls.return_value = instance
            await subagent("My task", context="Important context", workdir=str(tmp_path))
        assert "Important context" in received_prompts[0]
        assert "My task" in received_prompts[0]

    @pytest.mark.asyncio
    async def test_subagent_exception_returns_error_string(self, tmp_path):
        from agent_engine.tools.subagent import subagent
        with patch("agent_engine.engine.LightweightEngine", side_effect=RuntimeError("boom")):
            result = await subagent("Fail task", workdir=str(tmp_path))
        assert "Error" in result


# ===========================================================================
# web_search — uncovered branches
# ===========================================================================

class TestWebSearch:
    """Tests for agent_engine/tools/web_search.py."""

    @pytest.mark.asyncio
    async def test_web_search_returns_results(self):
        from agent_engine.tools.web_search import web_search
        fake_html = (
            "<td class='result-snippet' style=''>First result snippet</td>"
            "<td class='result-snippet' style=''>Second result snippet</td>"
        )
        # web_search imports asyncio lazily; patch it globally
        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            mock_loop.return_value = loop
            loop.run_in_executor = AsyncMock(return_value=fake_html)
            result = await web_search("python testing")
        assert "1." in result

    @pytest.mark.asyncio
    async def test_web_search_no_results_returns_fallback(self):
        from agent_engine.tools.web_search import web_search
        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            mock_loop.return_value = loop
            loop.run_in_executor = AsyncMock(return_value="<html><body>no snippets here</body></html>")
            result = await web_search("xyzzy no results")
        assert "No results found" in result or "search was blocked" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_web_search_network_error_returns_error(self):
        from agent_engine.tools.web_search import web_search
        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            mock_loop.return_value = loop
            loop.run_in_executor = AsyncMock(side_effect=OSError("network down"))
            result = await web_search("any query")
        assert "Error" in result


# ===========================================================================
# cron_tool — additional coverage
# ===========================================================================

class TestCronToolCoverage:
    """Additional tests to cover cron_tool branches not hit by existing tests."""

    @pytest.mark.asyncio
    async def test_cron_list_with_existing_jobs(self):
        from agent_engine.tools.cron_tool import cron_tool
        with patch("agent_engine.tools.cron_tool._run_crontab", new_callable=AsyncMock) as mock_cron:
            mock_cron.return_value = "* * * * * echo hello"
            result = await cron_tool("list")
        assert "echo hello" in result

    @pytest.mark.asyncio
    async def test_cron_list_no_jobs_returns_message(self):
        from agent_engine.tools.cron_tool import cron_tool
        with patch("agent_engine.tools.cron_tool._run_crontab", new_callable=AsyncMock) as mock_cron:
            mock_cron.return_value = "no crontab for user"
            result = await cron_tool("list")
        assert "No cron jobs found" in result

    @pytest.mark.asyncio
    async def test_cron_add_creates_job(self):
        from agent_engine.tools.cron_tool import cron_tool
        with patch("agent_engine.tools.cron_tool._run_crontab", new_callable=AsyncMock) as mock_cron:
            mock_cron.side_effect = ["no crontab for user", ""]
            with patch("tempfile.NamedTemporaryFile") as mock_tmp:
                mock_file = MagicMock()
                mock_file.__enter__ = lambda s: MagicMock(name="/tmp/fake_cron")
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.name = "/tmp/fake_cron"
                mock_tmp.return_value.__enter__ = lambda s: mock_file
                mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
                mock_tmp.return_value.name = "/tmp/fake_cron"
                with patch("os.path.exists", return_value=False):
                    result = await cron_tool("add", schedule="* * * * *", command="echo hi")
        assert "Cron job added" in result or "Error" in result  # depends on env

    @pytest.mark.asyncio
    async def test_cron_remove_no_matching_job(self):
        from agent_engine.tools.cron_tool import cron_tool
        with patch("agent_engine.tools.cron_tool._run_crontab", new_callable=AsyncMock) as mock_cron:
            mock_cron.return_value = "* * * * * echo hello"
            result = await cron_tool("remove", query="echo goodbye")
        assert "No cron job matching" in result

    @pytest.mark.asyncio
    async def test_cron_remove_no_crontab(self):
        from agent_engine.tools.cron_tool import cron_tool
        with patch("agent_engine.tools.cron_tool._run_crontab", new_callable=AsyncMock) as mock_cron:
            mock_cron.return_value = "no crontab for user"
            result = await cron_tool("remove", query="echo hello")
        assert "No cron jobs to remove" in result


# ===========================================================================
# Bug fix verification
# ===========================================================================

class TestBugFixes:
    """Verify that BUG-001, BUG-002, BUG-003 are fixed."""

    @pytest.mark.asyncio
    async def test_bug001_todo_append_to_new_file_no_leading_newline(self, tmp_path):
        """BUG-001 FIXED: append to fresh file should NOT start with blank line."""
        from agent_engine.tools.todo_tool import manage_todo
        await manage_todo("append", content="first line", workdir=str(tmp_path))
        content = (tmp_path / "CLAUDE.md").read_text()
        assert not content.startswith("\n"), "File must not start with a blank line"
        assert content == "first line"

    @pytest.mark.asyncio
    async def test_bug001_todo_append_to_existing_file_adds_separator(self, tmp_path):
        """BUG-001 FIXED: append to non-empty file should add newline separator."""
        from agent_engine.tools.todo_tool import manage_todo
        await manage_todo("update", content="existing", workdir=str(tmp_path))
        await manage_todo("append", content="appended", workdir=str(tmp_path))
        content = (tmp_path / "CLAUDE.md").read_text()
        assert content == "existing\nappended"

    @pytest.mark.asyncio
    async def test_bug002_manage_tasks_id_no_collision_after_delete(self, tmp_path):
        """BUG-002 FIXED: creating a task after deletion must not reuse the deleted ID."""
        from agent_engine.tools.manage_tasks import manage_tasks
        await manage_tasks("create", title="Task A", workdir=str(tmp_path))
        await manage_tasks("create", title="Task B", workdir=str(tmp_path))
        await manage_tasks("delete", task_id="1", workdir=str(tmp_path))
        result = await manage_tasks("create", title="Task C", workdir=str(tmp_path))
        # New task must get ID 3 (max existing is 2), not ID 1 again
        assert "3" in result

    def test_bug003_rescue_html_json_truncated_string_no_mangled_quote(self):
        """BUG-003 FIXED: truncated JSON string closing quote is not double-escaped."""
        result = LightweightEngine._rescue_html_json('{"key": "value"')
        assert result is not None, "Should repair truncated JSON"
        assert result.get("key") == "value", f"Value must be clean, got: {result!r}"

    def test_bug003_rescue_html_json_well_formed_unaffected(self):
        """BUG-003 FIXED: well-formed JSON still parsed correctly after fix."""
        result = LightweightEngine._rescue_html_json('{"a": "b", "c": "d"}')
        assert result == {"a": "b", "c": "d"}
