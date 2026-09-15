"""AI Market Protocol v1: channel-open payer proof wiring + the operator liability API.

Two things are pinned here that no other suite can pin, because only the monorepo
venv can import BOTH channel stacks at once:

1. The v1 HTTP layer forwards the depositor's `signature` to the service. Without
   it, ``open_channel`` refuses with ``deposit_proof_required`` on every production
   open — a total outage, not a degraded path.
2. The canonical challenge really is ONE message: the bytes aimarket-hub asks a
   client to sign are byte-identical to the ones this package verifies, and a single
   signature is accepted by both. That is the interoperability contract every SDK
   depends on, and it is exactly what had drifted.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict, deque

import pytest
from fastapi.testclient import TestClient

import aimarket_hub.channels as hub_channels
from web.backend.services.ai_market_protocol import channels as web_channels
from web.backend.services.ai_market_protocol import on_chain as oc

PLATFORM = "0x" + "11" * 20


# ── Canonical challenge: one message, both stacks ────────────────────────────

class TestChallengeIsSharedAcrossStacks:
    def test_hub_and_web_build_identical_bytes(self):
        payer = "0x" + "Ab" * 20
        assert hub_channels.payer_proof_challenge(
            payer=payer, tx_hash="0xDEADBEEF", chain="Base", deposit_usd=6.0
        ) == web_channels.deposit_proof_challenge(
            chain="base", tx_hash="0xdeadbeef", payer=payer, deposit_usd=6.0
        )

    def test_a_bare_hex_hash_builds_the_same_bytes_on_both_sides(self):
        """Each stack feeds the challenge a differently-prepared hash.

        This package normalises first (``normalize_tx_hash`` adds the 0x), the hub
        forwards the raw request value. A client that submits its hash without the
        prefix therefore got two different preimages for one deposit, and whichever
        signature it produced was rejected at the other door.
        """
        payer = "0x" + "Ab" * 20
        bare = "b2" * 32
        assert hub_channels.payer_proof_challenge(
            payer=payer, tx_hash=bare, chain="base", deposit_usd=6.0
        ) == web_channels.deposit_proof_challenge(
            chain="base",
            tx_hash=oc.normalize_tx_hash(bare, chain="base"),
            payer=payer,
            deposit_usd=6.0,
        )

    def test_one_signature_satisfies_both_recovery_paths(self):
        """The actual contract: sign once, present at either door."""
        from eth_account import Account
        from eth_account.messages import encode_defunct

        key = "0x" + "7a" * 32
        acct = Account.from_key(key)
        message = web_channels.deposit_proof_challenge(
            chain="base", tx_hash="0xfeedface", payer=acct.address, deposit_usd=6.0
        )
        signature = "0x" + Account.sign_message(
            encode_defunct(text=message), private_key=key
        ).signature.hex().removeprefix("0x")

        # web side
        assert oc.recover_channel_open_payer(
            chain="base", tx_hash="0xfeedface", payer=acct.address,
            amount_usd=6.0, signature=signature,
        ).lower() == acct.address.lower()
        # hub side — different normalisation inputs, same verdict
        assert hub_channels._recover_payer_address(
            payer=acct.address, tx_hash="0xFEEDFACE", chain="Base",
            deposit_usd=6.0, signature=signature,
        ).lower() == acct.address.lower()


# ── v1 HTTP wiring ───────────────────────────────────────────────────────────

@pytest.fixture
def chain_env(tmp_path, monkeypatch):
    """A v1 stack whose on-chain verifier answers from an in-test transfer table."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "0")
    monkeypatch.delenv("AIFACTORY_AI_MARKET_DEMO_PAYMENT", raising=False)
    monkeypatch.setenv("AIFACTORY_AI_MARKET_CHAIN", "base")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_TOKEN", "USDC")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_REQUIRE_PAYER_PROOF", "1")

    records: dict[str, dict] = {}

    def _verify_evm(*, chain, tx_hash, expected_recipient, expected_amount, expected_token):
        rec = records.get(tx_hash)
        if not rec:
            return {"verified": False, "error": "unknown_tx"}
        if rec["to"].lower() != (expected_recipient or "").lower():
            return {"verified": False, "error": "recipient_mismatch"}
        if abs(float(rec["amount"]) - float(expected_amount)) > 1e-9:
            return {"verified": False, "error": "amount_mismatch"}
        return {"verified": True, "from": rec["from"], "to": rec["to"], "amount": rec["amount"]}

    monkeypatch.setattr(oc, "platform_recipient", lambda chain: PLATFORM)
    monkeypatch.setattr(
        oc, "_payment_api",
        lambda: type("_P", (), {"_verify_evm_transaction": staticmethod(_verify_evm)}),
    )
    return records


