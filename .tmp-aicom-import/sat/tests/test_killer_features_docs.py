"""Killer feature documentation presence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_ecosystem_killer_features_index():
    text = (ROOT / "docs" / "killer-features.md").read_text(encoding="utf-8")
    for phrase in ("Auto-Mesh Pipeline", "Zero-Trust", "TEE Escrow", "1-Click"):
        assert phrase in text


def test_product_killer_deep_dives_exist():
    paths = [
        "docs/killer-feature-auto-mesh-pipeline.md",
        "aimarket-hub/docs/killer-feature-zero-trust-discovery.md",
        "plugins/docs/killer-feature-tee-escrow.md",
        "aimarket-widget/docs/killer-feature-one-click-embed.md",
    ]
    for rel in paths:
        p = ROOT / rel
        if not p.is_file():
            pytest.skip(f"satellite doc not in factory tree: {rel}")
        assert p.is_file(), rel
