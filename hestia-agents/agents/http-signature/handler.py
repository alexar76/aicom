"""http.signature.verify@v1: does this HTTP message's RFC 9421 signature verify, and what does
it actually cover?

Give `message`: {"method", "url" (the full target URI), "headers", optionally "body"} for a
request, or {"status", "headers", optionally "body"} for a response (with `request` for the
components a response signature takes from its request, `;req`). `headers` is an object, a value
may be a list for a repeated field, or a list of [name, value] pairs. The Signature-Input and
Signature fields are read from the headers. Keys: `keys` {keyid: key} or one `key`. A key is a
JWK (OKP Ed25519, EC P-256 / P-384, RSA, oct), a PEM public key (SPKI, or PKCS#1 RSA), or
{"alg": ..., "key": base64} for a raw Ed25519 key or an HMAC secret.

Algorithms of the RFC 9421 registry: ed25519, ecdsa-p256-sha256, ecdsa-p384-sha384,
rsa-pss-sha512, rsa-v1_5-sha256, hmac-sha256. The algorithm comes from the signature's alg
parameter, else from the key (an RSA key needs `alg` somewhere, as the RFC asks).

Each signature gets its signature base, exactly as the verifier rebuilt it, the covered
components, the parameters, and whether it verifies. With `now` (Unix seconds) the created and
expires parameters are judged too (`max_age` seconds optionally). With a body, Content-Digest
(RFC 9530, sha-256 / sha-512) is checked against it. `required` lists components every signature
must cover. Not supported: `;sf` re-serialization and trailers (`;tr`); those signatures are
reported as errors, never as verified. Everything is in the request; no network.
"""

import base64
import hashlib
import hmac

ALGORITHMS = ("ed25519", "ecdsa-p256-sha256", "ecdsa-p384-sha384", "rsa-pss-sha512",
              "rsa-v1_5-sha256", "hmac-sha256")
JOSE = {"EdDSA": "ed25519", "Ed25519": "ed25519", "ES256": "ecdsa-p256-sha256",
        "ES384": "ecdsa-p384-sha384", "PS512": "rsa-pss-sha512", "RS256": "rsa-v1_5-sha256",
        "HS256": "hmac-sha256"}
MAX_HEADERS = 200
MAX_BODY = 192 * 1024
MAX_LABELS = 8
CLOCK_SKEW = 60
DEFAULT_PORTS = {"http": "80", "https": "443"}
_UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789*-._"


class _Bad(ValueError):
    """The signature base cannot be built, or the input is malformed for one signature."""


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
        return True, "Ed25519 verifies over the signature base"
    return False, "Ed25519 does not verify over the signature base with this key"


# ------------------------------------------------------------------ ECDSA (FIPS 186-5)

CURVES = {
    "P-256": {
        "p": 2**256 - 2**224 + 2**192 + 2**96 - 1,
        "b": 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B,
        "g": (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
              0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5),
        "n": 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551,
        "size": 32, "hash": "sha256", "alg": "ecdsa-p256-sha256",
    },
    "P-384": {
        "p": 2**384 - 2**128 - 2**96 + 2**32 - 1,
        "b": int("B3312FA7E23EE7E4988E056BE3F82D19181D9C6EFE8141120314088F5013875A"
                 "C656398D8A2ED19D2A85C8EDD3EC2AEF", 16),
        "g": (int("AA87CA22BE8B05378EB1C71EF320AD746E1D3B628BA79B9859F741E082542A38"
                  "5502F25DBF55296C3A545E3872760AB7", 16),
              int("3617DE4A96262C6F5D9E98BF9292DC29F8F41DBD289A147CE9DA3113B5F0B8C0"
                  "0A60B1CE1D7E819D7A431D7C90EA0E5F", 16)),
        "n": int("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFC7634D81F4372DDF"
                 "581A0DB248B0A77AECEC196ACCC52973", 16),
        "size": 48, "hash": "sha384", "alg": "ecdsa-p384-sha384",
    },
}


def _jacobian_double(pt, p):
    x, y, z = pt
    if not y or not z:
        return (0, 1, 0)
    ysq = y * y % p
    s = 4 * x * ysq % p
    zsq = z * z % p
    m = 3 * (x - zsq) * (x + zsq) % p  # a = -3
    nx = (m * m - 2 * s) % p
    ny = (m * (s - nx) - 8 * ysq * ysq) % p
    nz = 2 * y * z % p
    return (nx, ny, nz)


