import os
import pytest

from agent_engine.tools import file_ops, search_ops

# ---------------------------------------------------------------------------
# _is_safe_path
# ---------------------------------------------------------------------------

def test_is_safe_path_allows_direct_file(tmp_path):
    (tmp_path / "file.txt").write_text("hi")
    assert file_ops._is_safe_path(str(tmp_path), "file.txt")

def test_is_safe_path_allows_nested_file(tmp_path):
    (tmp_path / "sub").mkdir()
    assert file_ops._is_safe_path(str(tmp_path), "sub/file.txt")

def test_is_safe_path_blocks_parent_traversal(tmp_path):
    assert not file_ops._is_safe_path(str(tmp_path), "../secret.txt")
    assert not file_ops._is_safe_path(str(tmp_path), "../../etc/passwd")

def test_is_safe_path_blocks_absolute_outside_workdir(tmp_path):
    assert not file_ops._is_safe_path(str(tmp_path), "/etc/passwd")

def test_is_safe_path_blocks_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside_dir"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("secret")
    link = tmp_path / "link"
    link.symlink_to(outside)
    assert not file_ops._is_safe_path(str(tmp_path), "link/secret.txt")

def test_is_safe_path_allows_workdir_itself(tmp_path):
    assert file_ops._is_safe_path(str(tmp_path), ".")

# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_file_full(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\n")
    result = await file_ops.read_file(str(tmp_path), "test.txt")
    assert "line1" in result
    assert "line3" in result

@pytest.mark.asyncio
async def test_read_file_line_range(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("a\nb\nc\nd\n")
    result = await file_ops.read_file(str(tmp_path), "test.txt", start_line=2, end_line=3)
    assert "b" in result
    assert "c" in result
    assert "a" not in result
    assert "d" not in result

@pytest.mark.asyncio
async def test_read_file_missing(tmp_path):
    result = await file_ops.read_file(str(tmp_path), "nonexistent.txt")
    assert "error" in result.lower()

@pytest.mark.asyncio
async def test_read_file_blocks_traversal(tmp_path):
    result = await file_ops.read_file(str(tmp_path), "../../etc/passwd")
    assert "security error" in result.lower()

@pytest.mark.asyncio
async def test_read_file_blocks_absolute_outside_workdir(tmp_path):
    result = await file_ops.read_file(str(tmp_path), "/etc/passwd")
    assert "security error" in result.lower()

@pytest.mark.asyncio
async def test_read_file_rejects_oversized_file(tmp_path):
    """read_file must refuse files larger than _MAX_FILE_BYTES."""
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (file_ops._MAX_FILE_BYTES + 1))
    result = await file_ops.read_file(str(tmp_path), "big.bin")
    assert "error" in result.lower()
    assert "large" in result.lower() or "limit" in result.lower()

@pytest.mark.asyncio
async def test_read_file_accepts_file_at_max_size_boundary(tmp_path):
    """A file of exactly _MAX_FILE_BYTES should succeed."""
    exact = tmp_path / "exact.bin"
    exact.write_bytes(b"a" * file_ops._MAX_FILE_BYTES)
    result = await file_ops.read_file(str(tmp_path), "exact.bin")
    assert "error" not in result.lower()
