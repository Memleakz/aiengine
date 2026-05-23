import os
import asyncio
from pathlib import Path

_MAX_FILE_BYTES = 10 * 1024 * 1024

def _is_safe_path(workdir: str, filepath: str) -> bool:
    try:
        w_dir_str = workdir if workdir is not None else os.getcwd()
        w_dir = Path(w_dir_str).resolve()
        target = Path(os.path.join(w_dir_str, filepath)).resolve()
        return w_dir == target or target.is_relative_to(w_dir)
    except (ValueError, OSError, TypeError):
        return False

def _read_lines_sync(filepath: str) -> list[str]:
    with open(filepath, encoding="utf-8", errors="replace") as f:
        return f.readlines()

async def read_file(workdir: str, filepath: str, start_line: int = 1, end_line: int = -1) -> str:
    """Read a file within workdir, optionally slicing to a line range (1-indexed, end_line=-1 means EOF)."""
    # Law #8 enforcement: steer model away from loading entire source files into context.
    _SOURCE_EXTENSIONS = (
        ".py", ".js", ".ts", ".jsx", ".tsx", ".cs", ".java", ".php",
        ".go", ".rs", ".rb", ".cpp", ".c", ".h", ".swift", ".kt", ".scala"
    )
    _source_warning = ""
    if any(filepath.endswith(ext) for ext in _SOURCE_EXTENSIONS) and start_line == 1 and end_line == -1:
        _source_warning = (
            "\n\n⚠️  TOOL_USAGE_WARNING (Law #8 — original_text_guard Supremacy): "
            "You called read_file on a source code file. This loads the entire file into context, "
            "wasting >90% of your token budget on code you will never touch. "
            "Use get_entity_coordinates(filepath, entity_name) instead — it returns the exact "
            "target code block via original_text_guard in a single surgical call."
        )

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

        # Snapshot original syntax validity before editing
        orig_valid = True
        try:
            from .ast_ops import verify_ast_integrity
            ast_res = await verify_ast_integrity(target)
            orig_valid = ast_res.get("syntax_valid", True)
        except Exception:
            pass

        original_content = content
        if replace_all:
            content = content.replace(old_string, new_string)
        else:
            content = content.replace(old_string, new_string, 1)

        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        # AST Safety: verify the edit did not introduce a syntax error
        try:
            from .ast_ops import verify_ast_integrity, TreeCache
            ast_res = await verify_ast_integrity(target)
            if orig_valid and not ast_res.get("syntax_valid", True):
                # Rollback! Restore original content to prevent corruption.
                with open(target, "w", encoding="utf-8") as f_rollback:
                    f_rollback.write(original_content)
                TreeCache.get_tree(target, force_reload=True)
                errors = ast_res.get("errors", [])
                err_msg = errors[0]['near_text'] if errors else "unknown context"
                return f"Error: Edit rejected! Replacing '{old_string}' introduces a syntax error near '{err_msg}'. Rolled back to preserve code integrity."
        except Exception:
            pass

        return f"Successfully edited {filepath}."
    except Exception as exc:
        return f"Error: {exc}"

