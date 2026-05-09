import inspect
from collections.abc import Callable

_PYTHON_TO_JSON_TYPE: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _python_type_to_json(annotation) -> str:
    return _PYTHON_TO_JSON_TYPE.get(annotation, "string")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}

    def register(self, func: Callable) -> None:
        sig = inspect.signature(func)
        docstring = (func.__doc__ or "").strip().splitlines()[0] if func.__doc__ else ""
        properties: dict[str, dict] = {}
        required: list[str] = []

        for name, param in sig.parameters.items():
            if name == "workdir":
                continue
            annotation = param.annotation
            json_type = (
                _python_type_to_json(annotation)
                if annotation is not inspect.Parameter.empty
                else "string"
            )
            properties[name] = {"type": json_type, "description": name}
            if param.default is inspect.Parameter.empty:
                required.append(name)

        schema = {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": docstring,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
        self._tools[func.__name__] = {"schema": schema, "fn": func}

    def register_mcp_tool(self, mcp_tool, session, workdir_getter: Callable[[], str] | None = None) -> None:
        tool_name = mcp_tool.name

        async def _wrapper(**kwargs):
            if workdir_getter and "directory" in (mcp_tool.inputSchema.get("properties") or {}):
                if "directory" not in kwargs:
                    kwargs["directory"] = workdir_getter()
                    # If we inject directory, remove projectId so the server doesn't use a wrong cache
                    kwargs.pop("projectId", None)
            result = await session.call_tool(tool_name, arguments=kwargs)
            parts = []
            for content in result.content:
                if hasattr(content, "text"):
                    parts.append(content.text)
                else:
                    parts.append(str(content))
            return "\n".join(parts)

        schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": mcp_tool.description or "",
                "parameters": mcp_tool.inputSchema,
            },
        }
        self._tools[tool_name] = {"schema": schema, "fn": _wrapper}

    def get_all_schemas(self) -> list[dict]:
        return [entry["schema"] for entry in self._tools.values()]

    async def dispatch(self, name: str, kwargs: dict) -> str:
        entry = self._tools.get(name)
        if entry is None:
            return f"Error: unknown tool '{name}'"
        try:
            result = await entry["fn"](**kwargs)
            return str(result)
        except Exception as exc:
            return f"Error executing '{name}': {exc}"
