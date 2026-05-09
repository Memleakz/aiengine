import os


async def manage_todo(action: str, content: str = "", workdir: str | None = None) -> str:
    """Manage the CLAUDE.md file which serves as the agent's persistent memory and checklist for the current project.

    Actions:
      - 'read': View the current CLAUDE.md content
      - 'update': Overwrite CLAUDE.md with new content
      - 'append': Append new content to the end of CLAUDE.md
    """
    filename = os.path.join(workdir or os.getcwd(), "CLAUDE.md")

    if action == "read":
        if not os.path.exists(filename):
            return "CLAUDE.md does not exist yet."
        with open(filename, encoding="utf-8") as f:
            return f.read()

    elif action == "update":
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return "CLAUDE.md updated successfully."

    elif action == "append":
        with open(filename, "a", encoding="utf-8") as f:
            # Only prepend a newline separator if the file already has content
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                f.write("\n" + content)
            else:
                f.write(content)
        return "Content appended to CLAUDE.md."

    else:
        return f"Error: Unknown todo action '{action}'."
