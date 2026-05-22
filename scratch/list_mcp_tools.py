import asyncio
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession
from contextlib import AsyncExitStack

async def main():
    params = StdioServerParameters(command="sh", args=["-c", "./web-cli/.venv/bin/mcp-server-tree-sitter | grep --line-buffered -E '^\\{'"])
    
    try:
        async with AsyncExitStack() as stack:
            transport = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(transport[0], transport[1]))
            await session.initialize()
            result = await session.list_tools()
            print(f"FOUND {len(result.tools)} TOOLS")
            for t in result.tools:
                if t.name in ("get_node_at_position", "run_query", "get_query_template", "find_text", "register_project_tool"):
                    print(f"--- Tool: {t.name} ---")
                    print(t.description)
                    import json
                    print("Args schema:")
                    print(json.dumps(t.inputSchema, indent=2))
                    print()
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
