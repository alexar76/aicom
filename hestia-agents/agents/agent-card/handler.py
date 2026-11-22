"""agent.card.verify@v1: is this A2A Agent Card well-formed, and do its JWS signatures verify?

Give `url`: a domain (the card is read from https://<domain>/.well-known/agent-card.json, then the
pre-1.0 /.well-known/agent.json) or the card's https URL. Or give `card`, the card itself, to check
it with no fetch. For signatures, the keys come from `keys` (a JWKS you trust), or from the JWKS at
a signature's `jku` when that is on the card's host or is the `jwks` URL you name, or from the
signature's own `kid` when it is a DID: did:web (its document on the card's host), did:key or
did:jwk. A key embedded in the header is used, and said to be self-asserted. With none of those, the
card host's /.well-known/jwks.json is read. `algorithms` limits the accepted JWS algorithms
(default: ES256, ES384, ES256K, EdDSA, RS256-512, PS256-512; never "none" or HMAC).

What it checks (A2A specification 1.0, sections 4.4, 8.2-8.4; 0.3 cards are read too):
  - the required fields for the card's version, their types, and the interfaces: each URL https, a
    binding name the specification defines, the preferred one first; which interface hosts are the
    card's own host;
  - each signature (RFC 7515, detached; RFC 7797 b64:false read too): the headers (protected and
    unprotected disjoint, alg protected and allowed, no crit but b64), the key (by kid, kty and
    curve match alg, use is sig when given), then the signature over BASE64URL(header) "."
    BASE64URL(payload), where the payload is the card without `signatures`, canonicalised with RFC
    8785 (JCS). Signers prepare that card in three ways seen in practice: as served; with empty
    strings, lists and objects removed (a2a-python's signing.py); and with false and zero values
    also removed (the specification's default-value rule as pydantic's exclude_defaults applies it);
    and some sign Python's json.dumps with sorted keys, which escapes non-ASCII. Each is tried, and
    the answer says which one the signature covers. A signature can only verify over the bytes its
    signer signed, so trying variants cannot make a forgery pass.

Verdict signed_verified needs a signature that verifies with a key tied to the card's host (a JWKS
or did:web document there, or keys you gave or named); signed_self_asserted means only keys the
signature carries itself (did:key, did:jwk, an embedded jwk) verify: the card is intact, but nothing
ties it to the domain. The interfaces are listed, not called.
"""

import base64
import hashlib
import json
from decimal import Decimal

ALGORITHMS = (
    "ES256",
    "ES384",
    "ES256K",
    "EdDSA",
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
)
HASHES = {"256": "sha256", "384": "sha384", "512": "sha512"}
BINDINGS = ("JSONRPC", "GRPC", "HTTP+JSON")
REQUIRED_V1 = {
    "name": str,
    "description": str,
    "supportedInterfaces": list,
    "version": str,
    "capabilities": dict,
    "defaultInputModes": list,
    "defaultOutputModes": list,
    "skills": list,
}
REQUIRED_V03 = {
    "name": str,
    "description": str,
    "url": str,
    "version": str,
    "capabilities": dict,
    "defaultInputModes": list,
    "defaultOutputModes": list,
    "skills": list,
}
MAX_FETCHES = 6
MAX_SIGNATURES = 8
MAX_DEPTH = 64


class _Budget(Exception):
    """The call has used the six requests the hearth allows."""


class _Bad(ValueError):
    """One signature or key cannot be read; that signature fails, the call goes on."""


# ------------------------------------------------------------------ base64url, hosts


def b64url_decode(text, where):
    if not isinstance(text, str) or not text:
        raise _Bad(where + " is not a base64url string")
    if any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=" for c in text
    ):
        raise _Bad(where + " is not base64url")
    t = text.rstrip("=")
    try:
        return base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))
    except ValueError:
        raise _Bad(where + " is not base64url") from None


