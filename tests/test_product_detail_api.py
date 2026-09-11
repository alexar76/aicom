"""Regression tests for storefront product detail builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def product_detail_module(monkeypatch, tmp_path):
    from web.backend.api import products as mod

    telemetry_root = tmp_path / "telemetry"
    telemetry_root.mkdir()

    def fake_telemetry_dir(product_id: str) -> Path:
        d = telemetry_root / product_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(mod, "telemetry_dir", fake_telemetry_dir)
    monkeypatch.setattr(mod, "_get_product_entry", lambda pid: {
        "idea": "Test product idea",
        "state": "LIVE",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "tags": ["test"],
    })
    monkeypatch.setattr(mod, "public_storefront_blocked", lambda pid: False)
    monkeypatch.setattr(mod, "_load_marketing", lambda pid: {"tags": ["test"], "monetization_scheme": {}})
    monkeypatch.setattr(mod, "_load_sales", lambda pid: {"pricing": {}, "license_terms": {}})
    monkeypatch.setattr(mod, "_spec_inner_for_storefront", lambda pid, product: {"features": []})
    monkeypatch.setattr(mod, "_load_architecture_from_disk", lambda pid: None)
    monkeypatch.setattr(mod, "assess_product_demo", lambda pid, spec: {"score": 0})
    monkeypatch.setattr(mod, "evaluate_marketplace_quality", lambda *a, **k: {
        "eligible": True,
        "reasons": [],
        "marketplace_rules": {},
    })
    monkeypatch.setattr(mod, "build_stakeholder_brief", lambda *a, **k: {})
    monkeypatch.setattr(mod, "marketplace_listing_card_fields", lambda mq: {})
    return mod


def test_build_product_detail_evolution_history_empty(product_detail_module):
    detail = product_detail_module._build_product_detail_response("prod-test-empty")
    assert isinstance(detail["evolution_history"], list)
    assert detail["evolution_history"] == []


def test_build_product_detail_evolution_history_from_telemetry(product_detail_module, tmp_path):
    mod = product_detail_module
    evo_dir = mod.telemetry_dir("prod-test-evo")
    evo_file = evo_dir / "evolution_001.json"
    evo_file.write_text(json.dumps({"event": "improvement", "tick": 1}), encoding="utf-8")

    detail = mod._build_product_detail_response("prod-test-evo")
    assert len(detail["evolution_history"]) == 1
    assert detail["evolution_history"][0]["event"] == "improvement"
