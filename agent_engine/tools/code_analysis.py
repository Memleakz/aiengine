import ast
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


async def code_analysis(filepath: str, workdir: str | None = None) -> str:
    """Analyze a Python file and return a summary of its classes, functions, and docstrings."""
    base = os.path.abspath(workdir or os.getcwd())
    full_path = os.path.join(base, filepath)
    if not _is_within_workdir(base, full_path):
        return f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."
    if not os.path.exists(full_path):
        return f"Error: File '{filepath}' not found."

    if not filepath.endswith(".py"):
        return "Error: Only Python (.py) files are supported for code analysis."

    try:
        with open(full_path, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        summary = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                summary.append(f"Class: {node.name}")
                doc = ast.get_docstring(node)
                if doc:
                    summary.append(f"  Doc: {doc.splitlines()[0]}...")
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        summary.append(f"  Method: {item.name}")
            elif isinstance(node, ast.FunctionDef):
                summary.append(f"Function: {node.name}")
                doc = ast.get_docstring(node)
                if doc:
                    summary.append(f"  Doc: {doc.splitlines()[0]}...")

        if not summary:
            return "No classes or functions found in file."

        return "\n".join(summary)
    except Exception as e:
        return f"Error analyzing file: {e}"
