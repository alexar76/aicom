"""RFC 8785 JCS as profiled by SPEC.md section 4."""

from __future__ import annotations

import json
import unicodedata

import pytest
from conftest import assert_raises_code

from awr.jcs import (
    MAX_SAFE_INTEGER,
    canonical_self_check,
    canonicalize,
    loads,
    sort_keys_rfc8785,
    utf16_code_units,
)

# ---------------------------------------------------------------------------
# section 4.1 item 1 -- UTF-16 code-unit ordering of property names
# ---------------------------------------------------------------------------

#: The RFC 8785 section 3.2.3 illustration: a non-BMP name sorts *before* high BMP names
#: because its first UTF-16 code unit is a high surrogate (0xD83D), while its code point
#: (0x1F600) is larger than every BMP code point.
UTF16_SORT_SAMPLE = {
    "€": "Euro Sign",
    "\r": "Carriage Return",
    "דּ": "Hebrew Letter Dalet With Dagesh",
    "1": "One",
    "\U0001f600": "Emoji: Grinning Face",
    "": "Control",
    "ö": "Latin Small Letter O With Diaeresis",
}

UTF16_SORT_EXPECTED = (
    '{"\\r":"Carriage Return",'
    '"1":"One",'
    '"":"Control",'
    '"ö":"Latin Small Letter O With Diaeresis",'
    '"€":"Euro Sign",'
    '"\U0001f600":"Emoji: Grinning Face",'
    '"דּ":"Hebrew Letter Dalet With Dagesh"}'
)


def test_utf16_code_units_expand_astral_characters():
    assert utf16_code_units("\U0001f600") == (0xD83D, 0xDE00)
    assert utf16_code_units("דּ") == (0xFB33,)
    assert utf16_code_units("ab") == (0x61, 0x62)


def test_key_order_is_utf16_and_differs_from_code_point_order():
    keys = list(UTF16_SORT_SAMPLE)
    utf16_order = sort_keys_rfc8785(keys)
    code_point_order = sorted(keys)

    # The whole point of section 4.1 item 1: these two orders are not the same.
    assert utf16_order != code_point_order
    assert utf16_order.index("\U0001f600") < utf16_order.index("דּ")
    assert code_point_order.index("\U0001f600") > code_point_order.index("דּ")


def test_canonicalize_uses_the_utf16_order():
    assert canonicalize(UTF16_SORT_SAMPLE) == UTF16_SORT_EXPECTED.encode("utf-8")


def test_python_sorted_would_produce_different_bytes():
    """A canonicalizer built on ``sorted()`` signs different bytes for this object."""
    naive = "{" + ",".join(
        '%s:%s' % (json.dumps(k, ensure_ascii=False), json.dumps(v, ensure_ascii=False))
        for k, v in sorted(UTF16_SORT_SAMPLE.items())
    ) + "}"
    assert naive.encode("utf-8") != canonicalize(UTF16_SORT_SAMPLE)


# ---------------------------------------------------------------------------
# section 4.1 item 2 -- no Unicode normalization
# ---------------------------------------------------------------------------


def test_no_unicode_normalization_of_values_or_names():
    decomposed = "é"  # e + COMBINING ACUTE ACCENT
    composed = "é"  # LATIN SMALL LETTER E WITH ACUTE
    assert unicodedata.normalize("NFC", decomposed) == composed

    assert canonicalize({"k": decomposed}) == '{"k":"é"}'.encode("utf-8")
    assert canonicalize({decomposed: "v"}) == '{"é":"v"}'.encode("utf-8")
    # The two spellings must stay distinguishable: NFC would collapse them.
    assert canonicalize({"k": decomposed}) != canonicalize({"k": composed})


