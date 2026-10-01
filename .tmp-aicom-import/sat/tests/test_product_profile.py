"""Tests for delivery profile inference."""
from __future__ import annotations

from agents.product_profile import (
    FULL_SOFTWARE,
    MARKETING_LANDING,
    admin_charter_forces_landing_only,
    idea_charter_forces_landing_only,
    infer_delivery_profile,
    normalize_delivery_profile,
    research_artifact_implies_full_product,
)


def test_normalize_delivery_profile_landing_alias():
    assert normalize_delivery_profile("landing") == MARKETING_LANDING
    assert normalize_delivery_profile("marketing_landing") == MARKETING_LANDING


def test_infer_force_full_software_env(monkeypatch):
    monkeypatch.setenv("AIFACTORY_FORCE_FULL_SOFTWARE", "1")
    assert infer_delivery_profile(None, "single-scroll landing page for teas") == FULL_SOFTWARE


def test_infer_force_full_respects_admin_charter(monkeypatch):
    monkeypatch.setenv("AIFACTORY_FORCE_FULL_SOFTWARE", "1")
    charter = "PRIMARY DELIVERABLE (guest): exactly one **business marketing landing page**"
    assert infer_delivery_profile(charter, "anything") == MARKETING_LANDING


def test_infer_single_scroll_landing_page():
    idea = (
        "Build a single-scroll landing page for an AI content atomization tool, "
        "targeting marketing managers, with a hero and pricing."
    )
    assert infer_delivery_profile(None, idea) == MARKETING_LANDING


def test_infer_landing_page_plain():
    """Bare «landing page» no longer forces brochure — need explicit brochure-only intent."""
    assert infer_delivery_profile(None, "We need a landing page for our devtool") == FULL_SOFTWARE


def test_infer_landing_page_only_is_brochure():
    assert (
        infer_delivery_profile(None, "Deliver only a landing page for our devtool — no backend")
        == MARKETING_LANDING
    )


def test_infer_respects_strong_backend_over_landing_words():
    idea = (
        "A landing page that also exposes a REST API for lead capture sync to PostgreSQL "
        "with multi-tenant isolation."
    )
    assert infer_delivery_profile(None, idea) == FULL_SOFTWARE


def test_infer_full_software_saas():
    assert infer_delivery_profile(None, "Multi-tenant SaaS dashboard with authentication service") == FULL_SOFTWARE


def test_infer_mobile_app_with_landing_stays_full():
    """Landing page wording must not override clear mobile product intent."""
    idea = "Mobile app with a marketing landing page for downloads"
    assert infer_delivery_profile(None, idea) == FULL_SOFTWARE


def test_research_implies_full_product_when_substantive():
    thin = '{"tagline": "nice"}'
    rich = '{"competitive_landscape": {"x": 1}, "pricing": {"tier": "saas"}, "integrations": ["slack"]}'
    assert research_artifact_implies_full_product(thin) is False
    assert research_artifact_implies_full_product(rich) is True


def test_admin_charter_blocks_escalation_detection():
    guest = "PRIMARY DELIVERABLE (guest): exactly one **business marketing landing page**"
    assert admin_charter_forces_landing_only(guest) is True
    assert admin_charter_forces_landing_only("Ship an internal CRUD tool") is False


def test_idea_charter_forces_landing_only():
    assert idea_charter_forces_landing_only("Marketing landing — waitlist promo") is True
    assert idea_charter_forces_landing_only("Multi-tenant SaaS CRM") is False
