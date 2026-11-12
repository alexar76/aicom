"""MCP tool lockfile (https://crawlcheck.io/spec/mcp-lockfile): pin the tools you approved, refuse a server whose tools changed.
A tool's hash is sha256 of the canonical JSON of {name, description, inputSchema, annotations}; the list hash is sha256 of the
sorted tool hashes joined by newlines. No network, no key: the same arithmetic the server uses."""
import hashlib

from .verify import canon


def _h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def lock_tool_hash(tool):
    t = tool or {}
    schema = t.get("inputSchema") if t.get("inputSchema") is not None else t.get("input_schema")
    return _h(canon({"name": t.get("name"), "description": t.get("description"), "inputSchema": schema, "annotations": t.get("annotations")}))


def lock_from_tools(tools):
    rows = [{"name": str((t or {}).get("name") or "")[:120], "sha256": lock_tool_hash(t)} for t in (tools or [])[:300]]
    rows.sort(key=lambda r: (r["name"], r["sha256"]))
    return {"tools": rows, "tools_sha256": _h("\n".join(sorted(r["sha256"] for r in rows))), "count": len(rows)}


def check_lock(lock, tools):
    """Compare a lockfile with the tools a server lists now. Anything added, removed or changed -> decision "block"."""
    now = lock_from_tools(tools)
    was = {r["name"]: r["sha256"] for r in (lock or {}).get("tools", [])}
    cur = {r["name"]: r["sha256"] for r in now["tools"]}
    added = [n for n in cur if n not in was]
    removed = [n for n in was if n not in cur]
    modified = [n for n in cur if n in was and was[n] != cur[n]]
    same = (lock or {}).get("tools_sha256") == now["tools_sha256"] and not (added or removed or modified)
    return {"verdict": "unchanged" if same else "changed", "decision": "connect" if same else "block",
            "approved_tools_sha256": (lock or {}).get("tools_sha256", ""), "current_tools_sha256": now["tools_sha256"],
            "added": added, "removed": removed, "modified": modified}
