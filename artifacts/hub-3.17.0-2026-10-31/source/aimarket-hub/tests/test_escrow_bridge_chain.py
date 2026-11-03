"""The bridge against a REAL AIMarketEscrow, on a local anvil.

Everything else in the bridge's test suite proves the Python code agrees with itself (or
with eth-account). Only this file proves the thing that actually matters: that the digest
this module computes is the digest the CONTRACT computes, and that a signature built here
is one ``debitChannel`` accepts. Without it, "153 tests pass" and "the money will move" are
unrelated statements.

It also pins the bridge's reading of the contract — the getChannel field order, the
ChannelStatus ordinals, and its interpretation of each revert — against the compiled
contract rather than against a fixture that agrees with the code by construction.

Skipped, loudly, when foundry is absent. Uses anvil's published throwaway keys only, on a
private chain, and tears the node down in a fixture finalizer.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from aimarket_hub.escrow_bridge import chain, escrow_verify, mirror, signer as signer_mod, store
from aimarket_hub.escrow_bridge.eip712 import (
    DebitAuthorization,
    crypto_available,
    debit_digest,
)
from aimarket_hub.escrow_bridge.errors import EscrowStateRejected

_REPO = Path(__file__).resolve().parents[2]
_FORGE_PROJECT = _REPO / "contracts/evm"

# anvil's deterministic, publicly documented development accounts. Safe to hardcode
# precisely because they are public: they exist only on a throwaway local chain.
_ACCOUNTS = [
    ("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
     "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"),   # depositor
    ("0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
     "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"),   # hub
    ("0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
     "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"),   # stranger
]
_DEPOSIT_UNITS = 5_000_000          # 5.00 at 6 decimals
_DEBIT_UNITS = 1_000_000            # 1.00

pytestmark = [
    pytest.mark.skipif(not crypto_available(), reason="eth-account/eth-utils not installed"),
    pytest.mark.skipif(
        not (shutil.which("anvil") and shutil.which("forge") and shutil.which("cast")),
        reason="foundry (anvil/forge/cast) not installed — contract compatibility UNPROVEN here",
    ),
    pytest.mark.skipif(
        not (_FORGE_PROJECT / "src/AIMarketEscrow.sol").exists(),
        reason="contracts/evm sources not present in this checkout",
    ),
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, **kw)


def _forge_create(rpc: str, key: str, target: str, *ctor: str) -> str:
    cmd = ["forge", "create", "--rpc-url", rpc, "--private-key", key, target,
           "--broadcast", "--json"]
    if ctor:
        cmd += ["--constructor-args", *ctor]
    proc = _run(cmd, cwd=str(_FORGE_PROJECT))
    if proc.returncode != 0:
        pytest.skip(f"forge create failed for {target}: {proc.stderr[-400:]}")
    # forge pretty-prints its --json payload across lines, so parse the whole document
    # first and only then fall back to per-line scanning; a line-only parser silently
    # "finds nothing" and turns a working toolchain into a skipped test.
    out = proc.stdout.strip()
    for candidate in (out, *(ln.strip() for ln in out.splitlines() if ln.strip().startswith("{"))):
        try:
            payload = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("deployedTo"):
            return str(payload["deployedTo"])
    match = re.search(r'"deployedTo"\s*:\s*"(0x[0-9a-fA-F]{40})"', out)
    if match:
        return match.group(1)
    pytest.skip(f"could not parse a deployment address for {target}: {out[-300:]}")


@pytest.fixture(scope="module")
def anvil():
    """A private chain with the escrow and a 6-decimal token deployed."""
    port = _free_port()
    proc = subprocess.Popen(
        ["anvil", "--port", str(port), "--silent", "--accounts", "4"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    rpc = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            if _run(["cast", "chain-id", "--rpc-url", rpc]).returncode == 0:
                break
            time.sleep(0.2)
        else:
            pytest.skip("anvil did not become ready")

        chain_id = int(_run(["cast", "chain-id", "--rpc-url", rpc]).stdout.strip())
        depositor, dep_key = _ACCOUNTS[0]
        hub, hub_key = _ACCOUNTS[1]

        token = _forge_create(rpc, dep_key, "src/FakeUSDT.sol:FakeUSDT")
        escrow = _forge_create(
            rpc, dep_key, "src/AIMarketEscrow.sol:AIMarketEscrow", f"[{hub}]", f"[{token}]"
        )
        yield {
            "rpc": rpc, "chain_id": chain_id, "token": token, "escrow": escrow,
            "depositor": depositor, "depositor_key": dep_key, "hub": hub, "hub_key": hub_key,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            proc.kill()


@pytest.fixture
def wired(anvil, monkeypatch):
    """Point the bridge's config and RPC pool at the local chain."""
    monkeypatch.setenv("AIMARKET_ESCROW_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ESCROW_CONTRACT", anvil["escrow"])
    monkeypatch.setenv("AIMARKET_ESCROW_HUB_ADDRESS", anvil["hub"])

    class _Pool:
        """A minimal JSON-RPC caller — the real chain_net pool needs a registered network."""

        def call(self, method, params=None):
            import urllib.request

            body = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
            ).encode()
            req = urllib.request.Request(
                anvil["rpc"], data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode())
            if payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            return payload.get("result")

    pool = _Pool()
    monkeypatch.setattr(chain, "_pool", lambda: pool)
    monkeypatch.setattr(
        chain, "_network",
        lambda: type("Spec", (), {
            "id": "anvil", "chain_id": anvil["chain_id"],
            "addresses": {"AIMarketEscrow": anvil["escrow"], "USDC": anvil["token"]},
        })(),
    )
    monkeypatch.setenv("AIMARKET_PAYMENT_TOKEN", "USDC")
    return anvil


