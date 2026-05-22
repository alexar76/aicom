#!/usr/bin/env python3
"""Generate reference test vectors for AIMarket Protocol v2.

Uses a deterministic test keypair. DO NOT USE THESE KEYS IN PRODUCTION.
"""

import base64
import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Deterministic test keypair (ed25519 test vector seed from RFC 8032)
SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)
priv = Ed25519PrivateKey.from_private_bytes(SEED)
pub = priv.public_key()
PUBLIC_KEY_BYTES = pub.public_bytes_raw()
PUBLIC_KEY_HEX = PUBLIC_KEY_BYTES.hex()
PUBLIC_KEY_B64 = base64.b64encode(PUBLIC_KEY_BYTES).decode()

print(f"Public key (hex):  {PUBLIC_KEY_HEX}")
print(f"Public key (b64):  {PUBLIC_KEY_B64}")


def sign_bytes(data: bytes) -> bytes:
    return priv.sign(data)


def sign_canonical(canonical: str) -> str:
    sig = sign_bytes(canonical.encode())
    return base64.b64encode(sig).decode()


def sign_manifest(manifest: dict) -> dict:
    canonical = (
        f"capabilities_count:{manifest['capabilities_count']}"
        f"|generated_at:{manifest['generated_at']}"
        f"|protocol_version:{manifest['protocol_version']}"
    )
    sig_b64 = sign_canonical(canonical)
    manifest["signature"] = {
        "algorithm": "ed25519",
        "public_key": PUBLIC_KEY_B64,
        "value": sig_b64,
    }
    print(f"\nManifest canonical string: {canonical}")
    print(f"Manifest signature: {sig_b64}")
    return manifest


def sign_receipt(receipt: dict) -> dict:
    canonical = (
        f"nonce:{receipt['nonce']}"
        f"|product_id:{receipt['product_id']}"
        f"|capability_id:{receipt['capability_id']}"
        f"|price_usd:{receipt['price_usd']}"
        f"|timestamp:{receipt['timestamp']}"
    )
    sig_b64 = sign_canonical(canonical)
    receipt["signature"] = {
        "algorithm": "ed25519",
        "value": sig_b64,
    }
    print(f"\nReceipt canonical string: {canonical}")
    print(f"Receipt signature: {sig_b64}")
    return receipt


def sign_federation_announce(msg: dict) -> dict:
    canonical = (
        f"hub_url:{msg['hub_url']}"
        f"|well_known_url:{msg['well_known_url']}"
        f"|capabilities_count:{msg.get('capabilities_count', 0)}"
    )
    sig_b64 = sign_canonical(canonical)
    msg["signature"] = {
        "algorithm": "ed25519",
        "value": sig_b64,
    }
    print(f"\nAnnounce canonical string: {canonical}")
    print(f"Announce signature: {sig_b64}")
    return msg


# ── Well-Known ────────────────────────────────────────────────
well_known = {
    "name": "Test AI Hub",
    "protocol_versions": ["v1", "v2"],
    "hub_version": "2.0.0",
    "mcp_endpoint": "https://test-hub.example.com/ai-market/mcp",
    "manifest_url": "https://test-hub.example.com/ai-market/manifest",
    "products_count": 3,
    "capabilities_count": 5,
    "federated_capabilities_count": 12,
    "supported_chains": ["base"],
    "supported_tokens": ["USDT"],
    "signer_public_key": PUBLIC_KEY_B64,
    "federation": {
        "crawl_interval_s": 3600,
        "routing_fee_bps": 100,
        "min_trust_score": 0.3,
        "seed_list": [],
    },
    "peers": [],
}

with open("well-known.json", "w") as f:
    json.dump(well_known, f, indent=2)

# ── Manifest ──────────────────────────────────────────────────
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
manifest = {
    "protocol_version": "v1",
    "generated_at": now,
    "base_url": "https://test-hub.example.com",
    "products_count": 3,
    "capabilities_count": 5,
    "tools": [
        {
            "name": "prod-001.translate.multi@v2",
            "description": "Translate text to multiple locales",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "locales": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "translations": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    }
                },
            },
            "price_per_call_usd": 0.40,
            "p50_latency_ms": 8100,
            "success_rate_30d": 0.97,
            "product_id": "prod-001",
            "capability_id": "translate.multi@v2",
        }
    ],
}
manifest = sign_manifest(manifest)

with open("manifest-signed.json", "w") as f:
    json.dump(manifest, f, indent=2)

# ── Receipt ───────────────────────────────────────────────────
receipt = {
    "nonce": "rcpt_test001",
    "product_id": "prod-001",
    "capability_id": "translate.multi@v2",
    "price_usd": 0.40,
    "latency_ms": 8100,
    "success": True,
    "channel_id": "ch_test001",
    "timestamp": now,
}
receipt = sign_receipt(receipt)

with open("receipt-signed.json", "w") as f:
    json.dump(receipt, f, indent=2)

# ── Federation Announce ───────────────────────────────────────
announce = {
    "hub_url": "https://test-hub.example.com",
    "well_known_url": "https://test-hub.example.com/.well-known/ai-market.json",
    "capabilities_count": 5,
    "hub_name": "Test AI Hub",
    "signer_public_key": PUBLIC_KEY_B64,
}
announce = sign_federation_announce(announce)

with open("federation-announce-signed.json", "w") as f:
    json.dump(announce, f, indent=2)

print("\n✅ All test vectors generated.")
print(f"Files written to: test-vectors/")