def _jacobian_add(p1, p2, p):
    if not p1[2]:
        return p2
    if not p2[2]:
        return p1
    z1s, z2s = p1[2] * p1[2] % p, p2[2] * p2[2] % p
    u1, u2 = p1[0] * z2s % p, p2[0] * z1s % p
    s1, s2 = p1[1] * z2s * p2[2] % p, p2[1] * z1s * p1[2] % p
    if u1 == u2:
        return _jacobian_double(p1, p) if s1 == s2 else (0, 1, 0)
    h, r = (u2 - u1) % p, (s2 - s1) % p
    h2 = h * h % p
    h3 = h * h2 % p
    v = u1 * h2 % p
    nx = (r * r - h3 - 2 * v) % p
    ny = (r * (v - nx) - s1 * h3) % p
    nz = h * p1[2] * p2[2] % p
    return (nx, ny, nz)


def _ecdsa(curve, x, y, message, signature):
    c = CURVES[curve]
    p, n, size = c["p"], c["n"], c["size"]
    if len(signature) != 2 * size:
        return False, (c["alg"] + " takes r||s of " + str(2 * size) + " bytes, this signature is "
                       + str(len(signature)))
    if not (0 <= x < p and 0 <= y < p and (y * y - x * x * x + 3 * x - c["b"]) % p == 0):
        return False, "the key is not a point on " + curve
    r = int.from_bytes(signature[:size], "big")
    s = int.from_bytes(signature[size:], "big")
    if not (0 < r < n and 0 < s < n):
        return False, "r or s is out of range"
    digest = hashlib.new(c["hash"], message).digest()
    e = int.from_bytes(digest[:size], "big")
    w = pow(s, n - 2, n)
    u1, u2 = e * w % n, r * w % n
    g = (c["g"][0], c["g"][1], 1)
    q = (x, y, 1)
    both = _jacobian_add(g, q, p)
    acc = (0, 1, 0)
    for i in range(max(u1.bit_length(), u2.bit_length()) - 1, -1, -1):
        acc = _jacobian_double(acc, p)
        b1, b2 = (u1 >> i) & 1, (u2 >> i) & 1
        if b1 and b2:
            acc = _jacobian_add(acc, both, p)
        elif b1:
            acc = _jacobian_add(acc, g, p)
        elif b2:
            acc = _jacobian_add(acc, q, p)
    if not acc[2]:
        return False, c["alg"] + " does not verify (point at infinity)"
    zinv = pow(acc[2], p - 2, p)
    if acc[0] * zinv * zinv % p % n == r:
        return True, c["alg"] + " verifies over the signature base"
    return False, c["alg"] + " does not verify over the signature base with this key"


# ------------------------------------------------------------------ RSA (RFC 8017)

_SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def _mgf1(seed, length, name):
    out, counter = b"", 0
    while len(out) < length:
        out += hashlib.new(name, seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:length]


def _rsa(n, e, alg, message, signature):
    k = (n.bit_length() + 7) // 8
    if n.bit_length() < 1024:
        return False, "the RSA key has only " + str(n.bit_length()) + " bits"
    if len(signature) != k:
        return False, "the signature is " + str(len(signature)) + " bytes, the key needs " + str(k)
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False, "the signature is not smaller than the modulus"
    m = pow(s, e, n)
    if alg == "rsa-v1_5-sha256":
        em = m.to_bytes(k, "big")
        t = _SHA256_INFO + hashlib.sha256(message).digest()
        expected = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
        if hmac.compare_digest(em, expected):
            return True, "rsa-v1_5-sha256 verifies over the signature base"
        return False, "rsa-v1_5-sha256 does not verify over the signature base with this key"
    # RSASSA-PSS with SHA-512, MGF1-SHA-512 and a 64-byte salt (RFC 9421 3.3.1)
    h_len, s_len = 64, 64
    em_bits = n.bit_length() - 1
    em_len = (em_bits + 7) // 8
    if m.bit_length() > em_bits:
        return False, "rsa-pss-sha512 does not verify (the encoded message is too long)"
    em = m.to_bytes(em_len, "big")
    if em_len < h_len + s_len + 2 or em[-1] != 0xBC:
        return False, "rsa-pss-sha512 does not verify (no 0xbc trailer)"
    masked, digest = em[:em_len - h_len - 1], em[em_len - h_len - 1:-1]
    zero_bits = 8 * em_len - em_bits
    if masked[0] >> (8 - zero_bits) if zero_bits else 0:
        return False, "rsa-pss-sha512 does not verify (leading bits set)"
    db = bytearray(a ^ b for a, b in zip(masked, _mgf1(digest, len(masked), "sha512"), strict=True))
    if zero_bits:
        db[0] &= 0xFF >> zero_bits
    pad = em_len - h_len - s_len - 2
    if any(db[:pad]) or db[pad] != 0x01:
        return False, "rsa-pss-sha512 does not verify (bad padding: another key, or 64-byte salt "
        "not used)"
    salt = bytes(db[-s_len:])
    check = hashlib.sha512(b"\x00" * 8 + hashlib.sha512(message).digest() + salt).digest()
    if hmac.compare_digest(check, digest):
        return True, "rsa-pss-sha512 verifies over the signature base"
    return False, "rsa-pss-sha512 does not verify over the signature base with this key"


