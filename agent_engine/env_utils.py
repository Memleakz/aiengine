import os
from pathlib import Path

def get_clean_env() -> dict[str, str]:
    """Return a copy of the environment with virtualenv variables removed to avoid leaking the current venv."""
    env = os.environ.copy()
    venv_path = env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)

    if venv_path:
        # Remove the venv's bin directory from PATH
        bin_path = os.path.abspath(os.path.join(venv_path, "bin"))
        path_parts = env.get("PATH", "").split(os.pathsep)
        # Filter out the current venv bin path
        new_path_parts = [p for p in path_parts if os.path.abspath(p) != bin_path]
        env["PATH"] = os.pathsep.join(new_path_parts)
    
    return env
