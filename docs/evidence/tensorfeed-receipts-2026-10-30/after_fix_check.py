"""After the 2026-10-30 fix: call free capabilities on live hubs with our own nonce and check
that every part of the answer can be recomputed and verified by the buyer.

usage: python3 -I after_fix_check.py OUT_DIR HUB_URL [HUB_URL ...]   (needs `cryptography`)

For each hub: one routed call (logos.federation.summary@v1 via that hub) and, when the hub
lists one, nothing else is needed — the routed path is the one that was broken. Writes the raw
answers and a report.json into OUT_DIR. No payment is made: the capability is free.
"""

import base64
import hashlib
import json
import pathlib
import sys
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
FIELDS = ("v", "hub", "receipt_nonce", "receipt_signer", "input_sha256",
          "output_member", "output_sha256", "client_nonce", "timestamp")


def compact(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(v):
    return hashlib.sha256(compact(v).encode()).hexdigest()


def sri(v):
    return "sha256-" + base64.b64encode(hashlib.sha256(compact(v).encode()).digest()).decode()


def http(url, body=None, headers=None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "aimarket-after-fix/1",
                                          **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, {k.lower(): v for k, v in r.headers.items()}, json.loads(r.read())


def ed_ok(pub_b64, sig_b64, msg):
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(base64.b64decode(sig_b64), msg.encode())
        return True
    except Exception:
        return False


report = {}
for hub in sys.argv[2:]:
    hub = hub.rstrip("/")
    name = hub.split("//")[1].replace("/", "_")
    nonce = "aftafix-" + name.replace(".", "-")[:40]
    candidates = [
        ("prod-logos", "logos.federation.summary@v1", "https://logos.modelmarket.dev"),
        ("gaia.gateway", "gaia.fleet.status@v1", "https://iot.modelmarket.dev"),
        ("symmartys", "symmartys.sources@v1", "https://modelmarket.dev/providers/symmartys"),
        ("attested-meter", "meter.prices@v1", "https://hub.attestedmemory.net"),
    ]
    answer = None
    for product, capability, source in candidates:
        body = {"product_id": product, "capability_id": capability, "input": {}, "source_hub": source}
        try:
            status, headers, answer = http(hub + "/ai-market/v2/invoke", body, {"X-Client-Nonce": nonce})
        except Exception as exc:  # noqa: BLE001 - try the next free capability this hub routes
            answer = None
            continue
        if answer.get("success"):
            break
    if not answer or not answer.get("success"):
        report[hub] = {"error": "no free routed capability answered"}
        continue
    (OUT / f"{name}-invoke.json").write_text(json.dumps(answer, indent=1, ensure_ascii=False))
    b = answer.get("receipt_binding") or {}
    wk = http(hub + "/.well-known/ai-market.json")[2]
    hub_key = wk.get("signer_public_key")
    canonical = "receipt_binding:1|" + sha({k: b.get(k) for k in FIELDS})
    row = {
        "capability": f"{body['capability_id']} via {body['source_hub']}",
        "status": status,
        "nonce_echoed": headers.get("x-client-nonce-echo") == nonce,
        "binding_present": bool(b),
        "binding_signed_by_hub_key": bool(b) and b.get("signature", {}).get("public_key") == hub_key
        and ed_ok(hub_key, b["signature"]["value"], canonical),
        "client_nonce_signed": b.get("client_nonce") == nonce,
        "input_sha256_reproduced": b.get("input_sha256") == sha(body["input"]),
        "output_sha256_reproduced": bool(b) and b.get("output_sha256") == sha(answer.get(b.get("output_member"))),
        "receipt_named": b.get("receipt_nonce") == (answer.get("receipt") or {}).get("nonce"),
    }
    _, _, checked = http(hub + "/ai-market/v2/receipts/verify",
                         {"receipt": answer["receipt"], "response": answer, "input": body["input"],
                          "client_nonce": nonce})
    (OUT / f"{name}-verify.json").write_text(json.dumps(checked, indent=1))
    row["hub_verifies_peer_receipt"] = checked.get("valid")
    row["hub_receipt_signer"] = checked.get("signer")
    row["hub_verifies_binding"] = (checked.get("binding") or {}).get("valid")
    prov = answer.get("provenance_receipt")
    if isinstance(prov, dict) and prov.get("receipt_url"):
        url = prov["receipt_url"] if prov["receipt_url"].startswith("http") else hub + prov["receipt_url"]
        awr = http(url)[2]
        (OUT / f"{name}-provenance.json").write_text(json.dumps(awr, indent=1, ensure_ascii=False))
        s = awr["credentialSubject"]
        row["awr_output_digest_of"] = s.get("outputDigestOf")
        row["awr_output_digest_reproduced"] = s.get("outputDigest") == sri(answer.get(s.get("outputDigestOf")))
        row["awr_gateway_receipt_digest_reproduced"] = s.get("gatewayReceiptDigest") == sri(answer.get("receipt"))
        row["awr_input_digest_reproduced"] = s.get("inputDigest") == sri(body["input"])
    else:
        row["awr"] = "no provenance plugin on this hub"
    report[hub] = row
    print(hub, json.dumps(row))
(OUT / "report.json").write_text(json.dumps(report, indent=1) + "\n")