# ------------------------------------------------------------------ keys: JWK, PEM, raw


def _b64any(text, where):
    if not isinstance(text, str) or not text.strip():
        raise ValueError(where + " must be a base64 or base64url string")
    t = "".join(text.split()).rstrip("=")
    t = t.replace("-", "+").replace("_", "/")
    try:
        return base64.b64decode(t + "=" * (-len(t) % 4), validate=True)
    except ValueError:
        raise ValueError(where + " is not base64") from None


def _der(data, start=0):
    """(tag, content, next offset) of one DER element."""
    if start + 2 > len(data):
        raise ValueError("truncated DER")
    tag, length, i = data[start], data[start + 1], start + 2
    if length & 0x80:
        count = length & 0x7F
        if not 0 < count <= 4 or i + count > len(data):
            raise ValueError("bad DER length")
        length, i = int.from_bytes(data[i:i + count], "big"), i + count
    if i + length > len(data):
        raise ValueError("truncated DER")
    return tag, data[i:i + length], i + length


def _children(content):
    out, i = [], 0
    while i < len(content):
        tag, value, i = _der(content, i)
        out.append((tag, value))
    return out


OIDS = {"2a864886f70d010101": "rsa", "2a864886f70d01010a": "rsa-pss", "2a8648ce3d0201": "ec",
        "2b6570": "ed25519", "2a8648ce3d030107": "P-256", "2b81040022": "P-384"}


def _rsa_numbers(content):
    parts = _children(content)
    if len(parts) < 2 or parts[0][0] != 0x02 or parts[1][0] != 0x02:
        raise ValueError("not an RSA public key (SEQUENCE of modulus and exponent)")
    return int.from_bytes(parts[0][1], "big"), int.from_bytes(parts[1][1], "big")


def _pem(text, where):
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if (len(lines) < 3 or not lines[0].startswith("-----BEGIN ")
            or not lines[-1].startswith("-----END")):
        raise ValueError(where + " is not a PEM block")
    label = lines[0][11:].strip("- ")
    if label not in ("PUBLIC KEY", "RSA PUBLIC KEY"):
        raise ValueError(where + ": only PUBLIC KEY and RSA PUBLIC KEY blocks are read; never "
                         "send a private key")
    der = _b64any("".join(lines[1:-1]), where)
    tag, content, _ = _der(der)
    if tag != 0x30:
        raise ValueError(where + ": not a DER SEQUENCE")
    if label == "RSA PUBLIC KEY":
        n, e = _rsa_numbers(content)
        return {"type": "rsa", "n": n, "e": e}
    parts = _children(content)
    if len(parts) != 2 or parts[0][0] != 0x30 or parts[1][0] != 0x03:
        raise ValueError(where + ": not a SubjectPublicKeyInfo")
    algo = _children(parts[0][1])
    kind = OIDS.get(algo[0][1].hex()) if algo and algo[0][0] == 0x06 else None
    bits = parts[1][1][1:]
    if kind in ("rsa", "rsa-pss"):
        n, e = _rsa_numbers(_der(bits)[1])
        key = {"type": "rsa", "n": n, "e": e}
        if kind == "rsa-pss":
            key["alg"] = "rsa-pss-sha512"
        return key
    if kind == "ed25519":
        if len(bits) != 32:
            raise ValueError(where + ": an Ed25519 key is 32 bytes")
        return {"type": "ed25519", "raw": bits}
    if kind == "ec":
        curve = OIDS.get(algo[1][1].hex()) if len(algo) > 1 and algo[1][0] == 0x06 else None
        if curve not in CURVES:
            raise ValueError(where + ": only P-256 and P-384 EC keys are supported")
        size = CURVES[curve]["size"]
        if len(bits) != 1 + 2 * size or bits[0] != 4:
            raise ValueError(where + ": the EC point must be uncompressed (04 || x || y)")
        return {"type": "ec", "curve": curve, "x": int.from_bytes(bits[1:1 + size], "big"),
                "y": int.from_bytes(bits[1 + size:], "big")}
    raise ValueError(where + ": unsupported key algorithm")


