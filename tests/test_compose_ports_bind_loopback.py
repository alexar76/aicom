"""Every published port in every documented compose combination binds to loopback, once.

Compose MERGES `ports` lists across overlay files (append, not replace). On 2026-09-11 the
split overlay — which README.md and docs/running.md hand to every self-hoster — therefore
kept the base `127.0.0.1:9081` and ADDED an unprefixed `9081`: the FastAPI API on 0.0.0.0,
published by Docker as a DNAT rule that a host UFW policy never covers. The author's
comment showed they believed the list was replaced. Same mechanism gave the prod stack two
services on 127.0.0.1:9080. `!override` is the fix; this test is what keeps it fixed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

COMBINATIONS = {
    "base": ["docker-compose.yml"],
    "split": ["docker-compose.yml", "docker-compose.split.yml"],
    "prod": ["docker-compose.yml", "docker-compose.prod.yml"],
}


def _rendered_ports(files: list[str]) -> list[tuple[str, str, str]]:
    cmd = ["docker", "compose"]
    for f in files:
        cmd += ["-f", str(ROOT / f)]
    cmd += ["config", "--format", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env={"PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin"})
    if proc.returncode != 0:
        pytest.skip(f"docker compose config failed here: {proc.stderr.strip()[:200]}")
    # compose may print warnings before the JSON document
    text = proc.stdout[proc.stdout.find("{"):]
    data = json.loads(text)
    out = []
    for name, svc in sorted((data.get("services") or {}).items()):
        for port in svc.get("ports") or []:
            if isinstance(port, str):
                out.append((name, "", port))
            else:
                out.append((name, str(port.get("host_ip") or ""), str(port.get("published") or "")))
    return out


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
@pytest.mark.parametrize("label,files", sorted(COMBINATIONS.items()))
def test_every_published_port_is_loopback_and_unique(label: str, files: list[str]):
    ports = _rendered_ports(files)
    assert ports, f"{label}: no published ports rendered — is the compose file empty?"
    exposed = [(svc, ip, pub) for svc, ip, pub in ports if ip != "127.0.0.1"]
    assert not exposed, (
        f"{label}: these ports are published on all interfaces (Docker DNAT bypasses UFW): "
        f"{exposed}. Prefix with 127.0.0.1: and use `ports: !override` in overlays."
    )
    seen: dict[str, str] = {}
    for svc, _ip, pub in ports:
        assert pub not in seen or seen[pub] == svc, (
            f"{label}: host port {pub} is claimed by both {seen[pub]} and {svc} — "
            f"an overlay appended to the base list instead of replacing it (`!override`)."
        )
        seen[pub] = svc
