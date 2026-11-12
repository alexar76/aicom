"""Scratch repro: if the mandate settle of an allowance fails once (after the credit release
succeeded), no sweep ever settles that mandate hold: the full allowance stays counted."""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")

from tests._mandate_kit import HUB, balance, hub, list_provider, list_static, mandated_invoke, setup_mandate
from tests.test_subcontract import Providers, job_headers, WEATHER, BRIEF
from aimarket_hub import invoke_funding, mandates, subcontract, credits


def test_allowance_mandate_hold_never_swept(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        providers = Providers(client.app_ref)
        import aimarket_hub.outbound_http as outbound

        monkeypatch.setattr(outbound, "safe_post", providers.post)
        list_static(db, capability_id="wx.read@v1", product_id="wx", price=0.001)
        list_provider(db, "brief.make@v1", "brief", 0.010, url="https://brief.test/invoke")
        m = setup_mandate(client, db, per_day=100_000, subcontract={"perCallAllowance": 5_000, "maxDepth": 1})

        async def brief(body, headers, p):
            r = await p.buy(WEATHER, job_headers(headers))
            assert r.status_code == 200, r.text
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        real_settle = mandates.MandateStore.settle

        def flaky(self, receipt_id, keep_micro):
            if receipt_id.startswith("alw_"):
                raise RuntimeError("database is locked")   # one transient failure
            return real_settle(self, receipt_id, keep_micro)

        monkeypatch.setattr(mandates.MandateStore, "settle", flaky)
        r = mandated_invoke(client, m, {**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert r.status_code == 200, r.text
        monkeypatch.setattr(mandates.MandateStore, "settle", real_settle)

        store = mandates.MandateStore(db._conn, HUB)
        jobs = subcontract.JobStore(db._conn, None, HUB)
        ledger = credits.CreditsLedger(db._conn)
        later = time.time() + 6 * 3600
        for _ in range(3):
            invoke_funding.sweep_stale_credit_holds(credits_ledger=ledger, store=store, now=later)
            invoke_funding.sweep_stale_allowances(credits_ledger=ledger, store=store, jobs=jobs, now=later)
            invoke_funding.sweep_orphaned_child_holds(credits_ledger=ledger, store=store, now=later)
        mh = [dict(x) for x in db._conn.execute("SELECT receipt_id, status, amount_micro FROM mandate_holds").fetchall()]
        ch = [dict(x) for x in db._conn.execute("SELECT receipt_id, status, amount_mc FROM credit_holds").fetchall()]
        usage = client.get(f"/ai-market/v2/mandates/{m['digest']}", headers={"X-API-Key": m["api_key"]}).json()["usage"]
        print("\nmandate holds after every sweep:", mh)
        print("credit holds:", ch)
        print("usage:", usage, "balance:", balance(db, m["account"]))
        alw = [h for h in mh if h["receipt_id"].startswith("alw_")][0]
        assert alw["status"] == "held" and alw["amount_micro"] == 5_000   # stuck forever
        # money actually spent: brief 0.010 + child 0.001; mandate counts 0.010 + 0.005
        assert usage["spent_today_usd"] == 0.015
        assert balance(db, m["account"]) == 1.0 - 0.011
