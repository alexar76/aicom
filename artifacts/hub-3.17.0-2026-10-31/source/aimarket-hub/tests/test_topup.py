"""Buying credits with USDC (aimarket_hub/topup.py) against the real hub app.

The chain is replaced by a verifier that answers like settle.verify_transfer would for the
transactions a test declares — paid, not final, underpaid, unreachable. Everything else is the
hub's own code: the 402, the quote store, the deposit-claim registry the channel door shares, the
x402 ledger of spent authorizations, the credits ledger. The same flow against a real token on a
local chain is tests/test_topup_chain.py.
"""
from __future__ import annotations

import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from aimarket_hub import settle, topup
from tests._mandate_kit import HUB, balance, funded_account, hub

PAY_TO = "0x" + "a1" * 20
PAYER = "0x" + "b2" * 20
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def tx(n: int) -> str:
    return "0x" + f"{n:064x}"


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("AIMARKET_TOPUP_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    # No test here may reach a real chain: the token's decimals are checked in
    # test_the_tokens_own_decimals_are_checked (stubbed RPC) and tests/test_topup_chain.py.
    monkeypatch.setenv("AIMARKET_TOPUP_VERIFY_DECIMALS", "0")
    topup._VERIFY_LOG.clear()
    topup._DECIMALS_READ.clear()


class Chain:
    """What the chain says about each transaction: {tx: {nonce: paid_units | Exception}}."""

    def __init__(self):
        self.txs: dict[str, dict[str, object]] = {}
        self.asked: list[tuple[str, str]] = []
        self.lock = threading.Lock()

    def pays(self, tx_hash: str, nonce: str, units: int, payer: str = PAYER) -> None:
        self.txs.setdefault(tx_hash, {})[nonce] = (units, payer)

    def fails(self, tx_hash: str, nonce: str, exc: Exception) -> None:
        self.txs.setdefault(tx_hash, {})[nonce] = exc

    def verify(self, *, tx_hash, terms, require_nonce, max_age_s=0, timeout=10.0, rpc_url=""):
        with self.lock:
            self.asked.append((tx_hash, require_nonce))
        found = self.txs.get(tx_hash, {}).get(require_nonce)
        if found is None:
            raise settle.PaymentError("payment is not bound to this call: the transaction carries no "
                                      "EIP-3009 authorization for the nonce this hub issued")
        if isinstance(found, Exception):
            raise found
        units, payer = found
        if units < terms.amount_units:
            raise settle.PaymentError(f"paid {units} base units, the seller's share is {terms.amount_units}")
        assert terms.pay_to == PAY_TO and terms.token_contract == USDC_BASE.lower()
        return {"tx_hash": tx_hash, "paid_units": units, "authorizer": payer}


@pytest.fixture
def chain(monkeypatch):
    c = Chain()
    monkeypatch.setattr(settle, "verify_transfer", c.verify)
    return c


def _quote(client, key: str, amount=5):
    return client.post("/ai-market/v2/account/topup", headers={"X-API-Key": key}, json={"amount_usd": amount})


def _account(client, key: str) -> dict:
    return client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()


def _redeem(client, nonce: str, tx_hash: str, key: str = ""):
    headers = {"X-API-Key": key} if key else {}
    return client.post(f"/ai-market/v2/topups/{nonce}", headers=headers, json={"tx_hash": tx_hash})


# ── the quote ───────────────────────────────────────────────────────────────


class TestQuote:
    def test_it_is_an_x402_offer_bound_to_the_account(self, monkeypatch, tmp_path, on):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            r = _quote(client, key, 12.5)
            assert r.status_code == 402
            body = r.json()
            v2 = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))
            quoted = db._conn.execute("SELECT * FROM credit_topup_quotes").fetchall()
            invoices = db._conn.execute("SELECT COUNT(*) AS n FROM settle_invoices").fetchone()["n"]
        nonce = body["nonce"]
        assert settle.is_nonce(nonce) and body["binding"] == "eip3009"
        accept = v2["accepts"][0]
        assert (accept["scheme"], accept["network"], accept["amount"], accept["payTo"]) == \
               ("exact", "eip155:8453", "12500000", PAY_TO)
        assert accept["asset"] == USDC_BASE and accept["extra"]["nonce"] == nonce
        assert accept["extra"]["name"] == "USD Coin" and accept["extra"]["chainId"] == 8453
        v1 = body["accepts"][0]
        assert v1["maxAmountRequired"] == "12500000" and v1["extra"]["verifyingContract"] == USDC_BASE
        assert body["topup"]["amount_usd"] == 12.5 and body["topup"]["redeem_url"].endswith(f"/topups/{nonce}")
        # The account is bound at quote time; nothing else is stored.
        assert [(r["account_id"], r["status"], int(r["amount_units"])) for r in quoted] == [(account, "quoted", 12_500_000)]
        # The x402 middleware left this 402 alone: no invoke invoice, no payment secret.
        assert invoices == 0 and "payment_secret" not in body

    @pytest.mark.parametrize("amount, error", [
        (0, "amount_out_of_range"), (-5, "amount_out_of_range"), (0.5, "amount_out_of_range"),
        (1000, "amount_out_of_range"), (1.005, "amount_invalid"), ("five", "amount_invalid"), (None, "amount_invalid"),
    ])
    def test_it_refuses_an_amount_it_would_have_to_round(self, monkeypatch, tmp_path, on, amount, error):
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            r = _quote(client, key, amount)
        assert r.status_code == 400 and r.json()["error"] == error

    def test_it_needs_the_key_of_the_account_to_credit(self, monkeypatch, tmp_path, on):
        with hub(monkeypatch, tmp_path) as (client, db):
            r = client.post("/ai-market/v2/account/topup", json={"amount_usd": 5})
            bad = _quote(client, "aimk_not_a_key")
        assert r.status_code == 401 and bad.status_code == 401 and r.json()["error"] == "api_key_required"

    def test_the_door_is_shut_unless_the_operator_opens_it(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            r = _quote(client, key)
            rails = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup"]
        assert r.status_code == 503 and r.json()["error"] == "topup_unavailable"
        assert rails["enabled"] is False and "AIMARKET_TOPUP_ENABLED" in rails["reason"]

    def test_the_well_known_names_the_terms(self, monkeypatch, tmp_path, on):
        with hub(monkeypatch, tmp_path) as (client, db):
            rails = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup"]
        assert rails["enabled"] is True and rails["pay_to"] == PAY_TO and rails["network"] == "eip155:8453"
        assert (rails["min_usd"], rails["max_usd"], rails["min_confirmations"]) == (1.0, 100.0, 2)
        assert rails["quote"] == "/ai-market/v2/account/topup" and rails["redeem"] == "/ai-market/v2/topups/{nonce}"

    def test_open_quotes_are_capped(self, monkeypatch, tmp_path, on):
        monkeypatch.setenv("AIMARKET_TOPUP_MAX_OPEN_QUOTES", "2")
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            codes = [_quote(client, key).status_code for _ in range(3)]
        assert codes == [402, 402, 429]

    def test_the_daily_limit_counts_what_was_bought(self, monkeypatch, tmp_path, on, chain):
        monkeypatch.setenv("AIMARKET_TOPUP_DAILY_USD", "10")
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 8).json()["nonce"]
            chain.pays(tx(1), nonce, 8_000_000)
            assert _redeem(client, nonce, tx(1)).status_code == 200
            over = _quote(client, key, 3)
            under = _quote(client, key, 2)
        assert over.status_code == 429 and over.json()["error"] == "daily_topup_limit"
        assert under.status_code == 402


