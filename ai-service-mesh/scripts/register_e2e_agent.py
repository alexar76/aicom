#!/usr/bin/env python3
"""Register the local real agent with mesh (for infra smoke tests)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

MESH_API = os.environ.get("MESH_API_URL", "http://127.0.0.1:8090").rstrip("/")
MESH_ADMIN = os.environ.get("MESH_ADMIN_TOKEN", "mesh-local-admin")
REAL_AGENT = os.environ.get("MESH_REAL_AGENT_URL", "http://127.0.0.1:8091").rstrip("/")


def main() -> int:
    key = ed25519.Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    caps = ["research", "summarize"]
    name = "E2E Real Agent"
    att = base64.urlsafe_b64encode(
        hashlib.sha256(f"{name}|{REAL_AGENT}|{','.join(sorted(caps))}".encode()).digest()
    ).decode().rstrip("=")
    body = {
        "name": name,
        "endpoint_url": REAL_AGENT,
        "public_key_pem": pub,
        "capabilities": caps,
        "attestation": att,
        "product_id": "",
        "capability_id": "",
        "source_hub": "local",
    }
    req = urllib.request.Request(
        f"{MESH_API}/v1/agents",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MESH_ADMIN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            agent = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(e.read().decode(), file=sys.stderr)
        return 1
    if agent.get("status") != "verified":
        print("agent not verified:", agent, file=sys.stderr)
        return 1
    print(json.dumps(agent, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
