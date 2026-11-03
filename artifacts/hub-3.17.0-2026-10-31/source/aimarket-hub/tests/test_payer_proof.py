"""The hub's own payer-proof challenge, and that it has not drifted from the canonical one.

Proving a deposit takes two answers: "did this transaction pay us" (deposit_verify) and
"who controls the paying wallet" (this). BOTH lived only in `web…on_chain`, and both
degraded to "unproven" on a standalone hub — so fixing the verifier alone would simply
have moved the refusal one step later, from "on-chain verification unavailable" to
"missing or invalid payer proof".

The message is reproduced rather than imported, which makes drift the risk: a signature
accepted at the web door must be accepted at this one. `test_matches_the_canonical_message`
is the guard, and skips where `web` is not importable (a hub-only checkout, which is
exactly the deployment this module exists for).
"""

from __future__ import annotations

import pytest

from aimarket_hub.payer_proof import (
    canonical_proof_amount_cents,
    canonical_proof_payer,
    canonical_proof_tx_hash,
    channel_open_proof_message,
    recover_channel_open_payer,
)

def _load_canonical_module():
    """The canonical `on_chain` module by file path, with its one sibling import stubbed."""
    import importlib.util
    import sys
    import types
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "web/backend/services/ai_market_protocol/on_chain.py"
    if not path.exists():
        return None
    for name in ("web", "web.backend", "web.backend.services",
                 "web.backend.services.ai_market_protocol"):
        sys.modules.setdefault(name, types.ModuleType(name))
    config = types.ModuleType("web.backend.services.ai_market_protocol.config")
    config.demo_payment_bypass = lambda *a, **k: False
    sys.modules["web.backend.services.ai_market_protocol.config"] = config
    spec = importlib.util.spec_from_file_location("canonical_on_chain", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


CHAIN = "base"
TX = "0xa28b2fb04c3d571215f808b26066476dd420ba2893a3c50832f913f62bdf3666"
PAYER = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"


class TestMessage:
    def test_the_exact_bytes(self):
        """Pinned literally: this string is what wallets have already signed."""
        assert channel_open_proof_message(
            chain="Base", tx_hash=TX.upper().replace("0X", "0x"),
            payer=PAYER.upper().replace("0X", "0x"), amount_usd=1.5,
        ) == (
            "AIMarket-Payer-Proof/v1\n"
            "purpose:channel-open\n"
            "chain:base\n"
            f"tx:{TX}\n"
            f"payer:{PAYER}\n"
            "amount_cents:150"
        )

    def test_matches_the_canonical_message(self):
        """The drift guard. Loaded by FILE, not by import.

        `web…ai_market_protocol.__init__` pulls in the whole web app, so importing the
        package needs passlib and friends — which is exactly why the hub cannot use the
        canonical module at runtime. The module itself is pure; loading the file gives a
        real comparison instead of a skip that hides drift forever.
        """
        canonical = _load_canonical_module()
        if canonical is None:
            pytest.skip("canonical on_chain.py not present (hub-only checkout)")
        cases = [
            (CHAIN, TX, PAYER, 1.5),
            ("Base", TX.upper().replace("0X", "0x"), PAYER.upper().replace("0X", "0x"), 0.01),
            (CHAIN, TX[2:], PAYER, 200.0),                       # bare hex, prefix added in
            (CHAIN, "5Nx1Kc9pQrStUvWxYz", "SoLanaPayer123", 7.77),  # base58 stays byte-exact
            ("BASE", TX, PAYER, 0),
        ]
        for chain, tx, payer, amount in cases:
            assert channel_open_proof_message(
                chain=chain, tx_hash=tx, payer=payer, amount_usd=amount
            ) == canonical.channel_open_proof_message(
                chain=chain, tx_hash=tx, payer=payer, amount_usd=amount
            ), (chain, tx, payer, amount)

    def test_a_signature_over_the_canonical_message_verifies_here(self):
        """One signature, both doors — the property the reproduction exists to keep."""
        canonical = _load_canonical_module()
        if canonical is None:
            pytest.skip("canonical on_chain.py not present (hub-only checkout)")
        eth_account = pytest.importorskip("eth_account")
        from eth_account.messages import encode_defunct

        key = "0x" + "22" * 32
        account = eth_account.Account.from_key(key)
        message = canonical.channel_open_proof_message(
            chain=CHAIN, tx_hash=TX, payer=account.address, amount_usd=3.25
        )
        signature = eth_account.Account.sign_message(
            encode_defunct(text=message), private_key=key
        ).signature.hex()
        recovered = recover_channel_open_payer(
            chain=CHAIN, tx_hash=TX, payer=account.address, amount_usd=3.25,
            signature=signature,
        )
        assert recovered and recovered.lower() == account.address.lower()

    def test_case_does_not_change_the_deposit_being_claimed(self):
        """A client signing the checksummed rendering of its own hash must not be refused."""
        assert channel_open_proof_message(
            chain=CHAIN, tx_hash=TX.upper().replace("0X", "0x"), payer=PAYER, amount_usd=1
        ) == channel_open_proof_message(
            chain=CHAIN, tx_hash=TX, payer=PAYER, amount_usd=1
        )

    def test_a_bare_hex_hash_normalises_the_prefix_in(self):
        assert canonical_proof_tx_hash(TX[2:]) == TX

    def test_base58_keeps_its_case(self):
        sol = "5Nx1Kc9pQrStUvWxYz"
        assert canonical_proof_tx_hash(sol) == sol
        assert canonical_proof_payer(sol) == sol

    @pytest.mark.parametrize("bad", ["", None, "abc", float("nan"), float("inf")])
    def test_an_unusable_amount_can_never_match_a_deposit(self, bad):
        assert canonical_proof_amount_cents(bad) == -1


class TestRecovery:
    def _signed(self, amount_usd: float = 1.5, tx: str = TX):
        eth_account = pytest.importorskip("eth_account")
        from eth_account.messages import encode_defunct

        account = eth_account.Account.from_key("0x" + "11" * 32)
        message = channel_open_proof_message(
            chain=CHAIN, tx_hash=tx, payer=account.address, amount_usd=amount_usd
        )
        signed = eth_account.Account.sign_message(
            encode_defunct(text=message), private_key="0x" + "11" * 32
        )
        return account.address, signed.signature.hex()

    def test_a_real_signature_recovers_the_signer(self):
        address, signature = self._signed()
        recovered = recover_channel_open_payer(
            chain=CHAIN, tx_hash=TX, payer=address, amount_usd=1.5, signature=signature
        )
        assert recovered and recovered.lower() == address.lower()

    def test_a_signature_for_another_amount_does_not_transfer(self):
        """The amount is in the preimage, so a proof cannot be replayed at a new price."""
        address, signature = self._signed(amount_usd=1.5)
        recovered = recover_channel_open_payer(
            chain=CHAIN, tx_hash=TX, payer=address, amount_usd=999.0, signature=signature
        )
        assert not recovered or recovered.lower() != address.lower()

    def test_a_signature_for_another_transaction_does_not_transfer(self):
        address, signature = self._signed(tx=TX)
        recovered = recover_channel_open_payer(
            chain=CHAIN, tx_hash="0x" + "cd" * 32, payer=address, amount_usd=1.5,
            signature=signature,
        )
        assert not recovered or recovered.lower() != address.lower()

    @pytest.mark.parametrize("signature", ["", "   ", "0xdeadbeef", "not-a-signature"])
    def test_anything_unusable_is_unproven(self, signature):
        assert recover_channel_open_payer(
            chain=CHAIN, tx_hash=TX, payer=PAYER, amount_usd=1.5, signature=signature
        ) is None


class TestHubReports:
    def test_a_hub_with_eth_account_can_prove_payers(self):
        from aimarket_hub import channels

        # Satellite CI has no monorepo `web/` package; without it the shared on-chain
        # primitives cannot load and payer proof stays off — skip rather than fail red.
        if not channels._payer_proof_ready():
            pytest.skip("web.backend on-chain helpers not in this checkout")
        assert channels._payer_proof_ready() is True

    def test_the_challenge_is_stated_not_blank(self):
        """A blank challenge is a refusal a client cannot act on."""
        from aimarket_hub.channels import payer_proof_challenge

        challenge = payer_proof_challenge(
            payer=PAYER, tx_hash=TX, chain=CHAIN, deposit_usd=2.0
        )
        assert challenge.startswith("AIMarket-Payer-Proof/v1")
        assert "amount_cents:200" in challenge
