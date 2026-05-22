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
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
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
            props = mcp_tool.inputSchema.get("properties") or {}
            if workdir_getter:
                # Inject workdir into common path-related arguments if not provided
                for key in ("directory", "path", "root_path", "project_path", "base_path"):
                    if key in props and key not in kwargs:
                        kwargs[key] = workdir_getter()
                        # Some servers use projectId as a cache key; clearing it ensures fresh analysis of the new path
                        kwargs.pop("projectId", None)
                        break
            result = await session.call_tool(tool_name, arguments=kwargs)
            parts = []
            for content in result.content:
                if hasattr(content, "text"):
                    parts.append(content.text)
                else:
                    parts.append(str(content))
            return "\n".join(parts)

        # Deep copy inputSchema to safely modify parameter descriptions
        import copy
        input_schema = copy.deepcopy(mcp_tool.inputSchema)
        props = input_schema.get("properties") or {}
        if "project" in props:
            props["project"]["description"] = "The registered project name (always use '.' for the current workspace)"

        schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": mcp_tool.description or "",
                "parameters": input_schema,
            },
        }
        self._tools[tool_name] = {"schema": schema, "fn": _wrapper}

    def get_all_schemas(self, allowed_names: list[str] = None) -> list[dict]:
        schemas = []
        for entry in self._tools.values():
            schema = entry["schema"]
            name = schema["function"]["name"]
            if allowed_names is not None and name not in allowed_names:
                continue
            
            # Compress schema to minimize prompt tokens
            import copy
            compressed = copy.deepcopy(schema)
            
            # Shorten main description to a single line
            desc = compressed["function"].get("description", "")
            if desc and len(desc) > 100:
                compressed["function"]["description"] = desc.splitlines()[0][:100] + "..."
                
            # Compress parameter descriptions
            params = compressed["function"].get("parameters", {})
            properties = params.get("properties", {})
            for prop_name, prop_data in properties.items():
                p_desc = prop_data.get("description", "")
                if p_desc and len(p_desc) > 80:
                    prop_data["description"] = p_desc.splitlines()[0][:80] + "..."
                    
            schemas.append(compressed)
        return schemas

    async def dispatch(self, name: str, kwargs: dict) -> str:
        entry = self._tools.get(name)
        if entry is None:
            return f"Error: unknown tool '{name}'"
        
        # Advanced Parameter Healing / Sanitization Layer
        try:
            schema = entry.get("schema", {})
            func_schema = schema.get("function", {})
            params_schema = func_schema.get("parameters", {})
            props = params_schema.get("properties", {})
            
            # Heal common parameter name confusion: file -> filepath
            if "filepath" in props and "file" in kwargs and "filepath" not in kwargs:
                kwargs["filepath"] = kwargs.pop("file")
            
            # Heal coords parameter name confusion: pattern -> command
            if name == "bash" and kwargs.get("action") == "coords" and "pattern" in kwargs and "command" not in kwargs:
                kwargs["command"] = kwargs.pop("pattern")
            
            # Heal missing start_byte or end_byte in patch_code_range
            if name == "patch_code_range" and "original_text" in kwargs:
                orig_len = len(str(kwargs["original_text"]).encode('utf-8'))
                if "end_byte" in kwargs and "start_byte" not in kwargs:
                    try:
                        kwargs["start_byte"] = int(kwargs["end_byte"]) - orig_len
                    except Exception:
                        pass
                elif "start_byte" in kwargs and "end_byte" not in kwargs:
                    try:
                        kwargs["end_byte"] = int(kwargs["start_byte"]) + orig_len
                    except Exception:
                        pass

            # Heal patches parameter structure inside patch_code_range
            if name == "patch_code_range" and "patches" in kwargs:
                patches = kwargs["patches"]
                import json
                import ast
                parsed_patches = None
                was_string = False
                if isinstance(patches, str):
                    was_string = True
                    try:
                        parsed_patches = ast.literal_eval(patches)
                    except Exception:
                        try:
                            parsed_patches = json.loads(patches)
                        except Exception:
                            pass
                elif isinstance(patches, list):
                    parsed_patches = patches
                
                if isinstance(parsed_patches, list):
                    healed_patches = []
                    for patch in parsed_patches:
                        if isinstance(patch, str):
                            try:
                                patch = ast.literal_eval(patch)
                            except Exception:
                                try:
                                    patch = json.loads(patch)
                                except Exception:
                                    pass
                        if isinstance(patch, dict):
                            # Heal new_text -> replacement
                            if "new_text" in patch and "replacement" not in patch:
                                patch["replacement"] = patch.pop("new_text")
                            # Heal original_text_guard -> original_text
                            if "original_text_guard" in patch and "original_text" not in patch:
                                patch["original_text"] = patch.pop("original_text_guard")
                            healed_patches.append(patch)
                        else:
                            healed_patches.append(patch)
                    
                    if len(healed_patches) > 0:
                        first_patch = healed_patches[0]
                        if isinstance(first_patch, dict) and ("filepath" not in kwargs or not kwargs["filepath"]) and "filepath" in first_patch:
                            kwargs["filepath"] = first_patch["filepath"]
                    
                    if was_string:
                        kwargs["patches"] = json.dumps(healed_patches)
                    else:
                        kwargs["patches"] = healed_patches
            
            for key, prop_schema in props.items():
                # 1. Coerce missing or incorrect "project" parameters to "."
                if key == "project":
                    if key not in kwargs or kwargs[key] != ".":
                        kwargs[key] = "."
                    continue

                if key in kwargs:
                    val = kwargs[key]
                    
                    # 2. Clean up strings: strip pythonic r"..." or r'...' and outer quotes
                    if isinstance(val, str):
                        s = val.strip()
                        if (s.startswith('r"') and s.endswith('"')) or (s.startswith("r'") and s.endswith("'")):
                            s = s[2:-1]
                        elif (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                            s = s[1:-1]
                        kwargs[key] = s
                        val = s
                    
                    # 3. Coerce expected array/list from dict, str, or scalar
                    is_array = False
                    prop_type = prop_schema.get("type")
                    if prop_type == "array":
                        is_array = True
                    elif "anyOf" in prop_schema:
                        for sub_schema in prop_schema["anyOf"]:
                            if sub_schema.get("type") == "array":
                                is_array = True
                                break
                    
                    if is_array:
                        raw_list = []
                        if isinstance(val, dict):
                            raw_list = [k for k, v in val.items() if v]
                        elif isinstance(val, str):
                            if "," in val:
                                raw_list = [item.strip() for item in val.split(",")]
                            else:
                                raw_list = [val]
                        elif val is None:
                            raw_list = []
                        elif isinstance(val, list):
                            raw_list = val
                        else:
                            raw_list = [val]

                        # Heal tree-sitter symbol_types automatically
                        healed_list = []
                        for item in raw_list:
                            if isinstance(item, str):
                                item_lower = item.strip().lower()
                                if item_lower in ("class", "classes"):
                                    healed_list.append("classes")
                                elif item_lower in ("function", "functions", "method", "methods"):
                                    healed_list.append("functions")
                                elif item_lower in ("import", "imports"):
                                    healed_list.append("imports")
                                else:
                                    healed_list.append(item)
                            else:
                                healed_list.append(item)

                        # If symbol_types is empty, default to returning all supported symbols
                        if key == "symbol_types" and not healed_list:
                            healed_list = ["classes", "functions"]

                        kwargs[key] = healed_list
        except Exception:
            pass  # Fall back to original parameters in case of any unexpected healing error

        try:
            result = await entry["fn"](**kwargs)
            return str(result)
        except Exception as exc:
            return f"Error executing '{name}': {exc}"
