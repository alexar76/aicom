"""C1 — escrow funding verification, and the calldata the mirror will simulate.

No network: a fake RPC pool answers ``eth_call``/``eth_chainId`` so every branch of the
decision is reachable, including the ones a real chain would rarely produce (junk return
data, a lying chain id, a channel bound to another hub).

The decoding these tests assert was verified against a real deployment on a local anvil —
``getChannel`` really is nine words in this order — so a fake that agrees with them is
agreeing with the contract, not with a guess.
"""

from __future__ import annotations

import pytest

from aimarket_hub.escrow_bridge import chain, config, escrow_verify
from aimarket_hub.escrow_bridge.eip712 import DebitAuthorization, Eip712Error, crypto_available
from aimarket_hub.escrow_bridge.errors import (
    BridgeConfigError,
    ChainUnavailable,
    ChannelNotOnChain,
    EscrowStateRejected,
)

pytestmark = pytest.mark.skipif(
    not crypto_available(), reason="eth-utils/eth-account not installed (platon venv)"
)

_ESCROW = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
_DEPOSITOR = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
_HUB = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
_TOKEN = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
_CHANNEL = "0x" + "11" * 32
_CHAIN_ID = 8453
_ZERO = "0x" + "00" * 20


def _word(value: int) -> str:
    return f"{value:064x}"


def _addr_word(addr: str) -> str:
    return _word(int(addr, 16))


def _channel_blob(**over) -> str:
    """A getChannel return value, in the contract's declared field order."""
    f = dict(
        depositor=_DEPOSITOR, hub=_ZERO, token=_TOKEN,
        deposit_amount=5_000_000, balance=5_000_000, used_amount=0,
        expires_at=4_000_000_000, nonce=0, status=chain.STATUS_OPEN,
    )
    f.update(over)
    return "0x" + "".join([
        _addr_word(f["depositor"]), _addr_word(f["hub"]), _addr_word(f["token"]),
        _word(f["deposit_amount"]), _word(f["balance"]), _word(f["used_amount"]),
        _word(f["expires_at"]), _word(f["nonce"]), _word(f["status"]),
    ])


class _FakePool:
    """Answers only what the bridge asks, and records what it was asked."""

    def __init__(self, *, channel_blob=None, chain_id=_CHAIN_ID, call_error=None,
                 authorized=True, estimate=21000):
        self.channel_blob = channel_blob if channel_blob is not None else _channel_blob()
        self.chain_id = chain_id
        self.call_error = call_error
        self.authorized = authorized
        self.estimate = estimate
        self.seen: list[tuple[str, object]] = []

    def call(self, method, params=None):
        self.seen.append((method, params))
        if method == "eth_chainId":
            return hex(self.chain_id)
        if method == "eth_estimateGas":
            return hex(self.estimate)
        if method == "eth_call":
            if self.call_error:
                raise RuntimeError(self.call_error)
            data = (params or [{}])[0].get("data", "")
            if data.startswith("0x" + chain.selector(chain.AUTHORIZED_HUBS_SIG).hex()):
                return "0x" + _word(1 if self.authorized else 0)
            return self.channel_blob
        raise AssertionError(f"unexpected RPC method {method}")


@pytest.fixture
def wired(monkeypatch):
    """Point the bridge at a fake chain with a resolvable escrow address."""
    monkeypatch.setenv("AIMARKET_ESCROW_CONTRACT", _ESCROW)
    monkeypatch.setenv("AIMARKET_ESCROW_HUB_ADDRESS", _HUB)
    monkeypatch.setenv("AIMARKET_PAYMENT_TOKEN", "USDC")

    def _install(pool):
        monkeypatch.setattr(chain, "_pool", lambda: pool)
        # A NetworkSpec stand-in: chain_id must agree with the RPC, and the registry
        # resolves the payment symbol to the channel's token so the cross-check passes.
        monkeypatch.setattr(
            chain, "_network",
            lambda: type("Spec", (), {"id": "base", "chain_id": _CHAIN_ID,
                                      "addresses": {"USDC": _TOKEN,
                                                    "AIMarketEscrow": _ESCROW}})(),
        )
        return pool

    return _install


class TestFundingIsAccepted:
    def test_a_fresh_fully_funded_channel_verifies(self, wired):
        wired(_FakePool())
        out = escrow_verify.verify_funding(
            channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
        )
        assert out.required_units == 5_000_000
        assert out.channel.depositor == _DEPOSITOR
        assert out.chain_id == _CHAIN_ID
        assert out.claim_id == f"escrow-channel:{_CHANNEL}"

    def test_the_claimed_wallet_may_differ_in_case(self, wired):
        wired(_FakePool())
        assert escrow_verify.verify_funding(
            channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR.upper().replace("0X", "0x"),
            deposit_usd=5.0,
        ).channel.exists

    def test_extra_on_chain_balance_is_allowed(self, wired):
        """Over-funding is the depositor's choice; the ledger credits what was asked."""
        wired(_FakePool(channel_blob=_channel_blob(balance=9_000_000, deposit_amount=9_000_000)))
        out = escrow_verify.verify_funding(
            channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
        )
        assert out.required_units == 5_000_000 and out.backed_usd == 9.0


