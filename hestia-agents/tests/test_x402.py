"""The buyer side of a bound payment: typed data in, calldata out, no key."""

from __future__ import annotations

import pytest

from hestia_agents.x402 import (
    TRANSFER_WITH_AUTHORIZATION_SELECTOR,
    QuoteError,
    calldata,
    split_signature,
    typed_data,
)

NONCE = "0x" + "ab" * 32
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAY_TO = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
BUYER = "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c"


def quote(**over) -> dict:
    body = {
        "nonce": NONCE,
        "binding": "eip3009",
        "accepts": [
            {
                "scheme": "exact",
                "payTo": PAY_TO,
                "maxAmountRequired": "4000",
                "asset": USDC,
                "extra": {
                    "name": "USD Coin",
                    "version": "2",
                    "chainId": 8453,
                    "verifyingContract": USDC,
                    "decimals": 6,
                },
            }
        ],
    }
    body.update(over)
    return body


def test_typed_data_uses_the_domain_the_hearth_published() -> None:
    typed = typed_data(quote(), sender=BUYER, valid_before=1800000000)
    assert typed["primaryType"] == "TransferWithAuthorization"
    assert typed["domain"] == {
        "name": "USD Coin",
        "version": "2",
        "chainId": 8453,
        "verifyingContract": USDC,
    }
    assert typed["message"]["nonce"] == NONCE
    assert typed["message"]["to"] == PAY_TO
    assert typed["message"]["value"] == "4000"
    assert typed["message"]["from"] == BUYER


def test_a_quote_without_a_nonce_cannot_be_paid_this_way() -> None:
    body = quote()
    body.pop("nonce")
    with pytest.raises(QuoteError, match="nonce"):
        typed_data(body, sender=BUYER, valid_before=1)


def test_a_quote_missing_the_domain_is_refused_rather_than_guessed() -> None:
    body = quote()
    body["accepts"][0]["extra"].pop("version")
    with pytest.raises(QuoteError, match="version"):
        typed_data(body, sender=BUYER, valid_before=1)


def test_signature_split_normalises_v() -> None:
    sig = "0x" + "11" * 32 + "22" * 32 + "00"
    v, r, s = split_signature(sig)
    assert (v, r, s) == (27, "0x" + "11" * 32, "0x" + "22" * 32)
    assert split_signature("0x" + "11" * 32 + "22" * 32 + "1c")[0] == 28


def test_calldata_is_the_selector_plus_nine_words() -> None:
    typed = typed_data(quote(), sender=BUYER, valid_before=1800000000)
    sig = "0x" + "11" * 32 + "22" * 32 + "1b"
    data = calldata(typed, sig)
    assert data.startswith(TRANSFER_WITH_AUTHORIZATION_SELECTOR)
    payload = data[len(TRANSFER_WITH_AUTHORIZATION_SELECTOR):]
    assert len(payload) == 9 * 64, "nine fixed-size words, no dynamic offsets"
    words = [payload[i * 64:(i + 1) * 64] for i in range(9)]
    assert words[0].endswith(BUYER[2:].lower())
    assert words[1].endswith(PAY_TO[2:].lower())
    assert int(words[2], 16) == 4000
    assert int(words[3], 16) == 0
    assert int(words[4], 16) == 1800000000
    assert words[5] == NONCE[2:]
    assert int(words[6], 16) == 27
    assert words[7] == "11" * 32
    assert words[8] == "22" * 32


def test_a_short_signature_is_refused() -> None:
    typed = typed_data(quote(), sender=BUYER, valid_before=1)
    with pytest.raises(QuoteError, match="65 bytes"):
        calldata(typed, "0xdeadbeef")
