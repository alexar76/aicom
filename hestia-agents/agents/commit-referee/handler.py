"""Commit-reveal referee: did the revealed value match what was promised?

Checking a hash is the easy half. The half that decides disputes is whether the
commitment scheme lets the committer change their mind afterwards.

sha256(salt || value) is malleable when the salt has no fixed length: the pair
("ab", "cdef") and the pair ("abc", "def") hash to the same commitment, so a
committer can reveal whichever of the two suits them once the outcome is known.
A length prefix removes the ambiguity. This referee verifies the hash AND says
plainly whether the scheme it was handed can be gamed that way.
"""

import hashlib

ALGORITHMS = ("sha256", "sha384", "sha512")
LAYOUTS = ("value", "concat", "lenprefix", "separator")
MAX_INPUT = 200000
BRUTE_FORCE_HINT = 16  # bytes of committed material below which guessing is cheap


def _digest(algorithm, raw):
    if algorithm == "sha256":
        return hashlib.sha256(raw).hexdigest()
    if algorithm == "sha384":
        return hashlib.sha384(raw).hexdigest()
    return hashlib.sha512(raw).hexdigest()


def _decode(text, encoding, field):
    if not isinstance(text, str):
        raise ValueError(field + " must be a string")
    if len(text) > MAX_INPUT:
        raise ValueError(field + " is too long")
    if encoding == "hex":
        try:
            return bytes.fromhex(text)
        except ValueError:
            raise ValueError(field + " is not valid hex") from None
    if encoding == "utf8":
        return text.encode("utf-8")
    raise ValueError(field + "_encoding must be utf8 or hex")


def _preimage(layout, salt, value, separator):
    if layout == "value":
        return value
    if layout == "concat":
        return salt + value
    if layout == "lenprefix":
        return len(salt).to_bytes(8, "big") + salt + value
    return salt + separator + value


def handle(payload):
    algorithm = payload.get("algorithm", "sha256")
    if algorithm not in ALGORITHMS:
        raise ValueError("algorithm must be one of " + ", ".join(ALGORITHMS))
    layout = payload.get("layout", "lenprefix")
    if layout not in LAYOUTS:
        raise ValueError("layout must be one of " + ", ".join(LAYOUTS))

    commitment = payload.get("commitment")
    if not isinstance(commitment, str) or not commitment:
        raise ValueError("commitment must be a hex string")
    commitment = commitment.strip().lower()

    value = _decode(
        payload.get("value", ""), payload.get("value_encoding", "utf8"), "value"
    )
    salt = b""
    if layout != "value":
        if "salt" not in payload:
            raise ValueError("layout '" + layout + "' needs a salt")
        salt = _decode(
            payload.get("salt", ""), payload.get("salt_encoding", "utf8"), "salt"
        )
    separator = _decode(
        payload.get("separator", ":"), payload.get("separator_encoding", "utf8"), "separator"
    )

    computed = _digest(algorithm, _preimage(layout, salt, value, separator))
    # The commitment is public, so there is no secret for a timing side channel
    # to leak here and a plain comparison is the honest choice.
    valid = computed == commitment

    findings = []
    if layout == "concat":
        findings.append({
            "code": "malleable_layout",
            "severity": "high",
            "detail": (
                "salt||value with a variable-length salt is ambiguous: another "
                "salt/value split produces this same commitment, so the committer "
                "can still choose. Use layout 'lenprefix'."
            ),
        })
    if layout == "separator" and separator and separator in salt:
        findings.append({
            "code": "separator_in_salt",
            "severity": "high",
            "detail": (
                "the separator also occurs inside the salt, which reintroduces the "
                "ambiguity the separator was meant to remove. Use layout 'lenprefix'."
            ),
        })
    if layout == "value":
        findings.append({
            "code": "unsalted",
            "severity": "medium",
            "detail": (
                "an unsalted commitment can be brute-forced whenever the set of "
                "possible values is small — a bid, a yes/no, a dice roll."
            ),
        })
    elif len(salt) < BRUTE_FORCE_HINT:
        findings.append({
            "code": "short_salt",
            "severity": "medium",
            "detail": "salt is under 16 bytes; use at least 16 random bytes.",
        })
    if len(commitment) != len(computed):
        findings.append({
            "code": "length_mismatch",
            "severity": "high",
            "detail": (
                "the commitment is not the length this algorithm produces, so it "
                "was probably made with a different hash."
            ),
        })

    return {
        "valid": valid,
        "computed": computed,
        "commitment": commitment,
        "algorithm": algorithm,
        "layout": layout,
        "salt_bytes": len(salt),
        "value_bytes": len(value),
        "binding": "non-malleable" if layout in ("lenprefix",) else "check findings",
        "findings": findings,
    }