def _jwk(jwk, where):
    kty = jwk.get("kty")
    if "d" in jwk or "p" in jwk:
        raise ValueError(where + " carries private key material: send the public key only")
    key = {}
    if kty == "OKP" and jwk.get("crv") == "Ed25519":
        key = {"type": "ed25519", "raw": _b64any(jwk.get("x"), where + ".x")}
        if len(key["raw"]) != 32:
            raise ValueError(where + ".x must be 32 bytes")
    elif kty == "EC" and jwk.get("crv") in CURVES:
        key = {"type": "ec", "curve": jwk["crv"],
               "x": int.from_bytes(_b64any(jwk.get("x"), where + ".x"), "big"),
               "y": int.from_bytes(_b64any(jwk.get("y"), where + ".y"), "big")}
    elif kty == "RSA":
        key = {"type": "rsa", "n": int.from_bytes(_b64any(jwk.get("n"), where + ".n"), "big"),
               "e": int.from_bytes(_b64any(jwk.get("e"), where + ".e"), "big")}
    elif kty == "oct":
        key = {"type": "hmac", "raw": _b64any(jwk.get("k"), where + ".k")}
    else:
        raise ValueError(where + ": kty must be OKP (Ed25519), EC (P-256, P-384), RSA or oct")
    if jwk.get("alg"):
        if jwk["alg"] not in JOSE and jwk["alg"] not in ALGORITHMS:
            raise ValueError(where + ".alg " + str(jwk["alg"]) + " is not one of "
                             + ", ".join(ALGORITHMS))
        key["alg"] = JOSE.get(jwk["alg"], jwk["alg"])
    return key


def parse_key(value, where):
    if isinstance(value, str):
        return _pem(value, where)
    if not isinstance(value, dict):
        raise ValueError(where + " must be a JWK, a PEM string or {alg, key}")
    if "kty" in value:
        return _jwk(value, where)
    alg = value.get("alg")
    if alg not in ALGORITHMS:
        raise ValueError(where + ".alg must be one of " + ", ".join(ALGORITHMS))
    inner = value.get("key")
    if isinstance(inner, dict) or (isinstance(inner, str) and inner.strip().startswith("-----")):
        key = parse_key(inner, where + ".key")
    elif alg == "hmac-sha256":
        key = {"type": "hmac", "raw": _b64any(inner, where + ".key")}
    elif alg == "ed25519":
        key = {"type": "ed25519", "raw": _b64any(inner, where + ".key")}
        if len(key["raw"]) != 32:
            raise ValueError(where + ".key must be the 32-byte Ed25519 public key")
    else:
        raise ValueError(where + ".key must be a JWK or PEM for " + alg)
    key["alg"] = alg
    return key


KEY_ALGS = {"ed25519": ("ed25519",), "hmac": ("hmac-sha256",),
            "rsa": ("rsa-pss-sha512", "rsa-v1_5-sha256")}


