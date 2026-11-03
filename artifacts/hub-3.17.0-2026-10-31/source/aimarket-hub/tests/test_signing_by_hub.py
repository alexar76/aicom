"""SEC regression: the manifest signature must cover by_hub (peer trust / routing metadata),
so a relay can't tamper with trust scores under a still-valid signature."""
from aimarket_hub.signing import Signer


def _manifest(trust):
    return {
        "protocol_version": "v2",
        "capabilities_count": 1,
        "generated_at": "2026-06-19T00:00:00Z",
        "tools": [{"capability_id": "x.y@v1", "price_usd": 0.01}],
        "by_hub": {"peer-a": {"trust_score": trust}},
    }


def test_manifest_signature_covers_by_hub():
    s = Signer()
    pk = s.public_key_b64  # pinned key (verify is fail-closed without one)
    m = _manifest(0.5)
    m["signature"] = s.sign_manifest(m)
    assert s.verify_manifest_signature(m, known_public_key=pk) is True

    # Tamper only with by_hub trust_score; the structural fields + tools are untouched.
    m["by_hub"]["peer-a"]["trust_score"] = 0.99
    assert s.verify_manifest_signature(m, known_public_key=pk) is False
