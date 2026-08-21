"""Tests for funnel lead capture and analytics."""

from __future__ import annotations

import json
import time

import pytest


def test_create_lead_and_start_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_FUNNEL_DIR", str(tmp_path / "funnel"))
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_LEAD_AUTO_PIPELINE", "1")

    products: list[dict] = []

    def _append(product: dict, **kwargs):
        products.append(product)

    monkeypatch.setattr(
        "web.backend.services.funnel_leads.append_product_to_pipeline_state",
        _append,
    )

    from web.backend.services.funnel_leads import create_lead_and_maybe_start_pipeline

    res = create_lead_and_maybe_start_pipeline(
        email="test@example.com",
        idea="Marketing landing for AI scheduling assistant with waitlist",
        source="lead_page",
    )
    assert res["ok"] is True
    assert res["pipeline_started"] is True
    assert res["status_token"]
    assert len(products) == 1
    assert products[0]["owner_email"] == "test@example.com"
    assert "funnel-lead" in products[0]["tags"]


def test_public_lead_status(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_FUNNEL_DIR", str(tmp_path / "funnel"))

    from web.backend.services.funnel_store import create_lead_record
    from web.backend.services.funnel_leads import public_lead_status

    lead = create_lead_record(
        email="owner@test.com",
        idea="Test idea for status page",
        product_id="prod-abc123",
    )
    status = public_lead_status(lead["status_token"])
    assert status is not None
    assert status["status"] in ("pipeline_started", "received")
    assert status["product_id"] == "prod-abc123"
    assert "@" in status["email"]


def test_funnel_analytics_stages(tmp_path, monkeypatch):
    from core.paths import marketing_logs_dir

    log_dir = tmp_path / "logs" / "marketing"
    log_dir.mkdir(parents=True)
    events = log_dir / "events.jsonl"
    now = time.time()
    rows = [
        {"ts": now, "event": "page_view"},
        {"ts": now, "event": "product_view", "product_id": "prod-1"},
        {"ts": now, "event": "sandbox_click", "product_id": "prod-1"},
        {"ts": now, "event": "checkout_click", "product_id": "prod-1"},
    ]
    events.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("web.backend.services.funnel_analytics.marketing_logs_dir", lambda: log_dir)

    from web.backend.services.funnel_analytics import build_funnel_metrics

    m = build_funnel_metrics(window_hours=24)
    assert m["stages"]["page_view"] == 1
    assert m["stages"]["sandbox_click"] == 1
