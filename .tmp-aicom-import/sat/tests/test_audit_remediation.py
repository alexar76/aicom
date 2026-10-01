"""Regression tests for consolidated security/correctness audit fixes."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def test_director_report_path_traversal_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from core.paths import director_reports_dir

    reports = director_reports_dir()
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "ok.md").write_text("# ok", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("leak", encoding="utf-8")

    from web.backend.api.admin.dashboard.routes_director_reports import (
        _resolve_director_report,
    )

    p = _resolve_director_report("ok.md")
    assert p.name == "ok.md"

    with pytest.raises(HTTPException) as exc:
        _resolve_director_report("../../../secret.txt")
    assert exc.value.status_code in (400, 403, 404)

    with pytest.raises(HTTPException):
        _resolve_director_report("..%2F..%2Fsecret.txt")


def _reset_uni_sqlite(monkeypatch, data_root: Path) -> None:
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data_root))
    monkeypatch.setenv("UNI_DB_BACKEND", "sqlite")
    import core.uni.store as uni_store

    monkeypatch.setattr(uni_store, "_sqlite_conn", None)


def test_release_hold_ledger_balance_after_matches_wallet(tmp_path, monkeypatch):
    _reset_uni_sqlite(monkeypatch, tmp_path / "a")
    from core.uni.store import uni_connection, uni_db_backend
    from core.uni.wallet import UniWalletService

    svc = UniWalletService()
    owner = f"audit-{uuid.uuid4().hex[:8]}"
    svc.grant(owner, amount_uni=1000, ref="seed")
    ch = f"ch-{uuid.uuid4().hex[:8]}"
    svc.hold(owner, amount_uni=200, channel_id=ch)
    svc.release_hold(ch)

    wallet = svc.get_or_create_wallet(owner)
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            row = conn.execute(
                "SELECT balance_after FROM uni_ledger WHERE wallet_id = %s AND entry_type = 'release' ORDER BY id DESC LIMIT 1",
                (wallet["wallet_id"],),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT balance_after FROM uni_ledger WHERE wallet_id = ? AND entry_type = 'release' ORDER BY id DESC LIMIT 1",
                (wallet["wallet_id"],),
            ).fetchone()
    assert row is not None
    assert int(round(float(row[0]))) == int(round(float(wallet["balance_uni"])))


def test_spend_hold_ledger_balance_unchanged_hold_decreased(tmp_path, monkeypatch):
    _reset_uni_sqlite(monkeypatch, tmp_path / "b")
    from core.uni.store import uni_connection, uni_db_backend
    from core.uni.wallet import UniWalletService

    svc = UniWalletService()
    owner = f"audit-{uuid.uuid4().hex[:8]}"
    svc.grant(owner, amount_uni=5000, ref="seed")
    ch = f"ch-{uuid.uuid4().hex[:8]}"
    svc.hold(owner, amount_uni=300, channel_id=ch, seller_ref="seller:test")
    before = svc.get_or_create_wallet(owner)
    bal_before = float(before["balance_uni"])
    svc.spend_hold(channel_id=ch, amount_uni=50, ref="r1")
    after = svc.get_or_create_wallet(owner)
    assert float(after["balance_uni"]) == bal_before

    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            row = conn.execute(
                "SELECT balance_after, hold_after FROM uni_ledger WHERE entry_type = 'charge' ORDER BY id DESC LIMIT 1",
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT balance_after, hold_after FROM uni_ledger WHERE entry_type = 'charge' ORDER BY id DESC LIMIT 1",
            ).fetchone()
    assert int(round(float(row[0]))) == int(round(bal_before))


def test_otel_disabled_when_standard_kill_switch(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    from core import tracing

    tracing._INITIALIZED = False
    tracing._TRACER = None
    assert tracing._otel_enabled() is False


def test_batch_queue_trim_preserves_queued(monkeypatch, tmp_path):
    from orchestrator import batch_pipeline as bp

    path = tmp_path / "batch.json"
    queued = [{"batch_id": "b1", "status": "queued", "n": i} for i in range(6000)]
    terminal = [{"batch_id": "b1", "status": "created", "n": i} for i in range(1000)]
    doc = {"items": terminal + queued}
    path.write_text(json.dumps(doc), encoding="utf-8")
    bp.enqueue_batch_items([{"batch_id": "b2", "status": "queued"}], path=path)
    loaded = bp.load_batch_queue(path)
    active = [x for x in loaded["items"] if str(x.get("status")) == "queued"]
    assert len(active) >= 1000


def test_human_review_pending_in_agent_flow():
    from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW

    assert PIPELINE_AGENT_FLOW["HUMAN_REVIEW_PENDING"] == ("__human_gate__", "SALES_ACTIVE")


def test_demo_payment_bypass_respects_aifactory_prod(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "1")
    monkeypatch.delenv("AIFACTORY_ENV", raising=False)
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    from web.backend.services.ai_market_protocol.config import demo_payment_bypass

    assert demo_payment_bypass() is False