def _algorithm(key, declared):
    allowed = KEY_ALGS.get(key["type"]) or (CURVES[key["curve"]]["alg"],)
    for source, alg in (("the signature's alg parameter", declared), ("the key", key.get("alg"))):
        if alg is None:
            continue
        if alg not in ALGORITHMS:
            raise _Bad(source + " names " + alg + ", not in the RFC 9421 registry")
        if alg not in allowed:
            raise _Bad(source + " names " + alg + " but the key is " + key["type"])
        if declared and key.get("alg") and declared != key["alg"]:
            raise _Bad("the signature says alg " + declared + ", the key is for " + key["alg"])
        return alg
    if len(allowed) > 1:
        raise _Bad("an RSA key fits rsa-pss-sha512 and rsa-v1_5-sha256: give alg with the key")
    return allowed[0]


def _verify(key, alg, message, signature):
    if alg == "ed25519":
        return _ed25519(key["raw"], message, signature)
    if alg == "hmac-sha256":
        mac = hmac.new(key["raw"], message, hashlib.sha256).digest()
        if hmac.compare_digest(mac, signature):
            return True, "hmac-sha256 matches over the signature base"
        return False, "hmac-sha256 does not match over the signature base with this secret"
    if alg.startswith("ecdsa"):
        return _ecdsa(key["curve"], key["x"], key["y"], message, signature)
    return _rsa(key["n"], key["e"], alg, message, signature)


# ------------------------------------------------------------------ structured fields (RFC 8941)


def _split_top(value, sep):
    """Split at `sep` outside quoted strings and parentheses."""
    parts, start, depth, quoted, escaped = [], 0, 0, False, False
    for index, char in enumerate(value):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == sep and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def dictionary(value, header):
    """{member name: raw member value} of a Structured Field dictionary."""
    out = {}
    for part in _split_top(value, ","):
        part = part.strip(" \t")
        if not part:
            continue
        name, eq, raw = part.partition("=")
        name = name.strip()
        if not name or not all(c in "abcdefghijklmnopqrstuvwxyz0123456789_-.*" for c in name):
            raise ValueError(header + ": bad member name " + name[:30])
        out[name] = raw.strip() if eq else "?1"
    return out


def _string(text, index):
    """(value, next index) of a quoted string starting at text[index] == '"'."""
    chars, i = [], index + 1
    while True:
        if i >= len(text):
            raise _Bad("a quoted string is not closed")
        char = text[i]
        if char == "\\":
            if i + 1 >= len(text) or text[i + 1] not in '"\\':
                raise _Bad("bad escape in a quoted string")
            chars.append(text[i + 1])
            i += 2
        elif char == '"':
            return "".join(chars), i + 1
        else:
            chars.append(char)
            i += 1


def params(text):
    """{name: value} of ;name=value parameters (value str, int or True)."""
    out, i = {}, 0
    while i < len(text):
        if text[i] in " \t":
            i += 1
            continue
        if text[i] != ";":
            raise _Bad("unexpected text in parameters: " + text[i:i + 20])
        i += 1
        while i < len(text) and text[i] == " ":
            i += 1
        end = i
        while end < len(text) and text[end] not in "=; ":
            end += 1
        name = text[i:end]
        if not name or name in out:
            raise _Bad("parameter '" + name + "' is empty or given twice")
        if end < len(text) and text[end] == "=":
            end += 1
            if end < len(text) and text[end] == '"':
                out[name], i = _string(text, end)
                continue
            stop = end
            while stop < len(text) and text[stop] not in "; ":
                stop += 1
            raw = text[end:stop]
            if raw.lstrip("-").isdigit() and raw.isascii():
                out[name] = int(raw)
            elif raw in ("?0", "?1"):
                out[name] = raw == "?1"
            else:
                out[name] = raw
            i = stop
        else:
            out[name] = True
            i = end
    return out


def inner_list(raw):
    """([(item text as written, name, params)], params text, params) of a Signature-Input member."""
    raw = raw.strip()
    if not raw.startswith("("):
        raise _Bad("the Signature-Input member is not an inner list")
    i, items = 1, []
    while True:
        while i < len(raw) and raw[i] == " ":
            i += 1
        if i >= len(raw):
            raise _Bad("the covered list is not closed")
        if raw[i] == ")":
            i += 1
            break
        if raw[i] != '"':
            raise _Bad("a covered component must be a quoted string")
        start = i
        name, i = _string(raw, i)
        stop = i
        while stop < len(raw) and raw[stop] not in " )":
            if raw[stop] == '"':
                stop = _string(raw, stop)[1]
            else:
                stop += 1
        items.append((raw[start:stop], name, params(raw[i:stop])))
        i = stop
    return items, raw[i:], params(raw[i:])


