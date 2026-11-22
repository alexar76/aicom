"""Two stale ARD + AID cases for an outside client, signed like the live manifest.

Runs inside the apex hub container (cwd /app), so the trustManifests are signed by the same
key and code as https://modelmarket.dev/.well-known/ard.json:

    docker exec -i -w /app modelmarket-hub python - --card /tmp/card.json --out /tmp/aid-fixtures < build_fixtures.py

``--card`` is the live MCP Server Card exactly as served (https://modelmarket.dev/mcp/server-card).
Each case is a one-entry ARD manifest at its own path whose only fault is the one it is named for:

- endpoint-mismatch: the card's bytes match the entry's digest and the trustManifest is valid,
  but remotes[] streamable-http url is not the AID record's u (https://modelmarket.dev/mcp).
- card-digest-mismatch: the card is the live card (url = AID u, valid trustManifest), but the
  entry pins the digest of the previous card version (version 1.2.0), so the bytes do not match.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import time
from pathlib import Path

from aimarket_hub import ard
from aimarket_hub.signing import Signer

BASE = "https://modelmarket.dev"
AID_U = BASE + "/mcp"
ROOT = "/interop/aid"


def entry(case: str, digest: str, description: str) -> dict:
    return {
        "description": description,
        "digest": digest,
        "displayName": f"modelmarket.dev (MCP), stale case: {case}",
        "identifier": f"urn:air:modelmarket.dev:mcp:aid-fixture-{case}",
        "type": "application/mcp-server-card+json",
        "url": f"{BASE}{ROOT}/{case}/server-card.json",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    live_bytes = Path(args.card).read_bytes()
    live = json.loads(live_bytes)
    assert ard.stable_bytes(live) == live_bytes, "live card is not in this hub's stable form"
    streamable = [r for r in live["remotes"] if r.get("type") == "streamable-http"]
    assert [r["url"] for r in streamable] == [AID_U], streamable

    signer = Signer(os.environ.get("AIMARKET_SIGNING_KEY_PATH", "data/hub_signing_key"))
    did = ard.did_web(BASE)
    issued = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = Path(args.out)

    # endpoint-mismatch: one field differs from the live card
    em = copy.deepcopy(live)
    for r in em["remotes"]:
        if r.get("type") == "streamable-http":
            r["url"] = f"{BASE}{ROOT}/endpoint-mismatch/mcp"
    em_bytes = ard.stable_bytes(em)
    em_entry = entry("endpoint-mismatch", ard.digest(em_bytes),
                     "Test fixture for ARD + AID clients. The card matches this digest and the trustManifest is "
                     "valid, but its streamable-http remotes[].url is not the u of the _agent.modelmarket.dev AID "
                     "record (https://modelmarket.dev/mcp). Expected result: endpoint mismatch, do not connect.")

    # card-digest-mismatch: the live card, pinned by the digest of the version before it
    previous = dict(live, version="1.2.0")
    dm_entry = entry("card-digest-mismatch", ard.digest(ard.stable_bytes(previous)),
                     "Test fixture for ARD + AID clients. The card's remotes[].url is the AID u and the "
                     "trustManifest is valid, but this digest pins the previous card version (1.2.0) and the card "
                     "served is 1.3.0, so its bytes do not match. Expected result: card digest mismatch, do not "
                     "connect.")

    cases = {"endpoint-mismatch": (em_entry, em_bytes), "card-digest-mismatch": (dm_entry, live_bytes)}
    for case, (e, card_bytes) in cases.items():
        signed = {**e, "trustManifest": ard.sign_trust_manifest(signer, did, ard.subject_of(e), issued)}
        d = out / case
        d.mkdir(parents=True, exist_ok=True)
        (d / "ard.json").write_bytes(ard.stable_bytes({"entries": [signed]}))
        (d / "server-card.json").write_bytes(card_bytes)

    index = {
        "about": "Stale cases for ARD + AID interop testing against modelmarket.dev. Each manifest has one "
                 "MCP entry and exactly one fault. The AID record is _agent.modelmarket.dev (u = "
                 "https://modelmarket.dev/mcp); the healthy case is the live manifest.",
        "issuedAt": issued,
        "cases": [
            {"name": "healthy", "manifest": f"{BASE}/.well-known/ard.json",
             "entry": "urn:air:modelmarket.dev:mcp:gateway", "expected": "digest matches, endpoint matches"},
            {"name": "endpoint-mismatch", "manifest": f"{BASE}{ROOT}/endpoint-mismatch/ard.json",
             "expected": "digest matches, trustManifest valid, remotes[].url != AID u"},
            {"name": "card-digest-mismatch", "manifest": f"{BASE}{ROOT}/card-digest-mismatch/ard.json",
             "expected": "trustManifest valid, remotes[].url == AID u, card bytes != entry digest"},
        ],
    }
    (out / "index.json").write_bytes(ard.stable_bytes(index))
    print("wrote", sorted(str(p.relative_to(out)) for p in out.rglob("*.json")))


if __name__ == "__main__":
    main()
