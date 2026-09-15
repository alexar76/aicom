#!/usr/bin/env python3
"""Which public URL hits which fleet server.

Load tests are not one box. Factory, oracles, Metis/SKOPOS and the
hub-lab are separate Docker daemons, disks and nginx edges. A 5xx on Pulse does
not tell you anything about Metis.

Never print IP addresses. Identify boxes by SSH alias and public hostname.
``--check-dns`` only says OK / DRIFT (same-box vs not).

Usage:
    python3 scripts/load/topology.py
    python3 scripts/load/topology.py --check-dns
    python3 scripts/load/topology.py --markdown
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys

# SSH aliases: ~/.ssh/config (factory key). Same split as scripts/llm_fleet.yaml.

SERVERS = (
    {
        "id": "factory",
        "ssh": "my-vps",
        "label": "Factory host",
        "repo": "/root/claudecode/aicom",
    },
    {
        "id": "oracles",
        "ssh": "admin-vps",
        "label": "Oracles host",
        "repo": "/root/aicom",
    },
    {
        "id": "metis",
        "ssh": "skopos.modelmarket.dev",
        "label": "Metis + SKOPOS (same box as not-my-vps)",
        "repo": "/opt/metis",
    },
    {
        "id": "hub-lab",
        "ssh": "competing-lab",
        "label": "Hub lab / Signal Hunt",
        "repo": "/opt/aicom",
    },
)

# module_id, public origin, path used in locust, server id, locust mix
MODULES = (
    ("factory-api", "https://magic-ai-factory.com", "/api/health", "factory", "core"),
    ("factory-html", "https://magic-ai-factory.com", "/", "factory", "core"),
    ("argus", "https://magic-ai-factory.com", "/arena", "factory", "core"),
    ("hub", "https://modelmarket.dev", "/ai-market/v2/health", "factory", "core"),
    ("hub-uni", "https://uni.modelmarket.dev", "/ai-market/v2/health", "factory", "off"),
    ("mesh", "https://service-mesh.modelmarket.dev", "/health", "factory", "core"),
    ("monitor-live", "https://monitor.modelmarket.dev", "/api/health", "factory", "core"),
    ("monitor-uni", "https://monitor-uni.modelmarket.dev", "/", "factory", "off"),
    ("pulse", "https://pulse.modelmarket.dev", "/pulse/", "factory", "core"),
    ("pulse-factory", "https://magic-ai-factory.com", "/pulse/", "factory", "core"),
    ("atlas", "https://atlas.modelmarket.dev", "/", "factory", "fleet"),
    ("themis", "https://themis.modelmarket.dev", "/health", "factory", "fleet"),
    ("verify", "https://verify.modelmarket.dev", "/", "factory", "fleet"),
    ("forge", "https://forge.modelmarket.dev", "/", "factory", "fleet"),
    ("gaia", "https://iot.modelmarket.dev", "/", "oracles", "fleet"),
    ("oracles", "https://oracles.modelmarket.dev", "/health", "oracles", "fleet"),
    ("platon", "https://oracles.modelmarket.dev", "/platon/umbral/", "oracles", "fleet"),
    ("lottery", "https://lottery.modelmarket.dev", "/", "oracles", "fleet"),
    ("momus", "https://momus.modelmarket.dev", "/health", "oracles", "fleet"),
    ("logos", "https://logos.modelmarket.dev", "/", "oracles", "fleet"),
    ("basanos", "https://basanos.modelmarket.dev", "/health", "oracles", "off"),
    ("metis", "https://metis.modelmarket.dev", "/health", "metis", "fleet"),
    ("skopos", "https://skopos.modelmarket.dev", "/health", "metis", "fleet"),
    ("hunt", "https://hunt.modelmarket.dev", "/", "hub-lab", "off"),
)

# Heavy POSTs — same hosts as the matching read module; tokens live on that host.
HEAVY = (
    ("mesh POST /v1/tasks", "mesh", "factory", "MESH_API_TOKEN on factory .env"),
    ("argus POST /ask", "argus", "factory", "ARGUS_HTTP_TOKEN in argus container on my-vps"),
    ("hub POST /ai-market/v2/invoke", "hub", "factory", "sandbox visitor or payment channel on factory hub"),
    ("metis POST /v1/verify", "metis", "metis", "public fast-route; LLM on Metis host"),
    ("factory pipeline create", "factory-api", "factory", "aicom-app-1 on my-vps — KI-3 risk"),
)


def _by_id() -> dict[str, dict]:
    return {s["id"]: s for s in SERVERS}


def _hostname(url_or_host: str) -> str:
    return url_or_host.split("://", 1)[-1].split("/", 1)[0]


def resolve(host: str) -> set[str]:
    name = _hostname(host)
    try:
        return {ai[4][0] for ai in socket.getaddrinfo(name, 443, type=socket.SOCK_STREAM)}
    except OSError:
        return set()


def ssh_hostname(alias: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["ssh", "-G", alias],
            text=True,
            timeout=8,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    for line in out.splitlines():
        if line.startswith("hostname "):
            return line.split(None, 1)[1].strip()
    return None


def lines(markdown: bool = False) -> list[str]:
    out: list[str] = []
    if markdown:
        out.append("## Servers")
        out.append("")
        out.append("| id | SSH | What runs there |")
        out.append("|---|---|---|")
        for s in SERVERS:
            out.append(f"| `{s['id']}` | `{s['ssh'] or '—'}` | {s['label']} |")
        out.append("")
        out.append("## Modules in the Locust mix")
        out.append("")
        out.append("| Module | Origin | Path | Server | Mix |")
        out.append("|---|---|---|---|---|")
        for mid, origin, path, sid, mix in MODULES:
            out.append(f"| {mid} | {origin} | `{path}` | `{sid}` | {mix} |")
        out.append("")
        out.append("## Heavy POSTs (which box they actually hit)")
        out.append("")
        out.append("| Call | Module | Server | Credential |")
        out.append("|---|---|---|---|")
        for name, mid, sid, cred in HEAVY:
            out.append(f"| `{name}` | {mid} | `{sid}` | {cred} |")
        return out

    out.append("=== Fleet topology (public) ===")
    out.append("Load is split across hosts. Failures are per-server, not 'the ecosystem'.")
    out.append("Boxes are named by SSH alias / public hostname — no addresses.")
    out.append("")
    for s in SERVERS:
        mods = [m[0] for m in MODULES if m[3] == s["id"] and m[4] != "off"]
        ssh = s["ssh"] or "no-ssh"
        out.append(f"  {s['id']:<10} ssh={ssh:<24} {s['label']}")
        out.append(f"             modules: {', '.join(mods)}")
    out.append("")
    out.append("  module            mix     server     origin")
    for mid, origin, path, sid, mix in MODULES:
        if mix == "off":
            continue
        out.append(f"  {mid:<17} {mix:<7} {sid:<10} {origin}{path}")
    out.append("")
    out.append("  heavy POST                              server")
    for name, _mid, sid, cred in HEAVY:
        out.append(f"  {name:<40} {sid:<10} {cred}")
    return out


def check_dns() -> int:
    """Same-box check: public names for one server must share an address set.

    Does not print addresses.
    """
    servers = _by_id()
    rc = 0
    print("=== DNS same-box check (no addresses) ===")
    grouped: dict[str, list[str]] = {}
    for _mid, origin, _path, sid, _mix in MODULES:
        grouped.setdefault(sid, [])
        host = _hostname(origin)
        if host not in grouped[sid]:
            grouped[sid].append(host)

    for sid, hosts in grouped.items():
        ssh = servers[sid].get("ssh")
        ref_host = ssh_hostname(ssh) if ssh else hosts[0]
        ref = resolve(ref_host) if ref_host else resolve(hosts[0])
        for host in hosts:
            got = resolve(host)
            ok = bool(ref) and bool(got) and got == ref
            if not ok:
                rc = 1
            mark = "OK" if ok else "DRIFT"
            via = f"ssh={ssh}" if ssh else "own-host"
            print(f"  {mark:<6} {host:<36} server={sid:<10} {via}")
    return rc


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--markdown", action="store_true")
    p.add_argument("--check-dns", action="store_true")
    args = p.parse_args()
    if args.check_dns:
        return check_dns()
    sys.stdout.write("\n".join(lines(markdown=args.markdown)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
