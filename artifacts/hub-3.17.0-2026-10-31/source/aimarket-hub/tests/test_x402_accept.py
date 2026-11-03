"""x402 payments the hub actually honours.

A PAYMENT-SIGNATURE is checked against the seller this listing named; the
call is served only after the same payment is on chain to that address.
A signature without a chain receipt is not a payment.

The signature tests need a crypto stack the hub's own test venv deliberately lacks (see
`escrow_bridge.eip712.CryptoUnavailable`), so they skip there and the rest still runs — the
terms checks are pure logic and must never be the reason a payment is wrongly accepted.
"""
from __future__ import annotations

import base64
import json
import secrets
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import x402
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.escrow_bridge import eip712
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer

PAY_TO = "0x1218Ff3600000000000000000000000000000a0a"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PRICE = 0.02

crypto = pytest.mark.skipif(
    not eip712.crypto_available(), reason="eth-account not installed in this interpreter",
)


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("AIMARKET_X402_ACCEPT", "1")
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    db.upsert_capability(Capability(
        capability_id="x.pay@v1", product_id="x-pay", name="Paid pack",
        description="static", price_per_call_usd=PRICE, source_hub="local",
        invoke_url="", prompt_template=json.dumps({"answer": "paid"}),
    ))
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client


def _authorization(sender: str, *, value: int = 20_000, to: str = PAY_TO,
                   valid_before: int = 4_000_000_000, nonce: str | None = None) -> dict:
    return {
        "from": sender,
        "to": to,
        "value": str(value),
        "validAfter": "0",
        "validBefore": str(valid_before),
        "nonce": nonce or ("0x" + secrets.token_hex(32)),
    }


