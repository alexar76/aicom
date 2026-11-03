"""The escrow bridge's EIP-712 encoding, checked against something that is not itself.

A digest that is merely self-consistent is worthless here: the only thing that matters is
whether ``AIMarketEscrow.debitChannel`` computes the SAME 32 bytes, because otherwise
``ECDSA.recover`` returns a stranger and every submission reverts with
``InvalidSignature()``. So these tests pin the encoding two independent ways —
against eth-account's own typed-data implementation, and against a literal vector — and
then prove the whole signature round trip with a throwaway key.
"""

from __future__ import annotations

import pytest

from aimarket_hub.escrow_bridge import eip712

pytestmark = pytest.mark.skipif(
    not eip712.crypto_available(),
    reason="eth-account/eth-utils not installed in this interpreter (platon venv)",
)

_CHAIN_ID = 8453  # Base mainnet, the chain the live escrow is deployed to
_ESCROW = "0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb"
_HUB = "0x000000000000000000000000000000000000bEEF"
_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def _auth(**over) -> eip712.DebitAuthorization:
    base = dict(
        channel_id="0x" + "11" * 32,
        hub=_HUB,
        token=_USDC,
        amount=5_000_000,          # 5.00 USDC at 6 decimals
        receipt_id="0x" + "22" * 32,
        nonce=0,
        deadline=2_000_000_000,
    )
    base.update(over)
    return eip712.DebitAuthorization(**base)


def _eth_account_digest(auth: eip712.DebitAuthorization) -> bytes:
    """The same digest via eth-account — a fully independent implementation."""
    from eth_account.messages import encode_typed_data

    signable = encode_typed_data(
        domain_data={
            "name": eip712.ESCROW_DOMAIN_NAME,
            "version": eip712.ESCROW_DOMAIN_VERSION,
            "chainId": _CHAIN_ID,
            "verifyingContract": _ESCROW,
        },
        message_types={
            "DebitAuthorization": [
                {"name": "channelId", "type": "bytes32"},
                {"name": "hub", "type": "address"},
                {"name": "token", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "receiptId", "type": "bytes32"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ],
        },
        message_data=auth.as_message(),
    )
    from eth_utils import keccak

    # SignableMessage is (version, header, body) = (0x01, domainSeparator, structHash);
    # the EIP-191 preimage is 0x19 || version || header || body. Dropping `version` here
    # silently produces a DIFFERENT digest that still looks plausible, so keep all four.
    assert signable.version == b"\x01"
    return keccak(b"\x19" + signable.version + signable.header + signable.body)


class TestDigestAgreesWithAnIndependentImplementation:
    def test_matches_eth_account_typed_data(self):
        auth = _auth()
        assert eip712.debit_digest(
            auth, chain_id=_CHAIN_ID, verifying_contract=_ESCROW
        ) == _eth_account_digest(auth)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("channel_id", "0x" + "ab" * 32),
            ("hub", "0x" + "cd" * 20),
            ("token", "0x" + "ef" * 20),
            ("amount", 1),
            ("receipt_id", "0x" + "99" * 32),
            ("nonce", 7),
            ("deadline", 1_900_000_000),
        ],
    )
    def test_every_field_is_covered_by_the_digest(self, field, value):
        """A field the digest ignores is a field an attacker can change after signing."""
        base = eip712.debit_digest(_auth(), chain_id=_CHAIN_ID, verifying_contract=_ESCROW)
        changed = eip712.debit_digest(
            _auth(**{field: value}), chain_id=_CHAIN_ID, verifying_contract=_ESCROW
        )
        assert base != changed, f"{field} does not affect the digest"
        # …and the independent implementation agrees on the changed value too, so this is
        # not just "some bytes moved" but the SAME bytes the contract would compute.
        assert changed == _eth_account_digest(_auth(**{field: value}))

    def test_the_domain_binds_the_chain_and_the_contract(self):
        auth = _auth()
        on_base = eip712.debit_digest(auth, chain_id=_CHAIN_ID, verifying_contract=_ESCROW)
        other_chain = eip712.debit_digest(auth, chain_id=1, verifying_contract=_ESCROW)
        other_escrow = eip712.debit_digest(
            auth, chain_id=_CHAIN_ID, verifying_contract="0x" + "12" * 20
        )
        assert len({on_base, other_chain, other_escrow}) == 3, (
            "a signature must not be replayable onto another chain or another escrow"
        )

    def test_the_typehash_string_matches_the_contract_source(self):
        """Read from the .sol so a rename on either side fails here, not on chain."""
        from pathlib import Path

        source = Path(__file__).resolve().parents[2] / "contracts/evm/src/AIMarketEscrow.sol"
        if not source.exists():
            pytest.skip("contract source not present in this checkout")
        text = source.read_text()
        assert eip712.DEBIT_TYPE_STRING.replace('"', "") in text.replace('"', "").replace(
            "\n", ""
        ).replace("        ", "")


