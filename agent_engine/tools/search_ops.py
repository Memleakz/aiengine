import os
import asyncio
from pathlib import Path
from agent_engine.env_utils import get_clean_env
from agent_engine.tools.file_ops import _is_safe_path

async def glob_search(workdir: str, pattern: str, path: str = ".") -> str:
    """Search for files matching a glob pattern."""
    import glob
    if not _is_safe_path(workdir, path):
        return f"Security Error: Access to '{path}' is denied."
    target_dir = str(Path(os.path.join(workdir, path)).resolve())
    try:
        matches = glob.glob(os.path.join(target_dir, pattern), recursive=True)
        rel_matches = [os.path.relpath(m, workdir) for m in matches]
        if not rel_matches:
            return "No files found matching pattern."
        return "\n".join(rel_matches)
    except Exception as exc:
        return f"Error: {exc}"

async def grep_search(workdir: str, query: str, path: str = ".", include: str = "") -> str:
    """Search for a string in files within a directory."""
    if not _is_safe_path(workdir, path):
        return f"Security Error: Access to '{path}' is denied."
    target_dir = str(Path(os.path.join(workdir, path)).resolve())
    try:
        cmd = ["grep", "-rn"]
        if include:
            cmd.extend(["--include", include])
        cmd.extend([query, target_dir])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env=get_clean_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode(errors="replace")
        if not output:
            return "No matches found."
        return output[:4000] + ("\n... [output truncated]" if len(output) > 4000 else "")
    except TimeoutError:
        import contextlib
        with contextlib.suppress(Exception):
            proc.kill()
        return "Error: grep search timed out"
    except Exception as exc:
        return f"Error: {exc}"
