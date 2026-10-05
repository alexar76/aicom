#!/usr/bin/env python3
"""Publish the demand funnel of what modelmarket.dev sells, from sources only its host can read.

For the demand test (scripts/demand_watch.py reads the result on the alerter's host). Every
number is since the test began, our own traffic left out, callers counted, never named:

  - ``x402``: per paid route of the x402 gateway (/x402/<route>), from the apex nginx log —
    price asked (an unpaid POST answered 402), paid and answered (200), refused input (400),
    failed (5xx), and the distinct callers behind each; plus who read the gateway's discovery
    documents (/x402/openapi.json, /.well-known/x402), by client software.
  - ``mcp``: the hub's MCP requests by method and client family (initialize, tools/list,
    tools/call per tool), from its /metrics. Those counters restart with the hub; this file
    keeps the running total across restarts. Scanners' empty probes are in here.
  - ``invocations``: every call of a direct-tool capability that reached the agent through the
    hub (hub.db invocation_stats, read in the hub container): when, which, the outcome, MCP trial
    visitor or credit account, and a 10-hex caller hash — never the caller id.

Our own traffic is the fleet's and the owner's addresses (AICOM_OWN_IPS). The log is read
incrementally (offset and inode kept in AICOM_DEMAND_EXPORT_STATE); a rotation is followed into
access.log.1. Run every 10 minutes (deploy/aicom-demand-export.timer):

    python3 demand_export.py --out /var/www/verify.modelmarket.dev/demand.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from typing import Any

START = "2026-10-05T14:00:00Z"
CAPABILITIES = (
    "x402.authorization.check@v1", "mcp.tools.diff@v1", "gaia.weather.read@v1",
    "gaia.air.read@v1", "atlas.nearest.read@v1", "sortes.draw@v1",
)
# Loopback and non-private defaults only. Extra fleet addresses belong in AICOM_OWN_IPS, not in this file.
DEFAULT_OWN_IPS = (
    "80.209.243.27", "108.165.32.182",
    "162.141.123.165", "212.113.104.129", "82.21.72.167", "95.24.31.225", "127.0.0.1", "::1",
)
DISCOVERY = ("/x402/openapi.json", "/.well-known/x402", "/x402/well-known.json")
_COMBINED = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S+)[^"]*" '
    r'(?P<status>\d{3}) \S+ "[^"]*" "(?P<ua>[^"]*)"')
_LINE = re.compile(r'^aimarket_hub_mcp_requests_total\{(?P<labels>[^}]*)\}\s+(?P<value>[0-9.eE+]+)\s*$')
_LABEL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')
# Runs inside the hub container (its own python and data directory), read-only.
_QUERY = """
import json, sqlite3, sys
start, caps = sys.argv[1], sys.argv[2].split(",")
db = sqlite3.connect("file:/app/data/hub.db?mode=ro", uri=True)
rows = db.execute(
    "select timestamp, capability_id, outcome, consumer_hub from invocation_stats "
    "where timestamp >= ? and capability_id in (%s) order by timestamp" % ",".join("?" * len(caps)),
    [start, *caps]).fetchall()