class TestFundingIsRefused:
    def test_a_channel_that_was_never_opened(self, wired):
        wired(_FakePool(channel_blob=_channel_blob(depositor=_ZERO)))
        with pytest.raises(ChannelNotOnChain):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
            )

    @pytest.mark.parametrize("status,name", [
        (chain.STATUS_SETTLED, "Settled"),
        (chain.STATUS_REFUNDED, "Refunded"),
        (chain.STATUS_EXPIRED, "Expired"),
    ])
    def test_a_channel_that_is_not_open(self, wired, status, name):
        wired(_FakePool(channel_blob=_channel_blob(status=status)))
        with pytest.raises(EscrowStateRejected, match=name):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
            )

    def test_a_stranger_claiming_someone_elses_escrow(self, wired):
        """The contract records the depositor, so this is refused by construction."""
        wired(_FakePool())
        with pytest.raises(EscrowStateRejected, match="does not match"):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet="0x" + "aa" * 20, deposit_usd=5.0
            )

    def test_an_underfunded_escrow(self, wired):
        wired(_FakePool(channel_blob=_channel_blob(balance=4_999_999)))
        with pytest.raises(EscrowStateRejected, match="does not cover"):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
            )

    def test_an_already_expired_escrow(self, wired):
        wired(_FakePool(channel_blob=_channel_blob(expires_at=1_000)))
        with pytest.raises(EscrowStateRejected, match="expired"):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0, now=2_000,
            )

    def test_an_escrow_that_already_has_debits(self, wired):
        """It is already backing a ledger channel; a second credit would double-spend it."""
        wired(_FakePool(channel_blob=_channel_blob(used_amount=1, balance=4_999_999)))
        with pytest.raises(EscrowStateRejected, match="already has on-chain debits"):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=4.0
            )

    def test_a_channel_funded_in_another_token(self, wired):
        wired(_FakePool(channel_blob=_channel_blob(token="0x" + "cc" * 20)))
        with pytest.raises(EscrowStateRejected, match="different token"):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
            )

    def test_a_channel_already_bound_to_another_hub(self, wired):
        """This hub could never debit it, so selling service against it is uncollectable."""
        wired(_FakePool(channel_blob=_channel_blob(hub="0x" + "dd" * 20)))
        with pytest.raises(EscrowStateRejected, match="different hub"):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
            )

    def test_an_unreadable_chain_is_not_a_verification(self, wired):
        wired(_FakePool(call_error="connection reset"))
        with pytest.raises(ChainUnavailable):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
            )

    def test_a_lying_chain_id_is_refused(self, wired):
        """Signatures are domain-bound, so the wrong chain means unusable authorizations."""
        wired(_FakePool(chain_id=1))
        with pytest.raises(BridgeConfigError, match="chainId"):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
            )

    def test_truncated_return_data_is_refused_not_decoded(self, wired):
        wired(_FakePool(channel_blob="0x" + _word(1) * 3))
        with pytest.raises(ChainUnavailable, match="expected at least"):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=5.0
            )

    @pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), "abc", None])
    def test_a_nonsense_deposit_amount_is_refused(self, wired, bad):
        wired(_FakePool())
        with pytest.raises(EscrowStateRejected):
            escrow_verify.verify_funding(
                channel_id=_CHANNEL, claimed_wallet=_DEPOSITOR, deposit_usd=bad
            )


class TestAmountConversion:
    @pytest.mark.parametrize("usd,units", [
        (5.0, 5_000_000), (0.01, 10_000), (0.35, 350_000), (1234.56, 1_234_560_000),
    ])
    def test_exact_cents_do_not_drift(self, usd, units):
        """0.35 * 100 is 34.999999999999996 in binary floating point."""
        assert escrow_verify.usd_to_base_units(usd) == units

    def test_a_sub_cent_amount_rounds_up_never_down(self):
        """The escrow must cover at least what the ledger credits."""
        assert escrow_verify.usd_to_base_units(0.004) == 10_000

    def test_round_trip(self):
        assert escrow_verify.base_units_to_usd(5_000_000) == 5.0


class TestClaimNamespacing:
    def test_an_escrow_channel_cannot_block_a_transfer_hash(self):
        """Both are 32-byte hex, so a raw channelId in the registry would let a depositor
        pre-claim a victim's pending funding tx and refuse their open."""
        tx_like = "0x" + "11" * 32
        assert escrow_verify.claim_identifier(tx_like) != tx_like
        assert escrow_verify.claim_identifier(tx_like).startswith(escrow_verify.CLAIM_PREFIX)

    def test_the_identifier_is_case_insensitive(self):
        assert escrow_verify.claim_identifier("0xAB" + "cd" * 31) == escrow_verify.claim_identifier(
            "0xab" + "CD" * 31
        )


