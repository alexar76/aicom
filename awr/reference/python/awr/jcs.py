"""RFC 8785 JSON Canonicalization Scheme, profiled by AWR/2 SPEC.md section 4.

Two things in here are the reason this module is hand-written instead of delegating to a
library:

1. Property names are sorted as **arrays of UTF-16 code units compared as unsigned
   integers** (RFC 8785 section 3.2.3).  Python's ``sorted()`` compares code points,
   which is a different order as soon as a name contains a character outside the Basic
   Multilingual Plane -- an astral character's first UTF-16 code unit is a high
   surrogate in ``[0xD800, 0xDBFF]``, which sorts *below* every BMP character in
   ``[0xE000, 0xFFFF]`` while its code point sorts *above* all of them.
2. AWR forbids non-integer JSON numbers instead of arbitrating them (section 4.3), so
   the parser must reject at the lexical level: a language that parses ``1`` to a double
   and a language that parses it to an integer would otherwise sign different bytes.

No Unicode normalization is applied anywhere (section 4.1 item 2).
"""

from __future__ import annotations

import json
from typing import Any, List, Sequence, Tuple

from .errors import (
    AWR_CANON_001,
    AWR_CANON_002,
    AWR_CANON_003,
    AWR_CANON_004,
    AWR_CANON_005,
    AWR_CANON_006,
    AwrError,
)

#: Largest magnitude of a JSON integer permitted inside a signed AWR document (2^53-1).
MAX_SAFE_INTEGER = 9007199254740991

_TWO_CHAR_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def utf16_code_units(text: str) -> Tuple[int, ...]:
    """Return *text* as the tuple of its UTF-16 code units.

    Characters outside the BMP expand to a surrogate pair, which is exactly what makes
    this ordering differ from code-point ordering.
    """
    units: List[int] = []
    for char in text:
        cp = ord(char)
        if cp < 0x10000:
            units.append(cp)
        else:
            cp -= 0x10000
            units.append(0xD800 + (cp >> 10))
            units.append(0xDC00 + (cp & 0x3FF))
    return tuple(units)


def sort_keys_rfc8785(keys: Sequence[str]) -> List[str]:
    """Sort object property names per RFC 8785 section 3.2.3."""
    return sorted(keys, key=utf16_code_units)


def _check_no_surrogates(text: str, where: str) -> None:
    for index, char in enumerate(text):
        if 0xD800 <= ord(char) <= 0xDFFF:
            raise AwrError(
                AWR_CANON_003,
                "lone surrogate U+%04X at index %d in %s" % (ord(char), index, where),
            )


