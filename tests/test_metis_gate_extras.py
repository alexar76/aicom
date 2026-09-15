"""Regression: the advisory metis_gate envelope must survive a persistence round-trip.

Per docs/testing-rules.md, any new top-level product field that must survive a
pipeline cycle needs a PRODUCT_EXTRA_KEYS entry + a round-trip test.
"""

from __future__ import annotations

from orchestrator.product_extras import (
    PRODUCT_EXTRA_KEYS,
    extract_product_extras,
    extras_from_json,
    extras_to_json,
    merge_product_extras,
)


def test_metis_gate_in_allowlist():
    assert "metis_gate" in PRODUCT_EXTRA_KEYS


def test_metis_gate_extras_roundtrip():
    gate = {
        "stage": "architect",
        "ok": False,
        "status": "needs_clarification",
        "verify_score": 0.0,
        "verified": False,
        "clarifications": ["Which platform?"],
        "blocked": False,
    }
    product = {"id": "p1", "idea": "x", "metis_gate": gate}

    extras = extract_product_extras(product)
    assert extras.get("metis_gate") == gate

    restored = extras_from_json(extras_to_json(extras))
    fresh = {"id": "p1"}
    merge_product_extras(fresh, restored)
    assert fresh["metis_gate"] == gate
