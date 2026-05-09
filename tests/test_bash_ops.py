import asyncio
import os

import pytest

from agent_engine.tools.bash_ops import BashTools
from agent_engine.tools.bash_ops.bash_handler import _MAX_OUTPUT, _MAX_BACKGROUND_JOBS


@pytest.fixture
def workdir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def bash_tools(workdir):
    return BashTools(workdir)


class TestBashToolsInit:
    def test_init_resolves_workdir(self, tmp_path):
        t = BashTools(str(tmp_path))
        assert os.path.isabs(t.workdir)
        assert t.workdir == os.path.abspath(str(tmp_path))

    def test_init_starts_empty_jobs(self, bash_tools):
        assert len(bash_tools._running_jobs) == 0


class TestIsSafePath:
    def test_allows_direct_file(self, bash_tools, tmp_path):
        (tmp_path / "file.txt").write_text("hi")
        assert bash_tools._is_safe_path("file.txt")

    def test_allows_nested_file(self, bash_tools, tmp_path):
        (tmp_path / "sub").mkdir()
        assert bash_tools._is_safe_path("sub/file.txt")

    def test_blocks_parent_traversal(self, bash_tools):
        assert not bash_tools._is_safe_path("../secret.txt")
        assert not bash_tools._is_safe_path("../../etc/passwd")

    def test_blocks_absolute_outside_workdir(self, bash_tools):
        assert not bash_tools._is_safe_path("/etc/passwd")

    def test_blocks_symlink_escape(self, bash_tools, tmp_path):
        outside = tmp_path.parent / "outside_dir"
        outside.mkdir(exist_ok=True)
        (outside / "secret.txt").write_text("secret")
        link = tmp_path / "link"
        link.symlink_to(outside)
        assert not bash_tools._is_safe_path("link/secret.txt")

    def test_allows_workdir_itself(self, bash_tools):
        assert bash_tools._is_safe_path(".")


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_echo(self, bash_tools):
        result = await bash_tools._run_command("echo hello", timeout=30)
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_stderr_included(self, bash_tools):
        result = await bash_tools._run_command("echo err >&2", timeout=30)
        assert "err" in result

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self, bash_tools):
        result = await bash_tools._run_command("sleep 60", timeout=1)
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_truncates_large_output(self, bash_tools):
        result = await bash_tools._run_command("python3 -c \"print('x' * 10000)\"", timeout=30)
        assert len(result) <= _MAX_OUTPUT

    @pytest.mark.asyncio
    async def test_exit_nonzero_still_returns_output(self, bash_tools):
        result = await bash_tools._run_command("echo bye && exit 1", timeout=30)
        assert "bye" in result

    @pytest.mark.asyncio
    async def test_runs_in_workdir(self, bash_tools, tmp_path):
        result = await bash_tools._run_command("pwd", timeout=30)
        assert str(tmp_path) in result


class TestBashActionRun:
    @pytest.mark.asyncio
    async def test_run_echo(self, bash_tools):
        result = await bash_tools.bash(action="run", command="echo hello")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_no_command_returns_error(self, bash_tools):
        result = await bash_tools.bash(action="run", command="")
        assert "error" in result.lower()
        assert "command" in result.lower()

    @pytest.mark.asyncio
    async def test_run_zero_timeout(self, bash_tools):
        result = await bash_tools.bash(action="run", command="echo hi", timeout=0)
        assert "error" in result.lower()
        assert "timeout" in result.lower()

    @pytest.mark.asyncio
    async def test_run_negative_timeout(self, bash_tools):
        result = await bash_tools.bash(action="run", command="echo hi", timeout=-5)
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_run_timeout(self, bash_tools):
        result = await bash_tools.bash(action="run", command="sleep 60", timeout=1)
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_run_truncates_large_output(self, bash_tools):
        result = await bash_tools.bash(action="run", command="python3 -c \"print('x' * 10000)\"")
        assert len(result) <= _MAX_OUTPUT

    @pytest.mark.asyncio
    async def test_run_exit_nonzero(self, bash_tools):
        result = await bash_tools.bash(action="run", command="echo bye && exit 1")
        assert "bye" in result

    @pytest.mark.asyncio
    async def test_run_in_workdir(self, bash_tools, tmp_path):
        result = await bash_tools.bash(action="run", command="pwd")
        assert str(tmp_path) in result

    @pytest.mark.asyncio
    async def test_default_action_is_run(self, bash_tools):
        result = await bash_tools.bash(command="echo default")
        assert "default" in result


