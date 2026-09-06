"""Channel settlement / on-chain binding regressions for the v1 AI-Market path.

Covers the money gates in ``web/backend/services/ai_market_protocol``:

* close_channel verifies the refund in the direction it actually travels
  (platform → depositor). It used to demand that the customer prove they had
  paid the PLATFORM the amount the platform owed THEM, which made every channel
  with a non-zero balance unclosable.
* open_channel / the pay-per-call invoke path bind the credit to the wallet that
  really paid and consume the transaction exactly once.
* refund_channel is capped at the deposit and idempotent per debit; deduct
  refuses negative amounts and expired channels.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict, deque

import pytest
from fastapi.testclient import TestClient

from web.backend.api import payment as payment_api
from web.backend.services.ai_market_protocol import channels as ch_mod
from web.backend.services.ai_market_protocol import on_chain as oc

PLATFORM = "0x" + "11" * 20
PAYER = "0x" + "22" * 20
STRANGER = "0x" + "33" * 20
CUSTOMER = "cust-1"
EMAIL = "cust-1@test.local"


def _tx(seed: str) -> str:
    return "0x" + (seed * 64)[:64]


def _fake_evm(records: dict[str, dict]):
    """Deterministic stand-in for payment_api._verify_evm_transaction."""

    def _verify(*, chain, tx_hash, expected_recipient, expected_amount, expected_token):
        rec = records.get(tx_hash)
        if not rec:
            return {"verified": False, "error": "Transaction not found on chain"}
        if str(rec["to"]).lower() != str(expected_recipient).lower():
            return {
                "verified": False,
                "error": f"Transaction recipient mismatch. Expected {expected_recipient}",
            }
        if float(rec["amount"]) + 1e-9 < float(expected_amount):
            return {"verified": False, "error": "Insufficient amount"}
        return {
            "verified": True,
            "confirmations": 12,
            "from": rec.get("from"),
            "to": rec["to"],
            "amount": float(rec["amount"]),
            "token": expected_token,
            "block_number": 123,
        }

    return _verify


@pytest.fixture
def chain_env(tmp_path, monkeypatch):
    """Crypto ON, demo bypass OFF, UNI OFF, no production markers, fake RPC."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "0")
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "0")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_CHAIN", "base")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_TOKEN", "USDT")
    for key in (
        "AIFACTORY_PROD",
        "AIFACTORY_PRODUCTION",
        "AIFACTORY_ENV",
        "AIFACTORY_AI_MARKET_REQUIRE_PAYER_PROOF",
        "AIFACTORY_AI_MARKET_ALLOW_UNPROVEN_PAYER",
        "AIFACTORY_AI_MARKET_REFUND_WALLETS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(payment_api, "RECIPIENT_ADDRESS_EVM", PLATFORM)
    records: dict[str, dict] = {}
    monkeypatch.setattr(payment_api, "_verify_evm_transaction", _fake_evm(records))
    # A fresh tx-claim + channel store per test.
    monkeypatch.setattr(ch_mod, "_commerce", _NoOrders())
    return records


class _NoOrders:
    """Commerce stub: no prior order ever consumed a hash."""

    def get_order_by_tx_hash(self, tx_hash):  # noqa: D102 - trivial stub
        return None


def _open(records, *, deposit=5.0, tx=None, wallet="", payer=PAYER, **kw):
    tx = tx or _tx(uuid.uuid4().hex[:8])
    records[tx] = {"from": payer, "to": PLATFORM, "amount": deposit}
    return ch_mod.open_channel(
        deposit_usd=deposit,
        tx_hash=tx,
        wallet=wallet,
        customer_id=CUSTOMER,
        customer_email=EMAIL,
        **kw,
    ), tx


# ═══════════════════════════════════════════════════════════════════════
# FINDING #8b — refund direction
# ═══════════════════════════════════════════════════════════════════════

def test_close_verifies_refund_paid_to_depositor(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=5.0)
    assert "error" not in opened, opened
    channel_id = opened["channel"]["channel_id"]
    secret = opened["channel_secret"]

    assert ch_mod.deduct_channel(channel_id, 1.0, ref="r1", secret=secret)["ok"]

    settle = _tx("ab")
    records[settle] = {"from": PLATFORM, "to": PAYER, "amount": 4.0}
    out = ch_mod.close_channel(
        channel_id=channel_id, settle_tx_hash=settle, customer_id=CUSTOMER
    )
    assert "error" not in out, out
    s = out["settlement"]
    assert s["refund_usd"] == 4.0
    assert s["used_usd"] == 1.0
    assert s["refund_status"] == "paid"
    assert s["refund_destination"].lower() == PAYER.lower()
    assert s["refund_owed_usd"] == 0.0
    assert ch_mod.list_outstanding_refunds() == []


def test_close_rejects_inverted_settlement_proof(chain_env):
    """The old logic accepted only this tx — a payment to the PLATFORM."""
    records = chain_env
    opened, _ = _open(records, deposit=2.0)
    channel_id = opened["channel"]["channel_id"]

    inverted = _tx("cd")
    records[inverted] = {"from": PAYER, "to": PLATFORM, "amount": 2.0}
    out = ch_mod.close_channel(
        channel_id=channel_id, settle_tx_hash=inverted, customer_id=CUSTOMER
    )
    assert out.get("error") == "settle_tx_not_verified"
    # ... and the channel is still closable without an impossible proof.
    assert ch_mod.get_channel(channel_id)["status"] == "open"
    ok = ch_mod.close_channel(channel_id=channel_id, customer_id=CUSTOMER)
    assert "error" not in ok, ok


def test_close_without_proof_records_refund_obligation(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=3.0)
    channel_id = opened["channel"]["channel_id"]

    out = ch_mod.close_channel(channel_id=channel_id, customer_id=CUSTOMER)
    assert "error" not in out, out
    s = out["settlement"]
    assert s["refund_usd"] == 3.0
    assert s["refund_status"] == "owed"
    assert s["refund_owed_usd"] == 3.0
    assert s["refund_paid_usd"] == 0.0
    assert s["signature"]
    assert out["channel"]["status"] == "closed"

    owed = ch_mod.list_outstanding_refunds()
    assert [(r["channel_id"], r["owed_usd"]) for r in owed] == [(channel_id, 3.0)]
    assert owed[0]["destination"].lower() == PAYER.lower()
    assert owed[0]["customer_email"] == EMAIL


def test_mark_refund_settled_requires_verified_outbound_tx(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=3.0)
    channel_id = opened["channel"]["channel_id"]
    ch_mod.close_channel(channel_id=channel_id, customer_id=CUSTOMER)

    # Unknown tx → obligation stands (fail closed).
    bad = ch_mod.mark_refund_settled(channel_id=channel_id, settle_tx_hash=_tx("ef"))
    assert bad["ok"] is False
    assert bad["error"] == "settle_tx_not_verified"
    assert ch_mod.list_outstanding_refunds()

    # A transfer from a stranger's wallet is not proof the platform paid.
    forged = _tx("1a")
    records[forged] = {"from": STRANGER, "to": PAYER, "amount": 3.0}
    assert ch_mod.mark_refund_settled(channel_id=channel_id, settle_tx_hash=forged)["ok"] is False
    assert ch_mod.list_outstanding_refunds()

    real = _tx("1b")
    records[real] = {"from": PLATFORM, "to": PAYER, "amount": 3.0}
    good = ch_mod.mark_refund_settled(
        channel_id=channel_id, settle_tx_hash=real, operator_id="ops"
    )
    assert good["ok"] is True
    assert good["settled_usd"] == 3.0
    assert ch_mod.list_outstanding_refunds() == []
    ch = ch_mod.get_channel(channel_id)
    assert ch["refund_status"] == "paid"
    assert ch["refund_owed_usd"] == 0.0
    assert any(e["type"] == "refund_settled" for e in ch["ledger"])
    # Re-recording the same payout is refused, not double-counted.
    assert ch_mod.mark_refund_settled(channel_id=channel_id, settle_tx_hash=real)["ok"] is False


def test_close_with_zero_balance_needs_no_settlement(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=1.0)
    channel_id = opened["channel"]["channel_id"]
    assert ch_mod.deduct_channel(
        channel_id, 1.0, ref="all", secret=opened["channel_secret"]
    )["ok"]

    out = ch_mod.close_channel(channel_id=channel_id, customer_id=CUSTOMER)
    s = out["settlement"]
    assert s["refund_status"] == "none"
    assert s["refund_usd"] == 0.0
    # An unverifiable hash is not recorded as settlement evidence.
    assert s["settle_tx_hash"] == ""


# ═══════════════════════════════════════════════════════════════════════
# FINDING #5 — bind the credit to the wallet that actually paid
# ═══════════════════════════════════════════════════════════════════════

def test_open_channel_binds_channel_to_onchain_sender(chain_env):
    records = chain_env
    opened, tx = _open(records, deposit=4.0)
    ch = opened["channel"]
    assert ch["deposit_wallet"].lower() == PAYER.lower()
    assert ch["wallet"].lower() == PAYER.lower()
    assert ch["deposit_wallet_verified"] is False
    assert ch["open_tx_hash"] == tx


def test_open_channel_rejects_wallet_that_did_not_pay(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=4.0, wallet=STRANGER)
    assert opened.get("error") == "wallet_mismatch"


def test_open_channel_fails_closed_when_sender_unknown(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=4.0, payer=None)
    assert opened.get("error") == "tx_not_verified"
    assert "sender_unresolved" in opened["detail"]


def test_open_channel_requires_payer_proof_when_configured(chain_env, monkeypatch):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    records = chain_env
    monkeypatch.setenv("AIFACTORY_AI_MARKET_REQUIRE_PAYER_PROOF", "1")
    key = "0x" + "42" * 32
    acct = Account.from_key(key)

    tx = _tx("2a")
    records[tx] = {"from": acct.address, "to": PLATFORM, "amount": 6.0}

    unproven = ch_mod.open_channel(
        deposit_usd=6.0, tx_hash=tx, customer_id=CUSTOMER, customer_email=EMAIL
    )
    assert unproven.get("error") == "deposit_proof_required"

    # The CANONICAL channel-open challenge, shared byte-for-byte with aimarket-hub.
    # (It replaced this package's private "channel deposit"/subject=customer_id
    # message: the two stacks had incompatible challenges for one concept, so no SDK
    # could target both. See on_chain's CANONICAL PAYER PROOF block.)
    message = oc.channel_open_proof_message(
        chain="base", tx_hash=tx, payer=acct.address, amount_usd=6.0
    )
    signed = Account.sign_message(encode_defunct(text=message), private_key=key)
    signature = "0x" + signed.signature.hex().removeprefix("0x")

    # A signature from a wallet that did not pay is not proof.
    other = Account.sign_message(encode_defunct(text=message), private_key="0x" + "43" * 32)
    bad = ch_mod.open_channel(
        deposit_usd=6.0,
        tx_hash=tx,
        customer_id=CUSTOMER,
        customer_email=EMAIL,
        signature="0x" + other.signature.hex().removeprefix("0x"),
    )
    assert bad.get("error") == "deposit_proof_invalid"

    ok = ch_mod.open_channel(
        deposit_usd=6.0,
        tx_hash=tx,
        customer_id=CUSTOMER,
        customer_email=EMAIL,
        signature=signature,
    )
    assert "error" not in ok, ok
    assert ok["channel"]["deposit_wallet_verified"] is True
    assert ok["channel"]["deposit_wallet"].lower() == acct.address.lower()


def test_deposit_tx_cannot_fund_two_channels_or_an_invoke(chain_env):
    records = chain_env
    opened, tx = _open(records, deposit=2.0)
    assert "error" not in opened

    again = ch_mod.open_channel(
        deposit_usd=2.0, tx_hash=tx, customer_id=CUSTOMER, customer_email=EMAIL
    )
    assert again.get("error") == "tx_hash_already_used"

    claimed = ch_mod.claim_payment_tx(
        tx_hash=tx, chain="base", token="USDT", amount_usd=2.0, purpose="invoke:x/y"
    )
    assert claimed["ok"] is False
    assert claimed["error"] == "tx_hash_already_used"


def test_payment_tx_claim_is_single_use(chain_env):
    first = ch_mod.claim_payment_tx(
        tx_hash=_tx("3a"),
        chain="base",
        token="USDT",
        amount_usd=0.4,
        purpose="invoke:p/c",
        sender=PAYER,
    )
    assert first["ok"] is True
    second = ch_mod.claim_payment_tx(
        tx_hash=_tx("3a"),
        chain="base",
        token="USDT",
        amount_usd=0.4,
        purpose="invoke:p/c",
        sender=PAYER,
    )
    assert second["ok"] is False
    assert ch_mod.payment_tx_claim(_tx("3a"))["sender"] == PAYER
    # Dev placeholder hashes are deliberately not registered.
    assert ch_mod.claim_payment_tx(
        tx_hash="demo-x", chain="base", token="USDT", amount_usd=1.0, purpose="invoke:p/c"
    )["ok"] is True


# ═══════════════════════════════════════════════════════════════════════
# refund / deduct symmetry
# ═══════════════════════════════════════════════════════════════════════

def test_refund_cannot_lift_channel_above_deposit(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=5.0)
    channel_id = opened["channel"]["channel_id"]
    secret = opened["channel_secret"]
    ch_mod.deduct_channel(channel_id, 1.0, ref="d1", secret=secret)

    out = ch_mod.refund_channel(channel_id, 100.0, ref="grief", debit_ref="d1")
    assert out["ok"] is True
    assert out["credited_usd"] == 1.0
    ch = ch_mod.get_channel(channel_id)
    assert ch["balance_usd"] == 5.0
    assert ch["spent_usd"] == 0.0

    # Nothing left to reverse.
    ch_mod.deduct_channel(channel_id, 1.0, ref="d2", secret=secret)
    ch_mod.refund_channel(channel_id, 1.0, ref="grief2", debit_ref="d2")
    assert (
        ch_mod.refund_channel(channel_id, 1.0, ref="grief3", debit_ref="d2")["error"]
        == "already_refunded"
    )
    assert ch_mod.get_channel(channel_id)["balance_usd"] == 5.0


def test_refund_requires_a_named_debit(chain_env):
    """An anonymous reversal is repeatable: the deposit cap bounds the BALANCE,
    not the number of reversals, so N unnamed calls used to hand back N debits'
    worth of spend one call at a time until spent_usd reached zero."""
    records = chain_env
    opened, _ = _open(records, deposit=5.0)
    channel_id = opened["channel"]["channel_id"]
    secret = opened["channel_secret"]
    ch_mod.deduct_channel(channel_id, 3.0, ref="d1", secret=secret)

    for i in range(3):
        out = ch_mod.refund_channel(channel_id, 1.0, ref=f"anon{i}", debit_ref="")
        assert out["ok"] is False
        assert out["error"] == "debit_ref_required"

    ch = ch_mod.get_channel(channel_id)
    assert ch["balance_usd"] == 2.0
    assert ch["spent_usd"] == 3.0
    # Naming the debit reverses it exactly once.
    assert ch_mod.refund_channel(channel_id, 1.0, ref="rev", debit_ref="d1")["credited_usd"] == 1.0
    assert ch_mod.refund_channel(channel_id, 1.0, ref="rev2", debit_ref="d1")["ok"] is False


def test_refund_is_capped_and_idempotent_per_debit(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=5.0)
    channel_id = opened["channel"]["channel_id"]
    secret = opened["channel_secret"]
    ch_mod.deduct_channel(channel_id, 0.40, ref="debit-a", secret=secret)
    ch_mod.deduct_channel(channel_id, 0.25, ref="debit-b", secret=secret)

    over = ch_mod.refund_channel(channel_id, 5.0, ref="rev-a", debit_ref="debit-a")
    assert over["credited_usd"] == 0.40

    dup = ch_mod.refund_channel(channel_id, 0.40, ref="rev-a2", debit_ref="debit-a")
    assert dup["ok"] is False
    assert dup["error"] == "already_refunded"

    unknown = ch_mod.refund_channel(channel_id, 0.10, ref="rev-x", debit_ref="nope")
    assert unknown["error"] == "unknown_debit"

    ch = ch_mod.get_channel(channel_id)
    assert ch["balance_usd"] == 4.75
    assert ch["spent_usd"] == 0.25


def test_uni_backed_refund_records_debt_instead_of_inflating_mirror(chain_env, monkeypatch):
    """The UNI hold was already spent and this bridge has no un-spend primitive."""
    records = chain_env
    opened, _ = _open(records, deposit=2.0)
    channel_id = opened["channel"]["channel_id"]
    ch_mod.deduct_channel(channel_id, 1.0, ref="d1", secret=opened["channel_secret"])

    with ch_mod.channel_store_lock():
        data = ch_mod._load_channels()
        data[channel_id]["uni"] = {"hold": {"channel_id": channel_id}}
        ch_mod._save_channels(data)
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "1")

    out = ch_mod.refund_channel(channel_id, 1.0, ref="rev", debit_ref="d1")
    assert out["ok"] is False
    assert out["error"] == "uni_refund_unavailable"
    assert out["owed_usd"] == 1.0

    ch = ch_mod.get_channel(channel_id)
    assert ch["balance_usd"] == 1.0  # mirror untouched — no invented balance
    assert ch["refund_owed_usd"] == 1.0
    assert any(e["type"] == "credit_owed" for e in ch["ledger"])
    assert [r["channel_id"] for r in ch_mod.list_outstanding_refunds()] == [channel_id]
    # The obligation is recorded once, not on every retry.
    assert ch_mod.refund_channel(channel_id, 1.0, ref="rev2", debit_ref="d1")["error"] == "already_refunded"


