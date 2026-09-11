"""Dashboard failed_alerts + Telegram FAILED notifications."""

from __future__ import annotations

import time
from unittest.mock import patch

# Patch the helpers module where these functions are defined and resolved at call
# time (the dashboard package only re-exports them).
from web.backend.api.admin.dashboard import helpers as dash_mod
from web.backend.services.pipeline_failure_report import build_failure_report
from web.backend.services.pipeline_failed_notify import (
    failure_reason_from_product,
    notify_pipeline_product_failed,
)
from web.backend.services.telegram_pipeline_notify import notify_telegram_pipeline_failed


def test_failure_reason_from_product_metadata():
    p = {"metadata": {"error": "spec gate failed"}, "failure_reason": "top level"}
    assert failure_reason_from_product(p) == "top level"


def test_build_failure_report_for_dashboard_alert():
    product = {
        "state": "FAILED",
        "failure_reason": "Specification failed quality gate: [structure]",
        "idea": "IoT dashboard",
    }
    tasks = [
        {
            "status": "failed",
            "agent_type": "pm",
            "state": "SPEC_WRITTEN",
            "error": product["failure_reason"],
            "completed_at": time.time(),
        }
    ]
    report = build_failure_report(product, tasks)
    assert report["cause_plain"]
    assert "quality gates" in report["cause_plain"].lower()


def test_notify_telegram_pipeline_failed_respects_config():
    sent: list[str] = []

    def fake_send(text: str):
        sent.append(text)
        return True, "ok"

    cfg = {
        "enabled": True,
        "notify_pipeline_failed": True,
        "token": "x",
        "chat_id": "1",
    }
    with patch(
        "web.backend.services.telegram_pipeline_notify.telegram_pipeline_config",
        return_value=cfg,
    ), patch(
        "web.backend.services.telegram_pipeline_notify.send_telegram_message_sync",
        side_effect=fake_send,
    ), patch(
        "web.backend.services.telegram_pipeline_notify._maybe_broadcast_web_push_after_telegram",
    ):
        notify_telegram_pipeline_failed(
            product_id="prod-abc-123",
            headline="Specification quality gate failed",
            cause_plain="PM spec was rejected by automated gates.",
            failure_reason="Specification failed quality gate",
            failed_agent="pm",
            idea_snippet="Test product",
        )
    assert len(sent) == 1
    assert "FAILED" in sent[0]
    assert "Cause:" in sent[0]
    assert "quality gate" in sent[0].lower()


def test_pipeline_failed_alerts_from_snapshot():
    products = {
        "p1": {
            "idea": "Alpha",
            "state": "FAILED",
            "updated_at": 100.0,
            "failure_reason": "Specification failed quality gate",
        }
    }
    tasks = [
        {
            "product_id": "p1",
            "status": "failed",
            "agent_type": "pm",
            "error": "Specification failed quality gate",
        }
    ]

    with patch.object(dash_mod, "_admin_use_sqlite_pipeline", return_value=False), patch.object(
        dash_mod, "_load_pipeline_snapshot_for_metrics", return_value=(products, tasks)
    ):
        alerts = dash_mod._pipeline_failed_alerts(limit=5)
    assert len(alerts) == 1
    assert alerts[0]["product_id"] == "p1"
    assert alerts[0]["cause_plain"]


def test_failed_notify_dedupe_helpers(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services import pipeline_failed_notify as pfn

    # Resolved per call now: a module-level constant built at import time pointed at
    # whichever data root was current when some earlier test first imported this module,
    # so this case saw another test's marker file and its first assertion failed.
    pfn._dedupe_path().parent.mkdir(parents=True, exist_ok=True)
    assert pfn._already_sent("p1", "reason a") is False
    pfn._mark_sent("p1", "reason a")
    assert pfn._already_sent("p1", "reason a") is True
    assert pfn._already_sent("p1", "reason b") is False
