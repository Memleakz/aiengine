import asyncio
import os
import uuid
from pathlib import Path
from agent_engine.env_utils import get_clean_env

_MAX_OUTPUT = 128000
_MAX_BACKGROUND_JOBS = 20       # DoS guard: cap concurrent background processes
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB guard: prevent OOM via large-file reads


class BuiltinTools:
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
            "timeout": int(timeout) if timeout else 60,
            "tail_lines": int(tail_lines) if tail_lines else 100,
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
                
            return await self.read_file(
                target_path,
                start_line=kwargs["start_line"],
                end_line=kwargs["end_line"]
            )

        else:
            return f"Error: unknown bash action '{action}'. Choose from: run, background, logs, kill, read."

    async def read_file(self, filepath: str, start_line: int = 1, end_line: int = -1) -> str:
        """Read a file within workdir, optionally slicing to a line range (1-indexed, end_line=-1 means EOF)."""
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."
        target = str(Path(os.path.join(self.workdir, filepath)).resolve())
        try:
            file_size = os.path.getsize(target)
            if file_size > _MAX_FILE_BYTES:
                return (
                    f"Error: file '{filepath}' is too large "
                    f"({file_size:,} bytes > {_MAX_FILE_BYTES:,} byte limit)."
                )
            lines = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _read_lines_sync, target),
                timeout=10,
            )
            start = max(0, start_line - 1)
            end = len(lines) if end_line == -1 else end_line
            return "".join(lines[start:end])
        except FileNotFoundError:
            return f"Error: file not found: {filepath}"
        except Exception as exc:
            return f"Error: {exc}"

    async def file_write(self, filepath: str, content: str = "", base64_content: str = "") -> str:
        """Create or overwrite a file with text content (via 'content') or base64 data (via 'base64_content')."""
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied."
        target = str(Path(os.path.join(self.workdir, filepath)).resolve())
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if base64_content:
                import base64
                data = base64.b64decode(base64_content)
                with open(target, "wb") as f:
                    f.write(data)
                return f"Successfully wrote base64 data to {filepath}"
            else:
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully wrote text to {filepath}"
        except Exception as exc:
            return f"Error: {exc}"

    async def file_edit(self, filepath: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """Edit a file by replacing old_string with new_string. Replaces all occurrences if replace_all is True, otherwise replaces only the first occurrence."""
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied."
        target = str(Path(os.path.join(self.workdir, filepath)).resolve())
        try:
            with open(target, encoding="utf-8") as f:
                content = f.read()
            if old_string not in content:
                return f"Error: '{old_string}' not found in {filepath}."

            if replace_all:
                content = content.replace(old_string, new_string)
            else:
                content = content.replace(old_string, new_string, 1)

            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully edited {filepath}."
        except Exception as exc:
            return f"Error: {exc}"

    async def patch_code_range(self, filepath: str, start_byte: int, end_byte: int, replacement: str) -> str:
        """
        Surgically replace a byte range in a file with new content.
        
        This tool is designed to be used with byte offsets provided by AST-analysis tools 
        (like Tree-Sitter MCP). It ensures precise, structural edits.
        """
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied."
        target = str(Path(os.path.join(self.workdir, filepath)).resolve())
        try:
            with open(target, "rb") as f:
                content = f.read()
            
            if start_byte < 0 or end_byte > len(content) or start_byte > end_byte:
                return f"Error: Byte range [{start_byte}, {end_byte}] is invalid."
            
            # --- Line-by-Line Indentation Tracking ---
            # 1. Identify the base indentation of the line we are patching
            line_start = content.rfind(b"\n", 0, start_byte) + 1
            base_indent_bytes = content[line_start:start_byte]
            # Ensure we only take leading whitespace
            base_indent = b""
            for b in base_indent_bytes:
                if b in b" \t":
                    base_indent += bytes([b])
                else:
                    break
            
            base_indent_str = base_indent.decode("utf-8")

            # 2. Re-align the replacement block
            lines = replacement.splitlines()
            if lines:
                # Remove common indentation from the AI's input to get a "flat" version
                # then apply the file's base indentation to every line.
                first_line_strip = len(lines[0]) - len(lines[0].lstrip())
                
                new_lines = []
                for i, line in enumerate(lines):
                    # We strip the AI's first-line indentation from all lines to find the "relative" shift
                    stripped = line[first_line_strip:] if len(line) >= first_line_strip else line.lstrip()
                    
                    if i == 0:
                        # For the first line, we only add the missing indentation
                        # If start_byte is already at/after the line's base indentation, we add nothing.
                        current_indent_len = start_byte - line_start
                        needed_indent = base_indent_str[current_indent_len:]
                        new_lines.append(needed_indent + stripped)
                    else:
                        # For subsequent lines, we always apply the full base indentation
                        new_lines.append(base_indent_str + stripped if stripped else "")
                
                replacement = "\n".join(new_lines)


            new_content = content[:start_byte] + replacement.encode("utf-8") + content[end_byte:]


            
            with open(target, "wb") as f:
                f.write(new_content)
            
            return f"Successfully patched {filepath} at byte range [{start_byte}, {end_byte}]."
        except Exception as exc:
            return f"Error: {exc}"






    async def file_delete(self, filepath: str) -> str:
        """Delete a file within the working directory."""
        if not self._is_safe_path(filepath):
            return f"Security Error: Access to '{filepath}' is denied."
        target = Path(os.path.join(self.workdir, filepath)).resolve()
        try:
            if not target.exists():
                return f"Error: File '{filepath}' does not exist."
            if target.is_dir():
                import shutil
                shutil.rmtree(target)
                return f"Successfully deleted directory {filepath}."
            else:
                os.remove(target)
                return f"Successfully deleted file {filepath}."
        except Exception as exc:
            return f"Error: {exc}"

    async def directory_create(self, path: str) -> str:
        """Create a new directory (and any necessary parent directories) within the working directory."""
        if not self._is_safe_path(path):
            return f"Security Error: Access to '{path}' is denied."
        target = Path(os.path.join(self.workdir, path)).resolve()
        try:
            os.makedirs(target, exist_ok=True)
            return f"Successfully created directory {path}."
        except Exception as exc:
            return f"Error: {exc}"

    async def glob_search(self, pattern: str, path: str = ".") -> str:
        """Search for files matching a glob pattern."""
        import glob
        if not self._is_safe_path(path):
            return f"Security Error: Access to '{path}' is denied."
        target_dir = str(Path(os.path.join(self.workdir, path)).resolve())
        try:
            matches = glob.glob(os.path.join(target_dir, pattern), recursive=True)
            rel_matches = [os.path.relpath(m, self.workdir) for m in matches]
            if not rel_matches:
                return "No files found matching pattern."
            return "\n".join(rel_matches)
        except Exception as exc:
            return f"Error: {exc}"

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


def _read_lines_sync(filepath: str) -> list[str]:
    with open(filepath, encoding="utf-8", errors="replace") as f:
        return f.readlines()