def test_refund_refused_on_closed_channel(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=2.0)
    channel_id = opened["channel"]["channel_id"]
    ch_mod.deduct_channel(channel_id, 1.0, ref="d", secret=opened["channel_secret"])
    ch_mod.close_channel(channel_id=channel_id, customer_id=CUSTOMER)

    out = ch_mod.refund_channel(channel_id, 1.0, ref="post-close", debit_ref="d")
    assert out["ok"] is False
    assert out["error"] == "channel_not_open"
    assert ch_mod.get_channel(channel_id)["balance_usd"] == 1.0


def test_deduct_rejects_negative_amount(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=1.0)
    channel_id = opened["channel"]["channel_id"]

    out = ch_mod.deduct_channel(
        channel_id, -50.0, ref="mint", secret=opened["channel_secret"]
    )
    assert out["ok"] is False
    assert out["error"] == "invalid_amount"
    assert ch_mod.get_channel(channel_id)["balance_usd"] == 1.0


def test_deduct_refuses_expired_channel_but_close_still_works(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=2.0)
    channel_id = opened["channel"]["channel_id"]
    secret = opened["channel_secret"]

    with ch_mod.channel_store_lock():
        data = ch_mod._load_channels()
        data[channel_id]["expires_at"] = time.time() - 5
        ch_mod._save_channels(data)

    out = ch_mod.deduct_channel(channel_id, 0.4, ref="late", secret=secret)
    assert out["ok"] is False
    assert out["error"] == "channel_expired"

    closed = ch_mod.close_channel(channel_id=channel_id, customer_id=CUSTOMER)
    assert closed["settlement"]["refund_usd"] == 2.0