def _open_escrow_channel(env, channel_id: str, units: int = _DEPOSIT_UNITS) -> None:
    rpc, key = env["rpc"], env["depositor_key"]
    approve = _run(["cast", "send", "--rpc-url", rpc, "--private-key", key, env["token"],
                    "approve(address,uint256)", env["escrow"], str(units)])
    assert approve.returncode == 0, approve.stderr[-300:]
    opened = _run(["cast", "send", "--rpc-url", rpc, "--private-key", key, env["escrow"],
                   "openChannel(bytes32,address,uint256)", channel_id, env["token"], str(units)])
    assert opened.returncode == 0, opened.stderr[-300:]


def _sign(env, auth: DebitAuthorization, key: str | None = None) -> str:
    from eth_account import Account

    digest = debit_digest(auth, chain_id=env["chain_id"], verifying_contract=env["escrow"])
    signed = Account._sign_hash(digest, Account.from_key(key or env["depositor_key"]).key)
    raw = signed.signature.hex()
    return raw if raw.startswith("0x") else "0x" + raw


def _auth(env, channel_id: str, **over) -> DebitAuthorization:
    """A default authorization whose receiptId is UNIQUE per channel.

    ``usedReceipts`` is global to the contract, not per channel, and ``debitChannel``
    checks it BEFORE recovering the signature — so a receipt shared between tests makes
    every later test revert with ReceiptAlreadyUsed instead of the error it is actually
    trying to provoke. These tests share one module-scoped chain, so the default is
    derived from the channel id rather than being a constant.
    """
    base = dict(
        channel_id=channel_id, hub=env["hub"], token=env["token"], amount=_DEBIT_UNITS,
        receipt_id="0x" + channel_id[2:4] * 32, nonce=0, deadline=4_000_000_000,
    )
    base.update(over)
    return DebitAuthorization(**base)


class TestTheContractAgreesWithOurDigest:
    """The claim the whole bridge rests on."""

    def test_our_digest_equals_computeDebitDigest(self, wired):
        env = wired
        cid = "0x" + "a1" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid)
        ours = debit_digest(
            auth, chain_id=env["chain_id"], verifying_contract=env["escrow"]
        ).hex()
        theirs = _run([
            "cast", "call", "--rpc-url", env["rpc"], env["escrow"],
            "computeDebitDigest(bytes32,address,address,uint256,bytes32,uint256,uint256)",
            auth.channel_id, auth.hub, auth.token, str(auth.amount), auth.receipt_id,
            str(auth.nonce), str(auth.deadline),
        ]).stdout.strip()
        assert theirs.lower() == "0x" + ours.lower(), (
            "the contract computes a different digest than this module — every submission "
            "would revert with InvalidSignature()"
        )

    def test_the_contract_accepts_a_signature_we_built(self, wired):
        """The decisive end-to-end fact: usedAmount stops being permanently zero."""
        env = wired
        cid = "0x" + "a2" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid)
        before = chain.read_channel(cid)
        assert before.used_amount == 0 and before.nonce == 0

        sent = _run([
            "cast", "send", "--rpc-url", env["rpc"], "--private-key", env["hub_key"],
            env["escrow"], chain.DEBIT_CHANNEL_SIG,
            auth.channel_id, str(auth.amount), auth.receipt_id, str(auth.deadline),
            _sign(env, auth),
        ])
        assert sent.returncode == 0, f"debitChannel reverted: {sent.stderr[-400:]}"

        after = chain.read_channel(cid)
        assert after.used_amount == _DEBIT_UNITS
        assert after.balance == _DEPOSIT_UNITS - _DEBIT_UNITS
        assert after.nonce == 1
        assert after.hub.lower() == env["hub"].lower()   # bound on first debit