def test_nfc_applying_canonicalizer_is_caught_as_canon_006():
    """Section 4.1 item 2 names AWR-CANON-006 for a normalizing implementation."""

    def nfc_normalize(value):
        if isinstance(value, str):
            return unicodedata.normalize("NFC", value)
        if isinstance(value, dict):
            return {nfc_normalize(k): nfc_normalize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [nfc_normalize(item) for item in value]
        return value

    def nfc_canonicalizer(value):
        return canonicalize(nfc_normalize(value))

    document = {"credentialSubject": {"note": "éclair"}}
    assert_raises_code(
        "AWR-CANON-006",
        lambda: canonical_self_check(document, canonicalizer=nfc_canonicalizer),
    )
    # The conforming canonicalizer passes the same check.
    assert canonical_self_check(document) == canonicalize(document)


def test_self_check_catches_a_canonicalizer_that_drops_unknown_members():
    def lossy(value):
        if isinstance(value, dict):
            return canonicalize({k: v for k, v in value.items() if k != "unknownExtra"})
        return canonicalize(value)

    assert_raises_code(
        "AWR-CANON-006",
        lambda: canonical_self_check({"a": 1, "unknownExtra": "keep me"}, canonicalizer=lossy),
    )


# ---------------------------------------------------------------------------
# section 4.1 item 3 -- escaping
# ---------------------------------------------------------------------------


def test_two_character_escapes_for_the_defined_set():
    assert canonicalize({"k": "\b\t\n\f\r\"\\"}) == b'{"k":"\\b\\t\\n\\f\\r\\"\\\\"}'


def test_remaining_c0_controls_use_lowercase_four_digit_escapes():
    assert canonicalize({"k": "\x00"}) == b'{"k":"\\u0000"}'
    assert canonicalize({"k": "\x1b"}) == b'{"k":"\\u001b"}'
    assert canonicalize({"k": "\x1f"}) == b'{"k":"\\u001f"}'
    # lowercase, not 
    assert b"\\u001B" not in canonicalize({"k": "\x1b"})


def test_everything_else_is_emitted_literally():
    # U+007F DELETE and U+0080 are not escaped by RFC 8785; only C0 controls are.
    assert canonicalize({"k": "\x7f"}) == '{"k":"\x7f"}'.encode("utf-8")
    assert canonicalize({"k": ""}) == '{"k":""}'.encode("utf-8")
    assert canonicalize({"k": "ü中\U0001f600"}) == (
        '{"k":"ü中\U0001f600"}'.encode("utf-8")
    )
    assert canonicalize({"k": "/"}) == b'{"k":"/"}'


# ---------------------------------------------------------------------------
# section 4.1 item 4 -- lone surrogates terminate with an error
# ---------------------------------------------------------------------------


def test_lone_surrogate_in_a_value_raises_canon_003():
    parsed = loads('{"k":"\\ud800"}')
    assert parsed == {"k": "\ud800"}
    error = assert_raises_code("AWR-CANON-003", lambda: canonicalize(parsed))
    assert "D800" in error.detail


def test_lone_surrogate_in_a_property_name_raises_canon_003():
    assert_raises_code("AWR-CANON-003", lambda: canonicalize({"\udfff": "v"}))


def test_lone_surrogate_is_not_replaced_with_u_fffd():
    try:
        canonicalize({"k": "\ud800"})
    except Exception as exc:  # noqa: BLE001 -- the type is asserted above
        assert "�" not in str(exc)


# ---------------------------------------------------------------------------
# section 4.1 item 5 -- duplicate property names
# ---------------------------------------------------------------------------


def test_duplicate_property_names_raise_canon_004():
    error = assert_raises_code(
        "AWR-CANON-004", lambda: loads('{"a":1,"b":2,"a":3}')
    )
    assert "'a'" in error.detail
    # json.loads without the hook silently keeps the last occurrence: that choice would
    # otherwise decide which bytes were signed.
    assert json.loads('{"a":1,"b":2,"a":3}') == {"a": 3, "b": 2}


def test_duplicate_property_names_are_detected_at_any_depth():
    assert_raises_code(
        "AWR-CANON-004", lambda: loads('{"outer":{"x":1,"x":2}}')
    )


# ---------------------------------------------------------------------------
# section 4.3 -- number restriction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("literal", ["1.5", "0.0", "2340.0", "1e2", "1E2", "-0.1", "1.0"])
def test_non_integer_number_literals_raise_canon_001(literal):
    assert_raises_code("AWR-CANON-001", lambda: loads('{"n":%s}' % (literal,)))


def test_float_python_values_raise_canon_001():
    assert_raises_code("AWR-CANON-001", lambda: canonicalize({"n": 1.5}))
    # Even a float that happens to be integral: nothing downstream can tell it from 1.5,
    # and the int/float divergence is the class of problem section 4.3 removes.
    assert_raises_code("AWR-CANON-001", lambda: canonicalize({"n": 2340.0}))


def test_integers_at_the_boundary_are_accepted():
    assert canonicalize({"n": MAX_SAFE_INTEGER}) == b'{"n":9007199254740991}'
    assert canonicalize({"n": -MAX_SAFE_INTEGER}) == b'{"n":-9007199254740991}'
    assert loads('{"n":9007199254740991}') == {"n": MAX_SAFE_INTEGER}


@pytest.mark.parametrize(
    "literal", ["9007199254740992", "-9007199254740992", "18446744073709551616"]
)
def test_integers_outside_the_range_raise_canon_002(literal):
    assert_raises_code("AWR-CANON-002", lambda: loads('{"n":%s}' % (literal,)))


def test_python_integers_outside_the_range_raise_canon_002():
    assert_raises_code("AWR-CANON-002", lambda: canonicalize({"n": 2 ** 53}))


def test_integers_are_serialized_without_a_fraction():
    assert canonicalize({"latencyMs": 2340}) == b'{"latencyMs":2340}'
    assert canonicalize({"n": 0}) == b'{"n":0}'
    assert canonicalize({"n": -0}) == b'{"n":0}'


# ---------------------------------------------------------------------------
# well-formedness and structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["{", "{'a':1}", "", "{\"a\":}", "[1,]", "tru"])
def test_malformed_json_raises_canon_005(text):
    assert_raises_code("AWR-CANON-005", lambda: loads(text))


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", '{"n":NaN}'])
def test_json_non_values_raise_canon_005(text):
    assert_raises_code("AWR-CANON-005", lambda: loads(text))


def test_invalid_utf8_bytes_raise_canon_005():
    assert_raises_code("AWR-CANON-005", lambda: loads(b'{"a":"\xff\xfe"}'))


def test_unserializable_python_value_raises_canon_005():
    assert_raises_code("AWR-CANON-005", lambda: canonicalize({"a": object()}))
    assert_raises_code("AWR-CANON-005", lambda: canonicalize({1: "int key"}))


def test_structural_canonical_forms():
    assert canonicalize({}) == b"{}"
    assert canonicalize([]) == b"[]"
    assert canonicalize(None) == b"null"
    assert canonicalize(True) == b"true"
    assert canonicalize(False) == b"false"
    assert canonicalize("x") == b'"x"'
    assert canonicalize([1, {"b": [True, None]}, "s"]) == b'[1,{"b":[true,null]},"s"]'
    assert canonicalize({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
    # no whitespace, no trailing newline
    assert b" " not in canonicalize({"a": [1, 2]})
    assert not canonicalize({"a": 1}).endswith(b"\n")


def test_booleans_are_not_confused_with_integers():
    assert canonicalize({"a": True}) == b'{"a":true}'
    assert canonicalize({"a": 1}) == b'{"a":1}'


def test_self_check_returns_the_canonical_bytes():
    document = {"a": 1, "b": ["x", {"c": None}], "\U0001f600": "astral"}
    assert canonical_self_check(document) == canonicalize(document)