def byte_sequence(raw, where):
    raw = raw.strip()
    if len(raw) < 2 or raw[0] != ":" or raw[-1] != ":":
        raise _Bad(where + " is not a byte sequence (:base64:)")
    try:
        return base64.b64decode(raw[1:-1], validate=True)
    except ValueError:
        raise _Bad(where + " is not valid base64") from None


# ------------------------------------------------------------------ the message


def _headers(value, where):
    pairs = []
    if value is None:
        return {}
    if isinstance(value, dict):
        for name, item in value.items():
            for one in (item if isinstance(item, list) else [item]):
                pairs.append((name, one))
    elif isinstance(value, list):
        for pair in value:
            if not (isinstance(pair, list) and len(pair) == 2):
                raise ValueError(where + " as a list must hold [name, value] pairs")
            pairs.append((pair[0], pair[1]))
    else:
        raise ValueError(where + " must be an object or a list of [name, value] pairs")
    if len(pairs) > MAX_HEADERS:
        raise ValueError(where + " has more than " + str(MAX_HEADERS) + " fields")
    out = {}
    for name, item in pairs:
        if not isinstance(name, str) or not isinstance(item, (str, int)) or isinstance(item, bool):
            raise ValueError(where + ": field names and values must be strings")
        text = str(item)
        if "\n" in text or "\r" in text:
            raise ValueError(where + "." + name + ": a field value has a line break")
        out.setdefault(name.strip().lower(), []).append(text.strip(" \t"))
    return out


def _message(value, where):
    if not isinstance(value, dict):
        raise ValueError(where + " must be an object")
    msg = {"headers": _headers(value.get("headers"), where + ".headers")}
    if value.get("status") is not None:
        status = value["status"]
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            raise ValueError(where + ".status must be an HTTP status code")
        msg["status"] = status
    if value.get("method") is not None:
        if not isinstance(value["method"], str) or not value["method"].strip():
            raise ValueError(where + ".method must be a string")
        msg["method"] = value["method"].strip()
    if value.get("url") is not None:
        url = value["url"]
        if not isinstance(url, str) or "://" not in url:
            raise ValueError(where + ".url must be the absolute target URI, e.g. "
                             "https://example.com/foo?x=1")
        scheme, rest = url.split("://", 1)
        rest = rest.split("#", 1)[0]
        authority, slash, tail = rest.partition("/")
        path, mark, query = ("/" + tail if slash else "/").partition("?")
        if "?" in authority:
            authority, _, query = authority.partition("?")
            mark = "?"
        host = authority.rsplit("@", 1)[-1].lower()
        if ":" in host and not host.endswith("]"):
            name, port = host.rsplit(":", 1)
            if DEFAULT_PORTS.get(scheme.lower()) == port:
                host = name
        msg.update(url=url.split("#", 1)[0], scheme=scheme.lower(), authority=host, path=path,
                   query=query if mark else None)
    for name in ("body", "body_base64"):
        if value.get(name) is not None:
            raw = value[name]
            if not isinstance(raw, str):
                raise ValueError(where + "." + name + " must be a string")
            msg["body"] = raw.encode() if name == "body" else _b64any(raw, where + "." + name)
            if len(msg["body"]) > MAX_BODY:
                raise ValueError(where + ": the body is larger than " + str(MAX_BODY) + " bytes")
    return msg


def _percent_decode(text):
    raw, i, data = bytearray(), 0, text.replace("+", " ").encode()
    while i < len(data):
        pair = data[i + 1:i + 3]
        if data[i] == 0x25 and len(pair) == 2 and all(chr(c) in "0123456789abcdefABCDEF"
                                                      for c in pair):
            raw.append(int(pair, 16))
            i += 3
        else:
            raw.append(data[i])
            i += 1
    return bytes(raw)


def _percent_encode(raw):
    return "".join(chr(b) if chr(b) in _UNRESERVED else "%" + format(b, "02X") for b in raw)


def _query_param(query, name):
    found = []
    for part in (query or "").split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        if _percent_encode(_percent_decode(key)) == name:
            found.append(_percent_encode(_percent_decode(value)))
    if not found:
        raise _Bad('"@query-param";name="' + name + '": no such query parameter')
    if len(found) > 1:
        raise _Bad('"@query-param";name="' + name + '" occurs more than once; RFC 9421 2.2.8 '
                   "says it must not be covered then")
    return found[0]