# ── redemption ──────────────────────────────────────────────────────────────


class TestRedeem:
    def test_a_mined_payment_credits_the_quoted_account_once(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 5).json()["nonce"]
            chain.pays(tx(7), nonce, 5_000_000)
            first = _redeem(client, nonce, tx(7))
            again = _redeem(client, nonce, tx(7))
            mine = _account(client, key)
            public = client.get(f"/ai-market/v2/topups/{nonce}").json()
            owned = client.get(f"/ai-market/v2/topups/{nonce}", headers={"X-API-Key": key}).json()
            ledger = client.get("/ai-market/v2/account/ledger", headers={"X-API-Key": key}).json()
            spent = db._conn.execute("SELECT capability_id, settle_tx_hash, payer FROM x402_payments "
                                     "WHERE nonce = ?", (nonce,)).fetchone()
        assert first.status_code == 200 and first.json()["credited_usd"] == 5.0
        assert first.json()["idempotent_replay"] is False and again.json()["idempotent_replay"] is True
        # Anyone may redeem; only the owner is told the balance and whose account it was.
        assert "balance_usd" not in first.json() and "account_id" not in first.json()
        assert mine["balance_usd"] == 5.0 and mine["topped_up_usd"] == 5.0 and mine["granted_usd"] == 0.0
        assert public["status"] == "credited" and "account_id" not in public and "payer" not in public
        assert owned["account_id"] == account and owned["payer"] == PAYER
        assert [e["kind"] for e in ledger.get("entries", ledger.get("ledger", []))] == ["topup"]
        assert dict(spent) == {"capability_id": "credits.topup", "settle_tx_hash": tx(7), "payer": PAYER}

    def test_the_x402_retry_on_the_quote_route_redeems_too(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 3).json()["nonce"]
            chain.pays(tx(3), nonce, 3_000_000)
            r = client.post("/ai-market/v2/account/topup", json={"amount_usd": 3},
                            headers={"X-API-Key": key, "X-Payment": tx(3), "X-Payment-Nonce": nonce})
        assert r.status_code == 200 and r.json()["balance_usd"] == 3.0 and r.json()["account_id"] == account

    def test_someone_elses_payment_credits_its_owner_not_the_presenter(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            alice, alice_key = funded_account(client, db, 0.0)
            mallory, mallory_key = funded_account(client, db, 0.0)
            nonce = _quote(client, alice_key, 5).json()["nonce"]
            chain.pays(tx(9), nonce, 5_000_000)
            r = client.post("/ai-market/v2/account/topup", json={"amount_usd": 5},
                            headers={"X-API-Key": mallory_key, "X-Payment": tx(9), "X-Payment-Nonce": nonce})
            balances = balance(db, alice), balance(db, mallory)
        assert r.status_code == 200 and "balance_usd" not in r.json() and "account_id" not in r.json()
        assert balances == (5.0, 0.0)

    def test_an_overpayment_is_credited_up_to_the_quote_and_the_excess_reported(
            self, monkeypatch, tmp_path, on, chain):
        """max_usd and the daily limit bound what is CREDITED: a $1 quote paid with 10 000 USDC
        credits $1, and the excess is shown for the operator to refund."""
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 1).json()["nonce"]
            chain.pays(tx(4), nonce, 10_000_000_000)
            r = _redeem(client, nonce, tx(4), key)
            left = balance(db, account)
        body = r.json()
        assert r.status_code == 200 and body["credited_usd"] == 1.0 and left == 1.0
        assert body["paid_usd"] == 10_000.0 and body["overpaid_usd"] == 9_999.0

    def test_an_underpayment_is_credited_for_what_arrived(self, monkeypatch, tmp_path, on, chain):
        """The nonce binds the money to one account whatever the amount: refusing a short
        payment would strand it. What arrived is credited, rounded down to the millicent."""
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 5).json()["nonce"]
            chain.pays(tx(24), nonce, 4_999_999)
            r = _redeem(client, nonce, tx(24))
            left = balance(db, account)
        assert r.status_code == 200 and r.json()["credited_usd"] == pytest.approx(4.99999) and left == pytest.approx(4.99999)

    @pytest.mark.parametrize("exc, status, error, retryable", [
        (settle.PaymentError("payment has 1 confirmation(s); 2 required"), 409, "payment_not_final", True),
        (settle.PaymentError("transaction is not on chain yet"), 409, "payment_not_final", True),
        (settle.PaymentError("transaction reverted"), 402, "payment_invalid", False),
        (RuntimeError("rpc is down"), 503, "verifier_unavailable", True),
    ])
    def test_a_payment_that_does_not_verify_leaves_the_quote_redeemable(
            self, monkeypatch, tmp_path, on, chain, exc, status, error, retryable):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 5).json()["nonce"]
            chain.fails(tx(5), nonce, exc)
            r = _redeem(client, nonce, tx(5))
            still = client.get(f"/ai-market/v2/topups/{nonce}").json()["status"]
            chain.pays(tx(5), nonce, 5_000_000)
            later = _redeem(client, nonce, tx(5))
            left = balance(db, account)
        assert r.status_code == status and r.json()["error"] == error
        assert bool(r.json().get("retryable")) is retryable
        assert still == "quoted" and later.status_code == 200 and left == 5.0

    def test_an_unbound_transfer_is_not_credited(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 5).json()["nonce"]
            unbound = _redeem(client, nonce, tx(66))     # a transfer with no authorization over it
            left = balance(db, account)
        assert unbound.status_code == 402 and "not bound" in unbound.json()["detail"] and left == 0.0

    def test_unknown_or_malformed(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            unknown = _redeem(client, "0x" + "00" * 32, tx(1))
            malformed = _redeem(client, "nonce", tx(1))
            _, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            no_tx = _redeem(client, nonce, "0xabc")
        assert unknown.status_code == 404 and malformed.status_code == 400 and no_tx.status_code == 400
        assert chain.asked == []      # nothing reached the chain for any of them

    def test_a_disabled_account_is_still_credited(self, monkeypatch, tmp_path, on, chain):
        from aimarket_hub import credits

        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            credits.CreditsLedger(db._conn).set_status(account, "disabled")
            chain.pays(tx(8), nonce, 5_000_000)
            r = _redeem(client, nonce, tx(8))
            left = balance(db, account)
        assert r.status_code == 200 and left == 5.0

    def test_a_nonce_is_checked_at_most_twelve_times_a_minute(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            codes = [_redeem(client, nonce, tx(100 + i)).status_code for i in range(13)]
        assert codes[:12] == [402] * 12 and codes[12] == 429 and len(chain.asked) == 12


# ── one payment, one credit ─────────────────────────────────────────────────


class TestExclusivity:
    def test_a_transaction_the_channel_door_took_is_not_credited(self, monkeypatch, tmp_path, on, chain):
        from aimarket_hub import channels

        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(11), nonce, 5_000_000)
            taken = channels._claim_deposit_shared(chain="base", tx_hash=tx(11), channel_id="ch_1",
                                                   amount_cents=500)
            r = _redeem(client, nonce, tx(11))
            status = client.get(f"/ai-market/v2/topups/{nonce}").json()
            left = balance(db, account)
        assert taken["ok"] is True
        assert r.status_code == 409 and r.json()["error"] == "payment_already_used"
        assert "another door" in r.json()["detail"] and left == 0.0
        # Not final: the quote stays open, so if the other door hands the claim back the
        # same payment can still be redeemed.
        assert status["status"] == "quoted"

    def test_a_credited_top_up_cannot_then_fund_a_channel(self, monkeypatch, tmp_path, on, chain):
        from aimarket_hub import channels

        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(12), nonce, 5_000_000)
            assert _redeem(client, nonce, tx(12)).status_code == 200
            # The same transaction, checksum-cased, at the channel door.
            again = channels._claim_deposit_shared(chain="BASE", tx_hash=tx(12).upper().replace("0X", "0x"),
                                                   channel_id="ch_2", amount_cents=500)
        assert again["ok"] is False and again["error"] == "already_claimed"
        assert again["claim"]["stack"] == topup.TOPUP_STACK

    def test_a_claim_being_written_is_retried_not_refused(self, monkeypatch, tmp_path, on, chain):
        """The registry says 'taken' but the record cannot be read yet — another writer is
        mid-way. Refusing then would strand the payment; the next attempt reads it whole."""
        from aimarket_hub import channels

        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(19), nonce, 5_000_000)
            real = channels.claim_deposit_as
            calls = {"n": 0}

            def half_written_once(stack, **kw):
                calls["n"] += 1
                if calls["n"] == 1:
                    return {"ok": False, "error": "already_claimed", "claim": None}
                return real(stack, **kw)

            monkeypatch.setattr(channels, "claim_deposit_as", half_written_once)
            first = _redeem(client, nonce, tx(19))
            still = client.get(f"/ai-market/v2/topups/{nonce}").json()["status"]
            second = _redeem(client, nonce, tx(19))
            left = balance(db, account)
        assert first.status_code == 503 and first.json()["retryable"] is True and still == "quoted"
        assert second.status_code == 200 and left == 5.0

    def test_two_top_up_authorizations_in_one_transaction_each_credit(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            a, key_a = funded_account(client, db, 0.0)
            b, key_b = funded_account(client, db, 0.0)
            na, nb = _quote(client, key_a, 2).json()["nonce"], _quote(client, key_b, 3).json()["nonce"]
            chain.pays(tx(13), na, 2_000_000)
            chain.pays(tx(13), nb, 3_000_000)          # a smart wallet settling both at once
            ra, rb = _redeem(client, na, tx(13)), _redeem(client, nb, tx(13))
            balances = balance(db, a), balance(db, b)
        assert (ra.status_code, rb.status_code) == (200, 200) and balances == (2.0, 3.0)

    def test_racing_redemptions_credit_once(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 7).json()["nonce"]
            chain.pays(tx(14), nonce, 7_000_000)
            # Redemption runs in the threadpool (it reads the chain), so these really race. Ten:
            # one anonymous caller is allowed twelve checks a minute.
            with ThreadPoolExecutor(max_workers=10) as pool:
                codes = list(pool.map(lambda _: _redeem(client, nonce, tx(14)).status_code, range(10)))
            left = balance(db, account)
            rows = db._conn.execute("SELECT COUNT(*) AS n FROM credit_topups").fetchone()["n"]
        assert left == 7.0 and rows == 1
        assert set(codes) <= {200, 409} and 200 in codes

    def test_a_redemption_interrupted_after_its_claims_is_finished_by_the_next(
            self, monkeypatch, tmp_path, on, chain):
        from aimarket_hub import credits

        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 4).json()["nonce"]
            chain.pays(tx(15), nonce, 4_000_000)
            real = credits.CreditsLedger.deposit
            crashes = {"n": 1}

            def crash_once(self, *a, **kw):
                if crashes["n"]:
                    crashes["n"] -= 1
                    raise RuntimeError("the process died here")
                return real(self, *a, **kw)

            monkeypatch.setattr(credits.CreditsLedger, "deposit", crash_once)
            with pytest.raises(RuntimeError):
                _redeem(client, nonce, tx(15))
            stuck = client.get(f"/ai-market/v2/topups/{nonce}").json()["status"]
            too_soon = _redeem(client, nonce, tx(15))
            db._conn.execute("UPDATE credit_topup_quotes SET redeeming_since = 1 WHERE nonce = ?", (nonce,))
            db._conn.commit()
            finished = _redeem(client, nonce, tx(15))
            left = balance(db, account)
        assert stuck == "redeeming" and too_soon.status_code == 409
        assert finished.status_code == 200 and left == 4.0

    def test_a_redemption_interrupted_after_the_credit_does_not_credit_twice(
            self, monkeypatch, tmp_path, on, chain):
        """The credit committed, then the process died before the quote was marked: the next
        redemption repeats every step, and the ledger's reference makes the credit a replay."""
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key, 6).json()["nonce"]
            chain.pays(tx(17), nonce, 6_000_000)
            real = topup.TopupStore.credit
            crashes = {"n": 1}

            def crash_once(self, *a, **kw):
                if crashes["n"]:
                    crashes["n"] -= 1
                    raise RuntimeError("the process died after the credit")
                return real(self, *a, **kw)

            monkeypatch.setattr(topup.TopupStore, "credit", crash_once)
            with pytest.raises(RuntimeError):
                _redeem(client, nonce, tx(17))
            after_crash = balance(db, account)
            db._conn.execute("UPDATE credit_topup_quotes SET redeeming_since = 1 WHERE nonce = ?", (nonce,))
            db._conn.commit()
            finished = _redeem(client, nonce, tx(17))
            left = balance(db, account)
            status = client.get(f"/ai-market/v2/topups/{nonce}").json()["status"]
        assert after_crash == 6.0 and left == 6.0 and status == "credited"
        assert finished.status_code == 200 and finished.json()["idempotent_replay"] is True

    def test_pruning_forgets_unpaid_quotes_and_keeps_the_record_of_money(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            paid, unpaid = _quote(client, key).json()["nonce"], _quote(client, key).json()["nonce"]
            chain.pays(tx(18), paid, 5_000_000)
            assert _redeem(client, paid, tx(18)).status_code == 200
            db._conn.execute("UPDATE credit_topup_quotes SET expires_at = 1")
            db._conn.commit()
            removed = topup.TopupStore(db._conn).prune()
            left = {r["nonce"] for r in db._conn.execute("SELECT nonce FROM credit_topup_quotes").fetchall()}
        assert removed == 1 and left == {paid} and unpaid not in left

    def test_a_top_up_nonce_cannot_pay_for_an_invoke(self, monkeypatch, tmp_path, on, chain):
        from tests._mandate_kit import list_static

        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            list_static(db, price=0.004)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(16), nonce, 5_000_000)
            r = client.post("/ai-market/v2/invoke", json={"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                                                          "input": {}},
                            headers={"X-Payment": tx(16), "X-Payment-Nonce": nonce})
        assert r.status_code in (402, 403) and r.json().get("success") is not True


# ── the operator's hand, for money no quote can match ──────────────────────


class TestOperatorCredit:
    def _credit(self, client, account, tx_hash, amount=5, admin=True):
        from tests._mandate_kit import ADMIN_TOKEN

        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"} if admin else {}
        return client.post(f"/ai-market/v2/accounts/{account}/credit", headers=headers,
                           json={"amount_usd": amount, "tx_hash": tx_hash, "note": "plain transfer"})

    def test_an_on_chain_payment_credited_by_hand_is_paid_credit_claimed_once(self, monkeypatch, tmp_path, on):
        from aimarket_hub import channels

        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            first = self._credit(client, account, tx(21))
            again = self._credit(client, account, tx(21))
            other = funded_account(client, db, 0.0)[0]
            elsewhere = self._credit(client, other, tx(21))
            mine = _account(client, key)
            channel = channels._claim_deposit_shared(chain="base", tx_hash=tx(21), channel_id="ch_3", amount_cents=500)
            nobody = self._credit(client, account, tx(22), admin=False)
        assert first.status_code == 200 and again.json()["idempotent_replay"] is True
        assert mine["balance_usd"] == 5.0 and mine["topped_up_usd"] == 5.0 and mine["granted_usd"] == 0.0
        assert elsewhere.status_code == 409          # the same money cannot be credited to two accounts
        assert channel["ok"] is False and channel["error"] == "already_claimed"
        assert nobody.status_code in (401, 403)

    def test_a_quote_paid_by_a_transaction_the_operator_already_credited_is_refused(
            self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(23), nonce, 5_000_000)
            assert self._credit(client, account, tx(23)).status_code == 200
            r = _redeem(client, nonce, tx(23))
            left = balance(db, account)
        assert r.status_code == 409 and r.json()["error"] == "payment_already_used" and left == 5.0


# ── what the independent review found (each was a confirmed defect) ─────────


class TestReviewFindings:
    def test_the_hub_local_registry_is_as_exclusive_as_the_web_one(self, monkeypatch, tmp_path, on, chain):
        """A hub image ships without `web`: the fallback registry must hold the same line."""
        from aimarket_hub import channels

        monkeypatch.setattr(channels, "_shared_on_chain", lambda attr: None)
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(31), nonce, 5_000_000)
            assert _redeem(client, nonce, tx(31)).status_code == 200
            channel = channels._claim_deposit_shared(chain="base", tx_hash=tx(31), channel_id="ch", amount_cents=500)
        assert channel["ok"] is False and channel["claim"]["stack"] == topup.TOPUP_STACK

    def test_one_transaction_is_one_claim_whatever_chain_label_a_door_uses(self, monkeypatch, tmp_path, on, chain):
        """With AIMARKET_DEPOSIT_RPC_URL every label is verified on the same node: claimed by
        label alone, one payment funded a top-up AND a channel labelled "ethereum" — and, at
        the channel door alone, two channels. Claimed by the node's own chain id, once."""
        from aimarket_hub import channels, deposit_verify

        monkeypatch.setenv("AIMARKET_DEPOSIT_RPC_URL", "http://deposit-node.test")
        monkeypatch.setattr(deposit_verify, "_rpc_chain_id", lambda url, timeout=5.0: 8453)
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(32), nonce, 5_000_000)
            assert _redeem(client, nonce, tx(32)).status_code == 200
            as_ethereum = channels._claim_deposit_shared(chain="ethereum", tx_hash=tx(32), channel_id="c1",
                                                         amount_cents=500)
            first = channels._claim_deposit_shared(chain="base", tx_hash=tx(33), channel_id="c2", amount_cents=500)
            second = channels._claim_deposit_shared(chain="ethereum", tx_hash=tx(33), channel_id="c3",
                                                    amount_cents=500)
        assert as_ethereum["ok"] is False and as_ethereum["error"] == "already_claimed"
        assert first["ok"] is True and second["ok"] is False

    def test_a_failure_to_record_the_authorization_is_retried_not_refused(self, monkeypatch, tmp_path, on, chain):
        """PaymentStore.claim returns False on ANY exception. Read as "spent elsewhere", one
        "database is locked" refused a paid top-up for good."""
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(34), nonce, 5_000_000)
            real = settle.PaymentStore.claim
            fails = {"n": 1}

            def locked_once(self, **kw):
                if fails["n"]:
                    fails["n"] -= 1
                    return False
                return real(self, **kw)

            monkeypatch.setattr(settle.PaymentStore, "claim", locked_once)
            first = _redeem(client, nonce, tx(34))
            still = client.get(f"/ai-market/v2/topups/{nonce}").json()["status"]
            second = _redeem(client, nonce, tx(34))
            left = balance(db, account)
        assert first.status_code == 503 and first.json()["retryable"] is True and still == "quoted"
        assert second.status_code == 200 and left == 5.0

    def test_a_deposit_that_fails_midway_writes_nothing_and_does_not_loop(self, monkeypatch, tmp_path, on):
        from aimarket_hub import credits

        with hub(monkeypatch, tmp_path) as (client, db):
            account, _ = funded_account(client, db, 0.0)
            ledger = credits.CreditsLedger(db._conn)
            calls = {"n": 0}

            def broken_log(self, *a, **kw):
                calls["n"] += 1
                raise RuntimeError("database is locked")

            monkeypatch.setattr(credits.CreditsLedger, "_log", broken_log)
            result = ledger.deposit(account, 500_000, reference="topup:base:0xabc")
            rows = db._conn.execute("SELECT COUNT(*) AS n FROM credit_topups").fetchone()["n"]
            left = balance(db, account)
        assert "error" in result and calls["n"] == 1
        assert rows == 0 and left == 0.0      # the balance and the reference rolled back with it

    def test_the_daily_limit_holds_at_redemption_too(self, monkeypatch, tmp_path, on, chain):
        """Quotes are paid after they are minted and stay redeemable after they expire: a
        limit checked only when quoting bounded nothing."""
        monkeypatch.setenv("AIMARKET_TOPUP_DAILY_USD", "10")
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            a = _quote(client, key, 6).json()["nonce"]
            import time as _time

            db._conn.execute("UPDATE credit_topup_quotes SET expires_at = ? WHERE nonce = ?", (_time.time() - 10, a))
            db._conn.commit()
            b = _quote(client, key, 6).json()["nonce"]       # A expired: no longer counts as offered
            chain.pays(tx(35), a, 6_000_000)
            chain.pays(tx(36), b, 6_000_000)
            ra, rb = _redeem(client, a, tx(35)), _redeem(client, b, tx(36))
            waiting = client.get(f"/ai-market/v2/topups/{b}").json()["status"]
            db._conn.execute("UPDATE credit_topup_quotes SET credited_at = credited_at - 90000 WHERE nonce = ?", (a,))
            db._conn.commit()
            later = _redeem(client, b, tx(36))
            left = balance(db, account)
        assert ra.status_code == 200 and rb.status_code == 429 and rb.json()["retryable"] is True
        assert waiting == "quoted" and later.status_code == 200 and left == 12.0

    def test_anonymous_checks_do_not_lock_the_owner_out(self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(37), nonce, 5_000_000)
            spam = [_redeem(client, nonce, tx(200 + i)).status_code for i in range(13)]
            owner = _redeem(client, nonce, tx(37), key)
            left = balance(db, account)
        assert spam[-1] == 429 and owner.status_code == 200 and left == 5.0

    def test_another_accounts_key_buys_no_budget_of_its_own(self, monkeypatch, tmp_path, on, chain):
        """Accounts are free to open: a key of some OTHER account spends its caller's address
        budget, across every quote — a budget per (account, nonce) multiplied chain reads by
        every account and every quote it could name. The owner keeps its own."""
        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            first, second = (_quote(client, key).json()["nonce"] for _ in range(2))
            _, other = funded_account(client, db, 0.0)
            chain.pays(tx(40), second, 5_000_000)
            spam = [_redeem(client, first if i % 2 else second, tx(300 + i), other).status_code
                    for i in range(13)]
            owner = _redeem(client, second, tx(40), key)
            left = balance(db, account)
        assert spam.count(429) == 1 and spam[-1] == 429
        assert owner.status_code == 200 and left == 5.0

    def test_a_claim_whose_writer_died_is_repaired(self, monkeypatch, tmp_path, on, chain):
        import os as _os
        import time as _time

        from aimarket_hub import deposit_claims

        with hub(monkeypatch, tmp_path) as (client, db):
            account, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(38), nonce, 5_000_000)
            path = deposit_claims.deposit_claims_dir() / f"{deposit_claims.deposit_claim_key('eip155:8453', tx(38))}.json"
            path.write_text("")                              # created, never written
            fresh = _redeem(client, nonce, tx(38))           # a writer mid-way: retry
            old = _time.time() - 600
            _os.utime(path, (old, old))                      # ...and it never came back
            repaired = _redeem(client, nonce, tx(38))
            left = balance(db, account)
        assert fresh.status_code == 503 and fresh.json()["retryable"] is True
        assert repaired.status_code == 200 and left == 5.0

    def test_a_slow_chain_does_not_stall_other_requests(self, monkeypatch, tmp_path, on, chain):
        import time as _time

        slow = chain.verify

        def sleepy(**kw):
            _time.sleep(1.5)
            return slow(**kw)

        monkeypatch.setattr(settle, "verify_transfer", sleepy)
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            chain.pays(tx(39), nonce, 5_000_000)
            worker = threading.Thread(target=lambda: _redeem(client, nonce, tx(39)))
            worker.start()
            _time.sleep(0.2)
            started = _time.monotonic()
            client.get("/.well-known/ai-market.json")
            waited = _time.monotonic() - started
            worker.join()
        assert waited < 1.0, f"an unrelated request waited {waited:.2f}s behind a chain read"

    def test_the_tokens_own_decimals_are_checked(self, monkeypatch, tmp_path, on):
        monkeypatch.setenv("AIMARKET_TOPUP_VERIFY_DECIMALS", "1")
        monkeypatch.setattr(settle, "rpc_urls", lambda: ["http://node.test"])
        reported = {"decimals": 18}
        monkeypatch.setattr(settle, "_rpc", lambda url, method, params, timeout: hex(reported["decimals"]))
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            wrong = _quote(client, key)
            topup._DECIMALS_READ.clear()
            reported["decimals"] = 6
            right = _quote(client, key)
        assert wrong.status_code == 503 and "18 decimals" in wrong.json()["detail"]
        assert right.status_code == 402

    def test_an_operator_credit_to_an_unknown_account_takes_no_claim(self, monkeypatch, tmp_path, on):
        from tests._mandate_kit import ADMIN_TOKEN

        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
        with hub(monkeypatch, tmp_path) as (client, db):
            account, _ = funded_account(client, db, 0.0)
            typo = client.post("/ai-market/v2/accounts/acct_typo/credit", headers=headers,
                               json={"amount_usd": 5, "tx_hash": tx(40)})
            right = client.post(f"/ai-market/v2/accounts/{account}/credit", headers=headers,
                                json={"amount_usd": 5, "tx_hash": tx(40)})
        assert typo.status_code == 404 and right.status_code == 200

    def test_a_client_that_sends_only_an_authorization_is_told_to_send_the_transaction(
            self, monkeypatch, tmp_path, on, chain):
        with hub(monkeypatch, tmp_path) as (client, db):
            _, key = funded_account(client, db, 0.0)
            nonce = _quote(client, key).json()["nonce"]
            payload = base64.b64encode(json.dumps({"x402Version": 2, "scheme": "exact", "payload": {
                "signature": "0x" + "11" * 65, "authorization": {"nonce": nonce}}}).encode()).decode()
            r = client.post("/ai-market/v2/account/topup", json={"amount_usd": 5},
                            headers={"X-API-Key": key, "X-Payment": payload})
        assert r.status_code == 400 and r.json()["error"] == "tx_hash_invalid"
        assert "never settles" in r.json()["detail"] and chain.asked == []


# ── units ───────────────────────────────────────────────────────────────────


def test_amounts_are_exact():
    assert topup.cents(12.5) == 1250 and topup.cents("3") == 300
    assert topup.units_for_cents(1250, 6) == 12_500_000
    assert topup.units_to_mc(12_500_000, 6) == 1_250_000        # $12.50 = 1 250 000 millicents
    assert topup.units_to_mc(9, 6) == 0                          # never a millicent not delivered
    with pytest.raises(topup.TopupError):
        topup.cents(float("nan"))
