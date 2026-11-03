"""Channel ids and public wallet addresses are never spending credentials."""

import pytest

from aimarket_hub import channels

import itertools as _itertools

_RIDS = _itertools.count()


def _rid() -> str:
    """A fresh receipt id: a debit that moves money must name the operation it pays for."""
    return f"test-receipt-{next(_RIDS)}"



@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")
    led = channels.ChannelLedger(db_path=str(tmp_path / "channels.db"))
    monkeypatch.setattr(channels, "_ledger", led)
    yield led
    led.stop_sweep()


def test_primitive_open_mints_secret_by_default(ledger):
    opened = ledger.open(5.0)["channel"]
    assert opened.get("channel_secret")
    assert not ledger.secret_error(opened["channel_id"], opened["channel_secret"])


@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("operation", ["debit", "hold", "close", "refund"])
@pytest.mark.parametrize("secret", ["", "invented-secret"])
def test_secretless_channel_is_frozen(ledger, public, operation, secret):
    # Simulate a row predating migration 007, including previously spent funds.
    ch = ledger.open(5.0, wallet="0xAlice")["channel"]
    cid = ch["channel_id"]
    with ledger._get_conn() as conn:
        conn.execute("UPDATE channels SET secret_hash = '', balance_cents = 400, "
                     "used_cents = 100 WHERE channel_id = ?", (cid,))
        conn.commit()
    before = ledger.get(cid)
    fn = getattr(channels, operation + "_channel") if public else getattr(ledger, operation)
    kwargs = {"secret": secret}
    if operation == "close":
        result = fn(cid, wallet="0xAlice", **kwargs)
    else:
        kwargs["requester_wallet"] = "0xAlice"
        if operation in ("hold", "debit"):
            kwargs["receipt_id"] = "unauthorized-operation"
        result = fn(cid, 1.0, **kwargs)
    assert result.get("error", "").startswith("unauthorized:"), result
    assert "balance" not in result
    assert ledger.get(cid) == before
    assert ledger.hold_state("unauthorized-operation") == ""
    with ledger._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM debited_receipts").fetchone()[0] == 0
    assert ledger.obligations() == []


@pytest.mark.parametrize("operation", ["debit", "hold", "close", "refund"])
@pytest.mark.parametrize("credential", ["missing", "wrong", "valid"])
def test_new_channel_requires_matching_secret(ledger, operation, credential):
    ch = ledger.open(5.0, wallet="0xAlice")["channel"]
    cid, secret = ch["channel_id"], ch["channel_secret"]
    assert ledger.debit(cid, 1.0, secret=secret, receipt_id=_rid())["ok"]
    before = ledger.get(cid)
    supplied = secret if credential == "valid" else "wrong" if credential == "wrong" else ""
    fn = getattr(ledger, operation)
    if operation == "close":
        result = fn(cid, wallet="0xAlice", secret=supplied)
    elif operation == "hold":
        result = fn(cid, 1.0, receipt_id="hold-auth", secret=supplied)
    elif operation == "debit":
        result = fn(cid, 1.0, secret=supplied, receipt_id=_rid())
    else:
        result = fn(cid, 1.0, secret=supplied)
    if credential == "valid":
        assert "error" not in result, result
    else:
        assert result["error"].startswith("unauthorized:")
        assert ledger.get(cid) == before
