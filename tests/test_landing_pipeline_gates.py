"""Landing delivery profile uses the same demo quality bar as other profiles."""

from __future__ import annotations

from web.backend.services.demo_quality import quality_gates_pass


def test_quality_gates_pass_landing_same_bar_as_full_software():
    report = {
        "score": 50,
        "has_index_html": True,
        "issues": [
            {"code": "cta_dead_hash_link", "detail": "hash"},
            {"code": "low_spec_alignment", "detail": "align"},
        ],
    }
    assert quality_gates_pass(report, delivery_profile="marketing_landing") is False
    assert quality_gates_pass(report, delivery_profile="full_software") is False


def test_quality_gates_pass_landing_requires_min_score():
    report = {
        "score": 90,
        "has_index_html": True,
        "issues": [],
    }
    assert quality_gates_pass(report, delivery_profile="marketing_landing") is True
