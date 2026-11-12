"""Refund of an old, already-consumed Watch payment takes back the NEW period the team just paid for."""
from __future__ import annotations

import socket
from dataclasses import replace
from datetime import timedelta

from fastapi.testclient import TestClient

from histor import watch_paid
from histor.app import create_app
from tests.conftest import make_target
from tests.test_app import TOOLS, target_id
from tests.test_security_events import public_resolver
from tests.test_watch_paid import FakeStripe, WHSEC, HOOK, signed, auth


def test_refund_of_consumed_period_eats_new_paid_period(world, monkeypatch):
    world["mcp"].tools["/a"] = TOOLS
    world["targets"] += [make_target("io.example/weather", "/a")]
    world["services"].crawler.run()
    s = world["services"]
    s.settings = replace(s.settings, stripe_secret_key="sk_test_fixture", stripe_webhook_secret=WHSEC,
                         public_base="https://histor.example")
    s.stripe = stripe = FakeStripe()
    monkeypatch.setattr(socket, "getaddrinfo", public_resolver)
    with TestClient(create_app(s)) as client:
        sub = client.post("/api/v1/watch/subscriptions",
                          json={"watch": [target_id(world, "io.example/weather")], "url": HOOK}).json()
        token = sub["manageToken"]
        # Payment A: first 30 days.
        a = stripe.pay(next(iter(stripe.sessions)))
        assert watch_paid.settle(s.store, s.settings, a["client_reference_id"], a) == "paid"
        # 31 days pass: A's period is fully consumed, the subscription lapses.
        past = watch_paid._ts(watch_paid._now() - timedelta(days=1))
        with s.store.db.transaction() as tx:
            tx.execute("UPDATE watch_subscriptions SET active_until=? WHERE id=?", (past, sub["id"]))
        assert client.get(f"/api/v1/watch/subscriptions/{sub['id']}", headers=auth(token)).json()["state"] == "lapsed"
        # Payment B: the team pays $29 again for the next 30 days.
        client.post(f"/api/v1/watch/subscriptions/{sub['id']}/renew", headers=auth(token))
        b = stripe.pay(list(stripe.sessions)[1])
        assert watch_paid.settle(s.store, s.settings, b["client_reference_id"], b) == "paid"
        view = client.get(f"/api/v1/watch/subscriptions/{sub['id']}", headers=auth(token)).json()
        assert view["state"] == "active"
        new_end = watch_paid._parse(view["activeUntil"])
        assert (new_end - watch_paid._now()).days >= 29
        # The operator refunds the OLD payment A (e.g. goodwill for last month's outage).
        refund = {"id": "ch_a", "object": "charge", "payment_intent": a["payment_intent"], "amount_refunded": 2900}
        body, sig = signed({"id": "evt_ra", "type": "charge.refunded", "data": {"object": refund}})
        assert client.post("/api/v1/watch/stripe", content=body,
                           headers={"Stripe-Signature": sig}).json()["outcome"] == "refunded"
        after = client.get(f"/api/v1/watch/subscriptions/{sub['id']}", headers=auth(token)).json()
        statuses = {p["id"]: p["status"] for p in after["payments"]}
        # B is still paid and was never refunded ...
        assert statuses[b["client_reference_id"]] == "paid"
        # ... yet the subscription is no longer active: B's 30 days were taken back for A.
        print("state after refunding A:", after["state"], "activeUntil:", after["activeUntil"])
        assert after["state"] == "lapsed"
        assert watch_paid.deliver_paid(s.store, s.settings, resolver=public_resolver)["subscriptions"] == 0
