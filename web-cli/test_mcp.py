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
        result = await session.list_tools()
        for t in result.tools:
            print(f"Tool: {t.name}, Args: {t.inputSchema}")

asyncio.run(main())