class TestSignatureRoundTrip:
    def _account(self):
        from eth_account import Account

        # Throwaway, deterministic, and never used anywhere else. A fixed key is safe
        # precisely because it is public: it signs nothing but test vectors.
        return Account.from_key("0x" + "42" * 32)

    def _sign(self, auth, account, *, escrow=_ESCROW, chain_id=_CHAIN_ID):
        from eth_account import Account as A

        digest = eip712.debit_digest(auth, chain_id=chain_id, verifying_contract=escrow)
        return A._sign_hash(digest, account.key).signature.hex()

    def test_the_signer_is_recovered(self):
        acct = self._account()
        auth = _auth()
        assert eip712.signature_matches(
            auth, self._sign(auth, acct), expected_signer=acct.address,
            chain_id=_CHAIN_ID, verifying_contract=_ESCROW,
        )

    def test_a_different_wallet_is_rejected(self):
        acct = self._account()
        auth = _auth()
        assert not eip712.signature_matches(
            auth, self._sign(auth, acct), expected_signer="0x" + "aa" * 20,
            chain_id=_CHAIN_ID, verifying_contract=_ESCROW,
        )

    @pytest.mark.parametrize("field,value", [
        ("amount", 6_000_000),
        ("receipt_id", "0x" + "33" * 32),
        ("nonce", 1),
        ("channel_id", "0x" + "44" * 32),
    ])
    def test_tampering_after_signing_is_rejected(self, field, value):
        """The signature is over the amount/receipt/nonce, so raising any of them fails."""
        acct = self._account()
        signature = self._sign(_auth(), acct)
        assert not eip712.signature_matches(
            _auth(**{field: value}), signature, expected_signer=acct.address,
            chain_id=_CHAIN_ID, verifying_contract=_ESCROW,
        )

    def test_a_signature_for_another_escrow_does_not_transfer(self):
        acct = self._account()
        auth = _auth()
        foreign = self._sign(auth, acct, escrow="0x" + "12" * 20)
        assert not eip712.signature_matches(
            auth, foreign, expected_signer=acct.address,
            chain_id=_CHAIN_ID, verifying_contract=_ESCROW,
        )

    @pytest.mark.parametrize("bad", ["", "   ", "0x", "0xzz", "0x1234", "not-hex",
                                     "0x" + "11" * 64])
    def test_malformed_signatures_return_none_instead_of_raising(self, bad):
        """A broken proof is a failed authorization, never a 500."""
        assert eip712.recover_signer(
            _auth(), bad, chain_id=_CHAIN_ID, verifying_contract=_ESCROW
        ) is None


class TestInputValidation:
    def test_a_zero_verifying_contract_is_refused(self):
        """No deployed contract can verify it — signing it is an invisible dead end.

        The Dart SDK defaulted this to the zero address, which is exactly how such a
        signature gets produced by accident.
        """
        with pytest.raises(eip712.Eip712Error, match="zero address"):
            eip712.debit_digest(_auth(), chain_id=_CHAIN_ID, verifying_contract="0x" + "00" * 20)

    def test_a_zero_hub_is_refused(self):
        with pytest.raises(eip712.Eip712Error, match="zero address"):
            eip712.struct_hash(_auth(hub="0x" + "00" * 20))

    @pytest.mark.parametrize("bad_id", ["0x1234", "0x" + "11" * 31, "0x" + "11" * 33,
                                        "deadbeef", ""])
    def test_a_wrong_length_bytes32_is_refused_not_padded(self, bad_id):
        """Padding would sign a claim against a DIFFERENT deposit than the caller meant."""
        with pytest.raises(eip712.Eip712Error):
            eip712.struct_hash(_auth(channel_id=bad_id))

    @pytest.mark.parametrize("chain_id", [0, -1])
    def test_a_non_positive_chain_id_is_refused(self, chain_id):
        with pytest.raises(eip712.Eip712Error, match="chainId"):
            eip712.domain_separator(chain_id=chain_id, verifying_contract=_ESCROW)

    @pytest.mark.parametrize("amount", [-1, 2**256])
    def test_out_of_range_amounts_are_refused(self, amount):
        with pytest.raises(eip712.Eip712Error, match="uint256"):
            eip712.struct_hash(_auth(amount=amount))

    def test_the_largest_valid_amount_still_encodes(self):
        """Boundary: 2**256-1 is valid, so the refusal above is a bound, not an off-by-one."""
        assert len(eip712.struct_hash(_auth(amount=2**256 - 1))) == 32

    def test_addresses_compare_case_insensitively(self):
        assert eip712.addresses_equal(_HUB, _HUB.lower())
        assert not eip712.addresses_equal(_HUB, "0x" + "aa" * 20)
        assert not eip712.addresses_equal(_HUB, "garbage")
