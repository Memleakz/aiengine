import os

async def get_tool_guide(workdir: str) -> str:
    """Retrieve the comprehensive developer playbook and usage instructions for the code intelligence tools."""
    skills_dir = os.path.join(workdir or os.getcwd(), ".agent_skills")
    guide_path = os.path.join(skills_dir, "ultimate_software_dev.md")
    
    if os.path.exists(guide_path):
        with open(guide_path, "r", encoding="utf-8") as f:
            return f.read()
            
    return (
        "# Code Intelligence Tool Guide\n\n"
        "You have access to a rich set of AST and code editing tools. Use them to surgically edit code:\n"
        "- `get_document_map`: Get structural blueprint of a file.\n"
        "- `get_entity_coordinates`: Get coordinates of functions/classes.\n"
        "- `patch_code_range`: Edit specific byte coordinates precisely.\n"
        "- `read_file` / `file_edit`: Slices lines or performs complete rewrites.\n"
    )
