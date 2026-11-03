"""Card top-ups through Stripe Checkout (card_topup.py, docs/credits-topup.md).

Stripe is faked at its HTTP edge; everything on the hub's side is real — the routes, the
store, the signature check, the ledger. The property that matters: money lands once, on the
account the hub bound when it opened the checkout, for exactly the amount it opened it for —
whatever an event claims.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import time

import pytest

from tests._mandate_kit import (  # noqa: E402
    ADMIN_TOKEN, balance, funded_account, hub, list_static, mandated_invoke, setup_mandate,
)
from aimarket_hub import card_topup

WHSEC = "whsec_test_secret"
ENV = {"AIMARKET_CARD_TOPUP_ENABLED": "1", "STRIPE_SECRET_KEY": "sk_test_hub", "STRIPE_WEBHOOK_SECRET": WHSEC}


class FakeStripe:
    """Checkout Sessions as Stripe keeps them, behind the one function the hub calls."""

    def __init__(self, *, livemode: bool = False, fail: str = ""):
        self.sessions: dict[str, dict] = {}
        self.versions: list[str] = []
        self.calls: list[tuple[str, str, dict | None, str]] = []
        self.livemode = livemode
        self.fail = fail

    def __call__(self, method, path, *, form=None, idempotency_key="", version=card_topup.STRIPE_VERSION):
        self.calls.append((method, path, form, idempotency_key))
        self.versions.append(version)
        if self.fail == "raise":
            raise ConnectionError("stripe down")
        if self.fail == "refuse":
            return 400, {"error": {"message": "amount too small"}}
        if method == "POST" and path == "/v1/checkout/sessions":
            sid = f"cs_test_{len(self.sessions) + 1:04d}"
            item = form["line_items"][0]
            session = {"id": sid, "object": "checkout.session", "url": f"https://checkout.stripe.test/{sid}",
                       "client_reference_id": form["client_reference_id"], "metadata": form["metadata"],
                       "amount_total": item["price_data"]["unit_amount"], "currency": "usd",
                       "payment_status": "unpaid", "status": "open", "livemode": self.livemode,
                       "payment_intent": None}
            self.sessions[sid] = session
            return 200, dict(session)
        if method == "GET" and path.startswith("/v1/checkout/sessions/"):
            sid = path.rsplit("/", 1)[1]
            return (200, dict(self.sessions[sid])) if sid in self.sessions else (404, {})
        if method == "GET" and path.startswith("/v1/checkout/sessions?"):
            from urllib.parse import parse_qs, urlsplit
            pi = parse_qs(urlsplit(path).query)["payment_intent"][0]
            return 200, {"data": [dict(s) for s in self.sessions.values() if s["payment_intent"] == pi]}
        return 404, {}

    def pay(self, sid: str) -> dict:
        self.sessions[sid].update(payment_status="paid", status="complete", payment_intent=f"pi_{sid}")
        return dict(self.sessions[sid])


@pytest.fixture
def stripe(monkeypatch):
    fake = FakeStripe()
    monkeypatch.setattr(card_topup, "_stripe_request", fake)
    return fake


def sign(payload: bytes, *, secret: str = WHSEC, t: int | None = None) -> str:
    t = int(time.time()) if t is None else t
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def event(kind: str, obj: dict) -> bytes:
    return json.dumps({"id": "evt_1", "type": kind, "data": {"object": obj}}).encode()


def deliver(client, payload: bytes, signature: str | None = None):
    return client.post("/ai-market/v2/stripe/webhook", content=payload,
                       headers={"Stripe-Signature": signature or sign(payload), "Content-Type": "application/json"})


def open_checkout(client, key: str, usd=10):
    return client.post("/ai-market/v2/account/topup/card", json={"amount_usd": usd}, headers={"X-API-Key": key})


class TestDoor:
    def test_off_by_default_and_says_why(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            block = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup_card"]
            assert block["enabled"] is False and "AIMARKET_CARD_TOPUP_ENABLED" in block["reason"]
            _account, key = funded_account(client, db, 0.0)
            r = open_checkout(client, key)
            assert r.status_code == 503 and r.json()["error"] == "card_topup_unavailable"

    def test_without_the_webhook_secret_the_door_stays_shut(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path, AIMARKET_CARD_TOPUP_ENABLED="1", STRIPE_SECRET_KEY="sk_test_x") as (client, db):
            block = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup_card"]
            assert block["enabled"] is False and "STRIPE_WEBHOOK_SECRET" in block["reason"]

    def test_secrets_may_come_from_files(self, monkeypatch, tmp_path):
        (tmp_path / "sk").write_text("sk_test_from_file\n")
        (tmp_path / "wh").write_text(WHSEC + "\n")
        monkeypatch.setenv("STRIPE_SECRET_KEY_FILE", str(tmp_path / "sk"))
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET_FILE", str(tmp_path / "wh"))
        assert card_topup.secret_key() == "sk_test_from_file" and card_topup.webhook_secret() == WHSEC

    def test_well_known_publishes_the_terms(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            block = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup_card"]
            assert block["enabled"] is True and block["currency"] == "usd"
            assert block["create"] == "/ai-market/v2/account/topup/card"
            assert (block["min_usd"], block["max_usd"], block["daily_usd"]) == (5.0, 100.0, 200.0)


class TestFlow:
    def test_paid_checkout_credits_the_bound_account_once(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            account, key = funded_account(client, db, 0.0)
            r = open_checkout(client, key, 10)
            assert r.status_code == 201, r.text
            opened = r.json()
            assert opened["checkout_url"].startswith("https://checkout.stripe.test/")
            assert opened["amount_usd"] == 10 and opened["charge_usd"] == 10 and opened["fee_usd"] == 0
            (_m, _p, form, idem), = stripe.calls
            assert idem == opened["topup_id"] and form["client_reference_id"] == opened["topup_id"]
            assert form["line_items"][0]["price_data"]["unit_amount"] == 1000
            assert account not in json.dumps(form), "Stripe learns the top-up id, not the account"

            sid = next(iter(stripe.sessions))
            paid = event("checkout.session.completed", stripe.pay(sid))
            r = deliver(client, paid)
            assert r.status_code == 200 and r.json()["outcome"] == "credited"
            assert balance(db, account) == pytest.approx(10.0)
            # Stripe redelivers: the same money is not credited twice.
            assert deliver(client, paid).json()["outcome"] == "already_credited"
            assert balance(db, account) == pytest.approx(10.0)

            status = client.get(f"/ai-market/v2/card-topups/{opened['topup_id']}").json()
            assert status["status"] == "credited" and status["credited_usd"] == 10
            assert "account_id" not in status and "checkout_url" not in status
            mine = client.get(f"/ai-market/v2/card-topups/{opened['topup_id']}", headers={"X-API-Key": key}).json()
            assert mine["account_id"] == account
            listed = client.get("/ai-market/v2/account/topups", headers={"X-API-Key": key}).json()
            assert [t["topup_id"] for t in listed["card_topups"]] == [opened["topup_id"]]

    def test_two_deliveries_racing_past_the_status_check_still_credit_once(self, monkeypatch, tmp_path, stripe):
        """The row's status is the first wall; the ledger reference (the session id) is the
        second. Simulate the loser of a race: it read the row while it was still open."""
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            account, key = funded_account(client, db, 0.0)
            open_checkout(client, key, 10)
            paid = event("checkout.session.completed", stripe.pay(next(iter(stripe.sessions))))
            assert deliver(client, paid).json()["outcome"] == "credited"
            db._conn.execute("UPDATE card_topups SET status = 'open'")
            db._conn.commit()
            r = deliver(client, paid)
            assert r.json()["outcome"] == "credited"
            assert balance(db, account) == pytest.approx(10.0)

    def test_an_unpaid_or_async_pending_session_credits_nothing(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            account, key = funded_account(client, db, 0.0)
            open_checkout(client, key, 10)
            sid = next(iter(stripe.sessions))
            r = deliver(client, event("checkout.session.completed", stripe.sessions[sid]))
            assert r.json()["outcome"] == "pending"
            assert balance(db, account) == 0

    def test_the_card_fee_is_charged_on_top_and_not_credited(self, monkeypatch, tmp_path, stripe):
        env = {**ENV, "AIMARKET_CARD_TOPUP_FEE_PCT": "2.9", "AIMARKET_CARD_TOPUP_FEE_FIXED_USD": "0.30"}
        with hub(monkeypatch, tmp_path, **env) as (client, db):
            account, key = funded_account(client, db, 0.0)
            opened = open_checkout(client, key, 10).json()
            assert opened["charge_usd"] == pytest.approx(10.59)   # 10 + 0.29 + 0.30
            assert stripe.calls[0][2]["line_items"][0]["price_data"]["unit_amount"] == 1059
            sid = next(iter(stripe.sessions))
            deliver(client, event("checkout.session.completed", stripe.pay(sid)))
            assert balance(db, account) == pytest.approx(10.0)

    def test_a_lost_webhook_is_recovered_by_refresh(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            account, key = funded_account(client, db, 0.0)
            opened = open_checkout(client, key, 25).json()
            url = f"/ai-market/v2/card-topups/{opened['topup_id']}/refresh"
            assert client.post(url).json()["outcome"] == "pending"
            stripe.pay(next(iter(stripe.sessions)))
            r = client.post(url)
            assert r.json()["outcome"] == "credited" and r.json()["status"] == "credited"
            assert balance(db, account) == pytest.approx(25.0)
            assert client.post(url).json()["outcome"] == "credited"     # nothing more to do
            assert balance(db, account) == pytest.approx(25.0)


class TestWhatAnEventCannotDo:
    def _paid_session(self, client, db, stripe):
        account, key = funded_account(client, db, 0.0)
        open_checkout(client, key, 10)
        sid = next(iter(stripe.sessions))
        return account, stripe.pay(sid)

    def test_no_valid_signature_no_credit(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            account, session = self._paid_session(client, db, stripe)
            payload = event("checkout.session.completed", session)
            assert deliver(client, payload, sign(payload, secret="whsec_other")).status_code == 400
            assert deliver(client, payload, sign(payload, t=int(time.time()) - 3600)).status_code == 400
            assert deliver(client, payload, "t=1,v1=").status_code == 400
            tampered = payload.replace(b'"amount_total": 1000', b'"amount_total": 1001')
            assert deliver(client, tampered, sign(payload)).status_code == 400
            assert balance(db, account) == 0

    @pytest.mark.parametrize("change, reason", [
        ({"amount_total": 100_000}, "amount"),
        ({"currency": "eur"}, "currency"),
        ({"id": "cs_test_9999"}, "session"),
    ])
    def test_a_signed_event_still_cannot_choose_the_amount_or_session(self, monkeypatch, tmp_path, stripe,
                                                                      change, reason):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            account, session = self._paid_session(client, db, stripe)
            r = deliver(client, event("checkout.session.completed", {**session, **change}))
            assert r.status_code == 200 and r.json()["outcome"] == "refused"
            assert balance(db, account) == 0

    def test_test_money_never_credits_a_live_hub(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **{**ENV, "STRIPE_SECRET_KEY": "sk_live_hub"}) as (client, db):
            account, session = self._paid_session(client, db, stripe)
            assert session["livemode"] is False
            assert deliver(client, event("checkout.session.completed", session)).json()["outcome"] == "refused"
            assert balance(db, account) == 0

    def test_events_about_something_else_are_acknowledged_and_ignored(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            r = deliver(client, event("checkout.session.completed",
                                      {"id": "cs_x", "client_reference_id": "ctp_" + "0" * 24, "payment_status": "paid"}))
            assert r.status_code == 200 and r.json()["outcome"] == "ignored"
            assert deliver(client, event("invoice.paid", {"id": "in_1"})).json()["outcome"] == "ignored"

    def test_a_dispute_is_recorded_on_the_topup(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            account, session = self._paid_session(client, db, stripe)
            deliver(client, event("checkout.session.completed", session))
            r = deliver(client, event("charge.dispute.created",
                                      {"id": "dp_1", "payment_intent": session["payment_intent"], "reason": "fraudulent"}))
            assert r.json()["outcome"] == "disputed"
            row = db._conn.execute("SELECT status, detail FROM card_topups").fetchone()
            assert row["status"] == "disputed" and "fraudulent" in row["detail"]


class TestLimits:
    def test_amount_bounds(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            _account, key = funded_account(client, db, 0.0)
            assert open_checkout(client, key, 1).json()["error"] == "amount_out_of_range"
            assert open_checkout(client, key, 500).json()["error"] == "amount_out_of_range"
            assert open_checkout(client, key, 10.005).json()["error"] == "amount_invalid"
            assert stripe.calls == [], "a refused amount never reaches Stripe"

    def test_open_checkouts_count_toward_the_daily_limit(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **{**ENV, "AIMARKET_CARD_TOPUP_DAILY_USD": "30"}) as (client, db):
            _account, key = funded_account(client, db, 0.0)
            assert open_checkout(client, key, 20).status_code == 201
            r = open_checkout(client, key, 20)
            assert r.status_code == 429 and r.json()["error"] == "daily_topup_limit"
            assert open_checkout(client, key, 10).status_code == 201

    def test_racing_checkouts_never_pass_the_daily_limit(self, monkeypatch, tmp_path, stripe):
        """Six requests of $100 at once against a $200 limit: each passed the check before
        any had a row, and all six opened."""
        import threading

        from aimarket_hub.topup import TopupError

        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            account, _key = funded_account(client, db, 0.0)
            store = card_topup.CardTopupStore(db._conn)
            for _ in range(5):
                db._conn.execute("DELETE FROM card_topups")
                db._conn.commit()
                barrier = threading.Barrier(6)

                def go() -> None:
                    barrier.wait(timeout=10)
                    with contextlib.suppress(TopupError):
                        card_topup.create(store=store, account_id=account, amount_usd=100,
                                          hub_url="https://hub.test", stripe=stripe)

                threads = [threading.Thread(target=go) for _ in range(6)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=20)
                assert store.committed_cents(account) <= 20_000
                assert db._conn.execute("SELECT COUNT(*) AS n FROM card_topups WHERE status = 'new'").fetchone()["n"] == 0

    def test_a_refunded_topup_still_counts_toward_the_limit(self, monkeypatch, tmp_path, stripe):
        """The credit stays when the money goes back, so the limit on what a card can turn
        into credit is not freed by a refund (or by Managed Payments refunding on its own)."""
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            _account, key = funded_account(client, db, 0.0)
            for _ in range(2):
                assert open_checkout(client, key, 100).status_code == 201
                paid = stripe.pay(list(stripe.sessions)[-1])
                assert deliver(client, event("checkout.session.completed", paid)).json()["outcome"] == "credited"
            assert open_checkout(client, key, 100).status_code == 429
            refund = {"id": "ch_1", "payment_intent": paid["payment_intent"], "amount_refunded": 10_000}
            assert deliver(client, event("charge.refunded", refund)).json()["outcome"] == "refunded"
            assert open_checkout(client, key, 100).status_code == 401  # frozen for operator review
            assert client.post(f"/ai-market/v2/accounts/{_account}/status", json={"status": "active"},
                               headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}).status_code == 200
            assert open_checkout(client, key, 100).status_code == 429

    def test_a_key_is_required(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            assert client.post("/ai-market/v2/account/topup/card", json={"amount_usd": 10}).status_code == 401

    @pytest.mark.parametrize("fail, status", [("raise", 503), ("refuse", 502)])
    def test_a_stripe_failure_charges_nothing_and_says_so(self, monkeypatch, tmp_path, fail, status):
        monkeypatch.setattr(card_topup, "_stripe_request", FakeStripe(fail=fail))
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            _account, key = funded_account(client, db, 0.0)
            r = open_checkout(client, key, 10)
            assert r.status_code == status and "nothing was charged" in r.json()["detail"]
            assert db._conn.execute("SELECT status FROM card_topups").fetchone()["status"] == "failed"


def test_a_checkout_handed_out_keeps_its_session_whatever_another_request_does(monkeypatch, tmp_path, stripe):
    """On SQLite every request shares one connection. A statement that fails on another
    request's thread rolls back whatever is pending on it; if the row's session id was
    written and committed as two steps, a failure between them lost it — and the checkout
    the buyer was handed, and paid, could never be credited."""
    import sqlite3
    import threading

    with hub(monkeypatch, tmp_path, **ENV) as (client, db):
        account, key = funded_account(client, db, 0.0)
        backend = db._conn
        real_commit, real_opened = backend.commit, card_topup.CardTopupStore.opened
        armed = []

        def failing_statement() -> None:
            with contextlib.suppress(sqlite3.Error, Exception):
                backend.execute("INSERT INTO card_topups (topup_id) VALUES (NULL)")

        def commit():
            if armed:
                armed.clear()
                other = threading.Thread(target=failing_statement)
                other.start()
                other.join(timeout=0.3)   # runs now unless this write still holds the connection
            return real_commit()

        def opened(self, *a, **k):
            armed.append(1)
            return real_opened(self, *a, **k)

        monkeypatch.setattr(backend, "commit", commit)
        monkeypatch.setattr(card_topup.CardTopupStore, "opened", opened)
        topup_id = open_checkout(client, key, 10).json()["topup_id"]
        monkeypatch.setattr(card_topup.CardTopupStore, "opened", real_opened)
        assert db._conn.execute("SELECT status FROM card_topups WHERE topup_id = ?",
                                (topup_id,)).fetchone()["status"] == "open"
        paid = stripe.pay(list(stripe.sessions)[-1])
        assert deliver(client, event("checkout.session.completed", paid)).json()["outcome"] == "credited"
        assert balance(db, account) == pytest.approx(10.0)


def test_signature_check_accepts_a_rolled_secret_and_rejects_trailing_junk():
    payload = b'{"a":1}'
    t = int(time.time())
    good = hmac.new(WHSEC.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    assert card_topup.verify_signature(payload, f"t={t},v1={'0' * 64},v1={good}", WHSEC)
    assert not card_topup.verify_signature(payload, f"t={t},v1={good}x", WHSEC)
    assert not card_topup.verify_signature(payload, f"t={t},v0={good}", WHSEC)
    assert not card_topup.verify_signature(payload, f"t={t},v1={good}", "")


def test_the_real_stripe_client_sends_what_stripe_reads(monkeypatch):
    """The HTTP edge itself, not a fake of it: the form-encoded body, the key, the idempotency
    key. Every other test replaces `_stripe_request`; this one runs it against a mock transport
    (a list of pairs passed to httpx as `data=` raised TypeError, found against the sandbox)."""
    import httpx
    from urllib.parse import parse_qsl

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(method=request.method, url=str(request.url), headers=dict(request.headers),
                    form=parse_qsl(request.content.decode()))
        return httpx.Response(200, json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "rk_test_client")
    status, body = card_topup._stripe_request("POST", "/v1/checkout/sessions", idempotency_key="ctp_x", form={
        "mode": "payment", "metadata": {"topup_id": "ctp_x"},
        "line_items": [{"quantity": 1, "price_data": {"currency": "usd", "unit_amount": 500}}]})
    assert status == 200 and body["id"] == "cs_test_1"
    assert seen["url"] == "https://api.stripe.com/v1/checkout/sessions" and seen["method"] == "POST"
    assert seen["headers"]["authorization"] == "Bearer rk_test_client"
    assert seen["headers"]["idempotency-key"] == "ctp_x"
    assert seen["headers"]["content-type"] == "application/x-www-form-urlencoded"
    assert ("line_items[0][price_data][unit_amount]", "500") in seen["form"]
    assert ("metadata[topup_id]", "ctp_x") in seen["form"]
    status, _ = card_topup._stripe_request("GET", "/v1/checkout/sessions/cs_test_1")
    assert status == 200 and seen["method"] == "GET" and seen["form"] == []


class TestTaxModes:
    """AIMARKET_CARD_TOPUP_TAX: who computes the sales tax. The credit is always the amount asked."""

    def _paid(self, stripe, *, subtotal, total, tax):
        sid = next(iter(stripe.sessions))
        session = stripe.pay(sid)
        session.update(amount_subtotal=subtotal, amount_total=total, total_details={"amount_tax": tax})
        stripe.sessions[sid].update(session)
        return session

    def test_off_is_the_default_and_sends_no_tax_parameters(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV) as (client, db):
            _account, key = funded_account(client, db, 0.0)
            assert open_checkout(client, key, 10).status_code == 201
            form = stripe.calls[0][2]
            assert "automatic_tax" not in form and "managed_payments" not in form
            assert "tax_code" not in form["line_items"][0]["price_data"]["product_data"]
            assert stripe.versions == [card_topup.STRIPE_VERSION]
            block = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup_card"]
            assert block["tax"] == {"mode": "off"}

    def test_stripe_tax_adds_tax_on_top_and_credits_the_amount_asked(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV, AIMARKET_CARD_TOPUP_TAX="stripe_tax") as (client, db):
            account, key = funded_account(client, db, 0.0)
            opened = open_checkout(client, key, 10).json()
            form = stripe.calls[0][2]
            assert form["automatic_tax"] == {"enabled": True}
            assert form["billing_address_collection"] == "required"
            price = form["line_items"][0]["price_data"]
            assert price["tax_behavior"] == "exclusive" and price["product_data"]["tax_code"] == "txcd_10000000"
            assert opened["tax"] == {"mode": "stripe_tax", "behavior": "exclusive"}
            block = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup_card"]
            assert block["tax"] == {"mode": "stripe_tax", "behavior": "exclusive", "seller_of_record": "operator"}
            paid = self._paid(stripe, subtotal=1000, total=1210, tax=210)   # 21 % VAT on top
            assert deliver(client, event("checkout.session.completed", paid)).json()["outcome"] == "credited"
            assert balance(db, account) == pytest.approx(10.0)
            status = client.get(f"/ai-market/v2/card-topups/{opened['topup_id']}").json()
            assert status["tax"]["tax_usd"] == pytest.approx(2.10)

    @pytest.mark.parametrize("subtotal, total, tax", [
        (1000, 1210, 100),     # the total is not subtotal + tax
        (900, 1089, 189),      # the subtotal is not the charge the hub asked
        (1000, 1000, 210),     # a discount took the tax back out
        (1000, 1210, -210),    # a negative tax is not a tax
    ])
    def test_with_tax_the_figures_must_still_add_up(self, monkeypatch, tmp_path, stripe, subtotal, total, tax):
        with hub(monkeypatch, tmp_path, **ENV, AIMARKET_CARD_TOPUP_TAX="stripe_tax") as (client, db):
            account, key = funded_account(client, db, 0.0)
            open_checkout(client, key, 10)
            paid = self._paid(stripe, subtotal=subtotal, total=total, tax=tax)
            assert deliver(client, event("checkout.session.completed", paid)).json()["outcome"] == "refused"
            assert balance(db, account) == 0

    def test_inclusive_tax_is_inside_the_price(self, monkeypatch, tmp_path, stripe):
        env = {**ENV, "AIMARKET_CARD_TOPUP_TAX": "stripe_tax", "AIMARKET_CARD_TOPUP_TAX_BEHAVIOR": "inclusive"}
        with hub(monkeypatch, tmp_path, **env) as (client, db):
            account, key = funded_account(client, db, 0.0)
            open_checkout(client, key, 10)
            assert stripe.calls[0][2]["line_items"][0]["price_data"]["tax_behavior"] == "inclusive"
            paid = self._paid(stripe, subtotal=1000, total=1000, tax=-174)
            assert deliver(client, event("checkout.session.completed", paid)).json()["outcome"] == "refused"
            paid = self._paid(stripe, subtotal=1000, total=1000, tax=174)
            assert deliver(client, event("checkout.session.completed", paid)).json()["outcome"] == "credited"
            assert balance(db, account) == pytest.approx(10.0)

    def test_managed_payments_makes_stripe_the_seller(self, monkeypatch, tmp_path, stripe):
        env = {**ENV, "AIMARKET_CARD_TOPUP_TAX": "managed_payments", "AIMARKET_CARD_TOPUP_TAX_CODE": "txcd_10105002"}
        with hub(monkeypatch, tmp_path, **env) as (client, db):
            account, key = funded_account(client, db, 0.0)
            opened = open_checkout(client, key, 10).json()
            form = stripe.calls[0][2]
            assert form["managed_payments"] == {"enabled": True}
            # Stripe refuses these next to managed_payments: it collects the address and picks the methods.
            assert "automatic_tax" not in form and "billing_address_collection" not in form
            assert "payment_method_types" not in form
            assert form["line_items"][0]["price_data"]["product_data"]["tax_code"] == "txcd_10105002"
            assert stripe.versions == [card_topup.STRIPE_VERSION_MANAGED]
            block = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup_card"]
            assert block["tax"]["seller_of_record"] == "stripe"
            self._paid(stripe, subtotal=1000, total=1200, tax=200)
            r = client.post(f"/ai-market/v2/card-topups/{opened['topup_id']}/refresh")
            assert r.json()["outcome"] == "credited"
            assert stripe.versions[-1] == card_topup.STRIPE_VERSION_MANAGED, "read back under the same API version"
            assert balance(db, account) == pytest.approx(10.0)

    def test_a_checkout_keeps_the_rule_it_was_opened_under(self, monkeypatch, tmp_path, stripe):
        with hub(monkeypatch, tmp_path, **ENV, AIMARKET_CARD_TOPUP_TAX="stripe_tax") as (client, db):
            account, key = funded_account(client, db, 0.0)
            open_checkout(client, key, 10)
            monkeypatch.setenv("AIMARKET_CARD_TOPUP_TAX", "off")    # the operator switches tax off meanwhile
            paid = self._paid(stripe, subtotal=1000, total=1210, tax=210)
            assert deliver(client, event("checkout.session.completed", paid)).json()["outcome"] == "credited"
            assert balance(db, account) == pytest.approx(10.0)

    @pytest.mark.parametrize("env, needle", [
        ({"AIMARKET_CARD_TOPUP_TAX": "vat_please"}, "AIMARKET_CARD_TOPUP_TAX"),
        ({"AIMARKET_CARD_TOPUP_TAX": "stripe_tax", "AIMARKET_CARD_TOPUP_TAX_CODE": "10000000"}, "TAX_CODE"),
        ({"AIMARKET_CARD_TOPUP_TAX": "stripe_tax", "AIMARKET_CARD_TOPUP_TAX_BEHAVIOR": "sometimes"}, "TAX_BEHAVIOR"),
    ])
    def test_a_setting_the_hub_does_not_understand_shuts_the_door(self, monkeypatch, tmp_path, stripe, env, needle):
        with hub(monkeypatch, tmp_path, **ENV, **env) as (client, db):
            block = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup_card"]
            assert block["enabled"] is False and needle in block["reason"]
            _account, key = funded_account(client, db, 0.0)
            assert open_checkout(client, key, 10).status_code == 503
            assert stripe.calls == []


def test_a_refund_in_stripe_is_recorded_and_ends_the_topup(monkeypatch, tmp_path, stripe):
    with hub(monkeypatch, tmp_path, **ENV) as (client, db):
        account, key = funded_account(client, db, 0.0)
        opened = open_checkout(client, key, 10).json()
        paid = stripe.pay(next(iter(stripe.sessions)))
        deliver(client, event("checkout.session.completed", paid))
        r = deliver(client, event("charge.refunded", {"id": "ch_1", "payment_intent": paid["payment_intent"],
                                                      "amount_refunded": 1000}))
        assert r.json()["outcome"] == "refunded"
        row = db._conn.execute("SELECT status, detail FROM card_topups").fetchone()
        assert row["status"] == "refunded" and "1000" in row["detail"]
        # The credit is not taken back by the hub: it may be spent; the operator corrects it by hand.
        assert balance(db, account) == pytest.approx(10.0)
        r = client.post(f"/ai-market/v2/card-topups/{opened['topup_id']}/refresh")
        assert r.json()["outcome"] == "refunded"
        unknown = deliver(client, event("charge.refunded", {"id": "ch_2", "payment_intent": "pi_other"}))
        assert unknown.json()["outcome"] == "ignored"


@pytest.mark.parametrize("kind", ["charge.refunded", "charge.dispute.created"])
def test_verified_card_reversal_freezes_every_new_credit_spend_until_admin_review(monkeypatch, tmp_path, stripe, kind):
    from aimarket_hub.credits import CreditsLedger

    with hub(monkeypatch, tmp_path, **ENV) as (client, db):
        m = setup_mandate(client, db, usd=0.0)
        account, key = m["account"], m["api_key"]
        other, other_key = funded_account(client, db, 2.0)
        list_static(db)
        open_checkout(client, key, 10)
        paid = stripe.pay(next(iter(stripe.sessions)))
        assert deliver(client, event("checkout.session.completed", paid)).status_code == 200
        ledger = CreditsLedger(db._conn)
        assert not ledger.hold(account, 1.0, "preexisting-allowance").get("error")
        before = balance(db, account)
        reversal = event(kind, {"id": "reversal-test", "payment_intent": paid["payment_intent"],
                                "amount_refunded": 1000, "reason": "fraudulent"})
        assert deliver(client, reversal).status_code == 200
        assert ledger.account(account)["status"] == "disabled"
        assert balance(db, account) == before  # preserve money for reconciliation
        assert ledger.account(other)["status"] == "active"

        payload = {"product_id": "demo-echo", "capability_id": "demo.echo@v1", "input": {}}
        assert client.post("/ai-market/v2/invoke", json=payload, headers={"X-API-Key": key}).status_code >= 400
        assert mandated_invoke(client, m, payload).status_code >= 400
        assert ledger.debit(account, 0.01, "new-direct").get("error")
        assert ledger.hold(account, 0.01, "new-hold").get("error")
        assert ledger.transfer_hold("preexisting-allowance", "new-granted-child", 0.01).get("error")
        assert not ledger.release_hold("preexisting-allowance").get("error")
        assert client.post("/ai-market/v2/invoke", json=payload, headers={"X-API-Key": other_key}).status_code == 200

        # A duplicate cannot create another freeze/audit row or undo a trusted resolution.
        deliver(client, reversal)
        rows = db._conn.execute("SELECT COUNT(*) AS n FROM credit_ledger WHERE account_id=? AND kind='review_freeze'",
                                (account,)).fetchone()["n"]
        assert rows == 1
        path = f"/ai-market/v2/accounts/{account}/status"
        assert client.post(path, json={"status": "active"}, headers={"X-API-Key": key}).status_code in (401, 403)
        assert client.post(path, json={"status": "active"},
                           headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}).status_code == 200
        deliver(client, reversal)
        assert ledger.account(account)["status"] == "active"
        assert client.post("/ai-market/v2/invoke", json=payload, headers={"X-API-Key": key}).status_code == 200


@pytest.mark.parametrize("historical_status", ["refunded", "disputed"])
def test_upgrade_freezes_historical_reversals_once_without_changing_balances(monkeypatch, tmp_path, stripe, historical_status):
    from aimarket_hub.credits import CreditsLedger
    from aimarket_hub.migrations import Migrations

    with hub(monkeypatch, tmp_path, **ENV) as (client, db):
        account, key = funded_account(client, db, 2.0)
        other, _ = funded_account(client, db, 3.0)
        opened = open_checkout(client, key, 5).json()
        paid = stripe.pay(next(iter(stripe.sessions)))
        assert deliver(client, event("checkout.session.completed", paid)).status_code == 200
        ledger = CreditsLedger(db._conn)
        assert not ledger.hold(account, 1.0, "historical-reservation").get("error")
        before = ledger.account(account)
        # Reproduce a pre-upgrade database: the verified reversal was recorded,
        # but its remaining balance was still spendable and had no review marker.
        db._conn.execute("UPDATE card_topups SET status=? WHERE topup_id=?",
                         (historical_status, opened["topup_id"]))
        db._conn.execute("DELETE FROM _migrations WHERE version=62")
        db._conn.commit()
        migrations = Migrations(db._backend)
        assert migrations.apply(target_version=62) == 1
        after = ledger.account(account)
        assert after["status"] == "disabled"
        for field in ("balance_usd", "held_usd", "spent_usd", "granted_usd", "collateral_usd", "topped_up_usd"):
            assert after[field] == before[field]
        assert ledger.account(other)["status"] == "active"
        assert ledger.debit(account, 0.01, "post-upgrade-spend").get("error")
        assert ledger.transfer_hold("historical-reservation", "post-upgrade-child", 0.01).get("error")
        assert db._conn.execute("SELECT COUNT(*) AS n FROM credit_ledger WHERE account_id=? AND kind='review_freeze'",
                                (account,)).fetchone()["n"] == 1
        assert migrations.apply(target_version=62) == 0
        assert client.post(f"/ai-market/v2/accounts/{account}/status", json={"status": "active"},
                           headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}).status_code == 200
        assert migrations.apply(target_version=62) == 0
        assert ledger.account(account)["status"] == "active"


@pytest.mark.parametrize("kind,expected", [("charge.dispute.created", "disputed"), ("charge.refunded", "refunded")])
def test_reversal_before_completed_reconciles_once_and_survives_late_payment(monkeypatch, tmp_path, stripe, kind, expected):
    with hub(monkeypatch, tmp_path, **ENV) as (client, db):
        account, key = funded_account(client, db, 0.0)
        opened = open_checkout(client, key, 5).json()
        paid = stripe.pay(next(iter(stripe.sessions)))
        reversal = event(kind, {"id": "reversal_1", "payment_intent": paid["payment_intent"],
                                "amount_refunded": 500, "reason": "fraudulent"})
        assert deliver(client, reversal).json()["outcome"] == expected
        assert deliver(client, event("checkout.session.completed", paid)).json()["outcome"] == expected
        deliver(client, reversal)
        assert client.get(f"/ai-market/v2/card-topups/{opened['topup_id']}").json()["status"] == expected
        assert balance(db, account) == 5
        assert db._conn.execute("SELECT count(*) AS n FROM credit_ledger WHERE account_id=? AND kind='topup'", (account,)).fetchone()["n"] == 1


def test_early_reversal_lookup_failure_is_retried_and_does_not_credit(monkeypatch, tmp_path, stripe):
    with hub(monkeypatch, tmp_path, **ENV) as (client, db):
        account, key = funded_account(client, db, 0.0)
        open_checkout(client, key, 5)
        paid = stripe.pay(next(iter(stripe.sessions)))
        stripe.fail = "raise"
        result = deliver(client, event("charge.dispute.created", {"payment_intent": paid["payment_intent"]}))
        assert result.status_code == 503
        assert balance(db, account) == 0


@pytest.mark.parametrize("corruption,status,outcome", [("id", 200, "ignored"), ("amount_total", 503, None)])
def test_early_reversal_does_not_bypass_session_or_amount_checks(monkeypatch, tmp_path, stripe, corruption, status, outcome):
    with hub(monkeypatch, tmp_path, **ENV) as (client, db):
        account, key = funded_account(client, db, 0.0)
        open_checkout(client, key, 5)
        sid = next(iter(stripe.sessions))
        paid = stripe.pay(sid)
        stripe.sessions[sid][corruption] = "cs_other" if corruption == "id" else 499
        result = deliver(client, event("charge.dispute.created", {"payment_intent": paid["payment_intent"]}))
        assert result.status_code == status
        if outcome:
            assert result.json()["outcome"] == outcome
        assert balance(db, account) == 0
