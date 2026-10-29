"""Official SDK probes of local Node implementations, with disposable homes."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
NODE = "/Users/alex/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
CASES = [
    ("domain-rails", ["domain-kit/bin/domain-rails.mjs", "mcp"]),
    ("warden-atomic-example", ["warden/examples/atomic-screen-server.mjs"]),
    ("warden-local", ["warden/dist/mcp-server.js"]),
    ("argus-local", ["argus/dist/index.js", "mcp"]),
]


async def main():
    results = []
    for name, args in CASES:
        result = {"case": name, "toolCalls": 0, "checkedAt": datetime.now(timezone.utc).isoformat()}
        with tempfile.TemporaryDirectory(prefix="ecosystem-mcp-local-") as home:
            command = [str(ROOT / args[0]), *args[1:]]
            env = {"HOME": home, "PATH": str(Path(NODE).parent) + ":/usr/bin:/bin"}
            if name == "argus-local":
                config = Path(home) / "argus.config.json"
                config.write_text(json.dumps({"mcp": {"servers": [], "catalogs": []}}))
                env["ARGUS_CONFIG"] = str(config)
                result["configuration"] = "isolated empty MCP client list; no operator config"
            params = StdioServerParameters(command=NODE, args=command, cwd=home,
                                          env=env)
            try:
                async with asyncio.timeout(30):
                    async with stdio_client(params) as (reader, writer):
                        async with ClientSession(reader, writer) as client:
                            init = await client.initialize()
                            tools = (await client.list_tools()).tools
                            for tool in tools:
                                Draft202012Validator.check_schema(tool.inputSchema)
                            result.update(status="ok", serverInfo=init.serverInfo.model_dump(),
                                          protocol=init.protocolVersion,
                                          tools=[tool.model_dump() for tool in tools])
            except Exception as exc:
                result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        print(name, result["status"], len(result.get("tools", [])), result.get("error", ""))
        results.append(result)
    (OUT / "local-stdio-probes.json").write_text(json.dumps(results, indent=2) + "\n")
    assert all(result["status"] == "ok" for result in results)


if __name__ == "__main__":
    asyncio.run(main())
