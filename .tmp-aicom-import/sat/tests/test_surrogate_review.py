"""Tests for surrogate review eligibility and confidence policy."""

from __future__ import annotations

from core.surrogate_review import (
    SURROGATE_ELIGIBLE_POINTS,
    apply_confidence_policy,
    fail_safe_verdict,
    is_point_surrogate_eligible,
)


def test_eligible_points_allowlist():
    assert is_point_surrogate_eligible("post_devops_gate")
    assert is_point_surrogate_eligible("qa_repair_exhausted")
    assert not is_point_surrogate_eligible("benchmark_gate")
    assert "benchmark_gate" not in SURROGATE_ELIGIBLE_POINTS


def test_low_confidence_becomes_block():
    v = fail_safe_verdict("post_devops_gate", "p1", "test")
    v.confidence = 0.2
    v.decision = "approve"
    v.rationale = "maybe ok"
    out = apply_confidence_policy(v, point="post_devops_gate")
    assert out.decision == "block"
