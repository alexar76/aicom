#!/usr/bin/env python3
"""Express one HISTOR observation as an evidence record (narko4u/evidence-record-spec 0.1.0), after checking
the observation's place in HISTOR's log the way any outsider can.

    python3 histor_evidence_record.py npm:@agentskit/mcp out/

What it checks, with public data only (https://histor.modelmarket.dev, no account):
  1. the newest co-signed checkpoint: the log's Ed25519 note signature under its published vkey, and each
     witness cosignature (c2sp.org/tlog-cosignature) under the witness keys pinned below;
  2. the newest "tool-set-observation" label for the package that sits under that checkpoint: its RFC 9162
     inclusion proof leads to the checkpoint's root (leaf = SHA-256(0x00 || RFC 8785 bytes of the label)).
Only then does it write:
  anchor.json            the checkpoint note, the label, the proof: everything a third party needs to redo 1-2
  record-as-published.json   source "sandbox", engines ["sandbox"]: the spec's engine table makes the sandbox
                         SELF custody, so the record is capped at E2
  record-operator-custody.json   the same observation, with the sandbox's operator (HISTOR, not the package's
                         publisher) named as external_authority and the label as the record of that party
Requires `cryptography` (Ed25519). Prints the checks.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HISTOR = "https://histor.modelmarket.dev"
LOG_VKEY = "histor.modelmarket.dev/log+ad3ca066+AfXpkWqXVW93sChXnhKsNzvGLTFAAredl1jLlEjbr4wU"
# Witness keys as each witness publishes them (same pins as hestia-agents/agents/histor-witnessed, 2026-11-19).
WITNESS_VKEYS = [
    "witness.stagemole.eu+67f7aea0+BEqSG3yu9YrmcM3BHvQYTxwFj3uSWakQepafafpUqklv",
    "markovianprotocol.com/witness+41b8827f+BJKLl8rBYM0oUxSaWh9rjTldTprEpYj/SWVIGgacA9XC",
    "staging.witness.transparency.goog/ring-any-bells+2e1a8dc9+BG5JTpLc3FJtwzgh1Uv+Qelz9qeOH2bfWjS1s0s+y4rL",
    "crawlcheck.io/witness+f6b056e2+BCYE6WcaJVekqxEETT9IF/pKvxP7yZM6dLW65YDWpQpE",
    "witness.gdbsecurity.com+a1398f73+BAbIijGonVIk3ikDac+KKlSm1ELHOzcddhjjB6zB4BNf",
    "witness.navigli.sunlight.geomys.org+a3e00fe2+BNy/co4C1Hn1p+INwJrfUlgz7W55dSZReusH/GhUhJ/G",
]
UA = {"User-Agent": "histor-evidence-record/0.1 (+https://histor.modelmarket.dev)"}


def get(path: str, text: bool = False):
    with urllib.request.urlopen(urllib.request.Request(HISTOR + path, headers=UA), timeout=60) as r:
        body = r.read().decode("utf-8")
    return body if text else json.loads(body)


def parse_vkey(vkey: str):
    name, khash, b64 = vkey.split("+", 2)
    raw = base64.b64decode(b64)
    if hashlib.sha256(name.encode() + b"\n" + raw).digest()[:4].hex() != khash:
        raise ValueError("key hash mismatch for " + name)
    return name, bytes.fromhex(khash), raw[0], raw[1:]


def verify(key: bytes, sig: bytes, msg: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(sig, msg)
        return True
    except InvalidSignature:
        return False


def check_checkpoint(note: str):
    body, sigs = note.split("\n\n", 1)
    body += "\n"
    origin, size, root_b64 = body.split("\n")[:3]
    log_name, log_hash, _, log_key = parse_vkey(LOG_VKEY)
    if origin != log_name:
        raise ValueError("checkpoint of another log")
    pins = {(n, h): (n, k) for n, h, _, k in map(parse_vkey, WITNESS_VKEYS)}
    log_ok, witnesses = False, []
    for line in filter(None, sigs.split("\n")):
        name, b64 = line[2:].rsplit(" ", 1)
        sig = base64.b64decode(b64)
        if name == log_name and sig[:4] == log_hash:
            log_ok = verify(log_key, sig[4:], body.encode())
        elif (name, sig[:4]) in pins and len(sig) == 76:
            (ts,) = struct.unpack(">Q", sig[4:12])
            msg = f"cosignature/v1\ntime {ts}\n".encode() + body.encode()
            if verify(pins[(name, sig[:4])][1], sig[12:], msg):
                witnesses.append({"witness": name, "cosigned_at_unix": ts})
    return int(size), base64.b64decode(root_b64), log_ok, witnesses


def jcs(v) -> str:
    """RFC 8785 for what a label holds (strings, integers, booleans, null, arrays, objects)."""
    if v is None or isinstance(v, bool):
        return json.dumps(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ",".join(jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + jcs(v[k]) for k in sorted(v, key=lambda k: k.encode("utf-16-be"))) + "}"
    raise ValueError(type(v).__name__)


def inclusion_root(leaf: bytes, index: int, size: int, path: list[bytes]):
    """RFC 9162 section 2.1.3.2."""
    if index >= size:
        return None
    fn, sn, r = index, size - 1, leaf
    for p in path:
        if sn == 0:
            return None
        if fn & 1 or fn == sn:
            r = hashlib.sha256(b"\x01" + p + r).digest()
            while not fn & 1 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = hashlib.sha256(b"\x01" + r + p).digest()
        fn >>= 1
        sn >>= 1
    return r if sn == 0 else None


def main(endpoint: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    note = get("/api/v1/log/checkpoint/cosigned", text=True)
    size, root, log_ok, witnesses = check_checkpoint(note)
    hits = get("/api/v1/servers?q=" + urllib.parse.quote(endpoint.split(":", 1)[-1]) + "&limit=20")
    target = next(s for s in hits.get("servers", []) if s.get("endpoint") == endpoint)
    detail = get("/api/v1/servers/" + target["id"])
    labels = [l for l in detail.get("labels", []) if l.get("method", "").endswith(":tool-set-observation") and 0 <= int(l.get("leaf_index", -1)) < size]
    lab = max(labels, key=lambda l: int(l["leaf_index"]))
    label = get("/api/v1/labels/" + urllib.parse.quote(lab["id"], safe=""))
    proof = get("/api/v1/labels/" + urllib.parse.quote(lab["id"], safe="") + f"/proof?tree_size={size}")
    leaf = hashlib.sha256(b"\x00" + jcs(label).encode("utf-8")).digest()
    computed = inclusion_root(leaf, int(proof["leafIndex"]), size, [bytes.fromhex(h) for h in proof["inclusionProof"]])
    included = computed == root
    mtl = (label.get("credentialSubject") or {}).get("mcpTrustLabel") or {}
    checks = {"log_signature": log_ok, "witness_cosignatures": len(witnesses), "inclusion": included,
              "tree_size": size, "leaf_index": int(proof["leafIndex"]), "label": lab["id"]}
    print(json.dumps(checks, indent=1))
    if not (log_ok and witnesses and included):
        print("NOT WRITTEN: the observation could not be proven in the witnessed log", file=sys.stderr)
        return 1

    version = (mtl.get("server") or {}).get("version") or detail["server"].get("packageVersion")
    observed_at = mtl.get("observedAt") or lab["observed_at"]
    (out / "anchor.json").write_text(json.dumps({
        "checkpoint_note": note, "log_vkey": LOG_VKEY, "witness_vkeys": WITNESS_VKEYS,
        "witness_cosignatures_verified": witnesses, "label": label,
        "inclusion": {"leaf_index": int(proof["leafIndex"]), "tree_size": size, "path": proof["inclusionProof"],
                      "leaf_hash": leaf.hex(), "root": root.hex()},
        "how_to_check": "leaf = SHA-256(0x00 || RFC 8785(label)); RFC 9162 inclusion to the checkpoint root; "
                        "Ed25519 note signature under log_vkey; c2sp.org/tlog-cosignature under each witness vkey",
    }, indent=1, ensure_ascii=False) + "\n")

    base = {
        "schema_version": "0.1.0",
        "agent_id": f"{endpoint}@{version}",
        "actor_chain": ["histor-crawler", "histor-sandbox (gVisor, no route out)", f"{endpoint}@{version}"],
        "timestamp": observed_at,
        "claims": [{"claim": "emission-conformant", "evidence": [lab["id"]]}],
        "integrity": {"signed": True, "chain_linked": True, "timestamped": True,
                      "verifiable_by": [w["witness"] for w in witnesses]},
        "declared_vs_observed": {
            "permitted": "the tool list the package publishes for this version",
            "occurred": f"tools/list answered with tool set {(mtl.get('toolSet') or {}).get('digestSRI')} "
                        f"when HISTOR installed and started version {version} in its sandbox"},
        "sampling": {"sampled": False, "audit_required": False},
    }
    as_published = dict(base, record_id=f"histor-{lab['id'].split(':')[-1]}-a",
                        observation={"source": "sandbox", "relationship": "direct", "directness": "direct_observation"},
                        verification={"vantage": "substrate", "method": "intercepted", "basis": "substrate_intercepted",
                                      "basis_engines": ["sandbox"]})
    operator = dict(base, record_id=f"histor-{lab['id'].split(':')[-1]}-b",
                    observation={"source": "external_authority", "relationship": "direct", "directness": "direct_observation"},
                    verification={"vantage": "substrate", "method": "intercepted", "basis": "substrate_intercepted",
                                  "basis_engines": ["external_authority", "sandbox"]},
                    provenance=[lab["id"]])
    (out / "record-as-published.json").write_text(json.dumps(as_published, indent=1, ensure_ascii=False) + "\n")
    (out / "record-operator-custody.json").write_text(json.dumps(operator, indent=1, ensure_ascii=False) + "\n")
    print("written:", ", ".join(p.name for p in sorted(out.glob("*.json"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
