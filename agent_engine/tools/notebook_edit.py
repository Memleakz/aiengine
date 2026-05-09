import json
import os
from pathlib import Path


def _is_within_workdir(base: str, target: str) -> bool:
    """Return True only if target resolves to a path inside base."""
    try:
        base_resolved = Path(base).resolve()
        target_resolved = Path(target).resolve()
        return base_resolved == target_resolved or target_resolved.is_relative_to(base_resolved)
    except (ValueError, OSError):
        return False


async def notebook_edit(filepath: str, cell_index: int, new_source: str, cell_type: str | None = None, workdir: str | None = None) -> str:
    """Edit or replace a specific cell in a Jupyter notebook (.ipynb)."""
    base = os.path.abspath(workdir or os.getcwd())
    full_path = os.path.join(base, filepath)
    if not _is_within_workdir(base, full_path):
        return f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."
    if not os.path.exists(full_path):
        return f"Error: Notebook not found at '{filepath}'."

    if not filepath.endswith(".ipynb"):
        return "Error: File must have a .ipynb extension."

    try:
        with open(full_path, encoding="utf-8") as f:
            nb = json.load(f)

        if "cells" not in nb:
            return "Error: Invalid notebook format (missing 'cells')."

        cells = nb["cells"]

        if cell_index < 0 or cell_index > len(cells):
            return f"Error: cell_index out of bounds. Must be between 0 and {len(cells)}."

        # Format source as a list of strings with newlines for standard Jupyter format
        source_lines = [line + "\n" for line in new_source.split("\n")]
        # Remove trailing newline from the very last line to match standard Jupyter behavior
        if source_lines and source_lines[-1].endswith("\n"):
            source_lines[-1] = source_lines[-1][:-1]

        if cell_index == len(cells):
            # Append new cell
            ctype = cell_type or "code"
            new_cell = {
                "cell_type": ctype,
                "metadata": {},
                "source": source_lines
            }
            if ctype == "code":
                new_cell["execution_count"] = None
                new_cell["outputs"] = []
            cells.append(new_cell)
            action = "Appended new"
        else:
            # Update existing cell
            cell = cells[cell_index]
            if cell_type:
                cell["cell_type"] = cell_type
            cell["source"] = source_lines
            # Clear outputs if it's a code cell being modified
            if cell["cell_type"] == "code":
                cell["execution_count"] = None
                cell["outputs"] = []
            action = "Updated"

        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1)
            f.write("\n") # standard trailing newline

        return f"{action} cell at index {cell_index} in {filepath}."

    except json.JSONDecodeError:
        return f"Error: '{filepath}' is not valid JSON."
    except Exception as e:
        return f"Error editing notebook: {e}"
