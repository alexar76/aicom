"""ACEX AI auditor — deterministic pack, no human score."""

from acex.integrations.ai_audit import (
    MIN_AUDIT_SCORE_BPS,
    build_pack,
    relevant_momus_findings,
    score_evidence,
)


def _cap(**kw):
    base = {
        "capability_id": "x@v1",
        "product_id": "atlas.products",
        "price_per_call_usd": 0.06,
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "output_schema": {"type": "object"},
        "source_hub": "https://atlas.modelmarket.dev",
        "route_status": "live",
        "observations_30d": 142,
        "reputation_basis": "measured",
        "offerable": True,
        "is_demo": False,
    }
    base.update(kw)
    return base


def test_hub_search_row_without_json_schema_still_counts():
    """Pulse/Hub search matches carry input_hint / offerable, not full JSON Schema."""
    row = {
        "capability_id": "atlas.situation.brief@v1",
        "product_id": "atlas.products",
        "price_per_call_usd": 0.06,
        "route_status": "live",
        "source_hub": "https://atlas.modelmarket.dev",
        "observations_30d": 142,
        "reputation_basis": "measured",
        "offerable": True,
        "input_required": ["west", "south", "east", "north"],
        "input_hint": {"west": {"type": "number"}},
    }
    scored = score_evidence("atlas.products", [row])
    assert scored["verdict"] == "approve"
    assert scored["priced_schema_count"] == 1


def test_atlas_like_product_approves():
    scored = score_evidence("atlas.products", [_cap(), _cap(capability_id="y@v1", price_per_call_usd=0.08)])
    assert scored["verdict"] == "approve"
    assert scored["score_bps"] >= MIN_AUDIT_SCORE_BPS


def test_empty_capabilities_reject():
    scored = score_evidence("prod-x", [])
    assert scored["verdict"] == "reject"
    assert "no_capabilities" in scored["reasons"]


def test_human_cannot_be_encoded_in_pack():
    pack = build_pack("atlas.products", [_cap()])
    assert pack["human_override"] is False
    assert pack["auditor_kind"] == "ai-agent"
    assert len(pack["pack_sha256"]) == 64


def test_momus_high_integrity_finding_hard_fails():
    findings = [
        {
            "outcome": "finding",
            "severity": "high",
            "category": "integrity",
            "target": "atlas",
            "probe": "manifest_signature_integrity",
            "finding_id": "mom-test",
            "title": "atlas: manifest signature does not verify",
        }
    ]
    assert relevant_momus_findings("atlas.products", findings)
    scored = score_evidence("atlas.products", [_cap()], momus_findings=findings)
    assert scored["verdict"] == "reject"
    assert scored["score_bps"] < MIN_AUDIT_SCORE_BPS


def test_skopos_host_findings_do_not_apply_to_listing():
    findings = [
        {
            "outcome": "finding",
            "severity": "high",
            "category": "ssh",
            "target": "factory",
            "probe": "skopos:ssh",
            "finding_id": "mom-host",
            "title": "Root login: yes",
        }
    ]
    scored = score_evidence("prod-011e2b0a45f7", [_cap(product_id="prod-011e2b0a45f7")], momus_findings=findings)
    assert not relevant_momus_findings("prod-011e2b0a45f7", findings)
    # factory catalog row with no observations still needs live+schema; may or may not pass.
    assert "momus_integrity_hard_fail" not in scored["reasons"]
