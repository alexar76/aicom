"""Capture two complete public Hub observations using HISTOR's bounded HTTP reader.

Read-only MCP discovery/initialization/listing. No credentials, tools/call or remote writes.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "histor"))

from histor.mcpclient import USER_AGENT, McpReader
from histor.upgrade_brief import _validate_snapshot

from histor import __version__

URL = "https://modelmarket.dev/mcp"
ALLOWED = {"server/discover", "initialize", "notifications/initialized", "tools/list"}


class AuditedReader(McpReader):
    def __init__(self):
        super().__init__(timeout=30, deadline=90)
        self.events = []

    def _client(self):
        # Do not inherit proxy credentials, authentication or custom certificate env settings.
        return httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                            trust_env=False, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})

    def _post(self, client, pinned, body, **kwargs):
        if body.get("method") not in ALLOWED:
            raise RuntimeError("only discovery, initialization and listing are allowed")
        event = {"request": copy.deepcopy(body)}
        self.events.append(event)
        try:
            message, headers, size = super()._post(client, pinned, body, **kwargs)
            event.update(response=copy.deepcopy(message), decodedBytes=size)
            return message, headers, size
        except Exception as exc:
            # Record the category only; arbitrary transport diagnostics could contain environment data.
            event["errorType"] = type(exc).__name__
            raise


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main():
    for slot in ("baseline", "recheck"):
        if (HERE / f"{slot}.json").exists() or (HERE / f"{slot}-wire.json").exists():
            raise RuntimeError("capture files already exist; preserve them and choose a new evidence directory")
    launch = {
        "transport": "streamable-http", "endpoint": URL,
        "client": {"name": "histor", "version": __version__, "reader": "McpReader"},
        "runtime": {"python": sys.version.split()[0], "httpx": importlib.metadata.version("httpx")},
        "profile": {"authentication": "none", "trustEnvironment": False, "allowPrivate": False,
                    "followRedirects": False, "timeoutSeconds": 30, "deadlineSeconds": 90,
                    "methods": sorted(ALLOWED)},
    }
    for slot in ("baseline", "recheck"):
        reader = AuditedReader()
        observed = reader.list_tools(URL)
        timestamp = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        save(HERE / f"{slot}-wire.json", {"observedAt": timestamp, "status": observed.status,
             "resolvedAddress": observed.address, "pages": observed.pages, "events": reader.events})
        if observed.status != "ok":
            raise RuntimeError("Hub observation was incomplete; retained its wire evidence")
        pages = [event["response"]["result"] for event in reader.events
                 if event["request"]["method"] == "tools/list" and event.get("response", {}).get("result")]
        listed = [tool for page in pages for tool in page["tools"]]
        if listed != observed.tools or not pages or pages[-1].get("nextCursor") is not None:
            raise RuntimeError("full tools do not match the drained raw pages")
        snapshot = {
            "format": "histor.upgrade-observation/v1", "targetId": URL, "status": "ok",
            "observedAt": timestamp, "packageVersion": None,
            "serverName": observed.server_info.get("name"), "serverVersion": observed.server_info.get("version"),
            "protocol": observed.protocol_version, "extrasCoverage": "observed", "launch": launch,
            "tools": observed.tools,
        }
        _validate_snapshot(snapshot)
        save(HERE / f"{slot}.json", snapshot)
        print(json.dumps({"slot": slot, "status": "ok", "protocol": observed.protocol_version,
                          "tools": len(listed), "pages": len(pages), "methods": [e["request"]["method"] for e in reader.events]}))
    sources = [Path(__file__), ROOT / "histor/histor/mcpclient.py", ROOT / "histor/histor/netguard.py"]
    save(HERE / "provenance.json", {
        "mode": "fresh-public-baseline-recheck", "target": URL, "toolCalls": 0, "authentication": "none",
        "historicalMetadataBackfilled": False, "installedPackageVersionKnown": False,
        "sourceHashes": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                         for p in sources],
        "limits": ["Two current observations test observed contract stability, not the original historical upgrade.",
                   "All extra fields are retained; absent extras are observed absence, not reconstructed history."],
    })


if __name__ == "__main__":
    main()