@pytest.fixture
def client(tmp_path, monkeypatch, chain_env):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-ci-only-32chars-minimum!!")
    pipeline = tmp_path / "data" / "state" / "pipeline.json"
    pipeline.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_text(json.dumps({"products": {}}), encoding="utf-8")
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pipeline))
    from web.backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def customer_auth(client, monkeypatch):
    monkeypatch.setenv("AIFACTORY_CUSTOMER_REGISTER_MAX_PER_HOUR", "1000")
    monkeypatch.setattr("web.backend.api.customer._register_attempts", defaultdict(deque))
    email = f"aim-{uuid.uuid4().hex[:10]}@test.local"
    reg = client.post(
        "/api/customer/register", json={"email": email, "password": "password12345"}
    )
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _sign(key: str, *, tx: str, deposit_usd: float, chain: str = "base") -> tuple[str, str]:
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.from_key(key)
    message = web_channels.deposit_proof_challenge(
        chain=chain, tx_hash=tx, payer=acct.address, deposit_usd=deposit_usd
    )
    signed = Account.sign_message(encode_defunct(text=message), private_key=key)
    return acct.address, "0x" + signed.signature.hex().removeprefix("0x")


class TestChannelOpenRouteForwardsTheProof:
    """POST /ai-market/channel/open was a 100% outage in production: the service
    demanded a payer proof and the route had no field to carry one."""

    def test_open_without_a_signature_is_refused_with_the_challenge(
        self, client, customer_auth, chain_env
    ):
        tx = "0x" + "a1" * 32
        payer, _sig = _sign("0x" + "51" * 32, tx=tx, deposit_usd=6.0)
        chain_env[tx] = {"from": payer, "to": PLATFORM, "amount": 6.0}

        resp = client.post(
            "/ai-market/channel/open",
            json={"deposit_usd": 6.0, "tx_hash": tx},
            headers=customer_auth,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["error"] == "deposit_proof_required"
        # the exact text to sign comes back, so a client never has to guess it
        assert body["challenge"].startswith("AIMarket-Payer-Proof/v1\n")

    def test_open_with_a_valid_signature_succeeds(self, client, customer_auth, chain_env):
        tx = "0x" + "a2" * 32
        key = "0x" + "52" * 32
        payer, signature = _sign(key, tx=tx, deposit_usd=6.0)
        chain_env[tx] = {"from": payer, "to": PLATFORM, "amount": 6.0}

        resp = client.post(
            "/ai-market/channel/open",
            json={"deposit_usd": 6.0, "tx_hash": tx, "signature": signature},
            headers=customer_auth,
        )
        assert resp.status_code == 200, resp.text
        channel = resp.json()["channel"]
        assert channel["deposit_wallet_verified"] is True
        assert channel["deposit_wallet"].lower() == payer.lower()
        assert resp.json()["channel_secret"]

    def test_a_front_runner_cannot_claim_the_deposit(self, client, customer_auth, chain_env):
        """Everything the attacker needs is public EXCEPT the payer's key."""
        tx = "0x" + "a3" * 32
        victim, _ = _sign("0x" + "53" * 32, tx=tx, deposit_usd=6.0)
        chain_env[tx] = {"from": victim, "to": PLATFORM, "amount": 6.0}

        # signature by the attacker's own wallet over the victim's deposit
        from eth_account import Account
        from eth_account.messages import encode_defunct

        message = web_channels.deposit_proof_challenge(
            chain="base", tx_hash=tx, payer=victim, deposit_usd=6.0
        )
        forged = "0x" + Account.sign_message(
            encode_defunct(text=message), private_key="0x" + "54" * 32
        ).signature.hex().removeprefix("0x")

        resp = client.post(
            "/ai-market/channel/open",
            json={"deposit_usd": 6.0, "tx_hash": tx, "signature": forged},
            headers=customer_auth,
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "deposit_proof_invalid"

    def test_a_proof_for_a_smaller_deposit_does_not_open_a_bigger_channel(
        self, client, customer_auth, chain_env
    ):
        """The amount is in the preimage precisely so this cannot work."""
        tx = "0x" + "a4" * 32
        key = "0x" + "55" * 32
        payer, small_sig = _sign(key, tx=tx, deposit_usd=1.0)
        chain_env[tx] = {"from": payer, "to": PLATFORM, "amount": 60.0}

        resp = client.post(
            "/ai-market/channel/open",
            json={"deposit_usd": 60.0, "tx_hash": tx, "signature": small_sig},
            headers=customer_auth,
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "deposit_proof_invalid"


class TestLiabilityLedgerRoleGate:
    """`require_admin_with_rbac` alone does NOT protect these routes.

    Its viewer/operator restrictions are prefix lists scoped to ``/api/admin/*``, and
    the liability routes live under ``/ai-market``, so every authenticated admin-panel
    role — including a read-only VIEWER — walks straight through it. The explicit
    ADMIN/SUPER_ADMIN check is the only thing keeping a viewer out of a table of
    customer emails, wallets and balances, and out of writing a debt off.
    """

    @staticmethod
    def _as_role(client, role: str):
        from web.backend.core.security import get_current_admin

        client.app.dependency_overrides[get_current_admin] = lambda: {
            "sub": f"{role}-1", "username": f"{role}-1", "role": role,
        }

    @staticmethod
    def _clear(client):
        from web.backend.core.security import get_current_admin

        client.app.dependency_overrides.pop(get_current_admin, None)

    @pytest.mark.parametrize("role", ["viewer", "operator"])
    def test_below_admin_cannot_read_customer_liabilities(self, client, role):
        self._as_role(client, role)
        try:
            resp = client.get("/ai-market/admin/refunds/outstanding")
        finally:
            self._clear(client)
        assert resp.status_code == 403, f"{role} read the liability ledger: {resp.text}"

    def test_an_operator_cannot_write_a_debt_off(self, client):
        # An operator POST is not blocked by check_admin_rbac either: its deny list is
        # /api/admin-prefixed, so nothing but the explicit role check stops it.
        self._as_role(client, "operator")
        try:
            resp = client.post("/ai-market/admin/refunds/settled", json={
                "channel_id": "ch_rolegate0001", "settle_tx_hash": "0x" + "ab" * 32,
            })
        finally:
            self._clear(client)
        assert resp.status_code == 403, resp.text

    def test_an_admin_role_is_admitted(self, client, chain_env):
        """The gate must not be a blanket refusal — an admin still gets in."""
        self._as_role(client, "admin")
        try:
            resp = client.get("/ai-market/admin/refunds/outstanding")
        finally:
            self._clear(client)
        assert resp.status_code == 200, resp.text
        assert "outstanding_refunds" in resp.json()


class TestLiabilityAdminRoutes:
    """list_outstanding_refunds / mark_refund_settled existed but nothing exposed
    them, so a recorded debt was invisible and unclearable."""

    def test_anonymous_cannot_read_the_liability_ledger(self, client):
        assert client.get("/ai-market/admin/refunds/outstanding").status_code in (401, 403)

    def test_a_customer_token_cannot_read_it(self, client, customer_auth):
        resp = client.get("/ai-market/admin/refunds/outstanding", headers=customer_auth)
        assert resp.status_code in (401, 403), resp.text

    def test_anonymous_cannot_write_a_debt_off(self, client):
        resp = client.post(
            "/ai-market/admin/refunds/settled",
            json={"channel_id": "ch_abcdef123456", "settle_tx_hash": "0x" + "ab" * 32},
        )
        assert resp.status_code in (401, 403), resp.text

    def test_admin_sees_a_recorded_debt(self, client, chain_env, monkeypatch):
        from web.backend.api import ai_market_protocol_v1 as v1

        # A closed channel that owes its depositor, written straight into the store
        # the service reads (the open→close path is covered by the settlement suite).
        with web_channels.channel_store_lock():
            data = web_channels._load_channels()
            data["ch_owedtest0001"] = {
                "channel_id": "ch_owedtest0001",
                "status": "closed",
                "customer_id": "cust-1",
                "customer_email": "owed@test.local",
                "deposit_wallet": "0x" + "cd" * 20,
                "chain": "base",
                "token": "USDC",
                "refund_owed_usd": 4.25,
                "closed_at": 1.0,
            }
            web_channels._save_channels(data)

        client.app.dependency_overrides[v1._require_liability_admin] = lambda: {
            "sub": "operator-1", "role": "admin",
        }
        try:
            resp = client.get("/ai-market/admin/refunds/outstanding")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert [r["channel_id"] for r in body["outstanding_refunds"]] == ["ch_owedtest0001"]
            assert body["outstanding_refunds_usd"] == 4.25
        finally:
            client.app.dependency_overrides.pop(v1._require_liability_admin, None)

    def test_settling_requires_a_verifiable_outbound_payout(self, client, chain_env):
        """Marking a debt paid must not be possible on the operator's word alone."""
        from web.backend.api import ai_market_protocol_v1 as v1

        destination = "0x" + "cd" * 20
        with web_channels.channel_store_lock():
            data = web_channels._load_channels()
            data["ch_owedtest0002"] = {
                "channel_id": "ch_owedtest0002",
                "status": "closed",
                "customer_id": "cust-2",
                "deposit_wallet": destination,
                "chain": "base",
                "token": "USDC",
                "refund_owed_usd": 2.0,
                "closed_at": 2.0,
            }
            web_channels._save_channels(data)

        client.app.dependency_overrides[v1._require_liability_admin] = lambda: {
            "sub": "operator-1", "role": "admin",
        }
        try:
            bogus = client.post("/ai-market/admin/refunds/settled", json={
                "channel_id": "ch_owedtest0002", "settle_tx_hash": "0x" + "ee" * 32,
            })
            assert bogus.status_code == 400
            assert bogus.json()["error"] == "settle_tx_not_verified"

            # ...and a REAL outbound payout from the platform wallet clears it
            payout = "0x" + "ef" * 32
            chain_env[payout] = {"from": PLATFORM, "to": destination, "amount": 2.0}
            ok = client.post("/ai-market/admin/refunds/settled", json={
                "channel_id": "ch_owedtest0002", "settle_tx_hash": payout,
            })
            assert ok.status_code == 200, ok.text
            assert ok.json()["settled_usd"] == 2.0

            listed = client.get("/ai-market/admin/refunds/outstanding").json()
            assert "ch_owedtest0002" not in [
                r["channel_id"] for r in listed["outstanding_refunds"]
            ]
        finally:
            client.app.dependency_overrides.pop(v1._require_liability_admin, None)
