"""Tests for desktop screenshot manifest (8 SKUs × 4 screens)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from desktop_sku_manifest import MANIFEST, expected_pngs  # noqa: E402

DESKTOP_SLUGS = [
    "interview-prep-coach",
    "personal-finance-coach",
    "capability-composer",
    "cold-outreach-coach",
    "creator-algorithm-coach",
    "discovery-prospector",
    "freelance-contract-reviewer",
    "reputation-dashboard",
]


def test_manifest_covers_all_eight_desktop_skus():
    assert set(MANIFEST.keys()) == set(DESKTOP_SLUGS)


def test_each_sku_has_four_unique_screens():
    for slug in DESKTOP_SLUGS:
        names = expected_pngs(slug)
        assert len(names) == 4, slug
        assert len(set(names)) == 4, slug


def test_ports_are_unique():
    ports = [m.port for m in MANIFEST.values()]
    assert len(ports) == len(set(ports))


def test_interview_prep_has_skip_onboarding_define():
    m = MANIFEST["interview-prep-coach"]
    assert m.dart_defines.get("SKIP_ONBOARDING") == "true"
    assert m.wallet is False


def test_cold_outreach_has_five_bottom_nav_slots():
    assert MANIFEST["cold-outreach-coach"].bottom_nav_slots == 5


def test_wallet_key_on_hub_dependent_skus():
    for slug in ("discovery-prospector", "reputation-dashboard", "personal-finance-coach"):
        assert MANIFEST[slug].wallet is True

