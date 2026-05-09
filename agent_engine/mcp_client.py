from contextlib import AsyncExitStack

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MCPServerManager:
    def __init__(self, command: str, args: list[str]) -> None:
        self._params = StdioServerParameters(command=command, args=args)
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def connect(self) -> ClientSession:
        transport = await self._exit_stack.enter_async_context(stdio_client(self._params))
        read_stream, write_stream = transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()
        return self._session

    async def disconnect(self) -> None:
        await self._exit_stack.aclose()