print(json.dumps(rows[-2000:]))
"""


def _start_ts() -> float:
    return datetime.strptime(START, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()


def client_family(ua: str) -> str:
    """A short, stable name for the client software behind a User-Agent."""
    low = ua.lower()
    for needle, name in (("x402scan", "x402scan"), ("agentcash", "agentcash"), ("x402jp", "x402jp"),
                         ("cdp", "coinbase"), ("coinbase", "coinbase"), ("python-httpx", "python-httpx"),
                         ("python-requests", "python-requests"), ("aiohttp", "aiohttp"),
                         ("node", "node"), ("undici", "node"), ("axios", "node"), ("curl", "curl"),
                         ("go-http", "go"), ("bot", "other-bot"), ("mozilla", "browser")):
        if needle in low:
            return name
    return "other" if ua.strip() and ua != "-" else "none"


def parse_log_line(line: str) -> dict[str, Any] | None:
    m = _COMBINED.match(line)
    if not m:
        return None
    try:
        at = datetime.strptime(m.group("time"), "%d/%b/%Y:%H:%M:%S %z").timestamp()
    except ValueError:
        return None
    return {"ip": m.group("ip"), "at": at, "method": m.group("method"),
            "path": m.group("path").split("?", 1)[0], "status": int(m.group("status")),
            "ua": m.group("ua")}


def fold_x402(state: dict[str, Any], hit: dict[str, Any], own_ips: set[str], start: float) -> None:
    """Count one access-log hit into state["x402"] if it is an outsider's x402 request."""
    if hit["at"] < start or hit["ip"] in own_ips:
        return
    salt = state["salt"]
    caller = hashlib.sha256((salt + hit["ip"]).encode()).hexdigest()[:12]
    path = hit["path"]
    if hit["method"] == "GET" and path in DISCOVERY:
        disc = state.setdefault("discovery", {})
        fam = client_family(hit["ua"])
        disc[fam] = disc.get(fam, 0) + 1
        return
    if hit["method"] != "POST" or not path.startswith("/x402/"):
        return
    route = path[len("/x402/"):].strip("/")
    if not route or "/" in route or len(route) > 40:
        return
    row = state.setdefault("routes", {}).setdefault(route, {"quoted": 0, "paid": 0, "refused": 0,
                                                           "failed": 0, "callers": []})
    kind = {402: "quoted", 200: "paid", 400: "refused"}.get(hit["status"])
    if kind is None and hit["status"] >= 500:
        kind = "failed"
    if kind is None:
        return
    row[kind] += 1
    if caller not in row["callers"]:
        row["callers"].append(caller)


def read_log(state: dict[str, Any], path: str, own_ips: set[str], start: float) -> int:
    """Fold every new line of the access log (and of its rotated copy) into state."""
    cursor = state.setdefault("cursor", {})
    try:
        st = os.stat(path)
    except OSError:
        return 0
    files = []
    if cursor.get("inode") == st.st_ino and st.st_size >= cursor.get("offset", 0):
        files.append((path, cursor.get("offset", 0)))
    else:
        rotated = path + ".1"
        try:
            if cursor.get("inode") and os.stat(rotated).st_ino == cursor["inode"]:
                files.append((rotated, cursor.get("offset", 0)))
        except OSError:
            pass
        files.append((path, 0))
    lines = 0
    for name, offset in files:
        with open(name, "rb") as fh:
            fh.seek(offset)
            for raw in fh:
                lines += 1
                # Most of this host's log is other sites; only these lines need parsing.
                if b"/x402/" not in raw and b"/.well-known/x402" not in raw:
                    continue
                hit = parse_log_line(raw.decode("utf-8", "replace"))
                if hit:
                    fold_x402(state["x402"], hit, own_ips, start)
            end = fh.tell()
        if name == path:
            cursor.update({"inode": st.st_ino, "offset": end})
    return lines


def mcp_requests(text: str) -> dict[str, dict[str, int]]:
    """{method or 'tools/call:<tool>': {client family: count}} from a Prometheus text page."""
    out: dict[str, dict[str, int]] = {}
    for line in text.splitlines():
        m = _LINE.match(line.strip())
        if not m:
            continue
        labels = dict(_LABEL.findall(m.group("labels")))
        method = labels.get("method") or "other"
        key = f"tools/call:{labels.get('tool') or 'other'}" if method == "tools/call" else method
        fam = (labels.get("client") or "unknown")[:48]
        out.setdefault(key[:80], {})
        out[key[:80]][fam] = out[key[:80]].get(fam, 0) + int(float(m.group("value")))
    return out


