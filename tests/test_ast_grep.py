import os
import pytest
from unittest.mock import patch, MagicMock
from agent_engine.tools.ast_grep import ast_grep_run

@pytest.mark.asyncio
async def test_ast_grep_run_not_installed():
    # Force shutil.which to return None and os.path.exists to return False to simulate no installation
    with patch("shutil.which", return_value=None), patch("os.path.exists", return_value=False):
        res = await ast_grep_run(workdir=".", action="search", pattern="foo()")
        assert res["success"] is False
        assert "ast-grep is not installed" in res["error"]
        assert "npm install" in res["error"]
        assert "pip install" in res["error"]

@pytest.mark.asyncio
async def test_ast_grep_run_invalid_action():
    with patch("shutil.which", return_value="/usr/local/bin/ast-grep"):
        res = await ast_grep_run(workdir=".", action="invalid_action", pattern="foo()")
        assert res["success"] is False
        assert "invalid_action" in res["error"]

@pytest.mark.asyncio
async def test_ast_grep_run_rewrite_missing_replacement():
    with patch("shutil.which", return_value="/usr/local/bin/ast-grep"):
        res = await ast_grep_run(workdir=".", action="rewrite", pattern="foo()")
        assert res["success"] is False
        assert "Argument 'rewrite' pattern is required" in res["error"]

@pytest.mark.asyncio
async def test_ast_grep_run_mock_subprocess_search():
    # Mocking subprocess behavior
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = MagicMock()
    
    # communicate is an async method
    async def mock_communicate():
        return b'[{"text": "match"}]', b""
    mock_proc.communicate.side_effect = mock_communicate

    with patch("shutil.which", return_value="/usr/local/bin/ast-grep"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
         
        res = await ast_grep_run(
            workdir=".",
            action="search",
            pattern="foo($A)",
            filepath_glob="*.py"
        )
        
        assert res["success"] is True
        assert res["count"] == 1
        assert res["results"][0]["text"] == "match"
        
        # Verify ast-grep arguments
        called_args = mock_exec.call_args[0]
        assert called_args[0] == "/usr/local/bin/ast-grep"
        assert "run" in called_args
        assert "--pattern" in called_args
        assert "foo($A)" in called_args
        assert "--json" in called_args
        assert "--globs" in called_args
        assert "*.py" in called_args
