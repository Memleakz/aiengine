import sys
import os

# Add package directory to sys.path
pkg_dir = "/home/tobias/dev/Repo/aiengine/src/web-cli/.venv/lib64/python3.14/site-packages"
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from mcp_server_tree_sitter.di import get_container
from mcp_server_tree_sitter.tools.ast_operations import get_file_ast
from pathlib import Path

def main():
    try:
        container = get_container()
        project_registry = container.project_registry
        
        # Register project
        print("Registering project...")
        project = project_registry.register_project(".", "/home/tobias/dev/Repo/aiengine/src")
        
        print("Calling get_file_ast...")
        res = get_file_ast(
            project=project,
            path="demosite/index.html",
            language_registry=container.language_registry,
            tree_cache=container.tree_cache,
            max_depth=5,
            include_text=True
        )
        print("Success! AST structure keys:")
        print(res.keys())
        print("Root AST details:")
        print(res["tree"].keys())
        print(f"Children count: {len(res['tree']['children'])}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
