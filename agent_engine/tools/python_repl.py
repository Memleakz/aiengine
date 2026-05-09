import asyncio
import contextlib
import os
import sys
import tempfile
from agent_engine.env_utils import get_clean_env


async def python_repl(code: str) -> str:
    """Execute Python code in a subprocess and return its stdout and stderr."""
    fd, path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(code)

        # If we are in a venv, sys.executable points to the venv's python.
        # We want to use the system python or whatever is in the clean PATH.
        executable = sys.executable
        if os.environ.get("VIRTUAL_ENV"):
            executable = "python3"

        proc = await asyncio.create_subprocess_exec(
            executable, path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=get_clean_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = (stdout + stderr).decode(errors="replace")

        if not output.strip():
            return "Code executed successfully with no output."

        if len(output) > 4000:
            return output[:4000] + "\n... [output truncated]"
        return output
    except TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return "Error: Python code execution timed out (30s)."
    except Exception as e:
        return f"Error executing Python code: {e}"
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)
