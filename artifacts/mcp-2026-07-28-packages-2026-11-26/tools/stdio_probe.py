"""stdio_probe.py LABEL COMMAND [ARGS...] — speak both MCP eras to one stdio server, print one line.

Handshake era: initialize (2025-06-18 asked) -> notifications/initialized -> tools/list.
2026-07-28: server/discover and tools/list with per-request _meta, on a fresh process, no handshake.
"""
import json, select, subprocess, sys, time

META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "stdio-probe", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def talk(cmd, messages, wait=30):
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    out = {}
    try:
        for m in messages:
            p.stdin.write(json.dumps(m) + "\n"); p.stdin.flush()
            if "id" not in m:
                continue
            end = time.time() + wait
            while time.time() < end:
                if not select.select([p.stdout], [], [], 0.5)[0]:
                    if p.poll() is not None:
                        break
                    continue
                line = p.stdout.readline()
                if not line:
                    break
                try:
                    reply = json.loads(line)
                except ValueError:
                    continue
                if reply.get("id") == m["id"]:
                    out[m["id"]] = reply
                    break
    finally:
        p.stdin.close(); p.terminate()
        try:
            p.wait(5)
        except Exception:
            p.kill()
    return out


label, cmd = sys.argv[1], sys.argv[2:]
old = talk(cmd, [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                                   "clientInfo": {"name": "stdio-probe", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
])
new = talk(cmd, [
    {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": META}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": META}},
])
init = (old.get(1) or {}).get("result") or {}
found = (new.get(1) or {}).get("result") or {}
lt = [t["name"] for t in ((old.get(2) or {}).get("result") or {}).get("tools", [])]
mt = ((new.get(2) or {}).get("result") or {}).get("tools", [])
same = ((old.get(2) or {}).get("result") or {}).get("tools") == mt and bool(mt)
print(label, "| handshake", init.get("protocolVersion"), init.get("serverInfo"),
      "| discover", found.get("supportedVersions") or (new.get(1) or {}).get("error"),
      found.get("_meta", {}).get("io.modelcontextprotocol/serverInfo"), found.get("resultType"),
      "| tools", len(lt), "identical in both eras" if same else "DIFFER OR MISSING")
sys.exit(0 if same and "2026-07-28" in (found.get("supportedVersions") or []) else 1)
