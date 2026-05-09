import asyncio
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession
from contextlib import AsyncExitStack

async def main():
    params = StdioServerParameters(command="sh", args=["-c", "npx -y @nendo/tree-sitter-mcp --mcp --quiet | grep --line-buffered -E '^\\{'"])
    async with AsyncExitStack() as stack:
        transport = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(transport[0], transport[1]))
        await session.initialize()
        
        result = await session.call_tool("search_code", arguments={"query": "init_db", "directory": "/home/tobias/dev/Ai_kanban_dev"})
        print(result.content[0].text if result.content else "No output")

asyncio.run(main())
