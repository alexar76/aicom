"""Source for generated stdio relays; no network activity before a tool call."""

SERVER_SOURCE = '''import asyncio
import base64
import json
import os

from jsonschema import Draft202012Validator
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from aimarket_mcp.tools import market_invoke

CONFIG = json.loads(base64.b64decode("__CONFIG_B64__"))
server = Server(CONFIG["name"], version="2.1.2")
validator = Draft202012Validator(CONFIG["tool"]["inputSchema"])


@server.list_tools()
async def list_tools():
    return [Tool.model_validate(CONFIG["tool"])]


@server.call_tool()
async def call_tool(name, arguments):
    if name != CONFIG["tool"]["name"]:
        raise ValueError("Unknown tool")
    validator.validate(arguments)
    result = await market_invoke({
        "capability_id": CONFIG["capability_id"],
        "product_id": CONFIG["product_id"],
        "source_hub": os.environ.get("AIMARKET_SOURCE_HUB", ""),
        "input": arguments,
    })
    return [TextContent(type="text", text=result)]


async def main():
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
'''
