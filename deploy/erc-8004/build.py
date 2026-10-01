#!/usr/bin/env python3
"""Build the ERC-8004 registration files served at https://modelmarket.dev/.well-known/erc-8004/.

    python3 deploy/erc-8004/build.py          # writes <slug>.json and agent-registration.json here

Each agent's registration file is what its on-chain agentURI points at (EIP-8004
"registration-v1"). The agentId is only known after `register(agentURI)` is mined, so it is read
from ids.json; until then `registrations` is empty. agent-registration.json is the
endpoint-domain proof: served at https://modelmarket.dev/.well-known/agent-registration.json, it
lists every agent this domain operates.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://modelmarket.dev/.well-known/erc-8004"
REGISTRY = "eip155:8453:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"  # IdentityRegistry, Base mainnet

AGENTS = {
    "aimarket-hub": {
        "name": "AIMarket Hub",
        "description": (
            "Open market hub for agent capabilities: live, signed real-world data (weather, air quality, "
            "sensors) and verifiable computation (randomness, oracles), sold per call by independent "
            "providers over MCP, A2A and x402 (USDC on Base). Every result carries a signed receipt."
        ),
        "services": [
            {"name": "web", "endpoint": "https://modelmarket.dev/"},
            {"name": "MCP", "endpoint": "https://modelmarket.dev/mcp", "version": "2025-06-18"},
            {"name": "A2A", "endpoint": "https://modelmarket.dev/.well-known/agent-card.json"},
        ],
        "x402Support": True,
        "supportedTrust": ["reputation", "crypto-economic"],
    },
    "histor": {
        "name": "HISTOR",
        "description": (
            "Public transparency log for MCP servers. Observes the official MCP registry daily, pins "
            "each server's tool set in an append-only Merkle log and issues signed labels when "
            "definitions change. Ask it about a server before your agent connects; it never contacts "
            "the server you ask about."
        ),
        "services": [
            {"name": "web", "endpoint": "https://histor.modelmarket.dev/"},
            {"name": "A2MCP", "endpoint": "https://modelmarket.dev/a2mcp/histor-check"},
            {"name": "DID", "endpoint": "did:key:z6Mkw1CVxsPj9utYp7VXWEbuuGM9Ev47itwKu1UfKd5ByxR9", "version": "v1"},
        ],
        "x402Support": False,
    },
    "warden": {
        "name": "WARDEN",
        "description": (
            "Open-source firewall for MCP tool definitions. Scans a server's tools/list for prompt "
            "injection, secret requests, exfiltration and hidden Unicode before a host shows them to a "
            "model, with deterministic published rules (version and digest in every verdict) and a "
            "published, reproducible false-positive profile."
        ),
        "services": [
            {"name": "web", "endpoint": "https://warden.modelmarket.dev/"},
            {"name": "A2MCP", "endpoint": "https://modelmarket.dev/a2mcp/warden-scan"},
            {"name": "npm", "endpoint": "https://www.npmjs.com/package/@aimarket/warden"},
        ],
        "x402Support": False,
    },
}


def main() -> None:
    ids_path = os.path.join(HERE, "ids.json")
    ids = json.load(open(ids_path)) if os.path.exists(ids_path) else {}
    domain = []
    for slug, a in AGENTS.items():
        regs = [{"agentId": int(ids[slug]), "agentRegistry": REGISTRY}] if slug in ids else []
        doc = {
            "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
            "name": a["name"],
            "description": a["description"],
            "image": f"{BASE}/{slug}.png",
            "services": a["services"],
            "x402Support": a["x402Support"],
            "active": True,
            "registrations": regs,
        }
        if a.get("supportedTrust"):
            doc["supportedTrust"] = a["supportedTrust"]
        with open(os.path.join(HERE, f"{slug}.json"), "w") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        domain += regs
    with open(os.path.join(HERE, "agent-registration.json"), "w") as f:
        json.dump({"registrations": domain}, f, indent=2)
        f.write("\n")
    print(f"built {len(AGENTS)} registration files; {len(domain)} with an agentId")


if __name__ == "__main__":
    main()