class TestCalldata:
    def _auth(self, **over):
        base = dict(channel_id=_CHANNEL, hub=_HUB, token=_TOKEN, amount=1_000_000,
                    receipt_id="0x" + "22" * 32, nonce=0, deadline=4_000_000_000)
        base.update(over)
        return DebitAuthorization(**base)

    @pytest.mark.parametrize("signature,expected", [
        # Obtained from `cast sig "<signature>"` — a different implementation of keccak
        # than the one under test, so this pins the selector against something external
        # rather than against ourselves. Hand-copied selectors are how the lottery relayer
        # ended up encoding a function that no longer existed.
        ("debitChannel(bytes32,uint256,bytes32,uint256,bytes)", "f7becd80"),
        ("getChannel(bytes32)", "831c2b82"),
        ("settleChannel(bytes32)", "fd3d3199"),
        ("authorizedHubs(address)", "34640839"),
    ])
    def test_selectors_match_an_independent_implementation(self, signature, expected):
        assert chain.selector(signature).hex() == expected

    def test_the_module_uses_those_exact_signatures(self):
        """Guards against the constants drifting away from the checked selectors above."""
        assert chain.DEBIT_CHANNEL_SIG == "debitChannel(bytes32,uint256,bytes32,uint256,bytes)"
        assert chain.GET_CHANNEL_SIG == "getChannel(bytes32)"
        assert chain.SETTLE_CHANNEL_SIG == "settleChannel(bytes32)"
        assert chain.AUTHORIZED_HUBS_SIG == "authorizedHubs(address)"

    def test_debit_calldata_layout(self):
        data = chain.encode_debit_channel(self._auth(), "0x" + "ab" * 65)
        body = data[10:]                       # strip 0x + 4-byte selector
        words = [body[i:i + 64] for i in range(0, len(body), 64)]
        assert words[0] == "11" * 32                     # channelId
        assert int(words[1], 16) == 1_000_000            # amount
        assert words[2] == "22" * 32                     # receiptId
        assert int(words[3], 16) == 4_000_000_000        # deadline
        assert int(words[4], 16) == 5 * 32               # offset to the bytes tail
        assert int(words[5], 16) == 65                   # signature length
        assert words[6].startswith("ab" * 32)            # signature, right-padded

    def test_a_65_byte_signature_is_padded_to_a_whole_word(self):
        data = chain.encode_debit_channel(self._auth(), "0x" + "ab" * 65)
        assert (len(data) - 10) % 64 == 0

    @pytest.mark.parametrize("bad", ["", "0x", "nope"])
    def test_a_missing_signature_is_refused(self, bad):
        with pytest.raises(Eip712Error):
            chain.encode_debit_channel(self._auth(), bad)

    def test_simulation_reports_a_revert_as_an_answer_not_a_crash(self, wired):
        pool = wired(_FakePool(call_error="execution reverted: ReceiptAlreadyUsed"))
        out = chain.simulate(to=_ESCROW, data="0xdeadbeef", sender=_HUB)
        assert out["ok"] is False and "ReceiptAlreadyUsed" in out["error"]
        assert pool.seen[0][0] == "eth_call"

    def test_a_successful_simulation_reports_gas(self, wired):
        wired(_FakePool(estimate=54321))
        out = chain.simulate(to=_ESCROW, data="0xdeadbeef", sender=_HUB)
        assert out["ok"] is True and out["gas"] == 54321

    def test_hub_authorization_is_readable(self, wired):
        wired(_FakePool(authorized=False))
        assert chain.hub_is_authorized(_HUB) is False


class TestDefaultsStayInert:
    def test_the_bridge_ships_disabled(self, monkeypatch):
        for var in ("AIMARKET_ESCROW_BRIDGE_ENABLED", "AIMARKET_ESCROW_SUBMIT_STRATEGY",
                    "AIMARKET_ESCROW_SUBMIT_CONFIRM"):
            monkeypatch.delenv(var, raising=False)
        assert config.enabled() is False
        assert config.submit_strategy() == config.STRATEGY_PLAN
        assert config.submit_policy().may_broadcast is False

    def test_an_unknown_strategy_falls_back_to_plan(self, monkeypatch):
        """A typo in a deployment variable must not escalate what the mirror may do."""
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_STRATEGY", "sudo-send-everything")
        assert config.submit_strategy() == config.STRATEGY_PLAN
        assert config.submit_policy().may_broadcast is False

    def test_a_value_moving_strategy_needs_the_confirmation_phrase(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ESCROW_SUBMIT_STRATEGY", "env")
        monkeypatch.setenv("AIMARKET_ESCROW_PRIVATE_KEY", "0x" + "11" * 32)
        monkeypatch.delenv("AIMARKET_ESCROW_SUBMIT_CONFIRM", raising=False)
        policy = config.submit_policy()
        assert policy.may_broadcast is False and "SUBMIT_CONFIRM" in policy.reason

    def test_describe_never_leaks_key_material(self, monkeypatch):
        secret = "0x" + "ab" * 32
        monkeypatch.setenv("AIMARKET_ESCROW_PRIVATE_KEY", secret)
        monkeypatch.setenv("AIMARKET_ESCROW_SIGNER_TOKEN", "bearer-secret")
        blob = repr(config.describe())
        assert secret not in blob and "bearer-secret" not in blob
        assert config.describe()["private_key_set"] is True
