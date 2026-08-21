"""Tests for admin panel user action log."""

from __future__ import annotations

import pytest


@pytest.fixture
def action_log_path(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_LOGS_DIR", str(tmp_path))
    return tmp_path / "admin_actions.jsonl"


def test_log_and_query_by_username(action_log_path):
    from web.backend.services import admin_action_log as al

    al.log_admin_action(
        actor_username="alice",
        action="login",
        resource="admin/auth",
        details={"role": "admin"},
        ip_address="127.0.0.1",
    )
    al.log_admin_action(
        actor_username="bob",
        action="product_created",
        resource="pipeline/prod-abc",
        details={"idea_preview": "Test idea"},
    )

    rows, total = al.query_admin_actions(username="alice", limit=10)
    assert total == 1
    assert rows[0]["action"] == "login"
    assert rows[0]["actor_username"] == "alice"


def test_verify_script_skips_auto_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_LEAD_AUTO_PIPELINE", "1")
    leads_path = tmp_path / "leads.json"
    monkeypatch.setattr(
        "web.backend.services.funnel_store.LEADS_PATH",
        leads_path,
        raising=False,
    )

    from web.backend.services.funnel_leads import create_lead_and_maybe_start_pipeline

    out = create_lead_and_maybe_start_pipeline(
        email="verify@test.com",
        idea="Ecosystem verification landing for AI scheduling assistant waitlist",
        source="verify_script",
    )
    assert out["ok"] is True
    assert out["pipeline_started"] is False
    assert out["product_id"] is None
