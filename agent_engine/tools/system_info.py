import multiprocessing
import os
import platform
import shutil
import sys


async def system_info() -> str:
    """Get information about the current system (OS, Python version, CPU, Memory, Disk)."""
    info = []

    # OS Info
    info.append(f"OS: {platform.system()} {platform.release()} ({platform.version()})")
    info.append(f"Platform: {platform.platform()}")

    # Python Info
    info.append(f"Python: {sys.version}")

    # CPU Info
    info.append(f"CPUs: {multiprocessing.cpu_count()}")

    # Memory Info (Linux/Unix only, using /proc/meminfo if available)
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo") as f:
                mem_lines = f.readlines()
                for line in mem_lines[:2]: # Total and Free
                    info.append(line.strip())
        except Exception:
            pass

    # Disk Info
    try:
        usage = shutil.disk_usage("/")
        info.append(f"Disk Total: {usage.total // (2**30)} GB")
        info.append(f"Disk Free: {usage.free // (2**30)} GB")
    except Exception:
        pass

    return "\n".join(info)