def b64url(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _host(url):
    text = str(url or "").strip()
    if not text.lower().startswith("https://"):
        return None
    rest = text[8:].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in rest:
        return None
    host = rest.lower().rstrip(".")
    if host.endswith(":443"):
        host = host[:-4]
    return host or None


# ------------------------------------------------------------------ RFC 8785


_SHORT = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _escape(text):
    out = ['"']
    for char in text:
        point = ord(char)
        short = _SHORT.get(point)
        if short is not None:
            out.append(short)
        elif point < 0x20:
            out.append("\\u" + format(point, "04x"))
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _number(value):
    """ECMAScript Number::toString for a finite double (RFC 8785 3.2.2.3)."""
    if value != value or value in (float("inf"), float("-inf")):
        raise _Bad("JSON has no NaN or Infinity")
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    digits_tuple = Decimal(repr(abs(value))).normalize().as_tuple()
    digits = "".join(str(d) for d in digits_tuple.digits)
    k = len(digits)
    n = k + digits_tuple.exponent
    if k <= n <= 21:
        text = digits + "0" * (n - k)
    elif 0 < n <= 21:
        text = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        text = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        text = (
            digits[0]
            + ("." + digits[1:] if k > 1 else "")
            + "e"
            + ("+" if e > 0 else "-")
            + str(abs(e))
        )
    return sign + text


def jcs(value, depth=0):
    if depth > MAX_DEPTH:
        raise _Bad("the card nests deeper than " + str(MAX_DEPTH) + " levels")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) > 2**53 - 1:
            raise _Bad(
                "an integer in the card is beyond 2^53-1, which JCS cannot represent exactly"
            )
        return str(value)
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, str):
        return _escape(value)
    if isinstance(value, list):
        return "[" + ",".join(jcs(v, depth + 1) for v in value) + "]"
    if isinstance(value, dict):
        names = sorted(value, key=lambda name: name.encode("utf-16-be"))
        return "{" + ",".join(_escape(n) + ":" + jcs(value[n], depth + 1) for n in names) + "}"
    raise _Bad("the card holds a value JSON cannot")


def _clean(value, drop_defaults, depth=0):
    """a2a-python's _clean_empty (empty strings, lists, objects go), and with drop_defaults also
    false and zero, as a default-dropping serializer leaves the card. None means: drop it."""
    if depth > MAX_DEPTH:
        raise _Bad("the card nests deeper than " + str(MAX_DEPTH) + " levels")
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            c = _clean(v, drop_defaults, depth + 1)
            if c is not None:
                out[k] = c
        return out or None
    if isinstance(value, list):
        out = [c for c in (_clean(v, drop_defaults, depth + 1) for v in value) if c is not None]
        return out or None
    if value is None or (isinstance(value, str) and not value):
        return None
    if drop_defaults and (
        value is False
        or (isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0)
    ):
        return None
    return value


def payload_variants(card):
    """The forms signers give the card before signing, each serialised once. Python's json.dumps
    with sorted keys escapes non-ASCII characters, which RFC 8785 does not: some signers use it."""
    body = {k: v for k, v in card.items() if k != "signatures"}
    seen, out = set(), []
    forms = (
        ("as served", jcs(body)),
        ("empty values removed (a2a-python signing.py)", jcs(_clean(body, False) or {})),
        ("empty and default values removed", jcs(_clean(body, True) or {})),
        (
            "keys sorted, non-ASCII escaped (Python json.dumps)",
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        ),
    )
    for name, text in forms:
        if text not in seen:
            seen.add(text)
            out.append((name, text.encode("utf-8")))
    return out


# ------------------------------------------------------------------ Ed25519 (RFC 8032)

_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)
_IDENTITY = (0, 1, 1, 0)


def _recover_x(y, sign):
    if y >= _Q:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _Q - 2, _Q) % _Q
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_Q + 3) // 8, _Q)
    if (x * x - x2) % _Q:
        x = x * _I % _Q
    if (x * x - x2) % _Q:
        return None
    if x & 1 != sign:
        x = _Q - x
    return x


def _decode(raw):
    y = int.from_bytes(raw, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _Q)


_BY = 4 * pow(5, _Q - 2, _Q) % _Q
_B = (_recover_x(_BY, 0), _BY, 1, _recover_x(_BY, 0) * _BY % _Q)


def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _Q
    b = (p[1] + p[0]) * (q[1] + q[0]) % _Q
    c = 2 * p[3] * q[3] * _D % _Q
    d = 2 * p[2] * q[2] % _Q
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _Q, g * h % _Q, f * g % _Q, e * h % _Q)


def _double(p):
    a = p[0] * p[0] % _Q
    b = p[1] * p[1] % _Q
    c = 2 * p[2] * p[2] % _Q
    h = a + b
    e = h - (p[0] + p[1]) * (p[0] + p[1])
    g = a - b
    f = c + g
    return (e * f % _Q, g * h % _Q, f * g % _Q, e * h % _Q)


def _same(p, q):
    return (p[0] * q[2] - q[0] * p[2]) % _Q == 0 and (p[1] * q[2] - q[1] * p[2]) % _Q == 0


def _two_mul(k1, p1, k2, p2):
    both = _add(p1, p2)
    acc = _IDENTITY
    for i in range(max(k1.bit_length(), k2.bit_length()) - 1, -1, -1):
        acc = _double(acc)
        b1, b2 = (k1 >> i) & 1, (k2 >> i) & 1
        if b1 and b2:
            acc = _add(acc, both)
        elif b1:
            acc = _add(acc, p1)
        elif b2:
            acc = _add(acc, p2)
    return acc