def fold_mcp(state: dict[str, Any], raw: dict[str, dict[str, int]]) -> None:
    """Running totals since the first look, across hub restarts (a counter that fell restarted)."""
    last = state.setdefault("last", {})
    total = state.setdefault("total", {})
    first_look = "seen" not in state
    state["seen"] = True
    for key, per_family in raw.items():
        for fam, value in per_family.items():
            before = last.get(key, {}).get(fam)
            last.setdefault(key, {})[fam] = value
            if first_look:
                continue      # the baseline: what the counters held before the test watched
            # A new family or a counter that fell (the hub restarted) counts from zero.
            delta = value if before is None or value < before else value - before
            if delta > 0:
                total.setdefault(key, {})[fam] = total.get(key, {}).get(fam, 0) + delta


def invocations(container: str) -> list[dict[str, str]]:
    """Direct-tool capability calls through the hub since START, callers hashed."""
    out = subprocess.run(["docker", "exec", "-i", container, "python3", "-", START, ",".join(CAPABILITIES)],
                         input=_QUERY, capture_output=True, text=True, timeout=60, check=True)
    rows = []
    for at, capability, outcome, consumer in json.loads(out.stdout or "[]"):
        consumer = str(consumer or "")
        kind = consumer.split(":", 1)[0] if ":" in consumer else "other"
        rows.append({"at": str(at), "capability": str(capability), "outcome": str(outcome or ""),
                     "caller": kind if kind in {"sandbox", "account"} else "other",
                     "who": hashlib.sha256(consumer.encode()).hexdigest()[:10]})
    return rows


def public(state: dict[str, Any], calls: list[dict[str, str]], now: float) -> dict[str, Any]:
    routes = {r: {k: v for k, v in row.items() if k != "callers"} | {"callers": len(row["callers"])}
              for r, row in sorted(state["x402"].get("routes", {}).items())}
    return {
        "generated_at": datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "since": START,
        "x402": {"routes": routes, "discovery": state["x402"].get("discovery", {})},
        "mcp": state["mcp"].get("total", {}),
        "invocations": calls,
        # Kept for readers of the first version of this file (scripts/demand_watch.py).
        "tools_call": {k.split(":", 1)[1]: v for k, v in state["mcp"].get("total", {}).items()
                       if k.startswith("tools/call:")},
        "notes": "ours left out (fleet and owner addresses; credit accounts are hashed, the reader "
                 "drops ours); mcp counts include scanners' empty probes; invocations reached the agent",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--out", required=True)
    parser.add_argument("--log", default=os.environ.get("AICOM_NGINX_LOG", "/var/log/nginx/access.log"))
    parser.add_argument("--metrics", default=os.environ.get("AICOM_HUB_METRICS", "http://127.0.0.1:9083/metrics"))
    parser.add_argument("--hub-container", default=os.environ.get("AICOM_HUB_CONTAINER", "modelmarket-hub"))
    parser.add_argument("--state", default=os.environ.get("AICOM_DEMAND_EXPORT_STATE",
                                                          "/var/lib/aicom-demand/state.json"))
    args = parser.parse_args(argv)
    own_ips = set(DEFAULT_OWN_IPS) | {i.strip() for i in os.environ.get("AICOM_OWN_IPS", "").split(",") if i.strip()}
    try:
        with open(args.state, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}
    state.setdefault("x402", {}).setdefault("salt", secrets.token_hex(16))
    state.setdefault("mcp", {})
    read_log(state, args.log, own_ips, _start_ts())
    try:
        req = urllib.request.Request(args.metrics, headers={"User-Agent": "aicom-demand-export/2"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            fold_mcp(state["mcp"], mcp_requests(resp.read(5_000_000).decode("utf-8", "replace")))
    except Exception as exc:
        print(f"metrics unreadable: {type(exc).__name__}", file=sys.stderr)
    try:
        calls = invocations(args.hub_container)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        print(f"invocations unreadable: {type(exc).__name__}", file=sys.stderr)
        calls = []
    os.makedirs(os.path.dirname(args.state), exist_ok=True)
    tmp_state = args.state + ".tmp"
    fd = os.open(tmp_state, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp_state, args.state)
    doc = public(state, calls, time.time())
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    os.chmod(tmp, 0o644)
    os.replace(tmp, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
