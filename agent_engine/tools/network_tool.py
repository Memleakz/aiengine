import asyncio


async def _run_cmd(cmd: list[str]) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        return (stdout + stderr).decode(errors="replace").strip()
    except TimeoutError:
        return f"Error: command {' '.join(cmd)} timed out."
    except Exception as e:
        return f"Error executing {' '.join(cmd)}: {e}"

async def network_tool(action: str, target: str = "") -> str:
    """Perform network diagnostics and information gathering.

    Actions:
      - 'ping': Ping a host (requires 'target')
      - 'lookup': Perform a DNS lookup for a host (requires 'target')
      - 'interfaces': List network interfaces and IP addresses
      - 'public_ip': Try to fetch the public IP address
    """
    if action == "ping":
        if not target:
            return "Error: 'target' is required for ping."
        return await _run_cmd(["ping", "-c", "3", target])

    elif action == "lookup":
        if not target:
            return "Error: 'target' is required for lookup."
        # Try nslookup, fallback to host
        res = await _run_cmd(["nslookup", target])
        if "Error" in res:
            res = await _run_cmd(["host", target])
        return res

    elif action == "interfaces":
        res = await _run_cmd(["ip", "addr"])
        if "Error" in res:
            res = await _run_cmd(["ifconfig"])
        return res

    elif action == "public_ip":
        # Use curl or wget to a public IP echo service
        res = await _run_cmd(["curl", "-s", "https://ifconfig.me"])
        if "Error" in res or not res:
            res = await _run_cmd(["wget", "-qO-", "https://ifconfig.me"])
        return res if res else "Error: Could not fetch public IP."

    else:
        return f"Error: Unknown network action '{action}'."
