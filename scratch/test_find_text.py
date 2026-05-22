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
            
            # Register project first
            print("Registering project...")
            reg_res = await session.call_tool("register_project_tool", {
                "name": ".",
                "path": "/home/tobias/dev/Repo/aiengine/src"
            })
            print(f"Register result: {reg_res}")
            
            # Call find_text
            print("Calling find_text...")
            find_res = await session.call_tool("find_text", {
                "project": ".",
                "pattern": "Vanilla Latte",
                "file_pattern": "demosite/index.html"
            })
            print(f"Find result: {find_res}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
