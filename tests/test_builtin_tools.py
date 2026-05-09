import asyncio
import os

import pytest

from agent_engine.builtin_tools import BuiltinTools

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tools(tmp_path):
    return BuiltinTools(workdir=str(tmp_path))


# ---------------------------------------------------------------------------
# __init__ / _is_safe_path
# ---------------------------------------------------------------------------

def test_init_resolves_workdir_to_abspath(tmp_path):
    t = BuiltinTools(workdir=str(tmp_path))
    assert os.path.isabs(t.workdir)
    assert t.workdir == os.path.abspath(str(tmp_path))


def test_is_safe_path_allows_direct_file(tools, tmp_path):
    (tmp_path / "file.txt").write_text("hi")
    assert tools._is_safe_path("file.txt")


def test_is_safe_path_allows_nested_file(tools, tmp_path):
    (tmp_path / "sub").mkdir()
    assert tools._is_safe_path("sub/file.txt")


def test_is_safe_path_blocks_parent_traversal(tools):
    assert not tools._is_safe_path("../secret.txt")
    assert not tools._is_safe_path("../../etc/passwd")


def test_is_safe_path_blocks_absolute_outside_workdir(tools):
    assert not tools._is_safe_path("/etc/passwd")


def test_is_safe_path_blocks_symlink_escape(tools, tmp_path):
    outside = tmp_path.parent / "outside_dir"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("secret")
    link = tmp_path / "link"
    link.symlink_to(outside)
    assert not tools._is_safe_path("link/secret.txt")


def test_is_safe_path_allows_workdir_itself(tools):
    assert tools._is_safe_path(".")


# ---------------------------------------------------------------------------
# bash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bash_echo(tools):
    result = await tools.bash(action="run", command="echo hello")
    assert "hello" in result


@pytest.mark.asyncio
async def test_bash_stderr_included(tools):
    result = await tools.bash(action="run", command="echo err >&2")
    assert "err" in result


@pytest.mark.asyncio
async def test_bash_timeout_kills_process(tools):
    result = await tools.bash(action="run", command="sleep 60", timeout=1)
    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_bash_truncates_large_output(tools):
    result = await tools.bash(action="run", command="python3 -c \"print('x' * 10000)\"")
    assert len(result) <= 4000


@pytest.mark.asyncio
async def test_bash_exit_nonzero_still_returns_output(tools):
    result = await tools.bash(action="run", command="echo bye && exit 1")
    assert "bye" in result


@pytest.mark.asyncio
async def test_bash_runs_in_workdir(tmp_path):
    """bash cwd must be the configured workdir."""
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.bash(action="run", command="pwd")
    assert str(tmp_path) in result


# ---------------------------------------------------------------------------
# bash action=background / action=logs / action=kill
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bash_background_returns_job_id(tools):
    result = await tools.bash(action="background", command="sleep 10")
    assert "Background process started" in result
    job_id = result.split("job_id: ")[1].strip()
    await tools.bash(action="kill", job_id=job_id)


@pytest.mark.asyncio
async def test_bash_background_job_tracked_in_instance(tools):
    result = await tools.bash(action="background", command="sleep 10")
    job_id = result.split("job_id: ")[1].strip()
    assert job_id in tools._running_jobs
    await tools.bash(action="kill", job_id=job_id)


@pytest.mark.asyncio
async def test_two_instances_do_not_share_jobs(tmp_path):
    """Jobs started on one instance must not be visible to another instance."""
    t1 = BuiltinTools(workdir=str(tmp_path))
    t2 = BuiltinTools(workdir=str(tmp_path))
    result = await t1.bash(action="background", command="sleep 10")
    job_id = result.split("job_id: ")[1].strip()
    assert job_id in t1._running_jobs
    assert job_id not in t2._running_jobs
    await t1.bash(action="kill", job_id=job_id)


@pytest.mark.asyncio
async def test_kill_process_removes_job(tools):
    result = await tools.bash(action="background", command="sleep 10")
    job_id = result.split("job_id: ")[1].strip()
    kill_result = await tools.bash(action="kill", job_id=job_id)
    assert job_id in kill_result or "terminated" in kill_result.lower()
    assert job_id not in tools._running_jobs


