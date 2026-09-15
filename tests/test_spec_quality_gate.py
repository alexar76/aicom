"""Tests for PM post-process spec quality gate."""
from __future__ import annotations

from agents.product_profile import FULL_SOFTWARE, MARKETING_LANDING
from agents.spec_quality_gate import validate_specification


def _minimal_landing_spec() -> dict:
    return {
        "product_name": "Morning Ember",
        "description": "Single-page marketing landing for artisan coffee subscriptions with hero, benefits, and CTA.",
        "target_audience": "home baristas",
        "core_features": [
            {"name": "Hero", "description": "Headline and primary CTA", "priority": "high"},
            {"name": "Benefits", "description": "Three reasons to subscribe", "priority": "high"},
            {"name": "Footer", "description": "Links and legal", "priority": "low"},
        ],
        "user_stories": [
            {
                "story": "Visitor understands the offer in 5 seconds",
                "acceptance_criteria": "Hero shows product name, one-line value prop, and a visible primary CTA button.",
            },
            {
                "story": "Visitor can start checkout",
                "acceptance_criteria": "Primary CTA scrolls or links to a section with plan choice and email capture.",
            },
        ],
        "technical_risks": [],
        "estimated_effort": "S",
        "estimated_days": 3,
        "market_potential": "medium",
    }


def _minimal_full_spec() -> dict:
    s = _minimal_landing_spec()
    s["functional_requirements"] = [
        {
            "id": "FR-01",
            "title": "User signup",
            "description": "Email/password registration with validation",
            "priority": "high",
            "acceptance_criteria": "Given valid email, user receives confirmation and account is created in under 2s p95.",
        },
        {
            "id": "FR-02",
            "title": "Session",
            "description": "JWT session for API calls",
            "priority": "high",
            "acceptance_criteria": "Issued token works on /api/me and expires per policy documented in spec.",
        },
        {
            "id": "FR-03",
            "title": "Widget CRUD",
            "description": "Create list edit delete widgets",
            "priority": "medium",
            "acceptance_criteria": "All CRUD operations return correct HTTP codes and persist in configured store.",
        },
    ]
    s["personas"] = [
        {
            "name": "Dev Dana",
            "context": "Builds internal tools",
            "jobs_to_be_done": ["Ship a working admin for widgets without writing boilerplate auth"],
        }
    ]
    s["non_functional_requirements"] = [
        {
            "category": "security",
            "requirement": "Secrets not in repo",
            "measurable_criteria": "No API keys in git; use env vars only.",
        },
        {
            "category": "performance",
            "requirement": "API latency",
            "measurable_criteria": "p95 read under 200ms for list endpoint with 1k rows.",
        },
    ]
    return s


def test_landing_passes():
    ok, issues = validate_specification(_minimal_landing_spec(), MARKETING_LANDING)
    assert ok, issues


def test_landing_fails_short_stories():
    s = _minimal_landing_spec()
    s["user_stories"] = [{"story": "x", "acceptance_criteria": "short"}]
    ok, issues = validate_specification(s, MARKETING_LANDING)
    assert not ok
    assert any("acceptance" in x.lower() for x in issues)


def test_full_passes():
    ok, issues = validate_specification(_minimal_full_spec(), FULL_SOFTWARE)
    assert ok, issues


def test_full_fails_missing_fr():
    s = _minimal_full_spec()
    s["functional_requirements"] = []
    ok, issues = validate_specification(s, FULL_SOFTWARE)
    assert not ok
    assert any("functional_requirements" in x for x in issues)
