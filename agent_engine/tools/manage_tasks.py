import json
import os

_TASKS_FILE = ".agent_tasks.json"

async def manage_tasks(
    action: str,
    task_id: str | None = None,
    title: str | None = None,
    status: str | None = None,
    workdir: str | None = None
) -> str:
    """Manage a simple local subtask list to help keep track of long-running objectives.

    Actions:
      - 'list': View all current tasks
      - 'create': Add a new task (requires 'title')
      - 'update': Update task status (requires 'task_id', 'status' must be 'pending', 'in_progress', or 'completed')
      - 'delete': Remove a task (requires 'task_id')
    """

    def load_tasks() -> dict:
        path = os.path.join(workdir or os.getcwd(), _TASKS_FILE)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def save_tasks(tasks: dict):
        path = os.path.join(workdir or os.getcwd(), _TASKS_FILE)
        with open(path, "w") as f:
            json.dump(tasks, f, indent=2)

    tasks = load_tasks()

    if action == "list":
        if not tasks:
            return "No tasks found."
        lines = []
        for tid, t in tasks.items():
            lines.append(f"[{tid}] {t['status'].upper()}: {t['title']}")
        return "\n".join(lines)

    elif action == "create":
        if not title:
            return "Error: 'title' is required for 'create' action."
        # Generate a robust ID that avoids collisions even after deletions
        if tasks:
            try:
                new_id = str(max(int(k) for k in tasks) + 1)
            except ValueError:
                new_id = str(len(tasks) + 1)
        else:
            new_id = "1"
        tasks[new_id] = {"title": title, "status": "pending"}
        save_tasks(tasks)
        return f"Task created with ID {new_id}."

    elif action == "update":
        if not task_id or task_id not in tasks:
            return f"Error: Task ID '{task_id}' not found."
        if status not in ("pending", "in_progress", "completed"):
            return "Error: status must be 'pending', 'in_progress', or 'completed'."
        tasks[task_id]["status"] = status
        save_tasks(tasks)
        return f"Task {task_id} updated to {status}."

    elif action == "delete":
        if not task_id or task_id not in tasks:
            return f"Error: Task ID '{task_id}' not found."
        del tasks[task_id]
        save_tasks(tasks)
        return f"Task {task_id} deleted."

    else:
        return f"Error: Unknown action '{action}'."