def _component(name, prm, msg, request, notes):
    source = msg
    if prm.get("req"):
        if request is None or "status" not in msg:
            raise _Bad(name + ";req needs a response and the request given as `request`")
        source = request
    for flag in ("sf", "tr"):
        if prm.get(flag):
            raise _Bad(name + ";" + flag + " is not supported here (" + (
                "Structured Field re-serialization" if flag == "sf" else "trailers") + ")")
    if name.startswith("@"):
        if name == "@status":
            if "status" not in source:
                raise _Bad("@status is only for responses")
            return str(source["status"])
        if name == "@signature-params":
            raise _Bad("@signature-params must not be listed as a covered component")
        if "status" in source:
            raise _Bad(name + " is a request component; a response covers it with ;req")
        if name == "@method":
            if "method" not in source:
                raise _Bad("@method is covered but the message has no method")
            return source["method"]
        if "url" not in source:
            raise _Bad(name + " is covered but the message has no url")
        if name == "@target-uri":
            return source["url"]
        if name == "@authority":
            return source["authority"]
        if name == "@scheme":
            return source["scheme"]
        if name == "@path":
            return source["path"]
        if name == "@query":
            return "?" + (source["query"] or "")
        if name == "@request-target":
            return source["path"] + ("?" + source["query"] if source["query"] is not None else "")
        if name == "@query-param":
            if not isinstance(prm.get("name"), str):
                raise _Bad("@query-param needs a name parameter")
            return _query_param(source["query"], prm["name"])
        raise _Bad("unknown derived component " + name)
    if name != name.lower():
        raise _Bad("component name " + name + " must be lower case")
    values = source["headers"].get(name)
    if values is None:
        raise _Bad('the covered field "' + name + '" is not in the message')
    if "key" in prm:
        member = dictionary(", ".join(values), name).get(prm["key"])
        if member is None:
            raise _Bad(name + " has no dictionary member " + str(prm["key"]))
        notes.append(name + ';key="' + str(prm["key"]) + '" uses the member as written, not '
                     "re-serialized")
        return member
    if prm.get("bs"):
        return ", ".join(":" + base64.b64encode(v.encode()).decode() + ":" for v in values)
    return ", ".join(values)


# ------------------------------------------------------------------ one signature


def _content_digest(msg):
    values = msg["headers"].get("content-digest")
    if values is None or "body" not in msg:
        return None
    members = dictionary(", ".join(values), "content-digest")
    result = {"algorithms": [], "ok": False}
    for alg, name in (("sha-256", "sha256"), ("sha-512", "sha512")):
        if alg in members:
            got = byte_sequence(members[alg], "content-digest " + alg)
            ok = got == hashlib.new(name, msg["body"]).digest()
            result["algorithms"].append({"alg": alg, "ok": ok})
    if not result["algorithms"]:
        result["detail"] = "Content-Digest has neither sha-256 nor sha-512"
        return result
    result["ok"] = all(a["ok"] for a in result["algorithms"])
    result["detail"] = ("the body matches Content-Digest" if result["ok"]
                        else "the body does NOT match Content-Digest")
    return result