class TestOurReadingOfTheContractIsRight:
    def test_getChannel_decodes_a_live_channel(self, wired):
        env = wired
        cid = "0x" + "b1" * 32
        _open_escrow_channel(env, cid)
        ch = chain.read_channel(cid)
        assert ch.exists and ch.is_open and ch.status == chain.STATUS_OPEN
        assert ch.depositor.lower() == env["depositor"].lower()
        assert ch.token.lower() == env["token"].lower()
        assert ch.deposit_amount == ch.balance == _DEPOSIT_UNITS
        assert not ch.hub_bound

    def test_an_unopened_channel_reads_as_absent(self, wired):
        assert not chain.read_channel("0x" + "cc" * 32).exists

    def test_hub_authorization_matches_the_contract(self, wired):
        env = wired
        assert chain.hub_is_authorized(env["hub"]) is True
        assert chain.hub_is_authorized(_ACCOUNTS[2][0]) is False

    def test_chain_id_is_read_not_assumed(self, wired):
        assert chain.chain_id() == wired["chain_id"]


class TestC1AgainstLiveState:
    def test_verification_passes_for_a_real_channel(self, wired):
        env = wired
        cid = "0x" + "b2" * 32
        _open_escrow_channel(env, cid)
        out = escrow_verify.verify_funding(
            channel_id=cid, claimed_wallet=env["depositor"], deposit_usd=5.0
        )
        assert out.required_units == _DEPOSIT_UNITS
        assert out.claim_id == escrow_verify.claim_identifier(cid)

    def test_a_stranger_cannot_claim_it(self, wired):
        env = wired
        cid = "0x" + "b3" * 32
        _open_escrow_channel(env, cid)
        with pytest.raises(EscrowStateRejected, match="does not match"):
            escrow_verify.verify_funding(
                channel_id=cid, claimed_wallet=_ACCOUNTS[2][0], deposit_usd=5.0
            )

    def test_an_overdrawn_credit_is_refused(self, wired):
        env = wired
        cid = "0x" + "b4" * 32
        _open_escrow_channel(env, cid)
        with pytest.raises(EscrowStateRejected, match="does not cover"):
            escrow_verify.verify_funding(
                channel_id=cid, claimed_wallet=env["depositor"], deposit_usd=6.0
            )

    def test_a_channel_already_debited_cannot_fund_another(self, wired):
        """Proven against real on-chain state rather than a hand-built fixture."""
        env = wired
        cid = "0x" + "b5" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid, receipt_id="0x" + "77" * 32)
        assert _run([
            "cast", "send", "--rpc-url", env["rpc"], "--private-key", env["hub_key"],
            env["escrow"], chain.DEBIT_CHANNEL_SIG, auth.channel_id, str(auth.amount),
            auth.receipt_id, str(auth.deadline), _sign(env, auth),
        ]).returncode == 0
        with pytest.raises(EscrowStateRejected, match="already has on-chain debits"):
            escrow_verify.verify_funding(
                channel_id=cid, claimed_wallet=env["depositor"], deposit_usd=1.0
            )


