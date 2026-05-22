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

    async def bash(self, command: str = "", action: str = "run", job_id: str = "", timeout: int = 60, tail_lines: int = 100, filepath: str = "", start_line: int = 1, end_line: int = -1, **extra_kwargs) -> str:
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
        # Shim for local model parameter JSON typos
        for key in ("start_lin", "startline", "start", "start_l"):
            if key in extra_kwargs:
                try:
                    start_line = int(extra_kwargs[key])
                    break
                except (ValueError, TypeError):
                    pass
        for key in ("end_lin", "endline", "end", "end_l"):
            if key in extra_kwargs:
                try:
                    end_line = int(extra_kwargs[key])
                    break
                except (ValueError, TypeError):
                    pass

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
        known_actions = {"run", "background", "logs", "kill", "read", "coords", "find_text"}
        if action not in known_actions:
            if command:
                action = "run"
            else:
                is_command_lookalike = (
                    " " in action or 
                    action.startswith(("python", "bash", "sh", "ls", "grep", "git", "cat", "echo", "mkdir", "rm"))
                )
                if is_command_lookalike:
                    command = action
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

        # ── find_text ────────────────────────────────────────────────────────
        elif action == "find_text":
            pattern = extra_kwargs.get("pattern") or command
            if not pattern:
                return "Error: 'find_text' action requires a 'pattern' or 'command' argument."
            
            # Fallback cleanup of JSON escapes in search pattern
            cleaned_pattern = pattern.replace('\\"', '"').replace("\\'", "'")
            
            target_filepath = filepath or extra_kwargs.get("file_pattern") or "index.html"
            norm_path = os.path.join(self.workdir, target_filepath)
            if not os.path.exists(norm_path):
                return f"Error: File not found: {target_filepath}"
            
            try:
                with open(norm_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                
                results = []
                for i, line in enumerate(lines):
                    if pattern in line or (cleaned_pattern != pattern and cleaned_pattern in line):
                        results.append(f"Line {i+1}: {line.strip()}")
                
                if not results:
                    return f"Pattern '{pattern}' not found in {target_filepath}"
                
                # Format JSON-like or standard results that match what find_text usually yields
                # so that agent parsers are fully compatible.
                formatted_lines = [{"line": int(item.split(":")[0].split(" ")[1]), "text": item.split(":", 1)[1].strip()} for item in results]
                import json
                return json.dumps({
                    "file": target_filepath,
                    "line": formatted_lines[0]["line"] if formatted_lines else 1,
                    "text": formatted_lines[0]["text"] if formatted_lines else "",
                    "context": formatted_lines
                }, indent=2)
            except Exception as exc:
                return f"Error executing find_text: {exc}"

        # ── coords ───────────────────────────────────────────────────────────
        elif action == "coords":
            if not filepath:
                return "Error: 'coords' action requires a 'filepath' argument."
            if start_line <= 0:
                return "Error: 'coords' action requires a positive 1-indexed 'start_line' (line number) argument."
            if not command:
                return "Error: 'coords' action requires a 'command' (target pattern string) argument."

            # Calculate coordinates
            norm_path = os.path.join(self.workdir, filepath)
            if not os.path.exists(norm_path):
                return f"Error: File not found: {filepath}"
            try:
                with open(norm_path, 'rb') as f:
                    lines = f.readlines()
                
                line_idx = start_line - 1
                if line_idx < 0 or line_idx >= len(lines):
                    return f"Error: Line number {start_line} out of range (1-{len(lines)})"
                
                # Calculate start byte offset
                start_byte = sum(len(l) for l in lines[:line_idx])
                
                # Search forward from start_line to find the pattern
                idx = -1
                found_line_idx = line_idx
                for current_idx in range(line_idx, len(lines)):
                    target_line = lines[current_idx].decode('utf-8', errors='ignore')
                    idx = target_line.find(command)
                    if idx == -1:
                        # Fallback 1: Try unescaping backslash-quotes (common LLM JSON escaping confusion)
                        cleaned = command.replace('\\"', '"').replace("\\'", "'")
                        if cleaned != command:
                            idx = target_line.find(cleaned)
                            if idx != -1:
                                command = cleaned
                    
                    if idx == -1:
                        # Fallback 2: Try unescaping general raw backslashes (e.g. double escaped \\")
                        try:
                            cleaned = command.replace('\\\\"', '"').replace('\\\\', '\\')
                            if cleaned != command:
                                idx = target_line.find(cleaned)
                                if idx != -1:
                                    command = cleaned
                        except Exception:
                            pass
                            
                    if idx == -1:
                        # Fallback 3: If it's a function signature with args (e.g. "def foo(self, x):"),
                        # try searching for the function name and open parenthesis (e.g. "def foo(")
                        try:
                            import re
                            match = re.match(r"(def\s+\w+|function\s+\w+|public\s+[\w\<\>]+\s+\w+|private\s+[\w\<\>]+\s+\w+|protected\s+[\w\<\>]+\s+\w+)\(.*\)", command)
                            if match:
                                simplified = match.group(1) + "("
                                idx = target_line.find(simplified)
                                if idx != -1:
                                    command = simplified
                        except Exception:
                            pass

                    if idx == -1:
                        # Fallback 4: Try matching just the core method or class name
                        try:
                            import re
                            match = re.search(r"(\w+)", command)
                            if match:
                                name = match.group(1)
                                if len(name) > 5 and name not in ("public", "private", "return", "function", "class", "import", "def", "static", "void"):
                                    idx = target_line.find(name)
                                    if idx != -1:
                                        command = name
                        except Exception:
                            pass
                    
                    if idx != -1:
                        found_line_idx = current_idx
                        break
                    
                    start_byte += len(lines[current_idx])

                if idx == -1:
                    return f"Error: Pattern '{command}' not found on or after line {start_line}"
                
                target_line = lines[found_line_idx].decode('utf-8', errors='ignore')
                pattern_start = start_byte + len(target_line[:idx].encode('utf-8'))
                pattern_end = pattern_start + len(command.encode('utf-8'))
                
                return f"START: {pattern_start}, END: {pattern_end}, LINE: {found_line_idx + 1}"
            except Exception as e:
                return f"Error: {e}"

        else:
            return f"Error: unknown bash action '{action}'. Choose from: run, background, logs, kill, read, coords."
