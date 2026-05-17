import os
import asyncio
import uuid
from agent_engine.env_utils import get_clean_env
from agent_engine.tools.file_ops import read_file

_MAX_OUTPUT = 128000
_MAX_BACKGROUND_JOBS = 20

class BashTool:
    def __init__(self, workdir: str) -> None:
        self.workdir = os.path.abspath(workdir)
        self._running_jobs: dict[str, asyncio.subprocess.Process] = {}

    async def _run_command(self, command: str, timeout: int) -> str:
        """Internal helper: run a shell command synchronously and return output."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
                env=get_clean_env(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = (stdout + stderr).decode(errors="replace")
            return output[-_MAX_OUTPUT:] if len(output) > _MAX_OUTPUT else output
        except TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return f"Error: command timed out after {timeout}s"
        except Exception as exc:
            return f"Error: {exc}"

    async def bash(self, command: str = "", action: str = "run", job_id: str = "", timeout: int = 60, tail_lines: int = 100, filepath: str = "", start_line: int = 1, end_line: int = -1) -> str:
        """Execute shell commands or read files.
        
        Args:
            command: The shell command to run (e.g., 'ls -l', 'grep ...'). Required for 'run' and 'background'.
            action: 'run' (default), 'background' (long-running), 'logs' (get background output), 'kill' (stop job), or 'read' (alias for read_file).
            job_id: The ID of a background job (for 'logs' and 'kill').
            timeout: Max seconds for 'run' (default 60).
            tail_lines: Lines of logs to return (default 100).
            filepath: Path to a file to read (for 'read' action).
            start_line: First line to read (for 'read', 1-indexed).
            end_line: Last line to read (for 'read', -1 for EOF).
        """
        kwargs = {
            "command": command.strip() if isinstance(command, str) else "",
            "action": action.strip().lower() if isinstance(action, str) else "run",
            "job_id": job_id.strip() if isinstance(job_id, str) else "",
            "timeout": int(timeout) if timeout is not None and str(timeout).strip() != "" else 60,
            "tail_lines": int(tail_lines) if tail_lines is not None and str(tail_lines).strip() != "" else 100,
            "filepath": filepath.strip() if isinstance(filepath, str) else "",
            "start_line": int(start_line) if start_line else 1,
            "end_line": int(end_line) if end_line else -1,
        }
        command = kwargs["command"]
        action = kwargs["action"]
        job_id = kwargs["job_id"]
        timeout = kwargs["timeout"]
        tail_lines = kwargs["tail_lines"]
        filepath = kwargs["filepath"]

        # Normalize unknown actions that look like shell commands (e.g. model sends action='ls')
        known_actions = {"run", "background", "logs", "kill", "read"}
        if action not in known_actions and command:
            action = "run"

        # ── run ──────────────────────────────────────────────────────────────
        if action == "run":
            if not command:
                return "Error: 'run' action requires a 'command' argument."
            if timeout <= 0:
                return "Error: timeout must be a positive integer."
            return await self._run_command(command, timeout)

        # ── background ───────────────────────────────────────────────────────
        elif action == "background":
            if not command:
                return "Error: 'background' requires a 'command' argument."
            if len(self._running_jobs) >= _MAX_BACKGROUND_JOBS:
                return (
                    f"Error: maximum concurrent background jobs ({_MAX_BACKGROUND_JOBS}) reached. "
                    "Kill an existing job before starting a new one."
                )
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.workdir,
                    env=get_clean_env(),
                )
                new_id = str(uuid.uuid4())
                self._running_jobs[new_id] = proc
                return f"Background process started. job_id: {new_id}"
            except Exception as exc:
                return f"Error: {exc}"

        # ── logs ─────────────────────────────────────────────────────────────
        elif action == "logs":
            if not job_id:
                return "Error: 'logs' requires a 'job_id' argument."
            proc = self._running_jobs.get(job_id)
            if proc is None:
                return f"Error: no job found with id '{job_id}'"
            output_parts: list[bytes] = []
            for stream in (proc.stdout, proc.stderr):
                if stream is None:
                    continue
                try:
                    chunk = await asyncio.wait_for(stream.read(65536), timeout=0.1)
                    output_parts.append(chunk)
                except TimeoutError:
                    pass
                except Exception as exc:
                    output_parts.append(f"[stream error: {exc}]".encode())
            raw = b"".join(output_parts).decode(errors="replace")
            if not raw:
                return "(no output yet)"
            lines = raw.splitlines()
            return "\n".join(lines[-tail_lines:])

        # ── kill ─────────────────────────────────────────────────────────────
        elif action == "kill":
            if not job_id:
                return "Error: 'kill' requires a 'job_id' argument."
            proc = self._running_jobs.pop(job_id, None)
            if proc is None:
                return f"Error: no job found with id '{job_id}'"
            try:
                proc.kill()
                await proc.wait()
                return f"Job '{job_id}' terminated."
            except Exception as exc:
                return f"Error terminating job: {exc}"

        # ── read ─────────────────────────────────────────────────────────────
        elif action == "read":
            target_path = filepath or command
            if not target_path:
                return "Error: 'read' action requires a 'filepath' or 'command' argument."
            
            # Heuristic: if action is 'read' but the input looks like a shell command (has spaces),
            # just execute it as a command instead of failing.
            if " " in target_path:
                return await self._run_command(target_path, timeout)
                
            return await read_file(
                self.workdir,
                target_path,
                start_line=kwargs["start_line"],
                end_line=kwargs["end_line"]
            )

        else:
            return f"Error: unknown bash action '{action}'. Choose from: run, background, logs, kill, read."
