"""id.check@v1 against published examples and the BIP 350 test vectors.

The valid examples are the ones the standards and their registries print (the IBAN registry's
country examples, the ISBN/ISSN/EAN/ISIN examples, Apple's LEI, the EIP-55 test cases, the
Bitcoin wiki's base58 addresses). bip350_vectors.json is copied byte for byte from
bitcoin/bips bip-0350.mediawiki. Then every single-character change to a valid identifier
must be caught by every check digit that promises to catch it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hestia_agents.manifests import handler_source

BIP350 = json.loads((Path(__file__).parent / "bip350_vectors.json").read_text(encoding="utf-8"))

VALID = [
    ("DE89370400440532013000", "iban"), ("GB82WEST12345698765432", "iban"),
    ("NL91ABNA0417164300", "iban"), ("FR1420041010050500013M02606", "iban"),
    ("CH9300762011623852957", "iban"), ("BE68539007547034", "iban"), ("NO9386011117947", "iban"),
    ("DE89 3704 0044 0532 0130 00", "iban"),
    ("DEUTDEFF", "bic"), ("DEUTDEFF500", "bic"),
    ("9780306406157", "isbn"), ("0306406152", "isbn"), ("0-8044-2957-X", "isbn"),
    ("ISBN 978-0-306-40615-7", "isbn"),
    ("4006381333931", "gtin"), ("036000291452", "gtin"), ("73513537", "gtin"),
    ("0378-5955", "issn"), ("2049-3630", "issn"),
    ("US0378331005", "isin"), ("AU0000XVGZA3", "isin"), ("GB0002634946", "isin"),
    ("HWUPKR0MPOU8FGXBT394", "lei"),
    ("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed", "evm"),
    ("0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359", "evm"),
    ("0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB", "evm"),
    ("0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb", "evm"),
    ("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "bitcoin"),
    ("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy", "bitcoin"),
]


@pytest.fixture(scope="module")
def ns():
    namespace: dict = {}
    exec(compile(handler_source("id-check"), "id-check", "exec"), namespace)  # noqa: S102
    return namespace


@pytest.fixture(scope="module")
def handle(ns):
    return ns["handle"]


@pytest.mark.parametrize(("ident", "kind"), VALID)
def test_published_examples_are_valid_and_detected(handle, ident, kind) -> None:
    out = handle({"id": ident})
    assert out["type"] == kind and out["valid"] is True, out
    assert out["input"] == ident


@pytest.mark.parametrize(("address", "script"), BIP350["valid"])
def test_bip350_valid_addresses(handle, address, script) -> None:
    out = handle({"id": address, "type": "bitcoin"})
    assert out["valid"] is True and out["script_pubkey"] == script


@pytest.mark.parametrize(("address", "why"), BIP350["invalid"])
def test_bip350_invalid_addresses(handle, address, why) -> None:
    assert handle({"id": address, "type": "bitcoin"})["valid"] is False, why


def _mutations(text):
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i, char in enumerate(text):
        if char.upper() not in alphabet:
            continue
        for other in alphabet:
            if other != char.upper() and (char.isdigit() == other.isdigit()):
                yield text[:i] + other + text[i + 1:]


@pytest.mark.parametrize("ident", ["DE89370400440532013000", "HWUPKR0MPOU8FGXBT394",
                                   "9780306406157", "4006381333931", "0306406152"])
def test_every_single_character_error_is_caught(handle, ident) -> None:
    kind = handle({"id": ident})["type"]
    missed = [m for m in _mutations(ident) if handle({"id": m, "type": kind})["valid"]]
    assert missed == [], missed[:5]


def test_isin_catches_digits_but_not_every_letter(handle) -> None:
    """ISIN's Luhn runs over the letters' two-digit expansion, so some letter swaps cancel out.
    That is the standard's weakness, not the checker's: it is stated rather than hidden."""
    digits = [m for m in _mutations("US0378331005") if m[:2] == "US"]
    assert not [m for m in digits if handle({"id": m, "type": "isin"})["valid"]]
    assert handle({"id": "ES0378331005", "type": "isin"})["valid"] is True


def test_iban_details_and_failures(handle) -> None:
    out = handle({"id": "gb82 west 1234 5698 7654 32"})
    assert out["normalized"] == "GB82WEST12345698765432"
    assert out["country"] == "GB" and out["check_digits"] == "82"
    assert "print_format" not in out and "bban" not in out
    assert "22 characters" in handle({"id": "DE8937040044053201300", "type": "iban"})["reason"]
    assert "does not issue" in handle({"id": "XX89370400440532013000", "type": "iban"})["reason"]
    assert "typo" in handle({"id": "DE89370400440532013001"})["reason"]


def test_isbn10_gets_its_isbn13(handle) -> None:
    assert handle({"id": "0306406152"})["isbn13"] == "9780306406157"


def test_evm_single_case_has_no_checksum_and_a_bad_one_is_not_corrected(handle) -> None:
    lower = handle({"id": "0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed"})
    assert lower["valid"] is True and lower["checksum"] is False
    assert lower["normalized"] == "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
    typo = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeD"
    out = handle({"id": typo})
    assert out["valid"] is False and out["normalized"] == typo


def test_bitcoin_details(handle) -> None:
    p2pkh = handle({"id": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"})
    assert (p2pkh["network"], p2pkh["kind"]) == ("mainnet", "p2pkh")
    taproot = handle({"id": BIP350["valid"][-1][0]})
    assert (taproot["network"], taproot["kind"], taproot["witness_version"]) == (
        "mainnet", "p2tr", 1)
    broken = "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN3"
    assert "checksum" in handle({"id": broken})["reason"]


def test_bic_has_no_check_digit_and_says_so(handle) -> None:
    out = handle({"id": "DEUTDEFF"})
    assert out["branch"] == "XXX" and "no check digit" in out["reason"]
    assert handle({"id": "DEUT1EFF", "type": "bic"})["valid"] is False


def test_batch_with_mixed_types(handle) -> None:
    out = handle({"ids": ["DE89370400440532013000", {"id": "03785955", "type": "issn"},
                          "not an id", "9780306406158"]})
    assert [r["valid"] for r in out["results"]] == [True, True, False, False]
    assert out["results"][2]["type"] is None and (out["valid"], out["invalid"]) == (2, 2)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({}, "send 'id'"),
        ({"id": ""}, "non-empty"),
        ({"id": "x" * 121}, "120"),
        ({"id": "DE89", "type": "card"}, "type must be"),
        ({"ids": []}, "non-empty list"),
        ({"ids": ["a"] * 1001}, "at most"),
    ],
)
def test_bad_requests_say_why(handle, payload, match) -> None:
    with pytest.raises(ValueError, match=match):
        handle(payload)