class TestTheContractRefusesWhatWeExpectItTo:
    """Each revert the mirror interprets, provoked for real.

    Guessing which revert means what is how an off-chain mirror ends up retrying a
    permanent failure forever, or abandoning a transient one.
    """

    def _submit(self, env, auth, signature, *, key=None):
        return _run([
            "cast", "send", "--rpc-url", env["rpc"], "--private-key", key or env["hub_key"],
            env["escrow"], chain.DEBIT_CHANNEL_SIG, auth.channel_id, str(auth.amount),
            auth.receipt_id, str(auth.deadline), signature,
        ])

    def test_a_signature_from_the_wrong_wallet(self, wired):
        env = wired
        cid = "0x" + "d1" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid)
        out = self._submit(env, auth, _sign(env, auth, key=_ACCOUNTS[2][1]))
        assert out.returncode != 0 and "InvalidSignature" in (out.stderr + out.stdout)

    def test_a_replayed_receipt(self, wired):
        env = wired
        cid = "0x" + "d2" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid, receipt_id="0x" + "d2" * 32)
        assert self._submit(env, auth, _sign(env, auth)).returncode == 0
        # Same receipt, re-signed at the channel's new nonce: only usedReceipts stops it.
        again = _auth(env, cid, receipt_id=auth.receipt_id, nonce=1)
        out = self._submit(env, again, _sign(env, again))
        assert out.returncode != 0 and "ReceiptAlreadyUsed" in (out.stderr + out.stdout)

    def test_a_stale_nonce(self, wired):
        env = wired
        cid = "0x" + "d3" * 32
        _open_escrow_channel(env, cid)
        first = _auth(env, cid, receipt_id="0x" + "31" * 32)
        assert self._submit(env, first, _sign(env, first)).returncode == 0
        stale = _auth(env, cid, receipt_id="0x" + "32" * 32, nonce=0)   # channel is at 1 now
        out = self._submit(env, stale, _sign(env, stale))
        assert out.returncode != 0 and "InvalidSignature" in (out.stderr + out.stdout)

    def test_an_expired_deadline(self, wired):
        env = wired
        cid = "0x" + "d4" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid, deadline=1)
        out = self._submit(env, auth, _sign(env, auth))
        assert out.returncode != 0 and "ChannelExpired" in (out.stderr + out.stdout)

    def test_an_unauthorized_caller(self, wired):
        env = wired
        cid = "0x" + "d5" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid)
        out = self._submit(env, auth, _sign(env, auth), key=_ACCOUNTS[2][1])
        assert out.returncode != 0 and "Unauthorized" in (out.stderr + out.stdout)

    def test_an_amount_above_the_balance(self, wired):
        env = wired
        cid = "0x" + "d6" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid, amount=_DEPOSIT_UNITS + 1)
        out = self._submit(env, auth, _sign(env, auth))
        assert out.returncode != 0 and "InsufficientBalance" in (out.stderr + out.stdout)


class TestPlanModeAgainstRealState:
    def test_a_valid_authorization_plans_clean_and_sends_nothing(self, wired, tmp_path):
        """Plan mode's whole promise, measured against a real contract."""
        env = wired
        cid = "0x" + "e1" * 32
        _open_escrow_channel(env, cid)
        auth = _auth(env, cid, receipt_id="0x" + "e1" * 32)

        st = store.AuthorizationStore(str(tmp_path / "bridge.db"))
        ledger = tmp_path / "channels.db"
        import sqlite3

        conn = sqlite3.connect(ledger)
        conn.execute(
            "CREATE TABLE debited_receipts (receipt_id TEXT PRIMARY KEY, channel_id TEXT, "
            "amount_cents INTEGER, timestamp TEXT)"
        )
        conn.execute(
            "INSERT INTO debited_receipts VALUES (?, 'ch_1', 100, '')", (auth.receipt_id,)
        )
        conn.commit()
        conn.close()
        from aimarket_hub import channels as ch_mod

        os.environ["AIMARKET_ESCROW_BRIDGE_DB_PATH"] = str(tmp_path / "bridge.db")
        original = ch_mod._DB_PATH
        ch_mod._DB_PATH = str(ledger)
        try:
            st.record(
                receipt_id=auth.receipt_id, ledger_channel="ch_1", escrow_channel=cid,
                chain_id=env["chain_id"], escrow_address=env["escrow"], hub=env["hub"],
                token=env["token"], depositor=env["depositor"], amount_units=auth.amount,
                nonce=0, deadline=auth.deadline, signature=_sign(env, auth),
            )
            report = mirror.Mirror(
                authorizations=st, signer=signer_mod.PlanOnlySigner()
            ).run(now=1_000_000)
            assert report.outcomes == {mirror.OUTCOME_PLANNED: 1}, report.rows
            assert report.rows[0]["gas"], "a clean plan should carry a gas estimate"
            # Nothing was sent: the channel is untouched on chain.
            assert chain.read_channel(cid).used_amount == 0
        finally:
            ch_mod._DB_PATH = original
            os.environ.pop("AIMARKET_ESCROW_BRIDGE_DB_PATH", None)
            st.close()

    def test_a_tampered_amount_is_caught_by_simulation(self, wired, tmp_path):
        """The contract's own verdict, not our guess, blocks it."""
        env = wired
        cid = "0x" + "e2" * 32
        _open_escrow_channel(env, cid)
        honest = _auth(env, cid, receipt_id="0x" + "e2" * 32, amount=100_000)
        signature = _sign(env, honest)
        inflated = _auth(env, cid, receipt_id=honest.receipt_id, amount=_DEBIT_UNITS)
        data = chain.encode_debit_channel(inflated, signature)
        out = chain.simulate(to=env["escrow"], data=data, sender=env["hub"])
        assert out["ok"] is False and "InvalidSignature" in out["error"]
