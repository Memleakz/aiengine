import asyncio
import os


async def _run_crontab(args: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec(
        "crontab", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    output = (stdout + stderr).decode(errors="replace").strip()
    return output

async def cron_tool(action: str, **kwargs) -> str:
    """Manage system cron jobs using the 'crontab' command.

    Actions:
      - 'list': List current user's cron jobs
      - 'add': Add a new cron job (requires 'schedule' and 'command')
      - 'remove': Remove a cron job by its command or comment match (requires 'query')
    """

    if action == "list":
        res = await _run_crontab(["-l"])
        if not res or "no crontab for" in res.lower():
            return "No cron jobs found."
        return res

    elif action == "add":
        schedule = kwargs.get("schedule")
        command = kwargs.get("command")
        if not schedule or not command:
            return "Error: 'schedule' and 'command' are required for 'add' action."

        current = await _run_crontab(["-l"])
        if "no crontab for" in current.lower():
            current = ""

        new_job = f"{schedule} {command}"
        new_crontab = current.strip() + "\n" + new_job + "\n"

        # Use a temporary file to update crontab
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(new_crontab)
            tmp_path = f.name

        try:
            res = await _run_crontab([tmp_path])
            return f"Cron job added: {new_job}"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    elif action == "remove":
        query = kwargs.get("query")
        if not query:
            return "Error: 'query' is required for 'remove' action."

        current = await _run_crontab(["-l"])
        if "no crontab for" in current.lower():
            return "No cron jobs to remove."

        lines = current.strip().split("\n")
        new_lines = [line for line in lines if query not in line]

        if len(new_lines) == len(lines):
            return f"No cron job matching '{query}' found."

        new_crontab = "\n".join(new_lines) + "\n"

        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(new_crontab)
            tmp_path = f.name

        try:
            await _run_crontab([tmp_path])
            return f"Removed {len(lines) - len(new_lines)} cron job(s) matching '{query}'."
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    else:
        return f"Error: Unknown cron action '{action}'."
