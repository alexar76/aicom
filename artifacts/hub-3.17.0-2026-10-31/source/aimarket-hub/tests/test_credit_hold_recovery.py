from __future__ import annotations

import pytest
from aimarket_hub import credits, invoke_funding, mandates, subcontract

from tests._mandate_kit import HUB, balance, hub, setup_mandate
from tests.test_verified_settlement import _insert_verifying_row


def test_abandoned_credit_and_mandate_holds_recover_once(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        m = setup_mandate(client, db)
        ledger = credits.CreditsLedger(db._conn)
        store = mandates.MandateStore(db._conn, HUB)
        chain = store.chain(m["digest"])
        for receipt in ("abandoned", "captured", "before_credit_hold", "recent"):
            store.reserve(chain, receipt_id=receipt, amount_micro=4000, product_id="demo")
            if receipt != "before_credit_hold":
                assert not ledger.hold(m["account"], 0.004, receipt).get("error")
        ledger.capture_hold("captured")
        for table in ("credit_holds", "mandate_holds"):
            db._conn.execute(f"UPDATE {table} SET created_at = '2000-01-01 00:00:00' WHERE receipt_id != 'recent'")
        db._conn.commit()
        assert invoke_funding.sweep_stale_credit_holds(credits_ledger=ledger, store=store) == 1
        assert invoke_funding.sweep_stale_credit_holds(credits_ledger=ledger, store=store) == 0
        assert balance(db, m["account"]) == pytest.approx(0.992)
        assert ledger.hold_status("recent")["status"] == "held"
        states = {r["receipt_id"]: r["status"] for r in db._conn.execute("SELECT * FROM mandate_holds").fetchall()}
        assert states == {"abandoned": "released", "captured": "captured",
                          "before_credit_hold": "released", "recent": "held"}
        usage = db._conn.execute("SELECT spent_micro FROM mandate_usage WHERE digest = ?", (m["digest"],)).fetchall()
        assert usage and all(r["spent_micro"] == 8000 for r in usage)


def test_reaper_leaves_verification_bonds_and_allowances_to_their_owner(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        m = setup_mandate(client, db)
        ledger = credits.CreditsLedger(db._conn)
        store = mandates.MandateStore(db._conn, HUB)
        for nonce in ("verification", "appeal_verification", "allowance", "child"):
            ledger.hold(m["account"], 0.004, nonce)
        _insert_verifying_row(db, nonce="verification")
        from aimarket_hub.signing import Signer

        jobs = subcontract.JobStore(db._conn, Signer(tmp_path / "key"), HUB)
        jobs.open_root(product_id="p", capability_id="p.work@v1", allowance_micro=4000,
                       allowance_receipt="allowance", account_id=m["account"])
        db._conn.execute("UPDATE credit_holds SET parent_receipt_id = 'allowance' WHERE receipt_id = 'child'")
        db._conn.execute("UPDATE credit_holds SET created_at = '2000-01-01 00:00:00'")
        db._conn.commit()
        assert invoke_funding.sweep_stale_credit_holds(credits_ledger=ledger, store=store) == 0
        assert all(ledger.hold_status(n)["status"] == "held" for n in (
            "verification", "appeal_verification", "allowance", "child"))


def test_the_age_of_a_hold_is_read_with_its_time_zone(monkeypatch, tmp_path):
    """PostgreSQL writes NOW() as text in the SESSION time zone. Compared as a string with a
    UTC cutoff, a hold seconds old in New York read as hours old and was released mid-call;
    an old one written in Moscow time was never released. The age is parsed, not compared."""
    import time as _time
    from datetime import datetime, timedelta, timezone

    with hub(monkeypatch, tmp_path) as (client, db):
        m = setup_mandate(client, db)
        ledger = credits.CreditsLedger(db._conn)
        store = mandates.MandateStore(db._conn, HUB)
        now = _time.time()
        new_york = timezone(timedelta(hours=-4))
        moscow = timezone(timedelta(hours=3))
        cases = {
            "fresh_west": datetime.fromtimestamp(now - 5, new_york).isoformat(sep=" "),
            "old_east": datetime.fromtimestamp(now - 7200, moscow).isoformat(sep=" "),
            "garbage": "not a time",
        }
        for receipt, stamp in cases.items():
            assert not ledger.hold(m["account"], 0.001, receipt).get("error")
            db._conn.execute("UPDATE credit_holds SET created_at = ? WHERE receipt_id = ?", (stamp, receipt))
        db._conn.commit()
        assert invoke_funding.sweep_stale_credit_holds(credits_ledger=ledger, store=store, now=now) == 1
        assert ledger.hold_status("fresh_west")["status"] == "held"
        assert ledger.hold_status("old_east")["status"] == "released"
        assert ledger.hold_status("garbage")["status"] == "held"   # unreadable: never swept


def test_a_hold_freed_under_a_running_call_fails_closed(monkeypatch, tmp_path):
    """If anything releases the reservation while the provider runs, the capture answers
    "already released" with no error field. Serving the answer then would give paid work
    away; the invoke must refuse instead, and nothing may be charged."""
    from tests._mandate_kit import funded_account, list_provider
    from tests.test_subcontract import BRIEF, Providers

    with hub(monkeypatch, tmp_path) as (client, db):
        providers = Providers(client.app_ref)
        import aimarket_hub.outbound_http as outbound

        monkeypatch.setattr(outbound, "safe_post", providers.post)
        list_provider(db, "brief.make@v1", "brief", 0.010, url="https://brief.test/invoke")
        ledger = credits.CreditsLedger(db._conn)

        async def brief(body, headers, p):
            for row in db._conn.execute("SELECT receipt_id FROM credit_holds WHERE status = 'held'").fetchall():
                ledger.release_hold(row["receipt_id"])
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        account, api_key = funded_account(client, db, 1.0)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=BRIEF)
        assert r.status_code == 502, r.text
        assert balance(db, account) == pytest.approx(1.0)


def test_an_abandoned_credit_hold_is_released_when_the_hub_starts(monkeypatch, tmp_path):
    """A crash between the hold and its capture leaves the buyer's credit frozen. The sweep
    runs once at startup — a restart after a crash is exactly when such holds exist."""
    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.signing import Signer
    from fastapi.testclient import TestClient

    from tests._mandate_kit import funded_account

    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 1.0)
        ledger = credits.CreditsLedger(db._conn)
        assert not ledger.hold(account, 0.004, "crashed_invoke").get("error")
        db._conn.execute("UPDATE credit_holds SET created_at = '2000-01-01 00:00:00'")
        db._conn.commit()
        assert balance(db, account) == pytest.approx(0.996)
        config = HubConfig()
        config.hub_url = HUB
        config.db_path = str(tmp_path / "restarted.db")
        config.signing_key_path = str(tmp_path / "restarted.key")
        restarted = create_app(config=config, db=db, signer=Signer(tmp_path / "restarted.key"))
        with TestClient(restarted, base_url=HUB):
            pass
        assert ledger.hold_status("crashed_invoke")["status"] == "released"
        assert balance(db, account) == pytest.approx(1.0)