async def patch_code_range(workdir: str, filepath: str, start_byte: int = None, end_byte: int = None, replacement: str = None, original_text: str = None, disable_indent_align: bool = False, override_base_indent: str = None, patches: list[dict] = None, version_token: str = None, **extra_kwargs) -> str:
    """
    Surgically replace a byte range in a file with new content.
    
    This tool is designed to be used with byte offsets provided by AST-analysis tools 
    (like Tree-Sitter MCP). It ensures precise, structural edits.
    
    Parameters:
    - original_text: Optional. The exact original text that should exist within the [start_byte, end_byte] range.
                     If specified, the tool will verify this matches before making the edit to prevent corruption.
    - patches: Optional. A list of multiple patches to apply in a single atomic transaction. Each patch dict should
               contain: start_byte, end_byte, replacement, and optional original_text.
    """
    if not _is_safe_path(workdir, filepath):
        return f"Security Error: Access to '{filepath}' is denied."
    target = str(Path(os.path.join(workdir, filepath)).resolve())
    
    if patches is not None:
        try:
            import json
            import ast
            if isinstance(patches, str):
                try:
                    patches = ast.literal_eval(patches)
                except Exception:
                    try:
                        patches = json.loads(patches)
                    except Exception:
                        pass
            if isinstance(patches, list):
                for i in range(len(patches)):
                    if isinstance(patches[i], str):
                        try:
                            patches[i] = ast.literal_eval(patches[i])
                        except Exception:
                            try:
                                patches[i] = json.loads(patches[i])
                            except Exception:
                                pass
            if isinstance(patches, str) or not isinstance(patches, list):
                return f"Error: The patches parameter must be a list of dicts (or a valid JSON/Python literal list). Failed to parse patches: {patches}"
            
            # Read backup bytes for absolute rollback safety
            with open(target, "rb") as f_orig:
                original_file_bytes = f_orig.read()
                
            # Perform initial syntactic verification
            orig_valid = True
            try:
                from .ast_ops import verify_ast_integrity
                ast_res = await verify_ast_integrity(target)
                orig_valid = ast_res.get("syntax_valid", True)
            except Exception:
                pass
                            
            # Sort patches in descending order of start_byte (bottom-up approach)
            # to ensure that byte shifts from preceding modifications do not invalidate
            # the offsets of subsequent modifications!
            sorted_patches = sorted(patches, key=lambda p: p.get("start_byte", 0), reverse=True)
            results = []
            for patch in sorted_patches:
                p_start = patch.get("start_byte")
                p_end = patch.get("end_byte")
                p_repl = patch.get("replacement")
                if p_repl is None and "text" in patch:
                    p_repl = patch.get("text")
                p_orig = patch.get("original_text")
                res = await patch_code_range(
                    workdir=workdir,
                    filepath=filepath,
                    start_byte=p_start,
                    end_byte=p_end,
                    replacement=p_repl,
                    original_text=p_orig,
                    disable_indent_align=disable_indent_align,
                    override_base_indent=override_base_indent,
                )
                if res.startswith("Error:") or res.startswith("Security Error:"):
                    # Rollback the entire file transaction
                    with open(target, "wb") as f_rollback:
                        f_rollback.write(original_file_bytes)
                    from .ast_ops import TreeCache
                    TreeCache.get_tree(target, force_reload=True)
                    return f"Transaction failed at patch [{p_start}, {p_end}]: {res} (Entire transaction rolled back to original state)."
                results.append(res)
                
            # Check final syntactic integrity after applying all patches
            try:
                from .ast_ops import verify_ast_integrity
                ast_res = await verify_ast_integrity(target)
                if orig_valid and not ast_res.get("syntax_valid", True):
                    # Rollback the entire transaction due to introduced syntax errors!
                    with open(target, "wb") as f_rollback:
                        f_rollback.write(original_file_bytes)
                    from .ast_ops import TreeCache
                    TreeCache.get_tree(target, force_reload=True)
                    errors = ast_res.get("errors", [])
                    err_msg = errors[0]['near_text'] if errors else "unknown context"
                    return f"Transaction failed: Applying these patches introduces a syntax error near '{err_msg}'. Entire transaction rolled back to preserve syntax validity."
            except Exception:
                pass
                
            return f"Successfully applied {len(sorted_patches)} patches to {filepath}."
        except Exception as e:
            return f"Error during transaction patching: {e}"

    try:
        with open(target, "rb") as f:
            raw_content = f.read()
        has_crlf = b"\r\n" in raw_content
        content = raw_content.replace(b"\r\n", b"\n")

        # Law #7 enforcement: version_token staleness check.
        # If the caller supplies the token stamped by get_entity_coordinates, verify the file
        # hasn't changed since those coordinates were queried. A mismatch means the coordinates
        # are stale (another patch already shifted bytes) and we must refuse to proceed.
        if version_token is not None:
            import hashlib
            current_hash = hashlib.sha256(content).hexdigest()[:16]
            if current_hash != version_token:
                return (
                    f"Error: Stale coordinates detected! The file '{filepath}' has changed since "
                    f"your coordinates were queried (version_token mismatch: expected '{version_token}', "
                    f"got '{current_hash}'). Re-query get_entity_coordinates or get_references to obtain "
                    f"fresh coordinates before patching."
                )

        if start_byte == -1 or end_byte == -1 or start_byte >= len(content):
            start_byte = len(content)
            end_byte = len(content)
            original_text = ""

        if replacement is None:
            replacement = ""

        if replacement is not None:
            # Fallback unescaping of JSON backslashes in replacement content
            replacement = (
                replacement
                .replace('\\"', '"')
                .replace("\\'", "'")
                .replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\t", "\t")
            )

        if original_text is not None:
            # Fallback unescaping of JSON backslashes in expected text
            cleaned_expected = (
                original_text
                .replace('\\"', '"')
                .replace("\\'", "'")
                .replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\t", "\t")
            )
            original_text_bytes = cleaned_expected.encode("utf-8")
            actual = b""
            if 0 <= start_byte <= end_byte <= len(content):
                actual = content[start_byte:end_byte]
            
            actual_norm = actual.replace(b"\r\n", b"\n")
            
            # 1. Idempotency Check: Gracefully skip if replacement has already been applied!
            if replacement is not None:
                repl_norm = replacement.encode("utf-8").replace(b"\r\n", b"\n")
                if actual_norm == repl_norm:
                    return f"Gracefully skipped patch at [{start_byte}, {end_byte}]: Already applied."
            
            expected_norm = original_text_bytes.replace(b"\r\n", b"\n")
            
            if actual_norm != expected_norm:
                import re
                actual_clean = re.sub(rb'\s+', rb' ', actual_norm.strip())
                expected_clean = re.sub(rb'\s+', rb' ', expected_norm.strip())
                
                if actual_clean != expected_clean:
                    # Search for all occurrences of original_text_bytes in the content
                    matches = []
                    idx = content.find(original_text_bytes)
                    while idx != -1:
                        matches.append(idx)
                        idx = content.find(original_text_bytes, idx + 1)
                    
                    if matches:
                        # Find the match closest to the requested start_byte (Proximity check: within 50 bytes)
                        closest_start = min(matches, key=lambda m: abs(m - start_byte))
                        if abs(closest_start - start_byte) <= 50:
                            start_byte = closest_start
                            end_byte = start_byte + len(original_text_bytes)
                        else:
                            actual_str = actual.decode("utf-8", errors="replace")
                            return (
                                f"Error: Range verification failed. The content at [{start_byte}, {end_byte}] "
                                f"is '{actual_str}', but expected '{original_text}'. Please re-query the AST to find the correct coordinates."
                            )
                    else:
                        # Also try finding the raw/unescaped original text directly
                        raw_expected = original_text.encode("utf-8")
                        idx = content.find(raw_expected)
                        if idx != -1:
                            matches = []
                            while idx != -1:
                                matches.append(idx)
                                idx = content.find(raw_expected, idx + 1)
                            closest_start = min(matches, key=lambda m: abs(m - start_byte))
                            if abs(closest_start - start_byte) <= 50:
                                start_byte = closest_start
                                end_byte = start_byte + len(raw_expected)
                            else:
                                actual_str = actual.decode("utf-8", errors="replace")
                                return (
                                    f"Error: Range verification failed. The content at [{start_byte}, {end_byte}] "
                                    f"is '{actual_str}', but expected '{original_text}'. Please re-query the AST to find the correct coordinates."
                                )
                        else:
                            actual_str = actual.decode("utf-8", errors="replace")
                            return (
                                f"Error: Range verification failed. The content at [{start_byte}, {end_byte}] "
                                f"is '{actual_str}', but expected '{original_text}'. Please re-query the AST to find the correct coordinates."
                            )
        
        if start_byte < 0 or end_byte > len(content) or start_byte > end_byte:
            return f"Error: Byte range [{start_byte}, {end_byte}] is invalid."
        
        if not disable_indent_align:
            if override_base_indent is not None:
                if isinstance(override_base_indent, int):
                    base_indent_str = " " * override_base_indent
                elif str(override_base_indent).isdigit():
                    base_indent_str = " " * int(override_base_indent)
                elif override_base_indent == "":
                    base_indent_str = "    "
                else:
                    base_indent_str = str(override_base_indent)
                line_start = content.rfind(b"\n", 0, start_byte) + 1
            else:
                line_start = content.rfind(b"\n", 0, start_byte) + 1
                i_end = line_start
                while i_end < len(content) and content[i_end] in b" \t":
                    i_end += 1
                base_indent_str = content[line_start:i_end].decode("utf-8")

            lines = replacement.splitlines()
            if lines:
                # Find the baseline indentation of the replacement block (excluding empty lines)
                non_empty_lines = [l for l in lines if l.strip()]
                
                # Find the indentation of the first line of the block
                first_line_strip = len(lines[0]) - len(lines[0].lstrip())
                
                new_lines = []
                for i, line in enumerate(lines):
                    if not line.strip():
                        new_lines.append("")
                        continue
                        
                    if i == 0 and override_base_indent is None:
                        # Dynamic preceding indent alignment
                        stripped = line[first_line_strip:]
                        current_indent_len = start_byte - line_start
                        needed_indent = base_indent_str[current_indent_len:] if len(base_indent_str) >= current_indent_len else ""
                        new_lines.append(needed_indent + stripped)
                    else:
                        # Absolute or relative base alignment
                        line_indent = len(line) - len(line.lstrip())
                        relative_indent = max(0, line_indent - first_line_strip)
                        stripped = line[line_indent:]
                        new_lines.append(base_indent_str + (" " * relative_indent) + stripped)
                
                replacement = "\n".join(new_lines)


            if start_byte == end_byte and start_byte > 0:
                preceding_char = content[start_byte - 1:start_byte]
                if preceding_char != b"\n" and not replacement.startswith("\n"):
                    replacement = "\n" + base_indent_str + replacement
        else:
            if start_byte == end_byte and start_byte > 0:
                preceding_char = content[start_byte - 1:start_byte]
                if preceding_char != b"\n" and not replacement.startswith("\n"):
                    replacement = "\n" + replacement

        # Check initial syntax validity before writing this single patch
        orig_valid = True
        try:
            from .ast_ops import verify_ast_integrity
            ast_res = await verify_ast_integrity(target)
            orig_valid = ast_res.get("syntax_valid", True)
        except Exception:
            pass

        new_content_lf = content[:start_byte] + replacement.encode("utf-8") + content[end_byte:]
        
        # If the original file had CRLF, translate LF line endings back to CRLF on disk
        if has_crlf:
            new_content = new_content_lf.replace(b"\n", b"\r\n")
        else:
            new_content = new_content_lf

        with open(target, "wb") as f:
            f.write(new_content)
        
        try:
            from .ast_ops import TreeCache
            new_end_byte = start_byte + len(replacement.encode("utf-8"))
            # TreeCache operates entirely on LF-normalized bytes, so notify it using LF content
            TreeCache.notify_edit(target, start_byte, end_byte, new_end_byte, new_content_lf)
        except Exception:
            pass
        
        # Verify if this patch introduced a syntax error
        try:
            from .ast_ops import verify_ast_integrity
            ast_res = await verify_ast_integrity(target)
            if orig_valid and not ast_res.get("syntax_valid", True):
                # Rollback this single patch write using the original raw bytes
                with open(target, "wb") as f_rollback:
                    f_rollback.write(raw_content)
                from .ast_ops import TreeCache
                TreeCache.get_tree(target, force_reload=True)
                errors = ast_res.get("errors", [])
                err_msg = errors[0]['near_text'] if errors else "unknown context"
                return f"Error: Patch rejected! Applying this patch introduces a syntax error near '{err_msg}'. Transaction rolled back to preserve code integrity."
        except Exception:
            pass
        
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
