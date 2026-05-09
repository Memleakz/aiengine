import asyncio
import sys
import os
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession
from contextlib import AsyncExitStack

async def main():
    python_path = sys.executable
    # Filter out non-JSON lines
    params = StdioServerParameters(command="sh", args=["-c", f"{python_path} -m mcp_server_tree_sitter | grep --line-buffered -E '^\\{{'"])
    
    try:
        async with AsyncExitStack() as stack:
            transport = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(transport[0], transport[1]))
            await session.initialize()
            result = await session.list_tools()
            print(f"FOUND {len(result.tools)} TOOLS")
            for t in result.tools:
                print(f"Tool: {t.name}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
