"""Scratch repro: a MANDATED subcontracting allowance taken by an A2A task is journaled as an
ordinary "hold", so the A2A crash recovery releases it and gives the whole allowance back to
the mandate counters, and reports "nothing was charged" although a child was captured."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import time

sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")

import httpx
import pytest

from tests._mandate_kit import HUB, balance, hub, list_provider, list_static, mandated_invoke, setup_mandate
from tests.test_subcontract import Providers, job_headers, WEATHER, BRIEF
from aimarket_hub import a2a, a2a_tasks, subcontract
from aimarket_hub.a2a_tasks import A2ATaskStore


def test_mandated_allowance_is_journaled_as_hold_and_recovery_misreports(monkeypatch, tmp_path):
    monkeypatch.setattr(a2a_tasks, "_SWEEP_EVERY_S", 0.0)
    with hub(monkeypatch, tmp_path) as (client, db):
        providers = Providers(client.app_ref)
        import aimarket_hub.outbound_http as outbound

        monkeypatch.setattr(outbound, "safe_post", providers.post)
        list_static(db, capability_id="wx.read@v1", product_id="wx", price=0.001)
        list_provider(db, "brief.make@v1", "brief", 0.010, url="https://brief.test/invoke")

        m = setup_mandate(client, db, per_day=100_000,
                          subcontract={"perCallAllowance": 5_000, "maxDepth": 1})
        payload = {**BRIEF, "subcontract": {"allowance_usd": 0.005}}
        raw = json.dumps(payload).encode()
        store = A2ATaskStore(db._conn)
        row, _ = store.create(principal=a2a._principal("mandate", m["digest"]), context_id="c1",
                              message_id="m1", product_id=BRIEF["product_id"],
                              capability_id=BRIEF["capability_id"], source_hub="local",
                              invoke_b64=base64.b64encode(raw).decode(),
                              invoke_sha256=hashlib.sha256(raw).hexdigest(), history=[])
        task_id = row["task_id"]
        store.started(task_id, rail="credits")
        seen: dict = {}

        async def brief(body, headers, p):
            r = await p.buy(WEATHER, job_headers(headers))
            assert r.status_code == 200, r.text
            seen["charges"] = store.charges(task_id)
            # The process "dies" here: its lease lapses and the hub's sweep takes the task over.
            db._conn.execute("UPDATE a2a_tasks SET lease_until = ? WHERE task_id = ?", (time.time() - 1, task_id))
            db._conn.commit()
            transport = httpx.ASGITransport(app=p.app)
            async with httpx.AsyncClient(transport=transport, base_url=HUB) as c:
                await c.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "ListTasks", "params": {}},
                             headers={"A2A-Version": "1.0"})
            t = store.get(task_id)
            seen["state"] = t["task_state"]
            seen["recovered"] = json.loads(t["metadata_json"])["aimarket"]["recovered"]
            seen["usage"] = client.app_ref and None
            holds = db._conn.execute("SELECT receipt_id, status, amount_mc, parent_receipt_id FROM credit_holds").fetchall()
            seen["holds"] = [dict(h) for h in holds]
            mh = db._conn.execute("SELECT receipt_id, status, amount_micro FROM mandate_holds").fetchall()
            seen["mandate_holds"] = [dict(h) for h in mh]
            usage = db._conn.execute("SELECT period, spent_micro FROM mandate_usage WHERE period LIKE 'd:%'").fetchall()
            seen["spent_today_micro"] = sum(int(u["spent_micro"]) for u in usage)
            seen["balance_after_recovery"] = balance(db, m["account"])
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        r = mandated_invoke(client, m, payload, extra_headers={
            a2a.TASK_HEADER: task_id, a2a.INTERNAL_HEADER: a2a.INTERNAL_SECRET})

        print("\ncharges journaled:", seen["charges"])
        print("task after recovery:", seen["state"], seen["recovered"])
        print("credit holds after recovery:", seen["holds"])
        print("mandate holds after recovery:", seen["mandate_holds"])
        print("mandate spent today (uUSD) after recovery:", seen["spent_today_micro"])
        print("balance after recovery:", seen["balance_after_recovery"])
        print("root invoke answer:", r.status_code, r.text[:300])
        print("final balance:", balance(db, m["account"]))
        usage = client.get(f"/ai-market/v2/mandates/{m['digest']}", headers={"X-API-Key": m["api_key"]}).json()["usage"]
        print("final mandate usage:", usage)

        kinds = {c["receipt_id"]: c["kind"] for c in seen["charges"]}
        alw = [rid for rid in kinds if rid.startswith("alw_")]
        assert alw, "the allowance receipt was journaled"
        # BUG 1: the allowance is journaled as an ordinary hold, not "allowance".
        assert kinds[alw[0]] == "hold"
        # BUG 2: recovery therefore says nothing was charged ...
        assert seen["recovered"]["outcome"] == "released"
        assert seen["state"] == "TASK_STATE_AUTH_REQUIRED"
        # ... although the child (wx.read, $0.001) was captured from the buyer's money
        child = [h for h in seen["holds"] if h["parent_receipt_id"]]
        assert child and child[0]["status"] == "captured"
        # BUG 3: and the mandate counters were given back the WHOLE allowance, so the child's
        # spend is no longer counted against perDay/total.
        assert seen["spent_today_micro"] == 0
        assert seen["balance_after_recovery"] == pytest.approx(1.0 - 0.001)