def test_sub_cent_price_bills_a_cent_and_ledger_stays_exact(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=1.0)
    channel_id = opened["channel"]["channel_id"]
    secret = opened["channel_secret"]

    tiny = ch_mod.deduct_channel(channel_id, 0.004, ref="tiny", secret=secret)
    assert tiny["billed_usd"] == 0.01

    for i, amount in enumerate([0.35, 0.07, 0.35]):
        assert ch_mod.deduct_channel(channel_id, amount, ref=f"d{i}", secret=secret)["ok"]

    ch = ch_mod.get_channel(channel_id)
    # deposit == balance + spent, exactly, with no float drift.
    assert round(ch["balance_usd"] + ch["spent_usd"], 4) == ch["deposit_usd"]
    assert ch["spent_usd"] == 0.78


def test_free_capability_debits_nothing(chain_env):
    records = chain_env
    opened, _ = _open(records, deposit=1.0)
    channel_id = opened["channel"]["channel_id"]
    out = ch_mod.deduct_channel(
        channel_id, 0.0, ref="free", secret=opened["channel_secret"]
    )
    assert out["ok"] is True
    assert out["billed_usd"] == 0.0
    assert ch_mod.get_channel(channel_id)["balance_usd"] == 1.0


def test_channel_store_lock_is_reentrant(chain_env):
    """A nested acquire must not deadlock against its own flock."""
    with ch_mod.channel_store_lock():
        with ch_mod.channel_store_lock():
            assert ch_mod._load_channels() == {}