def _one(label, raw_input, raw_signature, msg, request, keys, single, now, max_age, required):
    out = {"label": label}
    notes = []
    try:
        items, params_text, prm = inner_list(raw_input)
        out["covered"] = [text for text, _, _ in items]
        out["params"] = prm
        seen = set()
        lines = []
        for text, name, item_params in items:
            if text in seen:
                raise _Bad("the component " + text + " is covered twice")
            seen.add(text)
            value = _component(name, item_params, msg, request, notes)
            lines.append(text + ": " + value)
        lines.append('"@signature-params": ' + raw_input.strip())
        base = "\n".join(lines)
        out["signature_base"] = base
        if raw_signature is None:
            raise _Bad("the Signature field has no member " + label)
        signature = byte_sequence(raw_signature, "Signature " + label)
        keyid = prm.get("keyid")
        if keys is not None:
            if not isinstance(keyid, str):
                raise _Bad("the signature names no keyid; give one `key` instead of `keys`")
            if keyid not in keys:
                raise _Bad("no key given for keyid " + keyid)
            key = keys[keyid]
        else:
            key = single
        declared = prm.get("alg")
        if declared is not None and not isinstance(declared, str):
            raise _Bad("alg must be a string")
        alg = _algorithm(key, declared)
        out["alg"] = alg
        ok, detail = _verify(key, alg, base.encode(), signature)
        out["signature_ok"] = ok
        out["detail"] = detail
    except _Bad as exc:
        out.update(verdict="error", detail=str(exc))
        if notes:
            out["notes"] = notes
        return out
    problems = []
    if not ok:
        problems.append(detail)
    created, expires = prm.get("created"), prm.get("expires")
    for name, value in (("created", created), ("expires", expires)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            problems.append(name + " must be an integer")
    if now is not None:
        if isinstance(expires, int) and now >= expires:
            problems.append("expired " + str(now - expires) + " s ago")
        if isinstance(created, int):
            if created > now + CLOCK_SKEW:
                problems.append("created " + str(created - now) + " s in the future")
            elif max_age is not None and now - created > max_age:
                problems.append("older than max_age: created " + str(now - created) + " s ago")
    elif expires is not None:
        notes.append("expires is set but no `now` was given, so it was not checked")
    missing = [c for c in required if c not in out["covered"]]
    if missing:
        problems.append("does not cover the required " + ", ".join(missing))
    if not items:
        notes.append("covers no component: it proves the key, not this message, and could be "
                     "replayed onto another message")
    if created is None:
        notes.append("no created parameter: its age cannot be judged")
    if "content-digest" in msg["headers"] and '"content-digest"' not in out["covered"]:
        notes.append("Content-Digest is present but not covered: the body is not signed")
    out["verdict"] = "valid" if not problems else "invalid"
    out["problems"] = problems
    if notes:
        out["notes"] = notes
    return out


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: message, and keys or key")
    msg = _message(payload.get("message"), "message")
    request = None
    if payload.get("request") is not None:
        request = _message(payload["request"], "request")
    if payload.get("keys") is not None:
        given = payload["keys"]
        if not isinstance(given, dict) or not given or len(given) > 16:
            raise ValueError("keys must be an object {keyid: key} with 1 to 16 keys")
        keys = {kid: parse_key(value, "keys." + kid) for kid, value in payload["keys"].items()}
        single = None
    elif payload.get("key") is not None:
        keys, single = None, parse_key(payload["key"], "key")
    else:
        raise ValueError("give keys {keyid: key} or one key")
    now = payload.get("now")
    if now is not None and (isinstance(now, bool) or not isinstance(now, int)):
        raise ValueError("now must be Unix seconds")
    max_age = payload.get("max_age")
    if max_age is not None and (isinstance(max_age, bool) or not isinstance(max_age, int)
                                or max_age < 0):
        raise ValueError("max_age must be a number of seconds")
    required = payload.get("required") or []
    if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
        raise ValueError('required must be a list of component identifiers such as "@authority"')
    required = [r if r.startswith('"') else '"' + r + '"' for r in required]

    inputs = msg["headers"].get("signature-input")
    signatures = msg["headers"].get("signature")
    if not inputs or not signatures:
        raise ValueError("the message has no Signature-Input and Signature fields")
    try:
        members = dictionary(", ".join(inputs), "Signature-Input")
        sig_members = dictionary(", ".join(signatures), "Signature")
    except _Bad as exc:
        raise ValueError(str(exc)) from None
    labels = list(members)
    if payload.get("label") is not None:
        if payload["label"] not in members:
            raise ValueError("Signature-Input has no member " + str(payload["label"]))
        labels = [payload["label"]]
    if len(labels) > MAX_LABELS:
        raise ValueError("more than " + str(MAX_LABELS) + " signatures; name one with label")
    results = [_one(label, members[label], sig_members.get(label), msg, request, keys, single,
                    now, max_age, required) for label in labels]
    out = {"signatures": results}
    digest = _content_digest(msg)
    if digest is not None:
        out["content_digest"] = digest
    valid = all(r["verdict"] == "valid" for r in results) and (digest is None or digest["ok"])
    out["verdict"] = "valid" if valid else "invalid"
    out["valid_labels"] = [r["label"] for r in results if r["verdict"] == "valid"]
    return out
