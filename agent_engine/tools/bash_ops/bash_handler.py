import os
import asyncio
import uuid
import glob as glob_mod
from pathlib import Path

_MAX_OUTPUT = 4000
_MAX_BACKGROUND_JOBS = 20
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB guard: prevent OOM via large-file reads


class BashTools:
    def __init__(self, workdir: str) -> None:
        self.workdir = os.path.abspath(workdir)
        self._running_jobs: dict[str, asyncio.subprocess.Process] = {}

    def _is_safe_path(self, filepath: str) -> bool:
        """Block directory traversal and symlink-escape attacks."""
        try:
            workdir = Path(self.workdir).resolve()
            target = Path(os.path.join(self.workdir, filepath)).resolve()
            return workdir == target or target.is_relative_to(workdir)
        except (ValueError, OSError):
            return False

    # ── bash actions ─────────────────────────────────────────────

    async def bash(self, **kwargs) -> str:
        """Execute and manage shell commands.

        Actions:
          - 'run' (default): Execute a command synchronously and return output.
            Required: command
          - 'background': Start a command in the background without waiting.
            Required: command.  Returns a job_id to use with 'logs'/'kill'.
          - 'logs': Read buffered stdout/stderr from a background job.
            Required: job_id.  Optional: tail_lines (last N lines, default 100).
          - 'kill': Terminate a background job and free its resources.
            Required: job_id.
          - 'read': Read a file's contents (alias for read_file).
            Required: filepath.  Optional: start_line, end_line.

        Note: 'run' is assumed when only 'command' is supplied with no 'action'.
        Note: Output for 'run' action is truncated to the last 4000 characters.
        """
        command = kwargs.get("command", "")
        action = kwargs.get("action", "run")
        job_id = kwargs.get("job_id", "")
        timeout = int(kwargs.get("timeout", 60))
        tail_lines = int(kwargs.get("tail_lines", 100))

        known_actions = {"run", "background", "logs", "kill", "read"}
        if action not in known_actions and command.strip():
            action = "run"

        if action == "run" and not command.strip():
            return (
                "Error: `bash` with action='run' requires a `command` argument. "
                "If you are writing file content, use `file_write(filepath, content)` instead."
            )

        if action == "run":
            if timeout <= 0:
                return "Error: timeout must be a positive integer."
            return await self._run_command(command, timeout)

        elif action == "background":
            if not command.strip():
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
                )
                new_id = str(uuid.uuid4())
                self._running_jobs[new_id] = proc
                return f"Background process started. job_id: {new_id}"
            except Exception as exc:
                return f"Error: {exc}"

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

        elif action == "read":
            filepath = kwargs.get("filepath") or kwargs.get("args", {}).get("filepath")
            if not filepath:
                return "Error: 'read' action requires a 'filepath' argument."

            start_line = kwargs.get("start_line")
            if start_line is None:
                start_line = kwargs.get("args", {}).get("start_line", 1)

            end_line = kwargs.get("end_line")
            if end_line is None:
                end_line = kwargs.get("args", {}).get("end_line", -1)

            if not self._is_safe_path(filepath):
                return f"Security Error: Access to '{filepath}' is denied."
            target = str(Path(os.path.join(self.workdir, filepath)).resolve())
            try:
                if not os.path.exists(target):
                    return f"Error: File '{filepath}' not found."
                with open(target, encoding="utf-8", errors="replace") as f:
                    lines_content = f.readlines()
                start = max(0, start_line - 1)
                end = len(lines_content) if end_line == -1 else end_line
                return "".join(lines_content[start:end])
            except Exception as exc:
                return f"Error: {exc}"

        else:
            return f"Error: unknown bash action '{action}'. Choose from: run, background, logs, kill, read."

    async def _run_command(self, command: str, timeout: int) -> str:
        """Run a shell command synchronously with timeout."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
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

    # ── file read ────────────────────────────────────────────────

    async def read(self, filepath: str, start_line: int = 1, end_line: int = -1) -> str:
        """Read file contents, optionally slicing to a line range (1-indexed, end_line=-1 means EOF)."""
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied."
        target = str(Path(os.path.join(self.workdir, filepath)).resolve())
        try:
            if not os.path.exists(target):
                return f"Error: File '{filepath}' not found."
            file_size = os.path.getsize(target)
            if file_size > _MAX_FILE_BYTES:
                return f"Error: File '{filepath}' is too large ({file_size} bytes, max {_MAX_FILE_BYTES})."
            with open(target, encoding="utf-8", errors="replace") as f:
                lines_content = f.readlines()
            start = max(0, start_line - 1)
            end = len(lines_content) if end_line == -1 else end_line
            return "".join(lines_content[start:end])
        except Exception as exc:
            return f"Error: {exc}"

    # ── file write ───────────────────────────────────────────────

    async def file_write(self, filepath: str, content: str = "", base64_content: str = "") -> str:
        """Create or overwrite a file with text content or base64 data."""
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied."
        if not content and not base64_content:
            return "Error: either 'content' or 'base64_content' must be provided."
        try:
            import base64
            if base64_content:
                data = base64.b64decode(base64_content)
                write_data = data.decode("utf-8")
            else:
                write_data = content
            target = str(Path(os.path.join(self.workdir, filepath)).resolve())
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(write_data)
            return f"File written successfully: {filepath}"
        except Exception as exc:
            return f"Error writing file: {exc}"

    # ── file edit ────────────────────────────────────────────────

    async def file_edit(self, filepath: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """Edit a file by replacing old_string with new_string."""
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied."
        if not old_string:
            return "Error: 'old_string' must not be empty."
        try:
            target = str(Path(os.path.join(self.workdir, filepath)).resolve())
            if not os.path.exists(target):
                return f"Error: File '{filepath}' not found."
            with open(target, encoding="utf-8", errors="replace") as f:
                content = f.read()
            if not replace_all:
                new_content = content.replace(old_string, new_string, 1)
            else:
                new_content = content.replace(old_string, new_string)
            if new_content == content:
                return f"Error: 'old_string' not found in '{filepath}'."
            with open(target, "w", encoding="utf-8") as f:
                f.write(new_content)
            return f"File edited successfully: {filepath}"
        except Exception as exc:
            return f"Error editing file: {exc}"

    # ── file delete ──────────────────────────────────────────────

    async def file_delete(self, filepath: str) -> str:
        """Delete a file within the working directory."""
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied."
        try:
            target = str(Path(os.path.join(self.workdir, filepath)).resolve())
            if not os.path.exists(target):
                return f"Error: File '{filepath}' not found."
            if os.path.isdir(target):
                return f"Error: '{filepath}' is a directory. Use directory_create with recursive action for directories."
            os.remove(target)
            return f"File deleted successfully: {filepath}"
        except Exception as exc:
            return f"Error deleting file: {exc}"

    # ── directory create ─────────────────────────────────────────

    async def directory_create(self, path: str) -> str:
        """Create a directory (and any necessary parents) within the working directory."""
        if not self._is_safe_path(path):
            return f"Security Error: Access to '{path}' is denied."
        try:
            target = str(Path(os.path.join(self.workdir, path)).resolve())
            os.makedirs(target, exist_ok=True)
            return f"Directory created successfully: {path}"
        except Exception as exc:
            return f"Error creating directory: {exc}"

    # ── glob search ──────────────────────────────────────────────

    async def glob_search(self, pattern: str, path: str = ".") -> str:
        """Search for files matching a glob pattern."""
        if not self._is_safe_path(path):
            return f"Security Error: Access to '{path}' is denied."
        target_dir = str(Path(os.path.join(self.workdir, path)).resolve())
        try:
            matches = glob_mod.glob(os.path.join(target_dir, pattern), recursive=True)
            rel_matches = [os.path.relpath(m, self.workdir) for m in matches]
            if not rel_matches:
                return "No files found matching pattern."
            return "\n".join(rel_matches)
        except Exception as exc:
            return f"Error: {exc}"

    # ── grep search ──────────────────────────────────────────────

    async def grep_search(self, query: str, path: str = ".", include: str = "") -> str:
        """Search for a string in files within a directory."""
        if not self._is_safe_path(path):
            return f"Security Error: Access to '{path}' is denied."
        target_dir = str(Path(os.path.join(self.workdir, path)).resolve())
        try:
            cmd = ["grep", "-rn"]
            if include:
                cmd.extend(["--include", include])
            cmd.extend([query, target_dir])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode(errors="replace")
            if not output:
                return "No matches found."
            return output[:_MAX_OUTPUT] + ("\n... [output truncated]" if len(output) > _MAX_OUTPUT else "")
        except TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return "Error: grep search timed out"
        except Exception as exc:
            return f"Error: {exc}"