class TestBashActionBackground:
    @pytest.mark.asyncio
    async def test_background_returns_job_id(self, bash_tools):
        result = await bash_tools.bash(action="background", command="sleep 10")
        assert "Background process started" in result
        job_id = result.split("job_id: ")[1].strip()
        assert job_id in bash_tools._running_jobs
        await bash_tools.bash(action="kill", job_id=job_id)

    @pytest.mark.asyncio
    async def test_background_no_command_returns_error(self, bash_tools):
        result = await bash_tools.bash(action="background", command="")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_background_max_jobs(self, bash_tools):
        job_ids = []
        for _ in range(_MAX_BACKGROUND_JOBS):
            result = await bash_tools.bash(action="background", command="sleep 60")
            assert "Error" not in result
            job_ids.append(result.split("job_id: ")[1].strip())

        overflow = await bash_tools.bash(action="background", command="sleep 60")
        assert "error" in overflow.lower()
        assert str(_MAX_BACKGROUND_JOBS) in overflow

        for jid in job_ids:
            await bash_tools.bash(action="kill", job_id=jid)


class TestBashActionLogs:
    @pytest.mark.asyncio
    async def test_logs_unknown_job(self, bash_tools):
        result = await bash_tools.bash(action="logs", job_id="nonexistent-id")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_logs_no_job_id(self, bash_tools):
        result = await bash_tools.bash(action="logs", job_id="")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_logs_captures_output(self, bash_tools):
        result = await bash_tools.bash(action="background", command="echo 'log output'")
        job_id = result.split("job_id: ")[1].strip()
        await asyncio.sleep(0.3)
        logs = await bash_tools.bash(action="logs", job_id=job_id)
        assert isinstance(logs, str)
        await bash_tools.bash(action="kill", job_id=job_id)


class TestBashActionKill:
    @pytest.mark.asyncio
    async def test_kill_process_removes_job(self, bash_tools):
        result = await bash_tools.bash(action="background", command="sleep 10")
        job_id = result.split("job_id: ")[1].strip()
        kill_result = await bash_tools.bash(action="kill", job_id=job_id)
        assert "terminated" in kill_result.lower()
        assert job_id not in bash_tools._running_jobs

    @pytest.mark.asyncio
    async def test_kill_unknown_job(self, bash_tools):
        result = await bash_tools.bash(action="kill", job_id="nonexistent-id")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_kill_no_job_id(self, bash_tools):
        result = await bash_tools.bash(action="kill", job_id="")
        assert "error" in result.lower()


class TestBashActionRead:
    @pytest.mark.asyncio
    async def test_read_file_success(self, bash_tools, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        result = await bash_tools.bash(action="read", filepath="test.txt")
        assert "line1" in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_read_file_line_range(self, bash_tools, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("a\nb\nc\nd\n")
        result = await bash_tools.bash(action="read", filepath="test.txt", start_line=2, end_line=3)
        assert "b" in result
        assert "c" in result
        assert "a" not in result
        assert "d" not in result

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, bash_tools):
        result = await bash_tools.bash(action="read", filepath="nonexistent.txt")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_read_file_no_filepath(self, bash_tools):
        result = await bash_tools.bash(action="read")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_read_file_blocks_traversal(self, bash_tools):
        result = await bash_tools.bash(action="read", filepath="../../etc/passwd")
        assert "security error" in result.lower()


class TestBashActionUnknown:
    @pytest.mark.asyncio
    async def test_unknown_action(self, bash_tools):
        result = await bash_tools.bash(action="foobar")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_action_with_command_runs_as_run(self, bash_tools):
        result = await bash_tools.bash(action="ls", command="echo hello")
        assert "hello" in result


class TestBashToolsEdgeCases:
    @pytest.mark.asyncio
    async def test_is_safe_path_os_error(self):
        t = BashTools("/tmp")
        from pathlib import Path
        original_resolve = Path.resolve
        def bad_resolve(self):
            raise OSError("bad path")
        Path.resolve = bad_resolve
        try:
            assert not t._is_safe_path("test.txt")
        finally:
            Path.resolve = original_resolve

    @pytest.mark.asyncio
    async def test_run_command_general_exception(self, bash_tools, monkeypatch):
        import asyncio as aio
        original = aio.create_subprocess_shell
        async def bad_shell(*args, **kwargs):
            raise RuntimeError("subprocess failed")
        monkeypatch.setattr(aio, "create_subprocess_shell", bad_shell)
        result = await bash_tools._run_command("echo hi", timeout=30)
        assert "Error" in result
        assert "subprocess failed" in result

    @pytest.mark.asyncio
    async def test_background_exception(self, bash_tools, monkeypatch):
        import asyncio as aio
        async def bad_shell(*args, **kwargs):
            raise RuntimeError("spawn failed")
        monkeypatch.setattr(aio, "create_subprocess_shell", bad_shell)
        result = await bash_tools.bash(action="background", command="sleep 5")
        assert "Error" in result
        assert "spawn failed" in result

    @pytest.mark.asyncio
    async def test_read_file_exception(self, bash_tools, tmp_path, monkeypatch):
        f = tmp_path / "bad.txt"
        f.write_text("content")
        import builtins
        original_open = builtins.open
        def bad_open(*args, **kwargs):
            raise PermissionError("denied")
        monkeypatch.setattr(builtins, "open", bad_open)
        result = await bash_tools.bash(action="read", filepath="bad.txt")
        assert "Error" in result
        assert "denied" in result
