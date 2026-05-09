import os

_SKILLS_DIR_NAME = ".agent_skills"

async def skill_tool(action: str, name: str = "", content: str = "", workdir: str | None = None) -> str:
    """Manage project-specific 'skills' which are snippets of specialized instructions or knowledge."""
    skills_dir = os.path.join(workdir or os.getcwd(), _SKILLS_DIR_NAME)
    if not os.path.exists(skills_dir):
        os.makedirs(skills_dir, exist_ok=True)

    if action == "list":
        files = [f for f in os.listdir(skills_dir) if f.endswith(".md")]
        if not files:
            return "No skills found."
        return "\n".join([f[:-3] for f in files])

    elif action == "save":
        if not name or not content:
            return "Error: 'name' and 'content' are required to save a skill."
        safe_name = "".join([c for c in name if c.isalnum() or c in (" ", "_", "-")]).strip().replace(" ", "_")
        path = os.path.join(skills_dir, f"{safe_name}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Skill '{safe_name}' saved."

    elif action == "read":
        if not name:
            return "Error: 'name' is required to read a skill."
        safe_name = "".join([c for c in name if c.isalnum() or c in (" ", "_", "-")]).strip().replace(" ", "_")
        path = os.path.join(skills_dir, f"{safe_name}.md")
        if not os.path.exists(path):
            return f"Error: Skill '{safe_name}' not found."
        with open(path, encoding="utf-8") as f:
            return f.read()

    elif action == "delete":
        if not name:
            return "Error: 'name' is required to delete a skill."
        safe_name = "".join([c for c in name if c.isalnum() or c in (" ", "_", "-")]).strip().replace(" ", "_")
        path = os.path.join(skills_dir, f"{safe_name}.md")
        if not os.path.exists(path):
            return f"Error: Skill '{safe_name}' not found."
        os.remove(path)
        return f"Skill '{safe_name}' deleted."

    else:
        return f"Error: Unknown skill action '{action}'."