# ═══════════════════════════════════════════════════════════════════════
# on_chain verifier variants
# ═══════════════════════════════════════════════════════════════════════

def test_verify_tx_transfer_requires_explicit_sender_expectation(chain_env):
    records = chain_env
    tx = _tx("4a")
    records[tx] = {"from": PAYER, "to": PLATFORM, "amount": 1.0}
    kw = dict(tx_hash=tx, amount_usd=1.0, chain="base", token="USDT")

    bound = oc.verify_tx_transfer(**kw, expect_sender=oc.BIND_SENDER)
    assert bound["verified"] is True
    assert bound["from"] == PAYER

    assert oc.verify_tx_transfer(**kw, expect_sender=PAYER)["verified"] is True
    mismatch = oc.verify_tx_transfer(**kw, expect_sender=STRANGER)
    assert mismatch["verified"] is False
    assert mismatch["error"] == "sender_mismatch"

    # Legacy helper: still answers "somebody paid the platform" for out-of-tree callers.
    assert oc.verify_tx_payment(**kw) is True
    assert oc.verify_tx_payment_details(**kw) == (True, PAYER)

    with pytest.raises(ValueError):
        oc.verify_tx_transfer(**kw, expect_sender="")
    with pytest.raises(ValueError):
        oc.verify_tx_transfer(**kw, expect_sender=[])


