"""Real signatures and adversarial encodings at the checkout ownership boundary."""
from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from web.backend.services.payment_claim import (
    canonical_tx_hash,
    checkout_tx_hash,
    claim_message,
    verify_claim,
)


def base58(raw: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number, encoded = int.from_bytes(raw, "big"), ""
    while number:
        number, digit = divmod(number, 58)
        encoded = alphabet[digit] + encoded
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + encoded


@pytest.fixture
def solana_claim():
    key = Ed25519PrivateKey.generate()
    payer = base58(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    quote = {"payment_id": "pay-crypto", "customer_id": "buyer", "product_id": "prod-crypto",
                 "amount": 5, "currency": "USDC", "chain": "solana", "wallet_address": "recipient",
                 "site": "https://checkout.example.test"}
    tx = "A" * 88
    signature = key.sign(claim_message(quote, tx).encode()).hex()
    return quote, tx, payer, signature


def test_real_ed25519_proof_is_bound_to_customer_site_and_transfer(solana_claim):
    quote, tx, payer, signature = solana_claim
    assert verify_claim(quote, tx, signature, payer)
    for field, value in (("customer_id", "attacker"), ("site", "https://other.example.test")):
        assert not verify_claim({**quote, field: value}, tx, signature, payer)
    assert not verify_claim(quote, "B" * 88, signature, payer)


@pytest.mark.parametrize("signature", ["00" * 63, "00" * 65, "not-hex", None])
def test_malformed_ed25519_signature_never_authorizes(solana_claim, signature):
    quote, tx, payer, _ = solana_claim
    assert not verify_claim(quote, tx, signature, payer)


@pytest.mark.parametrize("raw", [bytes(32), b"\x01" + bytes(31)])
def test_small_order_key_cannot_authorize_a_forged_signature(solana_claim, raw):
    quote, tx, _, _ = solana_claim
    signature = (b"\x01" + bytes(63)).hex()
    assert not verify_claim(quote, tx, signature, base58(raw))


@pytest.mark.parametrize("payer", ["0-invalid", "1", "O" * 44])
def test_malformed_ed25519_public_key_is_refused(solana_claim, payer):
    quote, tx, _, signature = solana_claim
    assert not verify_claim(quote, tx, signature, payer)


@pytest.mark.parametrize("result", [True, False, RuntimeError("RPC unavailable")])
def test_contract_proof_failure_never_falls_back_to_accepting_a_hash(result):
    quote = {"payment_id": "pay-evm", "customer_id": "buyer", "product_id": "prod-crypto",
                 "amount": 5, "currency": "USDC", "chain": "base", "wallet_address": "0x" + "12" * 20,
                 "site": "https://checkout.example.test"}

    def check(payer, digest, signature):
        assert payer == "0x" + "34" * 20
        assert len(digest) == 32 and signature == b"\x12\x34"
        if isinstance(result, Exception):
            raise result
        return result

    assert verify_claim(quote, "0x" + "ab" * 32, "0x1234", "0x" + "34" * 20,
                        contract_check=check) is (result is True)
    assert not verify_claim(quote, "0x" + "ab" * 32, "0x1234", "0x" + "34" * 20)


@pytest.mark.parametrize("chain,value", [("solana", "0" * 88), ("base", "not-a-hash")])
def test_wrong_network_transaction_encoding_is_refused(chain, value):
    with pytest.raises(ValueError):
        checkout_tx_hash(chain, value)
    assert canonical_tx_hash("") == ""


def test_damaged_quote_cannot_produce_a_valid_ownership_proof():
    assert not verify_claim({}, "0x" + "ab" * 32, "0x1234", "0x" + "34" * 20)
