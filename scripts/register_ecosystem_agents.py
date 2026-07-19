#!/usr/bin/env python3
"""Register the REAL ecosystem nodes as Mesh agents (the lottery's participants).

The lottery should be played by actual ecosystem components — the 17 oracles + the hub,
mesh, factory and ACEX — NOT made-up names. Each node gets an EVM wallet DETERMINISTICALLY
bound to its node id (reproducible: same node → same wallet on every run / host), so the
on-chain participant maps 1:1 to a real infrastructure node.

  wallet(node) = keccak256("aicom-ecosystem-node|" + WALLET_SEED + "|" + node_id) → address

Usage:
  MESH_URL=http://127.0.0.1:8095 MESH_ADMIN_TOKEN=… WALLET_SEED=… \
  python3 scripts/register_ecosystem_agents.py
"""
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
from eth_account import Account
from web3 import Web3

MESH = os.environ.get("MESH_URL", "http://127.0.0.1:8095").rstrip("/")
ADMIN = os.environ.get("MESH_ADMIN_TOKEN", "")
SEED = os.environ.get("WALLET_SEED", "aicom-ecosystem")

# The canonical real ecosystem nodes (id, display name, real public endpoint, capabilities).
NODES = [
    ("oracle-platon", "Platon", "https://oracles.modelmarket.dev", ["platon.random@v1", "platon.ask@v1"]),
    ("oracle-chronos", "Chronos", "https://oracles.modelmarket.dev", ["chronos.eval@v1", "chronos.verify@v1"]),
    ("oracle-lattice", "Lattice", "https://oracles.modelmarket.dev", ["lattice.sequence@v1"]),
    ("oracle-murmuration", "Murmuration", "https://oracles.modelmarket.dev", ["murmuration.aggregate@v1"]),
    ("oracle-lumen", "Lumen", "https://oracles.modelmarket.dev", ["lumen.reputation@v1"]),
    ("oracle-colony", "Colony", "https://oracles.modelmarket.dev", ["colony.optimize@v1"]),
    ("oracle-turing", "Turing", "https://oracles.modelmarket.dev", ["turing.bluenoise@v1"]),
    ("oracle-percola", "Percola", "https://oracles.modelmarket.dev", ["percola.threshold@v1", "percola.verify@v1"]),
    ("oracle-fermat", "Fermat", "https://oracles.modelmarket.dev", ["fermat.route@v1", "fermat.verify@v1"]),
    ("oracle-ablation", "Ablation", "https://oracles.modelmarket.dev", ["ablation.cascade@v1", "ablation.verify@v1"]),
    ("oracle-landauer", "Landauer", "https://oracles.modelmarket.dev", ["landauer.audit@v1", "landauer.verify@v1"]),
    ("oracle-sortes", "Sortes", "https://oracles.modelmarket.dev", ["sortes.draw@v1", "sortes.verify@v1"]),
    ("oracle-gauss", "Gauss", "https://oracles.modelmarket.dev", ["gauss.field@v1", "gauss.suggest@v1", "gauss.verify@v1"]),
    ("oracle-aestus", "Aestus", "https://oracles.modelmarket.dev", ["aestus.seal@v1", "aestus.open@v1", "aestus.verify@v1"]),
    ("oracle-betti", "Betti", "https://oracles.modelmarket.dev", ["betti.homology@v1", "betti.distance@v1"]),
    ("oracle-kantor", "Kantor", "https://oracles.modelmarket.dev", ["kantor.transport@v1", "kantor.verify@v1"]),
    ("oracle-fourier", "Fourier", "https://oracles.modelmarket.dev", ["fourier.spectrum@v1", "fourier.verify@v1"]),
    ("hub", "AIMarket Hub", "https://modelmarket.dev", ["routing", "invoke"]),
    ("mesh", "AI Service Mesh", "https://modelmarket.dev", ["discovery", "escrow"]),
    ("factory", "AI-Factory", "https://modeldev.modelmarket.dev", ["build", "publish"]),
    ("acex", "ACEX", "https://modelmarket.dev", ["capital-markets"]),
]


def node_wallet(node_id: str) -> str:
    pk = Web3.keccak(text=f"aicom-ecosystem-node|{SEED}|{node_id}").hex()
    return Account.from_key(pk).address


def register(node_id: str, name: str, endpoint: str, caps: list[str]) -> str:
    wallet = node_wallet(node_id)
    pub = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    att = base64.urlsafe_b64encode(
        hashlib.sha256(f"{name}|{endpoint}|{','.join(sorted(caps))}".encode()).digest()
    ).decode().rstrip("=")
    body = json.dumps({
        "name": name, "endpoint_url": endpoint, "public_key_pem": pub,
        "capabilities": caps, "attestation": att, "evm_address": wallet,
        "source_hub": "aicom-ecosystem",
    }).encode()
    req = urllib.request.Request(
        f"{MESH}/v1/agents", data=body, method="POST",
        headers={"content-type": "application/json", "Authorization": f"Bearer {ADMIN}"},
    )
    try:
        r = json.load(urllib.request.urlopen(req, timeout=12))
        return f"{name:<14} {r.get('status'):<9} {wallet}"
    except urllib.error.HTTPError as e:
        return f"{name:<14} FAILED {e.code} {e.read().decode()[:120]}"


def main() -> None:
    if not ADMIN:
        sys.exit("set MESH_ADMIN_TOKEN")
    print(f"Registering {len(NODES)} real ecosystem nodes at {MESH}")
    for nid, name, ep, caps in NODES:
        print(" ", register(nid, name, ep, caps))


if __name__ == "__main__":
    main()
