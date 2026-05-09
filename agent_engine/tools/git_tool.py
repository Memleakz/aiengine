import asyncio
import os


async def _run_git_cmd(args: list[str], cwd: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd
    )
    stdout, stderr = await proc.communicate()
    output = (stdout + stderr).decode(errors="replace").strip()
    return output

async def git_tool(action: str, workdir: str | None = None, **kwargs) -> str:
    """Perform common git operations.

    Actions:
      - 'status': Show working tree status
      - 'diff': Show changes in the working tree
      - 'commit': Commit staged changes (requires 'message')
      - 'add': Stage files (requires 'path')
      - 'branch': List or create branches (optional 'name')
      - 'log': Show commit history
    """
    cwd = workdir or os.getcwd()

    if action == "status":
        return await _run_git_cmd(["status"], cwd)

    elif action == "diff":
        return await _run_git_cmd(["diff"], cwd)

    elif action == "add":
        path = kwargs.get("path", ".")
        res = await _run_git_cmd(["add", path], cwd)
        return res if res else f"Added {path} to staging."

    elif action == "commit":
        message = kwargs.get("message")
        if not message:
            return "Error: 'message' is required for commit."
        return await _run_git_cmd(["commit", "-m", message], cwd)

    elif action == "branch":
        name = kwargs.get("name")
        if name:
            return await _run_git_cmd(["checkout", "-b", name], cwd)
        return await _run_git_cmd(["branch"], cwd)

    elif action == "log":
        limit = kwargs.get("limit", "5")
        return await _run_git_cmd(["log", f"-n{limit}", "--oneline"], cwd)

    else:
        return f"Error: Unknown git action '{action}'."
