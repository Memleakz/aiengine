import os
import shutil
import json
import asyncio
from pathlib import Path

def _is_safe_path(workdir: str, filepath: str) -> bool:
    try:
        w_dir = Path(workdir).resolve()
        target = Path(os.path.join(workdir, filepath)).resolve()
        return w_dir == target or target.is_relative_to(w_dir)
    except (ValueError, OSError):
        return False

async def ast_grep_run(
    workdir: str,
    action: str,
    pattern: str,
    rewrite: str = None,
    filepath_glob: str = None,
    dry_run: bool = True
) -> dict:
    """
    Executes ast-grep (Rust structural tool) structurally on the codebase.
    
    This tool allows structural pattern-matching (using metavariables like $A, $B) and 
    atomic rewriting across the entire workspace.
    
    Args:
        workdir: The workspace directory context.
        action: Either 'search' (find occurrences) or 'rewrite' (replace matched patterns).
        pattern: The ast-grep structural query pattern (e.g. 'calculate_tax($AMT, $RATE)').
        rewrite: Optional. The target structural replacement pattern (e.g. 'calculate_tax(amount=$AMT, rate=$RATE)').
        filepath_glob: Optional. Glob pattern to restrict scanned files (e.g. '*.py' or 'src/**/*.js').
        dry_run: Optional. If True, rewrites are previewed as a structural diff without writing to disk. Default True.
        
    Returns:
        JSON structure with success, matches, diffs, or a helpful setup instruction if ast-grep is missing.
    """
    # 1. Detect if ast-grep is installed on the host system
    # Official name is 'ast-grep'. (Avoid 'sg' as it conflicts with Linux shadow group utility).
    binary = shutil.which("ast-grep")
    if not binary:
        # Check local node_modules fallbacks (useful for workspace-only npm installs)
        candidates = [
            os.path.join(workdir, "node_modules", ".bin", "ast-grep"),
            os.path.join(os.path.dirname(workdir), "node_modules", ".bin", "ast-grep"),
            os.path.join(os.getcwd(), "node_modules", ".bin", "ast-grep"),
            os.path.join(os.path.dirname(os.getcwd()), "node_modules", ".bin", "ast-grep")
        ]
        for cand in candidates:
            if os.path.exists(cand):
                binary = os.path.abspath(cand)
                break

    if not binary:
        return {
            "success": False,
            "error": (
                "ast-grep is not installed on this system. To enable lightning-fast workspace-wide "
                "structural pattern refactoring, please run one of the following installation commands:\n"
                "  - Via npm:  npm install -g @ast-grep/cli\n"
                "  - Via pip:  pip install ast-grep-cli\n"
                "  - Via cargo: cargo install ast-grep"
            )
        }

    if action not in ("search", "rewrite"):
        return {"success": False, "error": f"Invalid action '{action}'. Must be 'search' or 'rewrite'."}

    # 2. Build shell command arguments
    cmd = [binary, "run", "--pattern", pattern]

    if action == "rewrite":
        if not rewrite:
            return {"success": False, "error": "Argument 'rewrite' pattern is required for a rewrite action."}
        cmd.extend(["--rewrite", rewrite])
        if not dry_run:
            cmd.append("--update-all")
        else:
            # Output diff as JSON for preview
            cmd.append("--json")
    else:
        cmd.append("--json")

    if filepath_glob:
        cmd.extend(["--globs", filepath_glob])

    try:
        # Run subprocess asynchronously within the working directory
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0 and not stdout_str:
            return {
                "success": False,
                "error": f"ast-grep failed with exit code {proc.returncode}.\nStderr: {stderr_str}"
            }

        # Parse JSON output from ast-grep
        results = []
        if stdout_str:
            try:
                results = json.loads(stdout_str)
            except json.JSONDecodeError:
                # ast-grep sometimes outputs plain text if non-JSON flags are active
                return {
                    "success": True,
                    "raw_output": stdout_str,
                    "message": "Executed successfully (non-JSON response)."
                }

        return {
            "success": True,
            "action": action,
            "dry_run": dry_run if action == "rewrite" else None,
            "results": results,
            "count": len(results)
        }

    except Exception as e:
        return {"success": False, "error": f"Subprocess error: {str(e)}"}
