"""Tests for outcome prior cold start."""

from __future__ import annotations

from pathlib import Path

from core.outcome_memory import NEUTRAL_PRIOR, outcome_fit_score, outcome_prior


def test_cold_start_neutral(tmp_path: Path):
    prior = outcome_prior(tmp_path, category="saas")
    assert prior["ship_rate"] == NEUTRAL_PRIOR
    assert outcome_fit_score(tmp_path, category="saas") == NEUTRAL_PRIOR


def test_ship_rate_after_samples(tmp_path: Path):
    from core.outcome_memory import append_outcome

    for i in range(5):
        append_outcome(
            tmp_path,
            {
                "category": "saas",
                "delivery_profile": "full_software",
                "reached": "COMPLETED" if i < 4 else "FAILED",
                "telemetry": {"views": 10, "aimarket_invokes": 1},
            },
        )
    prior = outcome_prior(tmp_path, category="saas", delivery_profile="full_software")
    assert prior["samples"] >= 5
    assert prior["ship_rate"] > NEUTRAL_PRIOR
