"""Landing delivery profile must not trap products in PM/QA methodology loops."""

from __future__ import annotations

from web.backend.services.demo_quality import quality_gates_pass


def test_quality_gates_pass_landing_ignores_hash_cta():
    report = {
        "score": 50,
        "has_index_html": True,
        "issues": [
            {"code": "cta_dead_hash_link", "detail": "hash"},
            {"code": "low_spec_alignment", "detail": "align"},
        ],
    }
    assert quality_gates_pass(report, delivery_profile="marketing_landing") is True
    assert quality_gates_pass(report, delivery_profile="full_software") is False