def _serialize_string(text: str, where: str) -> str:
    _check_no_surrogates(text, where)
    out = ['"']
    for char in text:
        cp = ord(char)
        escape = _TWO_CHAR_ESCAPES.get(cp)
        if escape is not None:
            out.append(escape)
        elif cp < 0x20:
            # RFC 8785 section 3.2.2.2: lowercase hex for the remaining C0 controls.
            out.append("\\u%04x" % cp)
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _serialize(value: Any, out: List[str], path: str) -> None:
    if value is None:
        out.append("null")
        return
    if value is True:
        out.append("true")
        return
    if value is False:
        out.append("false")
        return
    if isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise AwrError(
                AWR_CANON_002,
                "integer %d at %s is outside +/-(2^53-1)" % (value, path or "$"),
            )
        out.append(str(value))
        return
    if isinstance(value, float):
        # Section 4.3: an issuer MUST NOT produce a non-integer number, and a value that
        # arrived as a float cannot be distinguished from one by the time it is a Python
        # object, so every float is refused rather than silently narrowed to an integer.
        raise AwrError(
            AWR_CANON_001,
            "non-integer JSON number %r at %s" % (value, path or "$"),
        )
    if isinstance(value, str):
        out.append(_serialize_string(value, path or "$"))
        return
    if isinstance(value, (list, tuple)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _serialize(item, out, "%s[%d]" % (path, index))
        out.append("]")
        return
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise AwrError(
                    AWR_CANON_005,
                    "object property name %r at %s is not a string" % (key, path or "$"),
                )
        out.append("{")
        first = True
        for key in sort_keys_rfc8785(list(value.keys())):
            if not first:
                out.append(",")
            first = False
            out.append(_serialize_string(key, "property name at %s" % (path or "$",)))
            out.append(":")
            _serialize(value[key], out, "%s.%s" % (path, key))
        out.append("}")
        return
    raise AwrError(
        AWR_CANON_005,
        "value of type %s at %s is not representable in JSON"
        % (type(value).__name__, path or "$"),
    )


def canonicalize(value: Any) -> bytes:
    """Return the RFC 8785 canonical UTF-8 bytes of *value*, no trailing newline."""
    out: List[str] = []
    _serialize(value, out, "")
    return "".join(out).encode("utf-8")


def _object_pairs_hook(pairs: Sequence[Tuple[str, Any]]) -> dict:
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise AwrError(
                AWR_CANON_004, "duplicate object property name %r" % (key,)
            )
        seen.add(key)
    return dict(pairs)


def _parse_int_strict(literal: str) -> int:
    value = int(literal)
    if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
        raise AwrError(
            AWR_CANON_002, "integer literal %s is outside +/-(2^53-1)" % (literal,)
        )
    return value


def _parse_float_strict(literal: str) -> float:
    raise AwrError(AWR_CANON_001, "non-integer JSON number literal %s" % (literal,))


def _parse_constant(literal: str) -> Any:
    # Python's json accepts NaN/Infinity/-Infinity; JSON does not.
    raise AwrError(AWR_CANON_005, "%s is not a JSON value" % (literal,))


def loads(data: Any, *, allow_non_integer_numbers: bool = False) -> Any:
    """Parse JSON text or bytes with the AWR profile's parser requirements.

    Duplicate property names raise ``AWR-CANON-004`` (section 4.1 item 5) so that the
    parser's last-wins habit never decides which bytes were signed.  Number literals are
    checked lexically: anything with a fraction or exponent raises ``AWR-CANON-001`` and
    an out-of-range integer raises ``AWR-CANON-002`` (section 4.3).

    ``allow_non_integer_numbers`` exists only for AWR/1 legacy documents (section 12),
    which predate the number restriction; nothing on the AWR/2 signing or verification
    path sets it.
    """
    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AwrError(AWR_CANON_005, "input is not valid UTF-8: %s" % (exc,))
    elif isinstance(data, str):
        text = data
    else:
        raise TypeError("loads() expects str or bytes, got %s" % type(data).__name__)

    kwargs = {
        "object_pairs_hook": _object_pairs_hook,
        "parse_constant": _parse_constant,
    }
    if allow_non_integer_numbers:
        kwargs["parse_int"] = int
    else:
        kwargs["parse_int"] = _parse_int_strict
        kwargs["parse_float"] = _parse_float_strict
    try:
        return json.loads(text, **kwargs)
    except AwrError:
        raise
    except ValueError as exc:
        raise AwrError(AWR_CANON_005, "not well-formed JSON: %s" % (exc,))


def _exactly_equal(left: Any, right: Any) -> bool:
    """Structural equality that does not conflate types.

    ``1 == 1.0`` and ``0 == False`` in Python; neither is true of JSON canonical bytes,
    and a canonicalizer that normalizes strings must be caught, so string comparison is
    by exact code points.
    """
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, int) and isinstance(right, int):
        return left == right
    if isinstance(left, float) or isinstance(right, float):
        return (
            isinstance(left, float) and isinstance(right, float) and left == right
        )
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _exactly_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left.keys()) != set(right.keys()):
            return False
        return all(_exactly_equal(left[k], right[k]) for k in left)
    return False


def canonical_self_check(value: Any, canonicalizer=canonicalize) -> bytes:
    """Canonicalize *value* and prove the operation was lossless.

    Section 4.1 item 2 and 4.2: a canonicalizer that applies Unicode normalization, drops
    unknown members, coerces integers to floats or reorders equal keys produces a
    different signature in a way that is otherwise silent.  Round-tripping the canonical
    bytes back through the strict parser and requiring exact structural equality catches
    all four.  Failure is ``AWR-CANON-006``.

    *canonicalizer* is injectable so that a conformance harness can point this check at a
    candidate implementation; the default is this module's own.
    """
    canonical = canonicalizer(value)
    reparsed = loads(canonical)
    if not _exactly_equal(reparsed, value):
        raise AwrError(
            AWR_CANON_006,
            "canonicalization was not lossless: re-parsing the canonical bytes did not "
            "reproduce the input (Unicode normalization, number coercion or member loss)",
        )
    return canonical
