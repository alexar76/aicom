"""Test installed PyPI distributions with -I, never imports workspace packages."""
import asyncio
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

OUT = Path(__file__).resolve().parent
BASE = Path(sys.prefix)


def package(name, module, version):
    loaded = __import__(module, fromlist=["__file__"])
    path = Path(loaded.__file__).resolve()
    assert path.is_relative_to(BASE), f"Not loaded from clean environment: {path}"
    assert importlib.metadata.version(name) == version
    return {"distribution": name, "version": version, "modulePath": str(path)}


async def live_http():
    from metis.mcp.client import MCPClient
    from metis.mcp.config import MCPServerConfig
    from metis.mcp.sse import MCPSSEClient

    results = []
    for client_type in [MCPClient, MCPSSEClient]:
        client = client_type(MCPServerConfig.from_ecosystem_preset("aimarket-web"))
        try:
            tools = await asyncio.wait_for(client.list_tools(), timeout=45)
            assert len(tools) == 13
            results.append({"client": client_type.__name__, "url": client.config.url,
                            "status": "ok", "toolCount": len(tools), "toolCalls": 0})
        finally:
            await client.close()
    return results


async def installed_stdio():
    from metis.mcp.client import MCPClient
    from metis.mcp.config import MCPServerConfig

    results = []
    for preset, count, name in [("aimarket-oracle-gateway", 36, "list_oracle_capabilities"),
                                 ("aimarket-plugins", 3, "package_capability")]:
        config = MCPServerConfig.from_ecosystem_preset(preset)
        client = MCPClient(config)
        messages = []
        original = client._request
        async def bounded_request(method, params):
            assert method in {"initialize", "tools/list", "tools/call"}
            if method == "tools/call":
                assert params["name"] in {"list_oracle_capabilities", "package_capability"}
            messages.append({"method": method, "params": params})
            return await original(method, params)
        client._request = bounded_request
        try:
            tools = await asyncio.wait_for(client.list_tools(), timeout=30)
            assert len(tools) == count
            args = ({} if name == "list_oracle_capabilities" else {
                "capability_id": "echo@v1", "product_id": "prod-echo", "name": "Release Check",
                "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}}})
            answer = await asyncio.wait_for(client.call_tool(config.tool_prefix + "__" + name, args), timeout=20)
            payload = json.loads(answer)
            if name == "list_oracle_capabilities":
                assert payload["tool_count"] == 35 and len(payload["tools"]) == 35
            else:
                assert payload["mcp_manifest"]["tools"][0]["name"] == "echo-v1"
                command = json.loads(payload["connection_string"])["mcpServers"]["release-check"]["args"]
                assert "-i" in command and "-d" not in command
            results.append({"preset": preset, "command": config.command, "args": config.args,
                            "status": "ok", "toolCount": len(tools), "safeCall": name,
                            "safeCallResult": payload, "messages": messages, "paidCalls": 0})
        finally:
            await client.close()
    return results


def main():
    phase = sys.argv[1]
    result = {"phase": phase, "checkedAt": datetime.now(timezone.utc).isoformat(),
              "isolatedPython": bool(sys.flags.isolated), "environment": str(BASE),
              "packages": [package("aimarket-metis", "metis", "0.2.4")]}
    assert sys.flags.isolated
    if phase == "base-metis":
        assert importlib.util.find_spec("mcp") is None
        result["mcpSdkInstalled"] = False
        with tempfile.TemporaryDirectory(prefix="pypi-metis-help-") as home:
            process = subprocess.run([str(BASE / "bin/metis"), "--help"], cwd=home,
                                     env={"PATH": str(BASE / "bin") + ":/usr/bin:/bin", "HOME": home},
                                     capture_output=True, text=True, timeout=30)
        result["cli"] = {"exitCode": process.returncode, "stdout": process.stdout, "stderr": process.stderr}
        assert process.returncode == 0, process.stderr
        result["liveHttp"] = asyncio.run(live_http())
    elif phase == "integration":
        result["packages"].extend([
            package("aimarket-oracle-gateway", "aimarket_oracle_gateway", "0.3.2"),
            package("aimarket-mcp-packager", "aimarket_mcp_packager", "2.1.2"),
        ])
        from aimarket_mcp_packager.plugin import MCPPlugin
        from aimarket_mcp_packager.packager_core import MCPPackager
        assert MCPPlugin.version == "2.1.2"
        generator = MCPPackager()
        product = generator.package("echo@v1", "prod-echo", "Release Check", "Release check", {"type": "object"})
        dockerfile = generator.generate_dockerfile(product)
        assert "mcp_server.py" in dockerfile and "pip install" in dockerfile
        compile(generator.generate_server_source(product), "published_generated_server.py", "exec")
        result["packagerGenerator"] = {"status": "ok", "pluginVersion": MCPPlugin.version}
        result["stdioIntegration"] = asyncio.run(installed_stdio())
    else:
        raise ValueError("unknown phase")
    result["status"] = "ok"
    (OUT / f"{phase}-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"phase": phase, "status": result["status"], "packages": result["packages"]}))


if __name__ == "__main__":
    main()