def test_verify_tx_transfer_fails_closed_without_crypto(chain_env, monkeypatch):
    records = chain_env
    tx = _tx("4b")
    records[tx] = {"from": PAYER, "to": PLATFORM, "amount": 1.0}
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
    out = oc.verify_tx_transfer(
        tx_hash=tx, amount_usd=1.0, chain="base", token="USDT", expect_sender=oc.BIND_SENDER
    )
    assert out["verified"] is False
    assert out["error"] == "crypto_disabled"


def test_verifier_exception_is_not_a_verified_payment(chain_env, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("rpc exploded")

    monkeypatch.setattr(payment_api, "_verify_evm_transaction", _boom)
    out = oc.verify_tx_transfer(
        tx_hash=_tx("4c"),
        amount_usd=1.0,
        chain="base",
        token="USDT",
        expect_sender=oc.BIND_SENDER,
    )
    assert out["verified"] is False
    assert out["error"] == "verifier_error"


def test_unconfigured_payout_wallet_refuses_instead_of_raising(chain_env, monkeypatch):
    """``RECIPIENT_ADDRESS_EVM`` is "" until load_wallets() runs, and an EVM-only
    deployment has no Solana wallet at all. refund_payer_wallets() is then empty,
    and verify_tx_transfer rejects an empty expectation with a ValueError. Letting
    that escape turns a customer-facing close into a 500 — i.e. straight back into
    the unclosable channel of finding #8b."""
    records = chain_env
    opened, _ = _open(records, deposit=3.0)
    channel_id = opened["channel"]["channel_id"]

    monkeypatch.setattr(payment_api, "RECIPIENT_ADDRESS_EVM", "")
    assert oc.refund_payer_wallets("base") == ()

    out = oc.verify_refund_transfer(
        tx_hash=_tx("8a"), amount_usd=3.0, chain="base", token="USDT", destination=PAYER
    )
    assert out["verified"] is False
    assert out["error"] == "refund_payout_wallet_unconfigured"

    # close is a plain refusal of the proof, never an exception...
    rejected = ch_mod.close_channel(
        channel_id=channel_id, settle_tx_hash=_tx("8b"), customer_id=CUSTOMER
    )
    assert rejected["error"] == "settle_tx_not_verified"
    assert "refund_payout_wallet_unconfigured" in rejected["detail"]

    # ...and closing without a proof still works, so the customer is never stuck.
    closed = ch_mod.close_channel(channel_id=channel_id, customer_id=CUSTOMER)
    assert closed["settlement"]["refund_status"] == "owed"

    # The operator-side clear fails closed the same way: obligation stands.
    marked = ch_mod.mark_refund_settled(channel_id=channel_id, settle_tx_hash=_tx("8c"))
    assert marked["ok"] is False
    assert marked["error"] == "settle_tx_not_verified"
    assert ch_mod.list_outstanding_refunds()[0]["owed_usd"] == 3.0


def test_sender_expectation_sentinels_cannot_be_forged_by_a_caller(chain_env):
    """invoke.py forwards the client's ``X-Payment.from`` straight into
    expect_sender. When the sentinels were magic strings, sending
    ``from: "<any-sender>"`` disabled the payer binding entirely — including the
    sender_unresolved refusal for a transfer whose payer the chain never reported."""
    records = chain_env
    tx = _tx("9a")
    records[tx] = {"from": None, "to": PLATFORM, "amount": 1.0}  # chain hides the payer
    kw = dict(tx_hash=tx, amount_usd=1.0, chain="base", token="USDT")

    assert not isinstance(oc.ANY_SENDER, str)
    assert not isinstance(oc.BIND_SENDER, str)

    bound = oc.verify_tx_transfer(**kw, expect_sender=oc.BIND_SENDER)
    assert bound["verified"] is False
    assert bound["error"] == "sender_unresolved"

    for forged in ("<any-sender>", "<bind-sender>", repr(oc.ANY_SENDER)):
        out = oc.verify_tx_transfer(**kw, expect_sender=forged)
        assert out["verified"] is False, forged
        assert out["error"] == "sender_unresolved", forged

    # Same over the wire: a resolvable payer plus a forged sentinel is a mismatch,
    # not a free pass.
    tx2 = _tx("9b")
    records[tx2] = {"from": PAYER, "to": PLATFORM, "amount": 1.0}
    forged2 = oc.verify_tx_transfer(
        tx_hash=tx2, amount_usd=1.0, chain="base", token="USDT", expect_sender="<any-sender>"
    )
    assert forged2["verified"] is False
    assert forged2["error"] == "sender_mismatch"


def test_deposit_below_one_cent_is_refused_not_swallowed(chain_env):
    """The ledger is integer cents, so a $0.004 deposit would credit a $0.00
    channel and silently keep the transfer. Refused before the tx is consumed."""
    records = chain_env
    tx = _tx("9c")
    records[tx] = {"from": PAYER, "to": PLATFORM, "amount": 0.004}
    out = ch_mod.open_channel(
        deposit_usd=0.004, tx_hash=tx, customer_id=CUSTOMER, customer_email=EMAIL
    )
    assert out["error"] == "invalid_deposit"
    # The hash was never consumed, so a correctly-sized deposit can still use it.
    records[tx] = {"from": PAYER, "to": PLATFORM, "amount": 1.0}
    ok = ch_mod.open_channel(
        deposit_usd=1.0, tx_hash=tx, customer_id=CUSTOMER, customer_email=EMAIL
    )
    assert "error" not in ok, ok
    assert ok["channel"]["balance_usd"] == 1.0


def test_refund_wallet_allowlist_extends_payout_senders(chain_env, monkeypatch):
    records = chain_env
    monkeypatch.setenv("AIFACTORY_AI_MARKET_REFUND_WALLETS", f" {STRANGER} ")
    tx = _tx("4d")
    records[tx] = {"from": STRANGER, "to": PAYER, "amount": 2.0}
    out = oc.verify_refund_transfer(
        tx_hash=tx, amount_usd=2.0, chain="base", token="USDT", destination=PAYER
    )
    assert out["verified"] is True
    assert oc.verify_refund_transfer(
        tx_hash=tx, amount_usd=2.0, chain="base", token="USDT", destination=""
    )["error"] == "refund_destination_unknown"


# ═══════════════════════════════════════════════════════════════════════
# Pay-per-call invoke: one transfer buys exactly one invoke
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def invoke_client(tmp_path, monkeypatch, chain_env):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-ci-only-32chars-minimum!!")
    monkeypatch.setenv("AIFACTORY_CUSTOMER_REGISTER_MAX_PER_HOUR", "1000")
    monkeypatch.setattr("web.backend.api.customer._register_attempts", defaultdict(deque))
    pipeline = tmp_path / "data" / "state" / "pipeline.json"
    pipeline.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_text(
        json.dumps({
            "products": {
                "prod-test0001": {
                    "state": "COMPLETED",
                    "name": "Legal Translator",
                    "idea": "Translate and localize legal documents for compliance review",
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pipeline))
    code_root = tmp_path / "data" / "code" / "prod-test0001"
    code_root.mkdir(parents=True, exist_ok=True)
    (code_root / "index.html").write_text("<html></html>", encoding="utf-8")
    (code_root / "code_manifest.json").write_text(
        json.dumps({"files": [{"path": "index.html"}]}), encoding="utf-8"
    )
    from web.backend.main import app

    return TestClient(app), chain_env


def test_onchain_invoke_payment_is_bound_and_single_use(invoke_client):
    client, records = invoke_client
    pid, cid = "prod-test0001", "summarize@v1"

    price = client.get(f"/ai-market/pricing/{pid}/{cid}").json()["price_usd"]
    assert price > 0

    tx = _tx("5a")
    records[tx] = {"from": PAYER, "to": PLATFORM, "amount": price}
    header = {"X-Payment": json.dumps({"tx_hash": tx, "chain": "base", "token": "USDT"})}

    r1 = client.post(f"/capabilities/{pid}/{cid}/invoke", json={"input": {"text": "hi"}}, headers=header)
    assert r1.status_code == 200, r1.text
    assert r1.json()["receipt"]["payment_kind"] == "on_chain"

    # Replaying the same transfer must not buy a second invoke.
    r2 = client.post(f"/capabilities/{pid}/{cid}/invoke", json={"input": {"text": "hi"}}, headers=header)
    assert r2.status_code == 402
    assert "already used" in r2.json()["detail"]


def test_onchain_invoke_rejects_declared_payer_that_did_not_pay(invoke_client):
    client, records = invoke_client
    pid, cid = "prod-test0001", "summarize@v1"
    price = client.get(f"/ai-market/pricing/{pid}/{cid}").json()["price_usd"]

    tx = _tx("5b")
    records[tx] = {"from": PAYER, "to": PLATFORM, "amount": price}
    r = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hi"}},
        headers={"X-Payment": json.dumps({"tx_hash": tx, "chain": "base", "from": STRANGER})},
    )
    assert r.status_code == 402
    assert "sender_mismatch" in r.json()["detail"]
    # The rejected attempt must not have consumed the honest payer's transfer.
    assert ch_mod.payment_tx_claim(tx) is None


def test_onchain_invoke_rejects_forged_sender_sentinel(invoke_client):
    """X-Payment.from lands in expect_sender. A caller sending the sentinel text
    must not switch the payer gate off for a transfer with no resolvable payer."""
    client, records = invoke_client
    pid, cid = "prod-test0001", "summarize@v1"
    price = client.get(f"/ai-market/pricing/{pid}/{cid}").json()["price_usd"]

    tx = _tx("5d")
    records[tx] = {"from": None, "to": PLATFORM, "amount": price}
    r = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hi"}},
        headers={"X-Payment": json.dumps({"tx_hash": tx, "chain": "base", "from": "<any-sender>"})},
    )
    assert r.status_code == 402, r.text
    assert "sender_unresolved" in r.json()["detail"]
    # Nothing was consumed, so the real payer (if any) is not out of pocket.
    assert ch_mod.payment_tx_claim(tx) is None


def test_failed_execution_on_onchain_payment_records_an_obligation(invoke_client, monkeypatch):
    """The transfer stays consumed, so the unearned money must be recorded as owed."""
    client, records = invoke_client
    from web.backend.services.ai_market_protocol import invoke as invoke_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("capability exploded")

    monkeypatch.setattr(invoke_mod, "_execute_capability", _boom)

    pid, cid = "prod-test0001", "summarize@v1"
    price = client.get(f"/ai-market/pricing/{pid}/{cid}").json()["price_usd"]
    tx = _tx("6a")
    records[tx] = {"from": PAYER, "to": PLATFORM, "amount": price}

    r = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hi"}},
        headers={"X-Payment": json.dumps({"tx_hash": tx, "chain": "base"})},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["error_type"] == "execution_failed"
    assert body["refund"]["status"] == "owed"
    assert body["receipt"]["amount_usd"] == 0.0

    owed = ch_mod.list_unfulfilled_payments()
    assert len(owed) == 1
    assert owed[0]["tx_hash"] == tx
    assert owed[0]["sender"] == PAYER
    # The hash stays consumed — a failed delivery is not a free retry token.
    retry = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hi"}},
        headers={"X-Payment": json.dumps({"tx_hash": tx, "chain": "base"})},
    )
    assert retry.status_code == 402


def test_failed_execution_on_channel_reverses_exactly_that_debit(invoke_client, monkeypatch):
    client, records = invoke_client
    from web.backend.services.ai_market_protocol import invoke as invoke_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("capability exploded")

    monkeypatch.setattr(invoke_mod, "_execute_capability", _boom)

    from web.backend.services.customer_auth import decode_customer

    reg = client.post(
        "/api/customer/register",
        json={"email": f"ch-{uuid.uuid4().hex[:8]}@test.local", "password": "password12345"},
    )
    assert reg.status_code == 200, reg.text
    auth = f"Bearer {reg.json()['access_token']}"
    sub = str(decode_customer(auth)["sub"])

    tx = _tx("7a")
    records[tx] = {"from": PAYER, "to": PLATFORM, "amount": 2.0}
    opened = ch_mod.open_channel(
        deposit_usd=2.0, tx_hash=tx, customer_id=sub, customer_email="ch@test.local"
    )
    assert "error" not in opened, opened
    channel_id = opened["channel"]["channel_id"]
    pid, cid = "prod-test0001", "summarize@v1"

    r = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hi"}},
        headers={
            "Authorization": auth,
            "X-Payment-Channel": channel_id,
            "X-Payment-Channel-Secret": opened["channel_secret"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["refund"]["status"] == "credited"

    ch = ch_mod.get_channel(channel_id)
    assert ch["balance_usd"] == 2.0
    assert ch["spent_usd"] == 0.0
    assert [e["type"] for e in ch["ledger"]] == ["debit", "credit"]


def test_onchain_invoke_requires_payer_proof_when_configured(invoke_client, monkeypatch):
    client, records = invoke_client
    monkeypatch.setenv("AIFACTORY_AI_MARKET_REQUIRE_PAYER_PROOF", "1")
    pid, cid = "prod-test0001", "summarize@v1"
    price = client.get(f"/ai-market/pricing/{pid}/{cid}").json()["price_usd"]

    from eth_account import Account
    from eth_account.messages import encode_defunct

    key = "0x" + "51" * 32
    acct = Account.from_key(key)
    tx = _tx("5c")
    records[tx] = {"from": acct.address, "to": PLATFORM, "amount": price}

    unproven = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hi"}},
        headers={"X-Payment": json.dumps({"tx_hash": tx, "chain": "base"})},
    )
    assert unproven.status_code == 402
    assert "signature proving control" in unproven.json()["detail"]

    message = oc.payer_proof_message(
        purpose="invoke payment", subject=acct.address, tx_hash=tx, chain="base"
    )
    signed = Account.sign_message(encode_defunct(text=message), private_key=key)
    proven = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hi"}},
        headers={
            "X-Payment": json.dumps({
                "tx_hash": tx,
                "chain": "base",
                "from": acct.address,
                "signature": "0x" + signed.signature.hex().removeprefix("0x"),
            })
        },
    )
    assert proven.status_code == 200, proven.text
