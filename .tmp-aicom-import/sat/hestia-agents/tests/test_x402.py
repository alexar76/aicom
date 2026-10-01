"""The buyer side of a bound payment: typed data in, calldata out, no key."""

from __future__ import annotations

import copy
import hashlib

import pytest

from hestia_agents import x402
from hestia_agents.x402 import (
    TRANSFER_WITH_AUTHORIZATION_SELECTOR,
    QuoteError,
    calldata,
    is_guessable,
    is_secret,
    mint_secret,
    nonce_for_secret,
    opens,
    redeem_by,
    secret_refusal,
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


# ------------------------------------------------------- the payment secret


def test_the_nonce_a_secret_commits_to_is_sha256_of_its_bytes() -> None:
    # sha256 of 32 zero bytes, a published test vector: the bytes, not the hex text.
    assert nonce_for_secret("0x" + "00" * 32) == (
        "0x66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925"
    )
    secret = "0x" + "5E" * 32
    assert nonce_for_secret(secret) == "0x" + hashlib.sha256(b"\x5e" * 32).hexdigest()


def test_the_nonce_rule_is_the_hearths() -> None:
    """A nonce derived any other way is a payment the hearth can never redeem."""
    try:
        from hestia.payments import nonce_for_secret as hearths
    except ImportError:  # pragma: no cover - standalone checkout
        pytest.skip("sibling hestia/ sources are not on the path")
    for secret in ("0x" + "00" * 32, "0x" + "Ab" * 32, mint_secret(), mint_secret()):
        assert nonce_for_secret(secret) == hearths(secret)


@pytest.mark.parametrize(
    "secret",
    ["", "0x", "0x" + "ab" * 31, "0x" + "ab" * 33, "ab" * 32, "0X" + "ab" * 32,
     "0x" + "zz" * 32, " 0x" + "ab" * 32, None, 12],
    ids=["empty", "bare-prefix", "short", "long", "unprefixed", "capital-x", "not-hex",
         "padded", "none", "a-number"],
)
def test_a_secret_that_is_not_32_bytes_of_hex_commits_to_nothing(secret) -> None:
    assert is_secret(secret) is False
    assert opens(secret, NONCE) is False
    with pytest.raises(QuoteError, match="0x followed by 64 hex digits"):
        nonce_for_secret(secret)


def test_a_secret_opens_its_own_nonce_and_no_other() -> None:
    secret = mint_secret()
    nonce = nonce_for_secret(secret)
    assert opens(secret, nonce) and opens(secret, nonce.upper().replace("0X", "0x"))
    assert not opens(secret, NONCE)
    # The nonce is public once mined: presented as a secret, it opens nothing.
    assert not opens(nonce, nonce)
    assert not opens(secret, nonce[:-2])


def test_every_minted_secret_is_new_and_well_formed() -> None:
    minted = {mint_secret() for _ in range(64)}
    assert len(minted) == 64
    assert all(is_secret(secret) and not is_guessable(secret) for secret in minted)


def pattern(distinct: int) -> str:
    """A secret with exactly `distinct` different bytes."""
    return "0x" + bytes(range(distinct)).hex() + "00" * (32 - distinct)


@pytest.mark.parametrize(
    ("secret", "guessable"),
    [
        ("0x" + "00" * 32, True),
        ("0x" + "5E" * 32, True),
        (pattern(15), True),
        (pattern(16), False),
        (pattern(32), False),
        ("0x" + hashlib.sha256(b"random enough").hexdigest(), False),
        # Not a secret at all: refused as that, not as guessable.
        ("0x" + "00" * 31, False),
        (None, False),
    ],
    ids=["zeros", "one-byte-repeated", "fifteen-distinct", "sixteen-distinct",
         "all-distinct", "a-digest", "short", "none"],
)
def test_a_secret_is_guessable_below_sixteen_distinct_bytes(secret, guessable) -> None:
    # The hearth's floor (hestia/app.py _compute_gate); test_compute_client runs both
    # sides of it against a real hearth.
    assert is_guessable(secret) is guessable


def test_what_is_wrong_with_a_secret_ends_a_sentence() -> None:
    assert secret_refusal(pattern(16)) == ""
    assert secret_refusal("0x" + "00" * 31) == "is not 0x followed by 64 hex digits"
    assert secret_refusal(pattern(15)) == (
        "is guessable (fewer than 16 distinct bytes): anyone could open its nonce; "
        "use 32 random bytes"
    )


def test_a_guessable_draw_is_drawn_again(monkeypatch) -> None:
    draws = iter(["00" * 32, "5e" * 32, bytes(range(32)).hex()])
    monkeypatch.setattr(x402.secrets, "token_hex", lambda _n: next(draws))
    assert mint_secret() == "0x" + bytes(range(32)).hex()


@pytest.mark.parametrize(
    ("expires", "last"),
    [(1800000900.7, 1800000900), (1800000900, 1800000900), (None, None)],
    ids=["float", "int", "absent"],
)
def test_the_redeem_by_time_is_the_expiry_in_whole_seconds_down(expires, last) -> None:
    body = {} if expires is None else {"expires_at": expires}
    assert redeem_by(body) == last


@pytest.mark.parametrize(
    "expires", ["1800000900", True, 0, -1, float("nan"), float("inf"), [1]],
    ids=["text", "bool", "zero", "negative", "nan", "inf", "list"],
)
def test_an_expiry_that_is_not_a_unix_time_is_refused(expires) -> None:
    with pytest.raises(QuoteError, match="402 'expires_at' is not a unix time"):
        redeem_by({"expires_at": expires})


# ---------------------------------------------------- signing another nonce


def test_a_nonce_given_is_signed_instead_of_the_quotes() -> None:
    body = quote()
    before = copy.deepcopy(body)
    other = "0x" + "cd" * 32
    typed = typed_data(body, sender=BUYER, valid_before=1800000000, nonce=other)
    assert typed["message"]["nonce"] == other
    assert body == before, "the quote is read, not rewritten"
    assert typed_data(body, sender=BUYER, valid_before=1800000000)["message"]["nonce"] == NONCE


def test_a_nonce_given_needs_no_nonce_in_the_quote() -> None:
    # The compute door mints none: the buyer's own secret makes it.
    body = quote()
    body.pop("nonce")
    nonce = nonce_for_secret("0x" + "5e" * 32)
    assert typed_data(body, sender=BUYER, valid_before=1, nonce=nonce)["message"]["nonce"] == nonce


@pytest.mark.parametrize("nonce", ["0x1234", "ab" * 32, "0X" + "ab" * 32, "0x" + "zz" * 32])
def test_a_nonce_given_that_is_not_32_bytes_is_refused(nonce) -> None:
    with pytest.raises(QuoteError, match="the payment nonce given is not 32 bytes"):
        typed_data(quote(), sender=BUYER, valid_before=1, nonce=nonce)


@pytest.mark.parametrize(
    ("moments", "flag"),
    [({"valid_before": -1}, "--valid-before"), ({"valid_before": True}, "--valid-before"),
     ({"valid_before": 1.5}, "--valid-before"), ({"valid_after": -60, "valid_before": 1},
                                                  "--valid-after")],
    ids=["negative", "bool", "float", "negative-after"],
)
def test_a_deadline_that_is_not_a_unix_time_is_refused(moments, flag) -> None:
    # A negative one used to be written into the calldata as '-000…1'.
    with pytest.raises(QuoteError, match=f"{flag} is not a unix time"):
        typed_data(quote(), sender=BUYER, **moments)


@pytest.mark.parametrize("sender", ["0xYOURADDRESS", BUYER[:-1], BUYER[2:], None])
def test_typed_data_refuses_a_sender_that_is_not_an_address(sender) -> None:
    # The CLI refuses these before asking the hearth; a caller of the library is held
    # to the same rule rather than handed typed data with a template in it.
    with pytest.raises(QuoteError, match="--from is not an address"):
        typed_data(quote(), sender=sender, valid_before=1)
