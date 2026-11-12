"""Verify a TensorFeed AFTA receipt and both AIMarket receipts offline, with one Ed25519 primitive.

Run from this directory:  python3 -I verify_receipts.py   (needs `cryptography`)

Inputs (saved responses of 2026-10-30, no payment made):
  tensorfeed/trial-response.json         free-trial call to /api/premium/news/search?q=receipts
  tensorfeed/tensorfeed-receipt-key.json TensorFeed's published JWK
  aimarket/invoke-logos.json             free call to logos.federation.summary@v1 via modelmarket.dev
  aimarket/provenance-receipt.json       the AWR/2 provenance receipt of that call

Writes verify-report.json. No network access.
"""

import base64
import hashlib
import json
import pathlib
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HERE = pathlib.Path(__file__).resolve().parent
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b64url(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b58(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw


def compact_sorted(v):
    # TensorFeed's canonicalJSON and RFC 8785 (JCS) agree on everything these receipts contain:
    # sorted keys, no whitespace, non-ASCII as itself. They would differ only on number formatting.
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ed25519_ok(pub, sig, msg):
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, msg)
        return True
    except Exception:
        return False


def tensorfeed():
    resp = json.loads((HERE / "tensorfeed/trial-response.json").read_text())
    jwk = json.loads((HERE / "tensorfeed/tensorfeed-receipt-key.json").read_text())
    r = resp["receipt"]
    meta = {"signature", "key_id", "signing_alg", "signing_curve", "canonical_form", "verify_doc"}
    core = {k: v for k, v in r.items() if k not in meta}
    body = {k: v for k, v in resp.items() if k not in ("receipt", "billing")}
    tampered = dict(core, credits_charged=5)
    sig = b64url(r["signature"])
    pub = b64url(jwk["x"])
    return {
        "signed_bytes": "canonical JSON of every field except the six signature fields",
        "signature_valid": ed25519_ok(pub, sig, compact_sorted(core).encode()),
        "tampered_credits_rejected": not ed25519_ok(pub, sig, compact_sorted(tampered).encode()),
        "request_hash_reproduced": r["request_hash"]
        == "sha256:" + hashlib.sha256(b"GET /api/premium/news/search?q=receipts").hexdigest(),
        "response_hash_reproduced": r["response_hash"]
        == "sha256:" + hashlib.sha256(compact_sorted(body).encode()).hexdigest(),
        "agent_nonce_echoed": r.get("agent_nonce") == "aimarket-receipt-map-20261030",
        "signed_fields": sorted(core),
    }


def aimarket_protocol():
    raw = (HERE / "aimarket/invoke-logos.json").read_text()
    r = json.loads(raw)["receipt"]

    def token(name):
        # price_usd and latency_ms are signed as the exact JSON number token (spec §7.3.3).
        return re.search(r'"%s"\s*:\s*(-?[0-9][0-9.eE+-]*)' % name, raw.split('"receipt"', 1)[1]).group(1)

    canonical = "|".join(
        [
            "nonce:" + r["nonce"],
            "product_id:" + r["product_id"],
            "capability_id:" + r["capability_id"],
            "price_usd:" + token("price_usd"),
            "timestamp:" + r["timestamp"],
            "success:" + ("1" if r.get("success") else "0"),
            "latency_ms:" + token("latency_ms"),
        ]
    )
    sig = r["signature"]
    pub = base64.b64decode(sig["public_key"])
    value = base64.b64decode(sig["value"])
    flipped = canonical.replace("success:1", "success:0")
    return {
        "signed_bytes": "pipe-joined seven-field canonical, spec §7.3.3",
        "canonical": canonical,
        "signature_valid": ed25519_ok(pub, value, canonical.encode()),
        "flipped_success_rejected": not ed25519_ok(pub, value, flipped.encode()),
        "post_quantum_signature_present": sig.get("pq_algorithm") == "ml-dsa-65",
        "binds_request_or_response_content": False,
        "signed_fields": ["nonce", "product_id", "capability_id", "price_usd", "timestamp", "success", "latency_ms"],
    }


def aimarket_provenance():
    doc = json.loads((HERE / "aimarket/provenance-receipt.json").read_text())
    answer = json.loads((HERE / "aimarket/invoke-logos.json").read_text())
    proof = dict(doc["proof"])
    proof_value = proof.pop("proofValue")
    unsigned = {k: v for k, v in doc.items() if k != "proof"}
    # eddsa-jcs-2022: sign sha256(JCS(proof config, with the document's @context)) || sha256(JCS(document)).
    proof.setdefault("@context", doc["@context"])
    msg = hashlib.sha256(compact_sorted(proof).encode()).digest() + hashlib.sha256(compact_sorted(unsigned).encode()).digest()
    mb = proof["verificationMethod"].split("#")[-1]
    key = b58(mb[1:])
    assert key[:2] == b"\xed\x01"  # multicodec ed25519-pub
    subject = doc["credentialSubject"]
    sri = lambda v: "sha256-" + base64.b64encode(hashlib.sha256(compact_sorted(v).encode()).digest()).decode()
    # Before the 2026-10-30 fix a routed receipt digested the whole answer as it stood when the
    # receipt was issued, i.e. everything except `provenance_receipt`; nothing said so.
    return {
        "signed_bytes": "W3C Data Integrity eddsa-jcs-2022 over the whole credential",
        "signature_valid": ed25519_ok(key[2:], b58(proof_value[1:]), msg),
        "output_digest_of_output_member": subject.get("outputDigest") == sri(answer["output"]),
        "output_digest_of_answer_minus_provenance": subject.get("outputDigest")
        == sri({k: v for k, v in answer.items() if k != "provenance_receipt"}),
        "says_what_it_digested": "outputDigestOf" in subject,
        "binds_request_or_response_content": True,
        "signed_fields": "whole document: issuer, work, inputDigest, outputDigest, providerHub, nonce, hubInfo",
    }


if __name__ == "__main__":
    report = {
        "tensorfeed_afta_receipt": tensorfeed(),
        "aimarket_protocol_receipt": aimarket_protocol(),
        "aimarket_provenance_receipt": aimarket_provenance(),
    }
    (HERE / "verify-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