def _envelope(auth: dict, signature: str) -> str:
    payload = {
        "x402Version": 2,
        "scheme": "exact",
        "network": "eip155:8453",
        "asset": USDC_BASE,
        "payload": {"authorization": auth, "signature": signature},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _sign(auth: dict, private_key: str) -> str:
    from eth_account import Account

    digest = eip712.transfer_authorization_digest(
        sender=auth["from"], recipient=auth["to"], value=int(auth["value"]),
        valid_after=int(auth["validAfter"]), valid_before=int(auth["validBefore"]),
        nonce=auth["nonce"], token_name="USD Coin", token_version="2",
        chain_id=8453, token_address=USDC_BASE,
    )
    return Account._sign_hash(digest, private_key).signature.hex()


def _invoke(client, header: str | None = None, secret: str = ""):
    headers = {"X-PAYMENT": header} if header else {}
    if secret:
        headers["X-Payment-Secret"] = secret
    return client.post("/ai-market/v2/invoke", headers=headers, json={
        "product_id": "x-pay", "capability_id": "x.pay@v1",
        "input": {}, "source_hub": "local",
    })


class TestTermsAreEnforcedBeforeAnyWork:
    def test_a_payment_to_somebody_else_is_refused(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            auth = _authorization("0x" + "11" * 20, to="0x" + "22" * 20)
            r = _invoke(client, _envelope(auth, "0x" + "00" * 65))
            assert r.status_code == 402
            assert "addressed to somebody else" in r.json()["detail"]

    def test_an_underpayment_is_refused_with_the_real_numbers(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            auth = _authorization("0x" + "11" * 20, value=1)
            r = _invoke(client, _envelope(auth, "0x" + "00" * 65))
            assert r.status_code == 402
            assert "the call costs 20000" in r.json()["detail"]

    def test_an_expired_authorization_is_refused(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            auth = _authorization("0x" + "11" * 20, valid_before=1)
            r = _invoke(client, _envelope(auth, "0x" + "00" * 65))
            assert r.status_code == 402
            assert "expired" in r.json()["detail"]

    def test_a_payment_on_another_chain_is_refused(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            payload = {
                "scheme": "exact", "network": "eip155:1", "asset": USDC_BASE,
                "payload": {"authorization": _authorization("0x" + "11" * 20),
                            "signature": "0x" + "00" * 65},
            }
            r = _invoke(client, base64.b64encode(json.dumps(payload).encode()).decode())
            assert r.status_code == 402
            assert "network" in r.json()["detail"]

    def test_a_malformed_header_is_a_400_not_a_free_call(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            r = _invoke(client, "!!!not base64 and not json!!!")
            assert r.status_code == 400
            assert r.json()["error"] == "payment_malformed"

    def test_an_unsigned_payload_never_buys_anything(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            payload = {"scheme": "exact", "payload": {
                "authorization": _authorization("0x" + "11" * 20)}}
            r = _invoke(client, base64.b64encode(json.dumps(payload).encode()).decode())
            assert r.status_code == 402
            assert "no signed authorization" in r.json()["detail"]


def _with_tx(envelope: str, tx: str = "0x" + "ab" * 32) -> str:
    payload = json.loads(base64.b64decode(envelope + "=" * (-len(envelope) % 4)))
    payload["txHash"] = tx
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _stub_chain(monkeypatch, pay_to: str = PAY_TO):
    def _ok(*, tx_hash, terms, **_k):
        return {
            "tx_hash": tx_hash.strip().lower(),
            "paid_units": int(terms.amount_units),
            "confirmations": 1,
            "block_number": 1,
            "chain": terms.chain,
            "token": terms.token,
            "pay_to": terms.pay_to,
            "nonce": "",
            "authorizer": "",
            "amount_usd": terms.amount_usd,
        }
    monkeypatch.setattr("aimarket_hub.settle.verify_transfer", _ok)


class TestWithARealSignature:
    @crypto
    def test_a_valid_payment_buys_the_call_once_it_is_on_chain(self, monkeypatch, tmp_path):
        from eth_account import Account

        acct = Account.create()
        _stub_chain(monkeypatch)
        with _hub(monkeypatch, tmp_path) as client:
            # Signed over the nonce of the 402 this buyer took, redeemed with its secret.
            quote = _invoke(client).json()
            auth = _authorization(acct.address, nonce=quote["nonce"])
            r = _invoke(client, _with_tx(_envelope(auth, _sign(auth, acct.key))),
                        secret=quote["payment_secret"])
            assert r.status_code == 200, r.text
            assert r.json()["result"]["answer"] == "paid"

            live = client.get("/ai-market/v2/stats/live").json()
            stats = live["summary"]["x402"]
            assert stats["payments"] == 1
            assert stats["x402_settled_usd"] == pytest.approx(PRICE)
            assert stats["x402_unsettled_usd"] == 0.0
            # The feed names the rail that paid; this used to read `anonymous`.
            assert [e["consumer_hub"] for e in live["events"]] == ["x402"]

    @crypto
    def test_the_same_authorization_cannot_buy_twice(self, monkeypatch, tmp_path):
        from eth_account import Account

        acct = Account.create()
        _stub_chain(monkeypatch)
        with _hub(monkeypatch, tmp_path) as client:
            quote = _invoke(client).json()
            auth = _authorization(acct.address, nonce=quote["nonce"])
            header = _with_tx(_envelope(auth, _sign(auth, acct.key)))
            assert _invoke(client, header, secret=quote["payment_secret"]).status_code == 200
            second = _invoke(client, header, secret=quote["payment_secret"])
            assert second.status_code == 402
            assert "already been" in second.json()["detail"]

    @crypto
    def test_somebody_elses_signature_does_not_pay_for_you(self, monkeypatch, tmp_path):
        from eth_account import Account

        payer, stranger = Account.create(), Account.create()
        with _hub(monkeypatch, tmp_path) as client:
            auth = _authorization(payer.address)
            r = _invoke(client, _envelope(auth, _sign(auth, stranger.key)))
            assert r.status_code == 402
            assert "does not match the stated payer" in r.json()["detail"]


class TestTheSwitchIsOff():
    def test_a_payment_header_is_ignored_when_acceptance_is_off(self, monkeypatch, tmp_path):
        """Discovery-only remains available: AIMARKET_X402_ACCEPT=0 ignores a header."""
        with _hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="0") as client:
            auth = _authorization("0x" + "11" * 20)
            r = _invoke(client, _envelope(auth, "0x" + "00" * 65))
            # No rail is on at all in this fixture, so the call is simply free — what must
            # not happen is the hub acting on an unverified payment.
            assert r.status_code == 200
            assert "x402" not in client.get("/ai-market/v2/stats/live").json()["summary"]


def test_verification_refuses_when_the_hub_cannot_check_signatures(monkeypatch):
    """A hub without a crypto stack must refuse, not assume. Nothing may read
    'we could not verify' as 'the payer signed'."""
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")

    def _boom(*_a, **_k):
        raise eip712.CryptoUnavailable("eth-account unavailable: test")

    monkeypatch.setattr(eip712, "recover_transfer_signer", _boom)
    result = x402.verify_payment(
        {"scheme": "exact", "payload": {
            "authorization": _authorization("0x" + "11" * 20),
            "signature": "0x" + "00" * 65,
        }},
        price_usd=PRICE,
    )
    assert result["ok"] is False
    assert "cannot verify signatures" in result["error"]
