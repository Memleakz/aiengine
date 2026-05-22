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

# ---------------------------------------------------------------------------
# patch_code_range
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_code_range_success(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello, World!")
    result = await file_ops.patch_code_range(str(tmp_path), "test.txt", start_byte=7, end_byte=12, replacement="Tobias")
    assert "successfully patched" in result.lower()
    assert f.read_text() == "Hello, Tobias!"

@pytest.mark.asyncio
async def test_patch_code_range_verification_success(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello, World!")
    result = await file_ops.patch_code_range(str(tmp_path), "test.txt", start_byte=7, end_byte=12, replacement="Tobias", original_text="World")
    assert "successfully patched" in result.lower()
    assert f.read_text() == "Hello, Tobias!"

@pytest.mark.asyncio
async def test_patch_code_range_verification_failure(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello, World!")
    result = await file_ops.patch_code_range(str(tmp_path), "test.txt", start_byte=7, end_byte=12, replacement="Tobias", original_text="Earth")
    assert "range verification failed" in result.lower()
    assert "expected 'Earth'" in result
    assert "is 'World'" in result
    assert f.read_text() == "Hello, World!"

@pytest.mark.asyncio
async def test_patch_code_range_batch_patches(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello, World! This is a test.")
    patches = [
        {"start_byte": 7, "end_byte": 12, "replacement": "Universe", "original_text": "World"},
        {"start_byte": 24, "end_byte": 28, "replacement": "demo", "original_text": "test"}
    ]
    result = await file_ops.patch_code_range(str(tmp_path), "test.txt", patches=patches)
    assert "successfully applied 2 patches" in result.lower()
    assert f.read_text() == "Hello, Universe! This is a demo."


@pytest.mark.asyncio
async def test_patch_code_range_whitespace_newline_tolerance(tmp_path):
    # Test with CRLF endings in file but LF endings in expected original_text
    f = tmp_path / "test_crlf.txt"
    f.write_bytes(b"Line One\r\nLine Two\r\nLine Three")
    
    # Original text matches but with LF instead of CRLF, and slightly different spaces
    result = await file_ops.patch_code_range(
        str(tmp_path), 
        "test_crlf.txt", 
        start_byte=9, 
        end_byte=17, 
        replacement="Replaced Two", 
        original_text="Line\nTwo"
    )
    assert "successfully" in result.lower()
    assert f.read_bytes() == b"Line One\r\nReplaced Two\r\nLine Three"


@pytest.mark.asyncio
async def test_patch_code_range_idempotency_graceful(tmp_path):
    f = tmp_path / "test_idem.txt"
    f.write_text("The fast brown fox jumps over the lazy dog.")
    
    # First apply the patch
    res1 = await file_ops.patch_code_range(
        str(tmp_path),
        "test_idem.txt",
        start_byte=4,
        end_byte=8,
        replacement="slow",
        original_text="fast"
    )
    assert "successfully" in res1.lower()
    assert f.read_text() == "The slow brown fox jumps over the lazy dog."
    
    # Re-apply the patch at the same coordinates (but the file now has "slow")
    res2 = await file_ops.patch_code_range(
        str(tmp_path),
        "test_idem.txt",
        start_byte=4,
        end_byte=8,
        replacement="slow",
        original_text="fast"
    )
    assert "already applied" in res2.lower()
    assert f.read_text() == "The slow brown fox jumps over the lazy dog."



