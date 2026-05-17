import os
import asyncio
from pathlib import Path

_MAX_FILE_BYTES = 10 * 1024 * 1024

def _is_safe_path(workdir: str, filepath: str) -> bool:
    try:
        w_dir = Path(workdir).resolve()
        target = Path(os.path.join(workdir, filepath)).resolve()
        return w_dir == target or target.is_relative_to(w_dir)
    except (ValueError, OSError):
        return False

def _read_lines_sync(filepath: str) -> list[str]:
    with open(filepath, encoding="utf-8", errors="replace") as f:
        return f.readlines()

async def read_file(workdir: str, filepath: str, start_line: int = 1, end_line: int = -1) -> str:
    """Read a file within workdir, optionally slicing to a line range (1-indexed, end_line=-1 means EOF)."""
    if not _is_safe_path(workdir, filepath):
        return f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."
    target = str(Path(os.path.join(workdir, filepath)).resolve())
    try:
        file_size = os.path.getsize(target)
        if file_size > _MAX_FILE_BYTES:
            return f"Error: file '{filepath}' is too large ({file_size:,} bytes > {_MAX_FILE_BYTES:,} byte limit)."
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

async def file_write(workdir: str, filepath: str, content: str = "", base64_content: str = "") -> str:
    """Create or overwrite a file with text content (via 'content') or base64 data (via 'base64_content')."""
    if not _is_safe_path(workdir, filepath):
        return f"Security Error: Access to '{filepath}' is denied."
    target = str(Path(os.path.join(workdir, filepath)).resolve())
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

async def file_edit(workdir: str, filepath: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Edit a file by replacing old_string with new_string. Replaces all occurrences if replace_all is True, otherwise replaces only the first occurrence."""
    if not _is_safe_path(workdir, filepath):
        return f"Security Error: Access to '{filepath}' is denied."
    target = str(Path(os.path.join(workdir, filepath)).resolve())
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

async def patch_code_range(workdir: str, filepath: str, start_byte: int, end_byte: int, replacement: str) -> str:
    """
    Surgically replace a byte range in a file with new content.
    
    This tool is designed to be used with byte offsets provided by AST-analysis tools 
    (like Tree-Sitter MCP). It ensures precise, structural edits.
    """
    if not _is_safe_path(workdir, filepath):
        return f"Security Error: Access to '{filepath}' is denied."
    target = str(Path(os.path.join(workdir, filepath)).resolve())
    try:
        with open(target, "rb") as f:
            content = f.read()
        
        if start_byte < 0 or end_byte > len(content) or start_byte > end_byte:
            return f"Error: Byte range [{start_byte}, {end_byte}] is invalid."
        
        line_start = content.rfind(b"\n", 0, start_byte) + 1
        base_indent_bytes = content[line_start:start_byte]
        base_indent = b""
        for b in base_indent_bytes:
            if b in b" \t":
                base_indent += bytes([b])
            else:
                break
        
        base_indent_str = base_indent.decode("utf-8")

        lines = replacement.splitlines()
        if lines:
            first_line_strip = len(lines[0]) - len(lines[0].lstrip())
            
            new_lines = []
            for i, line in enumerate(lines):
                stripped = line[first_line_strip:] if len(line) >= first_line_strip else line.lstrip()
                
                if i == 0:
                    current_indent_len = start_byte - line_start
                    needed_indent = base_indent_str[current_indent_len:]
                    new_lines.append(needed_indent + stripped)
                else:
                    new_lines.append(base_indent_str + stripped if stripped else "")
            
            replacement = "\n".join(new_lines)


        new_content = content[:start_byte] + replacement.encode("utf-8") + content[end_byte:]


        
        with open(target, "wb") as f:
            f.write(new_content)
        
        return f"Successfully patched {filepath} at byte range [{start_byte}, {end_byte}]."
    except Exception as exc:
        return f"Error: {exc}"

async def file_delete(workdir: str, filepath: str) -> str:
    """Delete a file within the working directory."""
    if not _is_safe_path(workdir, filepath):
        return f"Security Error: Access to '{filepath}' is denied."
    target = Path(os.path.join(workdir, filepath)).resolve()
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

async def directory_create(workdir: str, path: str) -> str:
    """Create a new directory (and any necessary parent directories) within the working directory."""
    if not _is_safe_path(workdir, path):
        return f"Security Error: Access to '{path}' is denied."
    target = Path(os.path.join(workdir, path)).resolve()
    try:
        os.makedirs(target, exist_ok=True)
        return f"Successfully created directory {path}."
    except Exception as exc:
        return f"Error: {exc}"
