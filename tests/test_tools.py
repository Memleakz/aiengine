import pytest

from agent_engine.tools import ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def sample_tool(command: str, count: int = 1) -> str:
    """Run sample tool with a command string."""
    return f"{command} x{count}"


async def no_doc_tool(x: str) -> str:
    return x


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

def test_register_creates_schema():
    reg = ToolRegistry()
    reg.register(sample_tool)
    schemas = reg.get_all_schemas()
    assert len(schemas) == 1
    s = schemas[0]
    assert s["type"] == "function"
    fn = s["function"]
    assert fn["name"] == "sample_tool"
    assert "command" in fn["parameters"]["properties"]
    assert "count" in fn["parameters"]["properties"]


def test_register_required_params():
    reg = ToolRegistry()
    reg.register(sample_tool)
    fn = reg.get_all_schemas()[0]["function"]
    assert "command" in fn["parameters"]["required"]
    assert "count" not in fn["parameters"]["required"]


def test_register_uses_docstring():
    reg = ToolRegistry()
    reg.register(sample_tool)
    fn = reg.get_all_schemas()[0]["function"]
    assert "sample tool" in fn["description"].lower()


def test_register_no_docstring():
    reg = ToolRegistry()
    reg.register(no_doc_tool)
    fn = reg.get_all_schemas()[0]["function"]
    assert fn["description"] == ""


def test_register_type_mapping():
    reg = ToolRegistry()
    reg.register(sample_tool)
    props = reg.get_all_schemas()[0]["function"]["parameters"]["properties"]
    assert props["command"]["type"] == "string"
    assert props["count"]["type"] == "integer"


# ---------------------------------------------------------------------------
# get_all_schemas
# ---------------------------------------------------------------------------

def test_get_all_schemas_empty():
    reg = ToolRegistry()
    assert reg.get_all_schemas() == []


def test_get_all_schemas_multiple():
    reg = ToolRegistry()
    reg.register(sample_tool)
    reg.register(no_doc_tool)
    assert len(reg.get_all_schemas()) == 2


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_known_tool():
    reg = ToolRegistry()
    reg.register(sample_tool)
    result = await reg.dispatch("sample_tool", {"command": "ls"})
    assert "ls" in result


@pytest.mark.asyncio
async def test_execute_with_default_param():
    reg = ToolRegistry()
    reg.register(sample_tool)
    result = await reg.dispatch("sample_tool", {"command": "ls"})
    assert "x1" in result


@pytest.mark.asyncio
async def test_execute_unknown_tool():
    reg = ToolRegistry()
    result = await reg.dispatch("nonexistent", {})
    assert "error" in result.lower()
    assert "nonexistent" in result


@pytest.mark.asyncio
async def test_execute_exception_returns_string():
    async def broken_tool(x: str) -> str:
        """A broken tool."""
        raise ValueError("something went wrong")

    reg = ToolRegistry()
    reg.register(broken_tool)
    result = await reg.dispatch("broken_tool", {"x": "hi"})
    assert "error" in result.lower()
    assert "something went wrong" in result


# ---------------------------------------------------------------------------
# register_mcp_tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_mcp_tool_schema():
    class FakeMCPTool:
        name = "mcp_search"
        description = "Search the DB"
        inputSchema = {  # noqa: N815
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    class FakeSession:
        async def call_tool(self, name, arguments):
            class Content:
                text = f"result for {arguments.get('query')}"
            class Result:
                content = [Content()]
            return Result()

    reg = ToolRegistry()
    reg.register_mcp_tool(FakeMCPTool(), FakeSession())
    schemas = reg.get_all_schemas()
    assert len(schemas) == 1
    fn = schemas[0]["function"]
    assert fn["name"] == "mcp_search"
    assert fn["description"] == "Search the DB"
    assert fn["parameters"] == FakeMCPTool.inputSchema


@pytest.mark.asyncio
async def test_register_mcp_tool_executes():
    class FakeMCPTool:
        name = "mcp_echo"
        description = "Echo"
        inputSchema = {"type": "object", "properties": {}}  # noqa: N815

    class FakeSession:
        async def call_tool(self, name, arguments):
            class Content:
                text = "echoed"
            class Result:
                content = [Content()]
            return Result()

    reg = ToolRegistry()
    reg.register_mcp_tool(FakeMCPTool(), FakeSession())
    result = await reg.dispatch("mcp_echo", {})
    assert "echoed" in result


@pytest.mark.asyncio
async def test_execute_parameter_healing():
    class HealingMCPTool:
        name = "mcp_heal"
        description = "Test Healing"
        inputSchema = {  # noqa: N815
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "pattern": {"type": "string"},
                "symbol_types": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["pattern", "symbol_types"],
        }

    last_args = {}

    class FakeSession:
        async def call_tool(self, name, arguments):
            nonlocal last_args
            last_args = dict(arguments)
            class Content:
                text = "ok"
            class Result:
                content = [Content()]
            return Result()

    reg = ToolRegistry()
    reg.register_mcp_tool(HealingMCPTool(), FakeSession())

    # Dispatch with raw strings, object/dict array mappings, and missing project
    await reg.dispatch("mcp_heal", {
        "pattern": 'r"(my pattern)"',
        "symbol_types": {"functions": True, "classes": False}
    })

    assert last_args["project"] == "."
    assert last_args["pattern"] == "(my pattern)"
    assert last_args["symbol_types"] == ["functions"]

    # Dispatch with single string, comma-separated array coercion, and incorrect project name
    await reg.dispatch("mcp_heal", {
        "project": "incorrect_name",
        "pattern": '"my pattern"',
        "symbol_types": "functions, classes"
    })
    assert last_args["project"] == "."
    assert last_args["pattern"] == "my pattern"
    assert last_args["symbol_types"] == ["functions", "classes"]

    # Dispatch with alternate/singular symbol types to verify plural mapping
    await reg.dispatch("mcp_heal", {
        "pattern": "pattern",
        "symbol_types": ["class", "method"]
    })
    assert last_args["symbol_types"] == ["classes", "functions"]

    # Dispatch with empty symbol_types to verify default fallback
    await reg.dispatch("mcp_heal", {
        "pattern": "pattern",
        "symbol_types": []
    })
    assert last_args["symbol_types"] == ["classes", "functions"]