def _ed25519(public, message, signature):
    if len(signature) != 64:
        return False, "an Ed25519 signature is 64 bytes, this one is " + str(len(signature))
    a = _decode(public)
    if a is None:
        return False, "the key is not a valid Ed25519 point"
    small = a
    for _ in range(3):
        small = _double(small)
    if _same(small, _IDENTITY):
        return False, "the key has small order: it would verify forged signatures"
    r = _decode(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if r is None or s >= _L:
        return False, "the signature is not canonical (R not a point, or S >= L)"
    k = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    neg_a = ((-a[0]) % _Q, a[1], a[2], (-a[3]) % _Q)
    if _same(_two_mul(s, _B, k, neg_a), r):
        return True, "verifies"
    return False, "does not verify with this key"


# ------------------------------------------------------------------ ECDSA and RSA

CURVES = {
    "P-256": {
        "p": 2**256 - 2**224 + 2**192 + 2**96 - 1,
        "b": 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B,
        "g": (
            0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
            0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
        ),
        "n": 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551,
        "size": 32,
        "alg": "ES256",
        "a": -3,
        "hash": "sha256",
    },
    "P-384": {
        "p": 2**384 - 2**128 - 2**96 + 2**32 - 1,
        "b": int(
            "B3312FA7E23EE7E4988E056BE3F82D19181D9C6EFE8141120314088F5013875A"
            "C656398D8A2ED19D2A85C8EDD3EC2AEF",
            16,
        ),
        "g": (
            int(
                "AA87CA22BE8B05378EB1C71EF320AD746E1D3B628BA79B9859F741E082542A38"
                "5502F25DBF55296C3A545E3872760AB7",
                16,
            ),
            int(
                "3617DE4A96262C6F5D9E98BF9292DC29F8F41DBD289A147CE9DA3113B5F0B8C0"
                "0A60B1CE1D7E819D7A431D7C90EA0E5F",
                16,
            ),
        ),
        "n": int(
            "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFC7634D81F4372DDF"
            "581A0DB248B0A77AECEC196ACCC52973",
            16,
        ),
        "size": 48,
        "alg": "ES384",
        "a": -3,
        "hash": "sha384",
    },
    "secp256k1": {
        "p": 2**256 - 2**32 - 977,
        "b": 7,
        "g": (
            0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
            0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
        ),
        "n": 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141,
        "size": 32,
        "alg": "ES256K",
        "a": 0,
        "hash": "sha256",
    },
}


def _jdouble(pt, p, a=-3):
    x, y, z = pt
    if not y or not z:
        return (0, 1, 0)
    ysq = y * y % p
    s = 4 * x * ysq % p
    zsq = z * z % p
    m = (3 * x * x + a * zsq * zsq) % p
    nx = (m * m - 2 * s) % p
    return (nx, (m * (s - nx) - 8 * ysq * ysq) % p, 2 * y * z % p)


def _jadd(p1, p2, p, a=-3):
    if not p1[2]:
        return p2
    if not p2[2]:
        return p1
    z1s, z2s = p1[2] * p1[2] % p, p2[2] * p2[2] % p
    u1, u2 = p1[0] * z2s % p, p2[0] * z1s % p
    s1, s2 = p1[1] * z2s * p2[2] % p, p2[1] * z1s * p1[2] % p
    if u1 == u2:
        return _jdouble(p1, p, a) if s1 == s2 else (0, 1, 0)
    h, r = (u2 - u1) % p, (s2 - s1) % p
    h2 = h * h % p
    h3 = h * h2 % p
    v = u1 * h2 % p
    nx = (r * r - h3 - 2 * v) % p
    return (nx, (r * (v - nx) - s1 * h3) % p, h * p1[2] * p2[2] % p)


def _ecdsa(curve, x, y, message, signature):
    c = CURVES[curve]
    p, n, size, a = c["p"], c["n"], c["size"], c["a"]
    if len(signature) != 2 * size:
        return False, c["alg"] + " takes r||s of " + str(
            2 * size
        ) + " bytes, this signature is " + str(len(signature))
    if not (0 <= x < p and 0 <= y < p and (y * y - x * x * x - a * x - c["b"]) % p == 0):
        return False, "the key is not a point on " + curve
    r, s = int.from_bytes(signature[:size], "big"), int.from_bytes(signature[size:], "big")
    if not (0 < r < n and 0 < s < n):
        return False, "r or s is out of range"
    e = int.from_bytes(hashlib.new(c["hash"], message).digest(), "big")
    w = pow(s, n - 2, n)
    u1, u2 = e * w % n, r * w % n
    g, q = (c["g"][0], c["g"][1], 1), (x, y, 1)
    both = _jadd(g, q, p, a)
    acc = (0, 1, 0)
    for i in range(max(u1.bit_length(), u2.bit_length()) - 1, -1, -1):
        acc = _jdouble(acc, p, a)
        b1, b2 = (u1 >> i) & 1, (u2 >> i) & 1
        if b1 and b2:
            acc = _jadd(acc, both, p, a)
        elif b1:
            acc = _jadd(acc, g, p, a)
        elif b2:
            acc = _jadd(acc, q, p, a)
    if not acc[2]:
        return False, c["alg"] + " does not verify"
    zinv = pow(acc[2], p - 2, p)
    if acc[0] * zinv * zinv % p % n == r:
        return True, c["alg"] + " verifies"
    return False, c["alg"] + " does not verify with this key"


DIGEST_INFO = {
    "sha256": bytes.fromhex("3031300d060960864801650304020105000420"),
    "sha384": bytes.fromhex("3041300d060960864801650304020205000430"),
    "sha512": bytes.fromhex("3051300d060960864801650304020305000440"),
}


def _mgf1(seed, length, name):
    out, counter = b"", 0
    while len(out) < length:
        out += hashlib.new(name, seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:length]


def _rsa(n, e, alg, message, signature):
    name = HASHES[alg[2:]]
    k = (n.bit_length() + 7) // 8
    if n.bit_length() < 2048:
        return False, "the RSA key has " + str(
            n.bit_length()
        ) + " bits; JWS requires at least 2048 (RFC 7518 3.3)"
    if len(signature) != k:
        return False, "the signature is " + str(len(signature)) + " bytes, the key needs " + str(k)
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False, "the signature is not smaller than the modulus"
    m = pow(s, e, n)
    digest = hashlib.new(name, message).digest()
    if alg.startswith("RS"):
        t = DIGEST_INFO[name] + digest
        expected = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
        ok = m.to_bytes(k, "big") == expected
        return ok, alg + (" verifies" if ok else " does not verify with this key")
    h_len = len(digest)
    em_bits = n.bit_length() - 1
    em_len = (em_bits + 7) // 8
    if m.bit_length() > em_bits:
        return False, alg + " does not verify (the encoded message is too long)"
    em = m.to_bytes(em_len, "big")
    if em_len < 2 * h_len + 2 or em[-1] != 0xBC:
        return False, alg + " does not verify (no 0xbc trailer)"
    masked, h = em[: em_len - h_len - 1], em[em_len - h_len - 1 : -1]
    zero_bits = 8 * em_len - em_bits
    if zero_bits and masked[0] >> (8 - zero_bits):
        return False, alg + " does not verify (leading bits set)"
    db = bytearray(a ^ b for a, b in zip(masked, _mgf1(h, len(masked), name), strict=True))
    if zero_bits:
        db[0] &= 0xFF >> zero_bits
    pad = em_len - 2 * h_len - 2
    if any(db[:pad]) or db[pad] != 0x01:
        return False, alg + " does not verify (bad padding, or a salt other than the hash length)"
    salt = bytes(db[-h_len:])
    ok = hashlib.new(name, b"\x00" * 8 + digest + salt).digest() == h
    return ok, alg + (" verifies" if ok else " does not verify with this key")


# ------------------------------------------------------------------ JWK


def parse_jwk(jwk, where):
    if not isinstance(jwk, dict):
        raise _Bad(where + " is not a JWK object")
    if any(k in jwk for k in ("d", "p", "q", "dp", "dq", "qi", "k")):
        raise _Bad(where + " carries private or symmetric key material; give public keys only")
    kty = jwk.get("kty")
    if kty == "EC" and jwk.get("crv") in CURVES:
        size = CURVES[jwk["crv"]]["size"]
        x, y = b64url_decode(jwk.get("x"), where + ".x"), b64url_decode(jwk.get("y"), where + ".y")
        if len(x) != size or len(y) != size:
            raise _Bad(where + ": x and y of a " + jwk["crv"] + " key are " + str(size) + " bytes")
        return {
            "type": "EC",
            "curve": jwk["crv"],
            "x": int.from_bytes(x, "big"),
            "y": int.from_bytes(y, "big"),
            "algs": (CURVES[jwk["crv"]]["alg"],),
        }
    if kty == "OKP" and jwk.get("crv") == "Ed25519":
        raw = b64url_decode(jwk.get("x"), where + ".x")
        if len(raw) != 32:
            raise _Bad(where + ": an Ed25519 key is 32 bytes")
        return {"type": "OKP", "raw": raw, "algs": ("EdDSA",)}
    if kty == "RSA":
        n = int.from_bytes(b64url_decode(jwk.get("n"), where + ".n"), "big")
        e = int.from_bytes(b64url_decode(jwk.get("e"), where + ".e"), "big")
        return {
            "type": "RSA",
            "n": n,
            "e": e,
            "algs": ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512"),
        }
    raise _Bad(where + ": kty must be EC (P-256, P-384), OKP (Ed25519) or RSA")


def jwk_thumbprint(jwk):
    """RFC 7638 SHA-256 thumbprint, base64url."""
    members = {
        "EC": ("crv", "kty", "x", "y"),
        "OKP": ("crv", "kty", "x"),
        "RSA": ("e", "kty", "n"),
    }.get(jwk.get("kty"))
    if not members:
        return None
    return b64url(hashlib.sha256(jcs({m: jwk.get(m) for m in members}).encode()).digest())


def verify_jws(key, alg, signing_input, signature):
    if alg not in key["algs"]:
        return False, "the key (" + key["type"] + ") cannot make " + alg + " signatures"
    if alg == "EdDSA":
        ok, why = _ed25519(key["raw"], signing_input, signature)
        return ok, "EdDSA (Ed25519) " + ("verifies" if ok else why)
    if alg.startswith("ES"):
        return _ecdsa(key["curve"], key["x"], key["y"], signing_input, signature)
    return _rsa(key["n"], key["e"], alg, signing_input, signature)


# ------------------------------------------------------------------ the card


def _get(state, url):
    if state["fetches"] >= MAX_FETCHES:
        raise _Budget()
    state["fetches"] += 1
    return fetch(url, headers={"accept": "application/json"})  # noqa: F821 — the sandbox provides fetch()


def _json(reply):
    if not reply.ok:
        return None
    try:
        return json.loads(reply.text)
    except ValueError:
        return None


def check_card(card, host):
    """Structure and interfaces. Returns (version, problems, warnings, interfaces)."""
    problems, warnings, interfaces = [], [], []
    v1 = isinstance(card.get("supportedInterfaces"), list)
    version = "1.0" if v1 else str(card.get("protocolVersion") or "0.3")
    required = REQUIRED_V1 if v1 else REQUIRED_V03
    for name, kind in required.items():
        if name not in card:
            problems.append("missing required field " + name)
        elif not isinstance(card[name], kind):
            problems.append(
                name + " must be " + {str: "a string", list: "a list", dict: "an object"}[kind]
            )
    if v1:
        rows = card.get("supportedInterfaces") or []
        for i, item in enumerate(rows[:16]):
            if not isinstance(item, dict):
                problems.append("supportedInterfaces[" + str(i) + "] is not an object")
                continue
            interfaces.append(
                {
                    "url": item.get("url"),
                    "binding": item.get("protocolBinding"),
                    "protocol_version": item.get("protocolVersion"),
                    "preferred": i == 0,
                }
            )
        if not rows:
            problems.append("supportedInterfaces is empty: a client has nothing to call")
    else:
        if isinstance(card.get("url"), str):
            interfaces.append(
                {
                    "url": card["url"],
                    "binding": card.get("preferredTransport") or "JSONRPC",
                    "protocol_version": card.get("protocolVersion"),
                    "preferred": True,
                }
            )
        for item in (card.get("additionalInterfaces") or [])[:16]:
            if isinstance(item, dict):
                interfaces.append(
                    {
                        "url": item.get("url"),
                        "binding": item.get("transport"),
                        "protocol_version": card.get("protocolVersion"),
                        "preferred": False,
                    }
                )
        if "protocolVersion" not in card:
            warnings.append("no protocolVersion: read as an A2A 0.3 card")
    for row in interfaces:
        row_host = _host(row["url"])
        if row_host is None:
            problems.append(
                "interface URL " + str(row["url"])[:120] + " is not an absolute https URL"
            )
        else:
            row["on_card_host"] = host is not None and (
                row_host == host or row_host.endswith("." + host)
            )
        if row["binding"] not in BINDINGS:
            warnings.append(
                "interface binding " + str(row["binding"]) + " is not one of " + ", ".join(BINDINGS)
            )
    for i, skill in enumerate(
        (card.get("skills") or [])[:256] if isinstance(card.get("skills"), list) else []
    ):
        if not isinstance(skill, dict) or not all(
            isinstance(skill.get(k), str) and skill.get(k) for k in ("id", "name", "description")
        ):
            problems.append("skills[" + str(i) + "] needs id, name and description")
            break
    if (
        not card.get("securitySchemes")
        and not card.get("security")
        and not card.get("securityRequirements")
    ):
        warnings.append(
            "declares no security scheme: the interfaces take unauthenticated calls, or say "
            "nothing about how they authenticate"
        )
    return version, problems, warnings, interfaces


# ------------------------------------------------------------------ keys that are not in a JWKS

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# multicodec prefixes (unsigned varint) of the public keys did:key carries
MULTICODEC = {
    b"\xed\x01": ("OKP", "Ed25519"),
    b"\x80\x24": ("EC", "P-256"),
    b"\x81\x24": ("EC", "P-384"),
    b"\xe7\x01": ("EC", "secp256k1"),
}


def base58btc(text):
    number = 0
    for char in text:
        index = _B58.find(char)
        if index < 0:
            raise _Bad("not base58btc")
        number = number * 58 + index
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + raw


def _decompress(curve, raw):
    c = CURVES[curve]
    p = c["p"]
    x = int.from_bytes(raw[1:], "big")
    rhs = (pow(x, 3, p) + c["a"] * x + c["b"]) % p
    y = pow(rhs, (p + 1) // 4, p)  # p = 3 mod 4 for all three curves
    if y * y % p != rhs:
        raise _Bad("the compressed key is not a point on " + curve)
    if y & 1 != raw[0] & 1:
        y = p - y
    return x, y


def multikey_jwk(text):
    """A multibase (z, base58btc) multicodec public key as a JWK."""
    if not text.startswith("z"):
        raise _Bad("only base58btc (z...) multibase keys are read")
    raw = base58btc(text[1:])
    for prefix, (kty, crv) in MULTICODEC.items():
        if raw.startswith(prefix):
            key = raw[len(prefix) :]
            if kty == "OKP":
                if len(key) != 32:
                    raise _Bad("an Ed25519 multikey is 32 bytes")
                return {"kty": "OKP", "crv": crv, "x": b64url(key)}
            size = CURVES[crv]["size"]
            if len(key) == 1 + size and key[0] in (2, 3):
                x, y = _decompress(crv, key)
            elif len(key) == 1 + 2 * size and key[0] == 4:
                x, y = (
                    int.from_bytes(key[1 : 1 + size], "big"),
                    int.from_bytes(key[1 + size :], "big"),
                )
            else:
                raise _Bad("a " + crv + " multikey is a compressed or uncompressed point")
            return {
                "kty": "EC",
                "crv": crv,
                "x": b64url(x.to_bytes(size, "big")),
                "y": b64url(y.to_bytes(size, "big")),
            }
    raise _Bad("the multikey's type is not Ed25519, P-256, P-384 or secp256k1")


def did_web_url(did):
    """did:web:host[:path...] -> the https URL of its DID document (did:web method, section 3.2)."""
    parts = did[len("did:web:") :].split("#", 1)[0].split(":")
    host = parts[0].replace("%3A", ":").lower()
    if not parts[0] or "/" in host or ":" in host:
        raise _Bad("did:web names no plain host (ports are not read)")
    path = "/".join(parts[1:])
    return "https://" + host + ("/" + path + "/did.json" if path else "/.well-known/did.json"), host


def did_document_key(doc, kid):
    """The verification method `kid` (absolute, or #fragment relative to the document) as a JWK."""
    if not isinstance(doc, dict):
        raise _Bad("the DID document is not a JSON object")
    did, frag = kid.split("#", 1) if "#" in kid else (kid, "")
    if doc.get("id") != did:
        raise _Bad("the DID document's id is " + str(doc.get("id"))[:80] + ", not " + did)
    for method in (doc.get("verificationMethod") or [])[:32]:
        if not isinstance(method, dict):
            continue
        if method.get("id") in (kid, "#" + frag) and (
            not method.get("controller") or method["controller"] == did
        ):
            if isinstance(method.get("publicKeyJwk"), dict):
                return method["publicKeyJwk"]
            if isinstance(method.get("publicKeyMultibase"), str):
                return multikey_jwk(method["publicKeyMultibase"])
            raise _Bad("the verification method has no publicKeyJwk or publicKeyMultibase")
    raise _Bad("the DID document has no verification method " + kid)


# Where a signature's key came from, and what that says.
ANCHORED = {"given", "jwks_on_card_host", "named_jwks", "did_web_on_card_host", "conventional_jwks"}
SOURCE_TEXT = {
    "given": "the keys you gave",
    "jwks_on_card_host": "the JWKS at jku, on the card's host",
    "named_jwks": "the JWKS you named",
    "did_web_on_card_host": "the did:web document on the card's host",
    "conventional_jwks": "the JWKS at the card host's /.well-known/jwks.json (no jku given)",
    "did_key": "the key inside its did:key identifier: self-certifying, it says nothing "
    "about the domain",
    "did_jwk": "the key inside its did:jwk identifier: self-certifying, it says nothing "
    "about the domain",
    "embedded": "a key embedded in the protected header: self-asserted",
    "embedded_unprotected": "a key in the unprotected header: self-asserted and not "
    "integrity-protected",
}


# ------------------------------------------------------------------ the call


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: url (or card), optionally keys, jwks, algorithms")
    algorithms = payload.get("algorithms") or list(ALGORITHMS)
    if (
        not isinstance(algorithms, list)
        or not algorithms
        or any(a not in ALGORITHMS for a in algorithms)
    ):
        raise ValueError("algorithms must be a list drawn from " + ", ".join(ALGORITHMS))
    keys_in = payload.get("keys")
    if keys_in is not None and not (
        isinstance(keys_in, dict) and isinstance(keys_in.get("keys"), list)
    ):
        raise ValueError('keys must be a JWKS: {"keys": [JWK, ...]}')
    jwks_url = payload.get("jwks")
    if jwks_url is not None and _host(jwks_url) is None:
        raise ValueError("jwks must be an https URL")
    state = {"fetches": 0}
    out = {}
    card = payload.get("card")
    host = None
    pre_warnings = []
    if card is not None:
        if not isinstance(card, dict):
            raise ValueError("card must be the Agent Card JSON object")
        out["source"] = "given"
        host = _host(payload.get("url")) if payload.get("url") else None
    else:
        raw = str(payload.get("url") or "").strip()
        if not raw:
            raise ValueError("give url (a domain or the card's https URL) or card")
        if "://" in raw:
            host = _host(raw)
            if host is None:
                raise ValueError("url must be https, with no credentials")
            candidates = [raw]
        else:
            host = _host("https://" + raw)
            if host is None or "/" in raw or "." not in raw:
                raise ValueError("url must be a domain such as example.com or an https URL")
            candidates = [
                "https://" + host + "/.well-known/agent-card.json",
                "https://" + host + "/.well-known/agent.json",
            ]
        tried = []
        for url in candidates:
            reply = _get(state, url)
            tried.append({"url": url, "status": reply.status})
            doc = _json(reply)
            if isinstance(doc, dict):
                card = doc
                out["source"] = url
                if url.endswith("/agent.json"):
                    pre_warnings.append(
                        "served at /.well-known/agent.json, the pre-1.0 name; A2A 1.0 "
                        "reads /.well-known/agent-card.json"
                    )
                break
            if reply.ok:
                tried[-1]["problem"] = "not a JSON object"
        out["fetched"] = tried
        if card is None:
            out.update(verdict="not_found", fetches=state["fetches"])
            return out
    out["card_host"] = host
    out["name"] = card.get("name")
    version, problems, warnings, interfaces = check_card(card, host)
    warnings = pre_warnings + warnings
    out.update(protocol_version=version, interfaces=interfaces)
    try:
        variants = payload_variants(card)
    except _Bad as exc:
        variants = []
        problems.append(str(exc))
    if variants:
        out["payload_sha256"] = hashlib.sha256(variants[0][1]).hexdigest()
    named_host = _host(jwks_url) if jwks_url else None
    documents = {}

    def read(url):
        if url not in documents:
            documents[url] = _json(_get(state, url))
        return documents[url]

    def find_key(header, unprotected, row):
        """(JWK, source) for one signature, or raises _Bad saying why there is none."""
        kid = header.get("kid", unprotected.get("kid"))
        if keys_in is not None:
            return _by_kid(keys_in, kid), "given"
        kid_text = str(kid or "")
        if kid_text.startswith("did:key:"):
            fragment = kid_text[len("did:key:") :].split("#", 1)
            if len(fragment) == 2 and fragment[1] != fragment[0]:
                raise _Bad("a did:key fragment must repeat the key")
            return multikey_jwk(fragment[0]), "did_key"
        if kid_text.startswith("did:jwk:"):
            try:
                jwk = json.loads(
                    b64url_decode(kid_text[len("did:jwk:") :].split("#", 1)[0], "did:jwk")
                )
            except ValueError:
                raise _Bad("did:jwk does not hold a JSON JWK") from None
            return jwk, "did_jwk"
        if kid_text.startswith("did:web:"):
            url, did_host = did_web_url(kid_text)
            row["did_document"] = url
            if did_host != host and did_host != named_host:
                raise _Bad(
                    "did:web names "
                    + did_host
                    + ", not the card's host; name its document as jwks to let the agent read it"
                )
            return did_document_key(read(url), kid_text), (
                "did_web_on_card_host" if did_host == host else "named_jwks"
            )
        jku = header.get("jku") or unprotected.get("jku")
        if jku:
            if "jku" not in header:
                row["jku_unprotected"] = True
            jku_host = _host(jku)
            if jku_host is None:
                raise _Bad("jku is not an https URL")
            if jku_host == host or jku == jwks_url:
                return _by_kid(read(jku), kid), (
                    "jwks_on_card_host" if jku_host == host else "named_jwks"
                )
            row["next"] = {"jwks": jku}
            raise _Bad(
                "jku is on "
                + jku_host
                + ", not the card's host; pass it as jwks to let the agent read it"
            )
        if jwks_url:
            return _by_kid(read(jwks_url), kid), "named_jwks"
        if isinstance(header.get("jwk"), dict):
            return header["jwk"], "embedded"
        if isinstance(unprotected.get("jwk"), dict):
            return unprotected["jwk"], "embedded_unprotected"
        if host:
            return _by_kid(
                read("https://" + host + "/.well-known/jwks.json"), kid
            ), "conventional_jwks"
        raise _Bad("no key: no jku, no did, no embedded jwk, and no keys or jwks given")

    sigs = card.get("signatures")
    results = []
    if sigs is not None and not isinstance(sigs, list):
        problems.append("signatures must be a list")
        sigs = []
    for i, sig in enumerate((sigs or [])[:MAX_SIGNATURES]):
        row = {"index": i}
        results.append(row)
        try:
            if not isinstance(sig, dict):
                raise _Bad("not an object with protected and signature")
            header_raw = b64url_decode(sig.get("protected"), "protected")
            try:
                header = json.loads(header_raw)
            except ValueError:
                raise _Bad("the protected header is not JSON") from None
            if not isinstance(header, dict):
                raise _Bad("the protected header is not a JSON object")
            unprotected = sig.get("header") if isinstance(sig.get("header"), dict) else {}
            both = sorted(set(header) & set(unprotected))
            if both:
                raise _Bad(
                    "the protected and unprotected headers both carry "
                    + ", ".join(both)
                    + "; RFC 7515 section 7.2.1 requires them disjoint"
                )
            alg = header.get("alg")
            row.update(
                alg=alg, kid=header.get("kid", unprotected.get("kid")), typ=header.get("typ")
            )
            if alg is None and "alg" in unprotected:
                raise _Bad("alg is in the unprotected header; A2A requires it protected")
            if alg not in algorithms:
                raise _Bad("alg " + str(alg) + " is not accepted (" + ", ".join(algorithms) + ")")
            crit = header.get("crit")
            unencoded = False
            if crit is not None:
                if crit != ["b64"] or header.get("b64") is not False:
                    raise _Bad(
                        "crit names "
                        + json.dumps(crit)[:80]
                        + "; only RFC 7797 b64:false is implemented"
                    )
                unencoded = True
                row["unencoded_payload"] = True
            elif "b64" in header:
                raise _Bad('b64 without crit ["b64"] is invalid (RFC 7797 section 6)')
            signature = b64url_decode(sig.get("signature"), "signature")
            jwk, source = find_key(header, unprotected, row)
            if not isinstance(jwk, dict):
                raise _Bad("the key is not a JWK object")
            if jwk.get("use") not in (None, "sig"):
                raise _Bad("the key's use is " + str(jwk.get("use")) + ", not sig")
            if jwk.get("alg") not in (None, alg):
                raise _Bad(
                    "the key is for " + str(jwk.get("alg")) + ", the signature says " + str(alg)
                )
            key = parse_jwk(jwk, "the key")
            row["key_source"] = source
            row["key"] = SOURCE_TEXT[source]
            row["key_thumbprint"] = jwk_thumbprint(jwk)
            prefix = sig["protected"].encode("ascii") + b"."
            verified, why = False, ""
            for name, body in variants:
                signing_input = prefix + (body if unencoded else b64url(body).encode("ascii"))
                ok, why = verify_jws(key, alg, signing_input, signature)
                if ok:
                    verified = True
                    row["payload"] = name
                    break
            row["verified"] = verified
            row["anchored"] = verified and source in ANCHORED
            row["detail"] = (
                why
                if verified
                else why + " over any of the " + str(len(variants)) + " payload forms"
            )
        except _Budget:
            row.update(verified=False, detail="the call's six requests were used up")
        except _Bad as exc:
            row.update(verified=False, detail=str(exc))
        except Exception as exc:  # the hearth refused a request; never the fetch signal
            row.update(verified=False, detail="request failed: " + str(exc)[:160])
    out["signatures"] = results
    out["problems"] = problems
    out["warnings"] = warnings
    if problems:
        out["verdict"] = "malformed"
    elif not results:
        out["verdict"] = "unsigned"
    elif any(r.get("anchored") for r in results):
        out["verdict"] = "signed_verified"
    elif any(r.get("verified") for r in results):
        out["verdict"] = "signed_self_asserted"
    else:
        out["verdict"] = "signature_failed"
    out["fetches"] = state["fetches"]
    return out


def _by_kid(jwks, kid):
    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise _Bad("no JWKS there (not a JSON object with keys)")
    matches = [k for k in jwks["keys"][:64] if isinstance(k, dict) and k.get("kid") == kid]
    if len(matches) != 1:
        raise _Bad(
            ("no key" if not matches else "more than one key")
            + " with kid "
            + str(kid)[:80]
            + " in the JWKS"
        )
    return matches[0]
