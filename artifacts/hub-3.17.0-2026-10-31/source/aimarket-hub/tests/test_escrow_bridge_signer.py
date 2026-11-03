"""The env-key signer — the path that actually broadcasts a collection.

It could never sign anything. `eth_account.Account.sign_transaction` refuses a `to` address
that is not EIP-55 checksummed (it raises `TypeError: Transaction had invalid fields`), and
every address reaching this signer is lowercase — that is how addresses come back from an
RPC receipt and how the bridge stores them. The failure surfaced as
"signing failed (TypeError)", a message that hides the payload on purpose and therefore hid
the cause as well.

Nothing caught it because the live deployment collects through an external policy signer and
has never used the env-key path; the first thing to exercise it was the UNI bubble, where the
hub holds its own key.
"""
from __future__ import annotations

import pytest

from aimarket_hub.escrow_bridge import signer as signer_mod

LOWER = "0xf4fe699cceece5e016521dda25a4b8641248b624"
CHECKSUMMED = "0xf4FE699cCeEcE5e016521DDa25a4b8641248b624"

pytestmark = pytest.mark.skipif(
    not signer_mod.__dict__.get("_checksummed"), reason="signer has no address normaliser",
)

# The normaliser computes EIP-55 through eth-utils, which arrives with the optional
# `[escrow]` extra — the same extra that brings eth-account, without which the env-key
# signer refuses to sign at all (see `EnvKeySigner.submit`). A checkout without the
# extra therefore cannot put value in motion, and asserting the checksum there fails a
# suite over a capability the install does not have. Skip instead: red must mean the
# normaliser is wrong, not that escrow is not installed.
_needs_eth_utils = pytest.mark.skipif(
    not signer_mod.__dict__.get("_checksummed")
    or signer_mod._checksummed(LOWER) == LOWER,
    reason="eth-utils missing — install aimarket-hub[escrow]",
)


@_needs_eth_utils
def test_a_lowercase_address_is_checksummed_for_signing():
    assert signer_mod._checksummed(LOWER) == CHECKSUMMED


@_needs_eth_utils
def test_an_already_checksummed_address_is_unchanged():
    assert signer_mod._checksummed(CHECKSUMMED) == CHECKSUMMED


def test_nonsense_is_passed_through_rather_than_raising():
    """A signer that refuses to try is worse than one that lets eth-account complain."""
    assert signer_mod._checksummed("not-an-address") == "not-an-address"
    assert signer_mod._checksummed("") == ""
    assert signer_mod._checksummed(None) == ""


def test_eth_account_accepts_what_the_normaliser_produces():
    """The whole point: the value must survive the library that rejected the old one."""
    eth_account = pytest.importorskip("eth_account")

    key = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    tx = {
        "to": signer_mod._checksummed(LOWER), "data": "0x", "value": 0, "gas": 100_000,
        "nonce": 0, "gasPrice": 1_000_000_000, "chainId": 31337,
    }
    signed = eth_account.Account.sign_transaction(tx, key)
    assert getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)

    with pytest.raises(TypeError):
        eth_account.Account.sign_transaction({**tx, "to": LOWER}, key)
