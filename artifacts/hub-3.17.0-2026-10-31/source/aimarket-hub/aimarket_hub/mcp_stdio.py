"""MCP stdio transport for the local hub, using its existing gateway in process."""

from __future__ import annotations

import json
import os
import sys

import httpx

from aimarket_hub.stdio import serve


async def run(app, *, output=None) -> None:
    app.state.mcp_stdio = True
    headers = {"Accept": "application/json, text/event-stream"}
    # Optional buyer credential, never a CLI argument or protocol result.
    if key := os.environ.get("AIMARKET_MCP_API_KEY", "").strip():
        headers["X-API-Key"] = key
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers=headers,
    ) as client:
        async def dispatch(message):
            response = await client.post("/mcp", json=message)
            response.raise_for_status()
            if session := response.headers.get("mcp-session-id"):
                client.headers["Mcp-Session-Id"] = session
            if response.status_code == 202:
                return None
            # The local gateway returns one SSE event per request.
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    reply = json.loads(line[5:])
                    if message["method"] == "initialize" and "result" in reply:
                        client.headers["MCP-Protocol-Version"] = reply["result"]["protocolVersion"]
                    return reply
            raise RuntimeError("Local MCP gateway returned no message")

        await serve(dispatch, output=output or sys.stdout)
