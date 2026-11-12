#!/usr/bin/env python3
"""Read public ARD data and reproduce only an outer-result version omission.

No authentication, paid invoke, repository write or deployment. The independent
signature check uses cryptography and an intentionally restricted JSON serializer:
the fetched trustManifest must consist only of objects and ASCII string leaves.
For this restricted input, json.dumps(sort_keys=True, separators=(',', ':')) is
the RFC 8785 serialization. Numbers, arrays and non-ASCII strings are refused.
"""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HERE = Path(__file__).resolve().parent
HUB = "https://modelmarket.dev"
FIELDS = ("identifier", "type", "version", "digest")


def fetch(url, payload=None):
    assert url.startswith(HUB + "/"), "This reproduction only reads the chosen public hub"
    headers = {"User-Agent": "AICOM-article-evidence/1.0"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, headers=headers,
        data=None if payload is None else json.dumps(payload).encode(),
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(2_000_001)
        assert len(body) <= 2_000_000
        return body


def unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def ascii_json(value):
    def validate(node):
        if isinstance(node, str):
            assert node.isascii(), "Use a full RFC 8785 library for non-ASCII inputs"
        elif isinstance(node, dict):
            for key, child in node.items():
                assert isinstance(key, str) and key.isascii()
                validate(child)
        else:
            raise AssertionError("Use a full RFC 8785 library for this JSON value")
    validate(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def coordinates(item):
    return {key: item[key] for key in FIELDS if key in item}


def main():
    manifest = json.loads(fetch(HUB + "/.well-known/ard.json"))
    registry = next(e["url"] for e in manifest["entries"] if e["type"] == "application/ai-registry+json")
    query = {"query": {"text": "weather", "filter": {"publisher": "modelmarket.dev"}}, "pageSize": 10}
    results = json.loads(fetch(registry + "/search", query))
    item = next(i for i in results["results"] if i.get("trustManifest"))
    tm = item["trustManifest"]
    assert "version" in item and item["version"]
    assert tm["subject"] == coordinates(item)
    assert item["identifier"].startswith("urn:air:modelmarket.dev:")

    descriptor = fetch(item["url"])
    expected_digest = "sha256:" + hashlib.sha256(descriptor).hexdigest()
    assert item["digest"] == expected_digest
    did = json.loads(fetch(HUB + "/.well-known/did.json"))
    assert did["id"] == tm["identity"] == "did:web:modelmarket.dev"
    h64, empty, s64 = tm["signature"].split(".")
    assert empty == ""
    header = json.loads(unb64(h64))
    assert header["alg"] == "EdDSA"
    method = next(m for m in did["verificationMethod"] if m["id"] == header["kid"])
    assert method["id"] in did["assertionMethod"]
    assert method["controller"] == did["id"]
    assert method["publicKeyJwk"]["kty"] == "OKP" and method["publicKeyJwk"]["crv"] == "Ed25519"
    key = Ed25519PublicKey.from_public_bytes(unb64(method["publicKeyJwk"]["x"]))

    def verify_signature(manifest):
        body = {k: v for k, v in manifest.items() if k != "signature"}
        signing_input = h64 + "." + b64(ascii_json(body))
        key.verify(unb64(s64), signing_input.encode("ascii"))

    verify_signature(tm)
    broken = deepcopy(item)
    del broken["version"]
    assert broken["trustManifest"] == tm
    verify_signature(broken["trustManifest"])
    assert broken["trustManifest"]["subject"] != coordinates(broken)
    assert broken["digest"] == expected_digest

    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "public_registry": registry,
        "selected_identifier": item["identifier"],
        "version": item["version"],
        "live_result": {"publisher_binding": True, "jws_signature": True, "subject_binding": True, "descriptor_digest": True},
        "controlled_outer_version_omission": {"jws_signature": True, "subject_binding": False, "descriptor_digest": True},
        "scope": "One public signed local search result, then an in-memory mutation; no paid invoke. Restricted ASCII-object RFC 8785 serialization only.",
    }
    (HERE / "binding-check.json").write_text(json.dumps(summary, indent=2) + "\n")
    (HERE / "public-signed-result.json").write_text(json.dumps(item, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