@pytest.mark.asyncio
async def test_kill_process_unknown_job(tools):
    result = await tools.bash(action="kill", job_id="nonexistent-id")
    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_read_logs_unknown_job(tools):
    result = await tools.bash(action="logs", job_id="nonexistent-id")
    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_read_logs_captures_output(tools):
    result = await tools.bash(action="background", command="echo 'log output'")
    job_id = result.split("job_id: ")[1].strip()
    await asyncio.sleep(0.3)
    logs = await tools.bash(action="logs", job_id=job_id)
    assert isinstance(logs, str)
    await tools.bash(action="kill", job_id=job_id)


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_full(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\n")
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("test.txt")
    assert "line1" in result
    assert "line3" in result


@pytest.mark.asyncio
async def test_read_file_line_range(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("a\nb\nc\nd\n")
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("test.txt", start_line=2, end_line=3)
    assert "b" in result
    assert "c" in result
    assert "a" not in result
    assert "d" not in result


@pytest.mark.asyncio
async def test_read_file_missing(tmp_path):
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("nonexistent.txt")
    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_read_file_blocks_traversal(tmp_path):
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("../../etc/passwd")
    assert "security error" in result.lower()


@pytest.mark.asyncio
async def test_read_file_blocks_absolute_outside_workdir(tmp_path):
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("/etc/passwd")
    assert "security error" in result.lower()


# ---------------------------------------------------------------------------
# bash unified action API
# ---------------------------------------------------------------------------

def test_bash_actions_are_callable():
    """The unified bash method must exist and be callable."""
    t = BuiltinTools(workdir=".")
    assert callable(t.bash)


# ---------------------------------------------------------------------------
# Security constraint: bash timeout validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bash_rejects_zero_timeout(tools):
    result = await tools.bash(action="run", command="echo hi", timeout=0)
    assert "error" in result.lower()
    assert "timeout" in result.lower()


@pytest.mark.asyncio
async def test_bash_rejects_negative_timeout(tools):
    result = await tools.bash(action="run", command="echo hi", timeout=-5)
    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# Security constraint: bash_background max concurrent jobs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bash_background_rejects_when_at_max_jobs(tmp_path):
    """bash_background must refuse new jobs when _MAX_BACKGROUND_JOBS are running."""
    from agent_engine.builtin_tools import _MAX_BACKGROUND_JOBS
    t = BuiltinTools(workdir=str(tmp_path))
    job_ids = []
    for _ in range(_MAX_BACKGROUND_JOBS):
        result = await t.bash(action="background", command="sleep 60")
        assert "Error" not in result
        job_ids.append(result.split("job_id: ")[1].strip())

    # One more must be refused
    overflow = await t.bash(action="background", command="sleep 60")
    assert "error" in overflow.lower()
    assert str(_MAX_BACKGROUND_JOBS) in overflow

    for jid in job_ids:
        await t.bash(action="kill", job_id=jid)


# ---------------------------------------------------------------------------
# Security constraint: read_file max file size
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_rejects_oversized_file(tmp_path):
    """read_file must refuse files larger than _MAX_FILE_BYTES."""
    from agent_engine.builtin_tools import _MAX_FILE_BYTES
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (_MAX_FILE_BYTES + 1))
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("big.bin")
    assert "error" in result.lower()
    assert "large" in result.lower() or "limit" in result.lower()


@pytest.mark.asyncio
async def test_read_file_accepts_file_at_max_size_boundary(tmp_path):
    """A file of exactly _MAX_FILE_BYTES should succeed."""
    from agent_engine.builtin_tools import _MAX_FILE_BYTES
    exact = tmp_path / "exact.bin"
    exact.write_bytes(b"a" * _MAX_FILE_BYTES)
    t = BuiltinTools(workdir=str(tmp_path))
    result = await t.read_file("exact.bin")
    assert "error" not in result.lower()
