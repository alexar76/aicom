"""RFC 8785 (JCS) canonical JSON + SHA-256, for anything that signs JSON.

Two documents that mean the same thing must serialise to the same bytes, or the
same signature verifies here and fails there. That is the whole job.

Numbers are the part every implementation gets wrong. JCS serialises them with
ECMAScript rules, so a float can canonicalise differently in Python and in a
JavaScript verifier, and an integer above 2^53-1 cannot survive a JavaScript
verifier at all. Rather than emit bytes that might not reproduce, this refuses
both and says why. AWR receipts are integers-only for exactly this reason.
"""

import hashlib

MAX_SAFE_INTEGER = 9007199254740991  # 2**53 - 1

_SHORT_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _escape(text):
    """RFC 8785 3.2.2.2: escape only what must be escaped, leave the rest literal."""
    out = ['"']
    for char in text:
        point = ord(char)
        short = _SHORT_ESCAPES.get(point)
        if short is not None:
            out.append(short)
        elif point < 0x20:
            out.append("\\u" + format(point, "04x"))
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _sort_key(name):
    """JCS sorts keys by UTF-16 code unit, not by Unicode code point.

    The two orders disagree for anything outside the BMP, so an emoji key can
    sort one way in a naive implementation and another way in a correct one.
    """
    return name.encode("utf-16-be")


def _serialise(value, path):
    where = path or "$"
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if value > MAX_SAFE_INTEGER or value < -MAX_SAFE_INTEGER:
            raise ValueError(
                "integer at " + where + " is outside the range a JavaScript verifier "
                "can represent exactly (2^53-1); send it as a string"
            )
        return str(value)
    if isinstance(value, float):
        raise ValueError(
            "number at " + where + " is not an integer. JCS serialises numbers with "
            "ECMAScript rules, so a float can canonicalise differently in another "
            "language and break the signature; send a string or a scaled integer"
        )
    if isinstance(value, str):
        return _escape(value)
    if isinstance(value, list):
        parts = []
        for index, item in enumerate(value):
            parts.append(_serialise(item, where + "[" + str(index) + "]"))
        return "[" + ",".join(parts) + "]"
    if isinstance(value, dict):
        names = []
        for name in value:
            if not isinstance(name, str):
                raise ValueError("object key at " + where + " must be a string")
            names.append(name)
        names.sort(key=_sort_key)
        parts = []
        for name in names:
            child = _serialise(value[name], where + "." + name)
            parts.append(_escape(name) + ":" + child)
        return "{" + ",".join(parts) + "}"
    raise ValueError("unsupported value at " + where)


def handle(payload):
    if "document" not in payload:
        raise ValueError("send the value to canonicalise as 'document'")
    document = payload.get("document")
    canonical = _serialise(document, "")
    raw = canonical.encode("utf-8")
    return {
        "canonical": canonical,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sha384": hashlib.sha384(raw).hexdigest(),
        "byte_length": len(raw),
        "algorithm": "JCS (RFC 8785), integer-only numbers",
    }
