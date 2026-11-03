import json, sys
import histor
from histor.mcpclient import McpReader
out = {"histor": histor.__version__, "reads": {}}
for url in ("https://mcp.quotewise.io/", "https://mcp.kaiku.tech/mcp"):
    o = McpReader(timeout=20).list_tools(url)
    d = o.__dict__ if hasattr(o, "__dict__") else {}
    out["reads"][url] = {k: d.get(k) for k in ("status", "detail", "protocol_version", "protocolVersion") if k in d}
    tools = d.get("tools") or []
    out["reads"][url]["tools"] = len(tools) if isinstance(tools, list) else None
print(json.dumps(out))
