import asyncio
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession
from contextlib import AsyncExitStack
import traceback
import json

async def main():
    params = StdioServerParameters(command="sh", args=["-c", "./web-cli/.venv/bin/mcp-server-tree-sitter | grep --line-buffered -E '^\\{'"])
    
    try:
        async with AsyncExitStack() as stack:
            transport = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(transport[0], transport[1]))
            await session.initialize()
            
            # Register project
            await session.call_tool("register_project_tool", {
                "name": ".",
                "path": "/home/tobias/dev/Repo/aiengine/src"
            })
            
            # Run query
            query = """
            (element
              (start_tag
                (tag_name) @tag (#eq? @tag "div")
                (attribute
                  (attribute_name) @attr (#eq? @attr "class")
                  (quoted_attribute_value) @class_val (#eq? @class_val "\\"opening-hours\\"")
                )
              )
            ) @opening_hours_div
            """
            
            print("Calling run_query...")
            res = await session.call_tool("run_query", {
                "project": ".",
                "file_path": "demosite/index.html",
                "query": query
            })
            print("Type of res:", type(res))
            for c in res.content:
                print("Content:")
                try:
                    data = json.loads(c.text)
                    print(json.dumps(data, indent=2))
                except Exception:
                    print(c.text)
            
    except Exception as e:
        print(f"ERROR: {type(e)}: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
