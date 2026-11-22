"""package.provenance.verify@v1: was this npm or PyPI release built where it says, and is that on
Sigstore's log?

Give `ecosystem` ("npm" or "pypi"), `package` and `version` (default: the latest). Optionally
`repository` (e.g. "github.com/owner/repo"), `workflow` (a path or file name) and `ref`: what you
expect the build to come from. For PyPI, `file` picks one file of the release; by default every file
is checked, up to the hearth's six requests.

For every Sigstore attestation of the release the agent verifies, itself, offline from pinned keys:
  - the certificate: issued by Sigstore's Fulcio CA (the public-good root and intermediate pinned
    below, from sigstore/root-signing's trusted_root.json), for code signing, and valid at the
    moment the transparency log recorded the signature;
  - the DSSE signature over the in-toto statement, by that certificate's key (or, for npm's own
    publish attestation, by the npm registry key the registry lists at /-/npm/v1/keys);
  - the statement's subject: the npm tarball's sha512 (dist.integrity), or the PyPI file's sha256;
  - the Rekor entry: its signed entry timestamp (SET) and its RFC 9162 inclusion proof under a
    checkpoint signed by Rekor's key, and that the logged entry carries this very signature, payload
    hash and certificate;
and reads the build identity from the certificate's Fulcio extensions: source repository, commit,
ref, workflow, trigger, runner and the run's URL. For npm it also checks the registry's own
signatures over name@version:integrity.

Not checked: the certificate's embedded SCTs (Certificate Transparency), revocation, and anything a
build did that its workflow file does not show. A verified provenance says where a release was
built, not that the code is safe; that is warden.scan's question.
"""

import base64
import hashlib
import json

NPM = "https://registry.npmjs.org"
PYPI = "https://pypi.org"
MAX_FETCHES = 6
MAX_FILES = 5
SLSA_V1 = "https://slsa.dev/provenance/v1"
SLSA_V02 = "https://slsa.dev/provenance/v0.2"
NPM_PUBLISH = "https://github.com/npm/attestation/tree/main/specs/publish/v0.1"
PYPI_PUBLISH = "https://docs.pypi.org/attestations/publish/v1"
IN_TOTO = "application/vnd.in-toto+json"

# Sigstore public-good trust root, from sigstore/root-signing targets/trusted_root.json
# (sha256 6494e21ea73fa7ee769f85f57d5a3e6a08725eae1e38c755fc3517c9e6bc0b66, read 2026-11-21).
FULCIO_CAS = (
    {
        "valid_from": "2021-03-07T03:20:29Z",
        "valid_to": "2022-12-31T23:59:59.999Z",
        "chain": (
            (
                "MIIB+DCCAX6gAwIBAgITNVkDZoCiofPDsy7dfm6geLbuhzAKBggqhkjOPQQDAzAqMRUwEwYDVQQKEwxzaWdzdG9y"
                "ZS5kZXYxETAPBgNVBAMTCHNpZ3N0b3JlMB4XDTIxMDMwNzAzMjAyOVoXDTMxMDIyMzAzMjAyOVowKjEVMBMGA1UE"
                "ChMMc2lnc3RvcmUuZGV2MREwDwYDVQQDEwhzaWdzdG9yZTB2MBAGByqGSM49AgEGBSuBBAAiA2IABLSyA7Ii5k+p"
                "NO8ZEWY0ylemWDowOkNa3kL+GZE5Z5GWehL9/A9bRNA3RbrsZ5i0JcastaRL7Sp5fp/jD5dxqc/UdTVnlvS16an+"
                "2Yfswe/QuLolRUCrcOE2+2iA5+tzd6NmMGQwDgYDVR0PAQH/BAQDAgEGMBIGA1UdEwEB/wQIMAYBAf8CAQEwHQYD"
                "VR0OBBYEFMjFHQBBmiQpMlEk6w2uSu1KBtPsMB8GA1UdIwQYMBaAFMjFHQBBmiQpMlEk6w2uSu1KBtPsMAoGCCqG"
                "SM49BAMDA2gAMGUCMH8liWJfMui6vXXBhjDgY4MwslmN/TJxVe/83WrFomwmNf056y1X48F9c4m3a3ozXAIxAKjR"
                "ay5/aj/jsKKGIkmQatjI8uupHr/+CxFvaJWmpYqNkLDGRU+9orzh5hI2RrcuaQ=="
            ),
        ),
    },
    {
        "valid_from": "2022-04-13T20:06:15Z",
        "valid_to": None,
        "chain": (
            (
                "MIICGjCCAaGgAwIBAgIUALnViVfnU0brJasmRkHrn/UnfaQwCgYIKoZIzj0EAwMwKjEVMBMGA1UEChMMc2lnc3Rv"
                "cmUuZGV2MREwDwYDVQQDEwhzaWdzdG9yZTAeFw0yMjA0MTMyMDA2MTVaFw0zMTEwMDUxMzU2NThaMDcxFTATBgNV"
                "BAoTDHNpZ3N0b3JlLmRldjEeMBwGA1UEAxMVc2lnc3RvcmUtaW50ZXJtZWRpYXRlMHYwEAYHKoZIzj0CAQYFK4EE"
                "ACIDYgAE8RVS/ysH+NOvuDZyPIZtilgUF9NlarYpAd9HP1vBBH1U5CV77LSS7s0ZiH4nE7Hv7ptS6LvvR/STk798"
                "LVgMzLlJ4HeIfF3tHSaexLcYpSASr1kS0N/RgBJz/9jWCiXno3sweTAOBgNVHQ8BAf8EBAMCAQYwEwYDVR0lBAww"
                "CgYIKwYBBQUHAwMwEgYDVR0TAQH/BAgwBgEB/wIBADAdBgNVHQ4EFgQU39Ppz1YkEZb5qNjpKFWixi4YZD8wHwYD"
                "VR0jBBgwFoAUWMAeX5FFpWapesyQoZMi0CrFxfowCgYIKoZIzj0EAwMDZwAwZAIwPCsQK4DYiZYDPIaDi5HFKnfx"
                "Xx6ASSVmERfsynYBiX2X6SJRnZU84/9DZdnFvvxmAjBOt6QpBlc4J/0DxvkTCqpclvziL6BCCPnjdlIB3Pu3BxsP"
                "mygUY7Ii2zbdCdliiow="
            ),
            (
                "MIIB9zCCAXygAwIBAgIUALZNAPFdxHPwjeDloDwyYChAO/4wCgYIKoZIzj0EAwMwKjEVMBMGA1UEChMMc2lnc3Rv"
                "cmUuZGV2MREwDwYDVQQDEwhzaWdzdG9yZTAeFw0yMTEwMDcxMzU2NTlaFw0zMTEwMDUxMzU2NThaMCoxFTATBgNV"
                "BAoTDHNpZ3N0b3JlLmRldjERMA8GA1UEAxMIc2lnc3RvcmUwdjAQBgcqhkjOPQIBBgUrgQQAIgNiAAT7XeFT4rb3"
                "PQGwS4IajtLk3/OlnpgangaBclYpsYBr5i+4ynB07ceb3LP0OIOZdxexX69c5iVuyJRQ+Hz05yi+UF3uBWAlHpiS"
                "5sh0+H2GHE7SXrk1EC5m1Tr19L9gg92jYzBhMA4GA1UdDwEB/wQEAwIBBjAPBgNVHRMBAf8EBTADAQH/MB0GA1Ud"
                "DgQWBBRYwB5fkUWlZql6zJChkyLQKsXF+jAfBgNVHSMEGDAWgBRYwB5fkUWlZql6zJChkyLQKsXF+jAKBggqhkjO"
                "PQQDAwNpADBmAjEAj1nHeXZp+13NWBNa+EDsDP8G1WWg1tCMWP/WHPqpaVo0jhsweNFZgSs0eE7wYI4qAjEA2WB9"
                "ot98sIkoF3vZYdd3/VtWB5b9TNMea7Ix/stJ5TfcLLeABLE4BNJOsQ4vnBHJ"
            ),
        ),
    },
)
REKOR_KEY = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE2G2Y+2tabdTV5BcGiBIx0a9fAFwrkBbmLSGtks4L3qX6yYY0zufB"
    "nhC8Ur/iy55GhWP/9A/bY2LhC30M9+RYtw=="
)
REKOR_LOG_ID = "wNI9atQGlz+VWfO6LRygH4QUfY/8W4RFwiT5i5WRgB0="


class _Budget(Exception):
    """The call has used the six requests the hearth allows."""


class _Bad(ValueError):
    """Malformed data inside an attestation: the attestation fails, the call goes on."""


# ------------------------------------------------------------------ bytes


def _b64(text, where):
    if not isinstance(text, str):
        raise _Bad(where + " is not a base64 string")
    t = "".join(text.split())
    if "-" in t or "_" in t:
        t = t.replace("-", "+").replace("_", "/")
    try:
        return base64.b64decode(t + "=" * (-len(t) % 4), validate=True)
    except ValueError:
        raise _Bad(where + " is not base64") from None


def _pem_der(text, where):
    lines = [line.strip() for line in str(text).strip().splitlines() if line.strip()]
    if (
        len(lines) < 3
        or not lines[0].startswith("-----BEGIN ")
        or not lines[-1].startswith("-----END ")
    ):
        raise _Bad(where + " is not a PEM block")
    return _b64("".join(lines[1:-1]), where)


# ------------------------------------------------------------------ DER and X.509


def _tlv(data, i):
    """(tag, content start, content end) of the DER element at i."""
    if i + 2 > len(data):
        raise _Bad("truncated DER")
    tag, length, j = data[i], data[i + 1], i + 2
    if length & 0x80:
        count = length & 0x7F
        if not 1 <= count <= 4 or j + count > len(data):
            raise _Bad("bad DER length")
        length, j = int.from_bytes(data[j : j + count], "big"), j + count
    if j + length > len(data):
        raise _Bad("truncated DER")
    return tag, j, j + length


def _items(data, start, end):
    """[(tag, content start, content end, element start)] of a constructed element's content."""
    out, i = [], start
    while i < end:
        tag, cs, ce = _tlv(data, i)
        out.append((tag, cs, ce, i))
        i = ce
    return out


OID_EC = bytes.fromhex("2a8648ce3d0201")
CURVE_OIDS = {bytes.fromhex("2a8648ce3d030107"): "P-256", bytes.fromhex("2b81040022"): "P-384"}
SIG_HASHES = {
    bytes.fromhex("2a8648ce3d040302"): "sha256",
    bytes.fromhex("2a8648ce3d040303"): "sha384",
}
OID_SAN = bytes.fromhex("551d11")
OID_EKU = bytes.fromhex("551d25")
OID_CODE_SIGNING = bytes.fromhex("2b06010505070303")
FULCIO_ARC = bytes.fromhex("2b0601040183bf3001")
FULCIO = {
    1: "issuer_v1",
    8: "issuer",
    9: "build_signer_uri",
    10: "build_signer_digest",
    11: "runner_environment",
    12: "source_repository_uri",
    13: "source_repository_digest",
    14: "source_repository_ref",
    15: "source_repository_identifier",
    16: "source_repository_owner_uri",
    18: "build_config_uri",
    19: "build_config_digest",
    20: "build_trigger",
    21: "run_invocation_uri",
    22: "source_repository_visibility",
}


def _days(year, month, day):
    """Days since 1970-01-01 (proleptic Gregorian), Howard Hinnant's days_from_civil."""
    year -= month <= 2
    era = year // 400
    yoe = year - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _asn1_time(tag, raw):
    text = raw.decode("ascii")
    if tag == 0x17 and len(text) == 13 and text.endswith("Z"):
        year = int(text[:2])
        year += 2000 if year < 50 else 1900
        rest = text[2:12]
    elif tag == 0x18 and len(text) == 15 and text.endswith("Z"):
        year, rest = int(text[:4]), text[4:14]
    else:
        raise _Bad("a certificate time is not UTCTime or GeneralizedTime in UTC")
    month, day, hour, minute, second = (int(rest[k : k + 2]) for k in range(0, 10, 2))
    return _days(year, month, day) * 86400 + hour * 3600 + minute * 60 + second


def _iso(seconds):
    days, rem = divmod(int(seconds), 86400)
    # civil_from_days
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + 3 if mp < 10 else mp - 9
    year = yoe + era * 400 + (month <= 2)
    return (
        f"{year:04d}-{month:02d}-{day:02d}T{rem // 3600:02d}:{rem // 60 % 60:02d}:{rem % 60:02d}Z"
    )


def _spki(data, start, end):
    """(curve, x, y) of an EC SubjectPublicKeyInfo."""
    parts = _items(data, start, end)
    if len(parts) != 2 or parts[0][0] != 0x30 or parts[1][0] != 0x03:
        raise _Bad("not a SubjectPublicKeyInfo")
    algo = _items(data, parts[0][1], parts[0][2])
    if len(algo) < 2 or data[algo[0][1] : algo[0][2]] != OID_EC:
        raise _Bad("the key is not an EC key")
    curve = CURVE_OIDS.get(data[algo[1][1] : algo[1][2]])
    if curve is None:
        raise _Bad("the key's curve is not P-256 or P-384")
    bits = data[parts[1][1] + 1 : parts[1][2]]
    size = CURVES[curve]["size"]
    if len(bits) != 1 + 2 * size or bits[0] != 4:
        raise _Bad("the EC point is not uncompressed")
    return curve, int.from_bytes(bits[1 : 1 + size], "big"), int.from_bytes(bits[1 + size :], "big")


def spki_key(der):
    tag, start, end = _tlv(der, 0)
    if tag != 0x30 or end != len(der):
        raise _Bad("a public key is not one DER SEQUENCE")
    return _spki(der, start, end)


def _utf8(value):
    """A Fulcio extension value: a DER UTF8String (1.8 on), or the raw text of the v1 OIDs."""
    if len(value) >= 2 and value[0] == 0x0C:
        try:
            tag, start, end = _tlv(value, 0)
            if end == len(value):
                return value[start:end].decode("utf-8")
        except _Bad:
            pass
    return value.decode("utf-8", "replace")


def parse_cert(der):
    tag, start, end = _tlv(der, 0)
    if tag != 0x30 or end != len(der):
        raise _Bad("the certificate is not one DER SEQUENCE")
    top = _items(der, start, end)
    if len(top) != 3 or top[0][0] != 0x30 or top[2][0] != 0x03:
        raise _Bad("the certificate does not have tbsCertificate, algorithm and signature")
    tbs_tag, tbs_start, tbs_end, tbs_at = top[0]
    tbs = _items(der, tbs_start, tbs_end)
    if tbs and tbs[0][0] == 0xA0:
        tbs = tbs[1:]
    if len(tbs) < 6:
        raise _Bad("tbsCertificate is too short")
    alg = _items(der, top[1][1], top[1][2])
    validity = _items(der, tbs[3][1], tbs[3][2])
    cert = {
        "der": der,
        "tbs": der[tbs_at:tbs_end],
        "sig_hash": SIG_HASHES.get(der[alg[0][1] : alg[0][2]]) if alg else None,
        "signature": der[top[2][1] + 1 : top[2][2]],
        "issuer": der[tbs[2][3] : tbs[2][2]],
        "subject": der[tbs[4][3] : tbs[4][2]],
        "not_before": _asn1_time(validity[0][0], der[validity[0][1] : validity[0][2]]),
        "not_after": _asn1_time(validity[1][0], der[validity[1][1] : validity[1][2]]),
        "key": _spki(der, tbs[5][1], tbs[5][2]),
        "san": [],
        "code_signing": False,
        "fulcio": {},
    }
    for item in tbs[6:]:
        if item[0] != 0xA3:
            continue
        (seq,) = _items(der, item[1], item[2])[:1]
        for ext in _items(der, seq[1], seq[2]):
            fields = _items(der, ext[1], ext[2])
            oid = der[fields[0][1] : fields[0][2]]
            value = der[fields[-1][1] : fields[-1][2]]
            if oid == OID_SAN:
                stag, sstart, send = _tlv(value, 0)
                for name in _items(value, sstart, send):
                    if name[0] in (0x86, 0x81):
                        cert["san"].append(value[name[1] : name[2]].decode("utf-8", "replace"))
            elif oid == OID_EKU:
                stag, sstart, send = _tlv(value, 0)
                cert["code_signing"] = any(
                    value[p[1] : p[2]] == OID_CODE_SIGNING for p in _items(value, sstart, send)
                )
            elif oid.startswith(FULCIO_ARC) and len(oid) == len(FULCIO_ARC) + 1:
                label = FULCIO.get(oid[-1])
                if label:
                    cert["fulcio"][label] = _utf8(value)
    return cert


# ------------------------------------------------------------------ ECDSA (FIPS 186-5)

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
    },
}


def _double(pt, p):
    x, y, z = pt
    if not y or not z:
        return (0, 1, 0)
    ysq = y * y % p
    s = 4 * x * ysq % p
    zsq = z * z % p
    m = 3 * (x - zsq) * (x + zsq) % p  # a = -3
    nx = (m * m - 2 * s) % p
    return (nx, (m * (s - nx) - 8 * ysq * ysq) % p, 2 * y * z % p)


def _add(p1, p2, p):
    if not p1[2]:
        return p2
    if not p2[2]:
        return p1
    z1s, z2s = p1[2] * p1[2] % p, p2[2] * p2[2] % p
    u1, u2 = p1[0] * z2s % p, p2[0] * z1s % p
    s1, s2 = p1[1] * z2s * p2[2] % p, p2[1] * z1s * p1[2] % p
    if u1 == u2:
        return _double(p1, p) if s1 == s2 else (0, 1, 0)
    h, r = (u2 - u1) % p, (s2 - s1) % p
    h2 = h * h % p
    h3 = h * h2 % p
    v = u1 * h2 % p
    nx = (r * r - h3 - 2 * v) % p
    return (nx, (r * (v - nx) - s1 * h3) % p, h * p1[2] * p2[2] % p)


def _der_signature(signature):
    tag, start, end = _tlv(signature, 0)
    parts = _items(signature, start, end)
    if tag != 0x30 or end != len(signature) or len(parts) != 2 or any(t[0] != 0x02 for t in parts):
        raise _Bad("the ECDSA signature is not DER SEQUENCE { r, s }")
    return tuple(int.from_bytes(signature[t[1] : t[2]], "big") for t in parts)


def ecdsa_verify(key, hash_name, message, signature):
    """True when `signature` (DER) is `key`'s ECDSA signature over hash_name(message)."""
    curve, x, y = key
    c = CURVES[curve]
    p, n = c["p"], c["n"]
    try:
        r, s = _der_signature(signature)
    except _Bad:
        return False
    if not (0 < r < n and 0 < s < n):
        return False
    if (y * y - x * x * x + 3 * x - c["b"]) % p:
        return False
    digest = hashlib.new(hash_name, message).digest()
    e = int.from_bytes(digest, "big") >> max(0, 8 * len(digest) - n.bit_length())
    w = pow(s, n - 2, n)
    u1, u2 = e * w % n, r * w % n
    g, q = (c["g"][0], c["g"][1], 1), (x, y, 1)
    both = _add(g, q, p)
    acc = (0, 1, 0)
    for i in range(max(u1.bit_length(), u2.bit_length()) - 1, -1, -1):
        acc = _double(acc, p)
        b1, b2 = (u1 >> i) & 1, (u2 >> i) & 1
        if b1 and b2:
            acc = _add(acc, both, p)
        elif b1:
            acc = _add(acc, g, p)
        elif b2:
            acc = _add(acc, q, p)
    if not acc[2]:
        return False
    zinv = pow(acc[2], p - 2, p)
    return acc[0] * zinv * zinv % p % n == r


# ------------------------------------------------------------------ the pinned roots


def _fulcio_cas():
    out = []
    for ca in FULCIO_CAS:
        chain = [parse_cert(base64.b64decode("".join(part))) for part in ca["chain"]]
        out.append({"from": ca["valid_from"], "to": ca["valid_to"], "chain": chain})
    return out


def _rekor():
    der = base64.b64decode("".join(REKOR_KEY))
    log_id = hashlib.sha256(der).digest()
    if base64.b64encode(log_id).decode() != REKOR_LOG_ID:
        raise RuntimeError("the pinned Rekor key does not hash to its log id")
    return spki_key(der), log_id


def _stamp(text):
    """An RFC 3339 instant of the trust root ("2022-04-13T20:06:15Z") as unix seconds."""
    return (
        _days(int(text[:4]), int(text[5:7]), int(text[8:10])) * 86400
        + int(text[11:13]) * 3600
        + int(text[14:16]) * 60
        + int(text[17:19])
    )


# ------------------------------------------------------------------ one attestation


def pae(payload_type, payload):
    """DSSE's pre-authentication encoding."""
    kind = payload_type.encode("utf-8")
    return (
        b"DSSEv1 "
        + str(len(kind)).encode()
        + b" "
        + kind
        + b" "
        + str(len(payload)).encode()
        + b" "
        + payload
    )


def _check(checks, name, ok, detail):
    checks.append({"check": name, "ok": bool(ok), "detail": detail})
    return bool(ok)


def _int(value, where):
    text = str(value if value is not None else "").strip()
    if not text.isdigit():
        raise _Bad(where + " is not a whole number")
    return int(text)


def _chain(checks, leaf, integrated):
    """Is the leaf issued by a pinned Fulcio CA, for code signing, valid when it was logged?"""
    for ca in CAS:
        issuer = ca["chain"][0]
        if leaf["issuer"] != issuer["subject"]:
            continue
        if not (
            _stamp(ca["from"]) <= leaf["not_before"]
            and (ca["to"] is None or leaf["not_before"] <= _stamp(ca["to"]))
        ):
            continue
        signed = leaf["sig_hash"] is not None and ecdsa_verify(
            issuer["key"], leaf["sig_hash"], leaf["tbs"], leaf["signature"]
        )
        _check(
            checks,
            "certificate_chain",
            signed,
            "issued by Sigstore's Fulcio CA (pinned, valid from " + ca["from"] + ")"
            if signed
            else "names the Fulcio CA as issuer but its signature does not verify",
        )
        break
    else:
        _check(checks, "certificate_chain", False, "not issued by a pinned Fulcio CA")
    _check(
        checks,
        "code_signing",
        leaf["code_signing"],
        "extended key usage: code signing" if leaf["code_signing"] else "no code-signing key usage",
    )
    inside = leaf["not_before"] <= integrated <= leaf["not_after"]
    _check(
        checks,
        "certificate_valid_when_logged",
        inside,
        "valid "
        + _iso(leaf["not_before"])
        + " to "
        + _iso(leaf["not_after"])
        + ", logged "
        + _iso(integrated),
    )


def _rekor_entry(checks, entry, payload, signature, verifier_der):
    """The SET, the inclusion proof and its signed checkpoint, and that the logged body is this
    signature over this payload by this verifier. Returns the integrated time."""
    log_key, log_id = REKOR
    kind = entry.get("kindVersion") or {}
    kind = str(kind.get("kind")) + " " + str(kind.get("version"))
    given = _b64((entry.get("logId") or {}).get("keyId"), "logId.keyId")
    if not _check(
        checks,
        "rekor_log",
        given == log_id,
        "rekor.sigstore.dev (pinned key)"
        if given == log_id
        else "another log than rekor.sigstore.dev, whose key is not pinned here",
    ):
        return None
    integrated = _int(entry.get("integratedTime"), "integratedTime")
    index = _int(entry.get("logIndex"), "logIndex")
    body_b64 = entry.get("canonicalizedBody")
    body_raw = _b64(body_b64, "canonicalizedBody")
    promise = (entry.get("inclusionPromise") or {}).get("signedEntryTimestamp")
    if promise:
        canonical = json.dumps(
            {
                "body": body_b64,
                "integratedTime": integrated,
                "logID": log_id.hex(),
                "logIndex": index,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        _check(
            checks,
            "rekor_set",
            ecdsa_verify(log_key, "sha256", canonical, _b64(promise, "SET")),
            "the signed entry timestamp verifies: index " + str(index) + " at " + _iso(integrated),
        )
    proof = entry.get("inclusionProof") or {}
    if proof:
        leaf = hashlib.sha256(b"\x00" + body_raw).digest()
        root = _b64(proof.get("rootHash"), "rootHash")
        size = _int(proof.get("treeSize"), "treeSize")
        at = _int(proof.get("logIndex"), "inclusionProof.logIndex")
        path = [_b64(h, "inclusion hash") for h in proof.get("hashes") or []][:64]
        got = inclusion_root(leaf, at, size, path)
        _check(
            checks,
            "rekor_inclusion",
            got == root,
            "RFC 9162 inclusion proof leads to the root of a " + str(size) + "-entry tree"
            if got == root
            else "the inclusion proof does not lead to the given root",
        )
        note = ((proof.get("checkpoint") or {}).get("envelope")) or ""
        _check(
            checks,
            "rekor_checkpoint",
            _checkpoint(note, size, root, log_key, log_id),
            "the checkpoint for that tree is signed by Rekor's key",
        )
    if not promise and not proof:
        _check(
            checks, "rekor_set", False, "the entry has neither a signed entry timestamp nor a proof"
        )
    try:
        body = json.loads(body_raw)
    except ValueError:
        raise _Bad("the logged body is not JSON") from None
    spec = body.get("spec") or {}
    if kind == "dsse 0.0.1":
        payload_hash = (spec.get("payloadHash") or {}).get("value")
        logged = [
            (
                _b64(s.get("signature"), "logged signature"),
                _pem_der(
                    _b64(s.get("verifier"), "logged verifier").decode("utf-8", "replace"),
                    "verifier",
                ),
            )
            for s in spec.get("signatures") or []
        ]
    elif kind == "intoto 0.0.2":
        content = spec.get("content") or {}
        payload_hash = (content.get("payloadHash") or {}).get("value")
        logged = [
            (
                _b64(_b64(s.get("sig"), "logged sig").decode("ascii", "replace"), "logged sig"),
                _pem_der(
                    _b64(s.get("publicKey"), "logged key").decode("utf-8", "replace"), "publicKey"
                ),
            )
            for s in (content.get("envelope") or {}).get("signatures") or []
        ]
    else:
        _check(checks, "rekor_body", False, "entry kind " + kind + " is not read by this agent")
        return integrated
    same_payload = payload_hash == hashlib.sha256(payload).hexdigest()
    same_sig = any(sig == signature and der == verifier_der for sig, der in logged)
    _check(
        checks,
        "rekor_body",
        same_payload and same_sig,
        "the logged " + kind + " entry holds this payload's hash, this signature and this key"
        if same_payload and same_sig
        else "the logged entry is for another "
        + ("payload" if not same_payload else "signature or key"),
    )
    return integrated


def _checkpoint(note, size, root, key, log_id):
    if "\n\n" not in note:
        return False
    body, sigs = note.split("\n\n", 1)
    lines = body.split("\n")
    if len(lines) < 3 or lines[1] != str(size) or lines[2] != base64.b64encode(root).decode():
        return False
    for line in sigs.split("\n"):
        if line.startswith("— "):
            name, _, b64 = line[2:].rpartition(" ")
            raw = base64.b64decode(b64 + "=" * (-len(b64) % 4))
            if raw[:4] == log_id[:4] and ecdsa_verify(
                key, "sha256", (body + "\n").encode(), raw[4:]
            ):
                return True
    return False


def _node(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def inclusion_root(leaf_hash, index, size, path):
    """RFC 9162 2.1.3.2: the root the path leads to, or None when its shape is wrong."""
    if index >= size:
        return None
    fn, sn, r = index, size - 1, leaf_hash
    for p in path:
        if sn == 0:
            return None
        if fn & 1 or fn == sn:
            r = _node(p, r)
            while not fn & 1 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = _node(r, p)
        fn >>= 1
        sn >>= 1
    return r if sn == 0 else None


def verify_attestation(payload_type, payload, signature, leaf_der, entry, public_key=None):
    """One DSSE envelope with its key material and Rekor entry. `leaf_der` for a Fulcio
    certificate, or `public_key` (der, (curve, x, y), name) for a registry key."""
    checks = []
    out = {"checks": checks}
    try:
        statement = json.loads(payload)
    except ValueError:
        statement = None
    out["statement"] = statement if isinstance(statement, dict) else None
    if leaf_der is not None:
        leaf = parse_cert(leaf_der)
        key, verifier_der = leaf["key"], leaf_der
        identity = dict(leaf["fulcio"])
        identity["san"] = leaf["san"]
        out["identity"] = identity
    else:
        verifier_der, key, name = public_key
        leaf = None
        out["identity"] = {"key": name}
    _check(
        checks,
        "dsse_signature",
        ecdsa_verify(key, "sha256", pae(payload_type, payload), signature),
        "the DSSE signature over the statement verifies with "
        + ("the certificate's key" if leaf else out["identity"]["key"]),
    )
    entries = entry if isinstance(entry, list) else [entry]
    integrated = None
    for item in entries[:1]:
        if isinstance(item, dict):
            integrated = _rekor_entry(checks, item, payload, signature, verifier_der)
    if integrated is None and not any(c["check"] == "rekor_log" for c in checks):
        _check(checks, "rekor_log", False, "no transparency-log entry with the attestation")
    if leaf is not None and integrated is not None:
        _chain(checks, leaf, integrated)
    out["logged_at"] = _iso(integrated) if integrated is not None else None
    return out


def _subject_ok(checks, statement, algorithm, digest_hex, name=None):
    subjects = (statement or {}).get("subject") or []
    hit = [
        s
        for s in subjects
        if isinstance(s, dict)
        and str((s.get("digest") or {}).get(algorithm, "")).lower() == digest_hex
    ]
    named = not name or any(s.get("name") == name for s in hit)
    return _check(
        checks,
        "subject",
        hit and named,
        "the statement's subject is this artifact (" + algorithm + " " + digest_hex[:16] + "…)"
        if hit and named
        else "the statement is about another artifact",
    )


# ------------------------------------------------------------------ build identity and expectations


def _identity_summary(identity):
    keys = (
        "issuer",
        "issuer_v1",
        "source_repository_uri",
        "source_repository_digest",
        "source_repository_ref",
        "build_signer_uri",
        "build_config_uri",
        "build_trigger",
        "runner_environment",
        "run_invocation_uri",
        "source_repository_visibility",
    )
    out = {k: identity[k] for k in keys if identity.get(k)}
    if "issuer" not in out and "issuer_v1" in out:
        out["issuer"] = out["issuer_v1"]
    out.pop("issuer_v1", None)
    if identity.get("san"):
        out["san"] = identity["san"]
    return out


def _norm_repo(text):
    t = str(text or "").strip().lower()
    for prefix in ("git+", "https://", "http://"):
        if t.startswith(prefix):
            t = t[len(prefix) :]
    if t.endswith(".git"):
        t = t[:-4]
    return t.rstrip("/")


def _expect(checks, build, repository, workflow, ref):
    if repository:
        got = _norm_repo(build.get("source_repository_uri"))
        want = _norm_repo(repository)
        if "/" in want and "." not in want.split("/", 1)[0]:
            want = "github.com/" + want
        _check(
            checks,
            "expected_repository",
            got == want,
            "built from "
            + (got or "no recorded repository")
            + (", as expected" if got == want else ", not " + want),
        )
    signer = str(build.get("build_signer_uri") or (build.get("san") or [""])[0])
    if workflow:
        path = signer.split("@", 1)[0]
        ok = path.endswith("/" + workflow.lstrip("/")) or path.rsplit("/", 1)[-1] == workflow
        _check(
            checks,
            "expected_workflow",
            ok,
            "signed by "
            + (path or "no workflow")
            + (", as expected" if ok else ", not " + workflow),
        )
    if ref:
        got = str(
            build.get("source_repository_ref") or (signer.split("@", 1)[1] if "@" in signer else "")
        )
        ok = got == ref or got == "refs/tags/" + ref or got == "refs/heads/" + ref
        _check(
            checks,
            "expected_ref",
            ok,
            "built at " + (got or "no recorded ref") + (", as expected" if ok else ", not " + ref),
        )


# ------------------------------------------------------------------ registries


def _path(text):
    safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~@"
    return "".join(
        c if c in safe else "%" + format(b, "02X") for c in str(text) for b in c.encode("utf-8")
    )


def _get(state, url, accept="application/json"):
    if state["fetches"] >= MAX_FETCHES:
        raise _Budget()
    state["fetches"] += 1
    return fetch(url, headers={"accept": accept})  # noqa: F821 — the sandbox provides fetch()


def _json(reply):
    if not reply.ok:
        return None
    try:
        return json.loads(reply.text)
    except ValueError:
        return None


def ssh_fingerprint(point):
    """npm's keyid: the OpenSSH SHA256 fingerprint of the ecdsa-sha2-nistp256 public key, so a
    listed key whose id does not match its own bytes is not used."""
    _, x, y = point

    def field(raw):
        return len(raw).to_bytes(4, "big") + raw

    wire = (
        field(b"ecdsa-sha2-nistp256")
        + field(b"nistp256")
        + field(b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big"))
    )
    return "SHA256:" + base64.b64encode(hashlib.sha256(wire).digest()).decode().rstrip("=")


def _npm(state, package, version, out):
    doc = _json(_get(state, NPM + "/" + _path(package) + "/" + _path(version or "latest")))
    if not isinstance(doc, dict) or not isinstance(doc.get("dist"), dict):
        out.update(
            verdict="not_found", detail="npm has no " + package + "@" + (version or "latest")
        )
        return
    version = doc["version"]
    dist = doc["dist"]
    integrity = str(dist.get("integrity") or "")
    if not integrity.startswith("sha512-"):
        out.update(verdict="invalid", detail="dist.integrity is not a sha512 integrity string")
        return
    sha512 = _b64(integrity[7:], "dist.integrity").hex()
    out.update(version=version, artifact={"integrity": integrity, "sha512": sha512})
    purl = (
        "pkg:npm/"
        + (package.replace("@", "%40", 1) if package.startswith("@") else package)
        + "@"
        + version
    )
    keys_doc = _json(_get(state, NPM + "/-/npm/v1/keys"))
    keys = {}
    for k in (keys_doc or {}).get("keys") or []:
        try:
            der = _b64(k.get("key"), "npm key")
            point = spki_key(der)
            if point[0] == "P-256" and ssh_fingerprint(point) == k.get("keyid"):
                keys[k["keyid"]] = (der, point, k.get("expires"))
        except (_Bad, KeyError):
            continue
    registry = []
    message = (package + "@" + version + ":" + integrity).encode()
    for sig in (dist.get("signatures") or [])[:4]:
        key = keys.get(sig.get("keyid"))
        ok = key is not None and ecdsa_verify(
            key[1], "sha256", message, _b64(sig.get("sig"), "sig")
        )
        registry.append({"keyid": sig.get("keyid"), "ok": ok})
    out["registry_signatures"] = registry
    if not dist.get("attestations"):
        out.update(
            verdict="no_provenance",
            detail=package + "@" + version + " was published without attestations",
        )
        return
    doc = _json(
        _get(state, NPM + "/-/npm/v1/attestations/" + _path(package) + "@" + _path(version))
    )
    attestations = []
    for att in ((doc or {}).get("attestations") or [])[:4]:
        bundle = att.get("bundle") or {}
        material = bundle.get("verificationMaterial") or {}
        envelope = bundle.get("dsseEnvelope") or {}
        row = {"predicate_type": att.get("predicateType"), "bundle": bundle.get("mediaType")}
        attestations.append(row)
        try:
            payload = _b64(envelope.get("payload"), "payload")
            signature = _b64(((envelope.get("signatures") or [{}])[0]).get("sig"), "signature")
            cert = (
                material.get("certificate")
                or ((material.get("x509CertificateChain") or {}).get("certificates") or [None])[0]
            )
            public = None
            leaf = None
            if cert:
                leaf = _b64(cert.get("rawBytes"), "certificate")
            else:
                hint = (material.get("publicKey") or {}).get("hint")
                key = keys.get(hint)
                if key is None:
                    raise _Bad(
                        "signed by npm key " + str(hint) + ", which the registry does not list"
                    )
                public = (key[0], key[1], "npm registry key " + hint)
            result = verify_attestation(
                envelope.get("payloadType"),
                payload,
                signature,
                leaf,
                material.get("tlogEntries") or [],
                public,
            )
            statement = result.pop("statement")
            checks = result["checks"]
            _subject_ok(checks, statement, "sha512", sha512, purl)
            if (
                public is not None
                and key[2]
                and result.get("logged_at")
                and result["logged_at"] > key[2][:19] + "Z"
            ):
                _check(
                    checks,
                    "key_not_expired",
                    False,
                    "the npm key expired " + key[2] + " before the signature was logged",
                )
            if att.get("predicateType") in (SLSA_V1, SLSA_V02) and isinstance(statement, dict):
                row["predicate"] = _slsa(statement.get("predicate") or {})
            row.update(result)
        except _Bad as exc:
            row["checks"] = [{"check": "readable", "ok": False, "detail": str(exc)}]
    out["attestations"] = attestations


def _slsa(predicate):
    definition = predicate.get("buildDefinition") or {}
    workflow = ((definition.get("externalParameters") or {}).get("workflow")) or {}
    deps = definition.get("resolvedDependencies") or []
    run = ((predicate.get("runDetails") or {}).get("metadata") or {}).get("invocationId")
    out = {
        "build_type": definition.get("buildType"),
        "workflow": workflow or None,
        "source": [
            {"uri": d.get("uri"), "digest": d.get("digest")}
            for d in deps[:2]
            if isinstance(d, dict)
        ],
        "invocation": run,
    }
    return {k: v for k, v in out.items() if v}


def _pypi(state, package, version, wanted_file, out):
    url = PYPI + "/pypi/" + _path(package) + ("/" + _path(version) if version else "") + "/json"
    doc = _json(_get(state, url))
    info = (doc or {}).get("info") if isinstance(doc, dict) else None
    if not isinstance(info, dict):
        out.update(verdict="not_found", detail="PyPI has no " + package + " " + (version or ""))
        return
    version = info.get("version")
    files = [f for f in doc.get("urls") or [] if isinstance(f, dict) and f.get("filename")]
    if wanted_file:
        files = [f for f in files if f["filename"] == wanted_file]
        if not files:
            out.update(
                verdict="not_found",
                detail=wanted_file + " is not a file of " + package + " " + str(version),
            )
            return
    out.update(version=version, files=[])
    for f in files[:MAX_FILES]:
        row = {"filename": f["filename"], "sha256": (f.get("digests") or {}).get("sha256")}
        out["files"].append(row)
        try:
            reply = _get(
                state,
                PYPI
                + "/integrity/"
                + _path(info.get("name") or package)
                + "/"
                + _path(version)
                + "/"
                + _path(f["filename"])
                + "/provenance",
                "application/vnd.pypi.integrity.v1+json",
            )
        except _Budget:
            row["not_checked"] = "the call's six requests were used up"
            continue
        if reply.status == 404:
            row["attestations"] = []
            continue
        prov = _json(reply)
        if not isinstance(prov, dict):
            row["error"] = "PyPI answered HTTP " + str(reply.status) + " for the provenance"
            continue
        row["attestations"] = []
        for bundle in (prov.get("attestation_bundles") or [])[:2]:
            publisher = bundle.get("publisher") or {}
            for att in (bundle.get("attestations") or [])[:2]:
                item = {"publisher": publisher}
                row["attestations"].append(item)
                try:
                    envelope = att.get("envelope") or {}
                    material = att.get("verification_material") or {}
                    payload = _b64(envelope.get("statement"), "statement")
                    result = verify_attestation(
                        IN_TOTO,
                        payload,
                        _b64(envelope.get("signature"), "signature"),
                        _b64(material.get("certificate"), "certificate"),
                        material.get("transparency_entries") or [],
                    )
                    statement = result.pop("statement")
                    checks = result["checks"]
                    _subject_ok(
                        checks, statement, "sha256", str(row["sha256"]).lower(), f["filename"]
                    )
                    item["predicate_type"] = (statement or {}).get("predicateType")
                    _publisher(checks, publisher, result.get("identity") or {})
                    item.update(result)
                except _Bad as exc:
                    item["checks"] = [{"check": "readable", "ok": False, "detail": str(exc)}]


def _publisher(checks, publisher, identity):
    """PyPI's Trusted Publisher record against the certificate it vouches for."""
    if str(publisher.get("kind")) != "GitHub" or not publisher.get("repository"):
        return
    repo = _norm_repo(identity.get("source_repository_uri"))
    want = "github.com/" + str(publisher["repository"]).lower()
    signer = str(identity.get("build_signer_uri") or (identity.get("san") or [""])[0]).split(
        "@", 1
    )[0]
    workflow = str(publisher.get("workflow") or "")
    ok = repo == want and (not workflow or signer.endswith("/.github/workflows/" + workflow))
    _check(
        checks,
        "trusted_publisher",
        ok,
        "PyPI's trusted publisher "
        + publisher["repository"]
        + " "
        + workflow
        + " is the certificate's"
        if ok
        else "PyPI names publisher "
        + publisher["repository"]
        + " "
        + workflow
        + ", the certificate says "
        + (repo or "nothing")
        + " "
        + signer.rsplit("/", 1)[-1],
    )


# ------------------------------------------------------------------ the handler

CAS = _fulcio_cas()
REKOR = _rekor()


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: ecosystem, package, optionally version")
    ecosystem = str(payload.get("ecosystem") or "").strip().lower()
    if ecosystem not in ("npm", "pypi"):
        raise ValueError("ecosystem must be npm or pypi")
    package = str(payload.get("package") or "").strip()
    if not package or len(package) > 214 or any(c.isspace() for c in package) or ".." in package:
        raise ValueError("package must be a package name")
    if ecosystem == "npm" and package.startswith("@") and package.count("/") != 1:
        raise ValueError("a scoped npm package is @scope/name")
    if ecosystem == "pypi" and "/" in package:
        raise ValueError("a PyPI project name has no slash")
    version = str(payload.get("version") or "").strip() or None
    if version and (len(version) > 128 or "/" in version or any(c.isspace() for c in version)):
        raise ValueError("version must be a version string")
    wanted_file = str(payload.get("file") or "").strip() or None
    if wanted_file and (ecosystem != "pypi" or "/" in wanted_file):
        raise ValueError("file is a PyPI file name of the release")
    expect = {
        k: str(payload.get(k) or "").strip() or None for k in ("repository", "workflow", "ref")
    }

    state = {"fetches": 0}
    out = {"ecosystem": ecosystem, "package": package}
    try:
        if ecosystem == "npm":
            _npm(state, package, version, out)
            rows = out.get("attestations") or []
        else:
            _pypi(state, package, version, wanted_file, out)
            rows = [a for f in out.get("files") or [] for a in f.get("attestations") or []]
    except _Budget:
        out["detail"] = "the call's six requests were used up"
        rows = []
    if "verdict" in out:
        out["fetches"] = state["fetches"]
        return out

    provenance = [r for r in rows if r.get("predicate_type") in (SLSA_V1, SLSA_V02, PYPI_PUBLISH)]
    builds = []
    for row in provenance:
        if row.get("identity"):
            build = _identity_summary(row["identity"])
            row["build"] = build
            _expect(row["checks"], build, expect["repository"], expect["workflow"], expect["ref"])
            builds.append(build)
        row.pop("identity", None)
    for row in rows:
        row.pop("identity", None)
        row["ok"] = bool(row.get("checks")) and all(c["ok"] for c in row["checks"])
    expectation = [
        c for r in provenance for c in r.get("checks") or [] if c["check"].startswith("expected_")
    ]
    crypto_ok = rows and all(
        all(c["ok"] for c in r["checks"] if not c["check"].startswith("expected_")) for r in rows
    )
    registry_ok = all(s["ok"] for s in out.get("registry_signatures") or [])
    if ecosystem == "pypi":
        missing = [f["filename"] for f in out.get("files") or [] if f.get("attestations") == []]
        if missing:
            out["files_without_provenance"] = missing
    if not provenance:
        out["verdict"] = "no_provenance"
    elif not crypto_ok or not registry_ok:
        out["verdict"] = "invalid"
    elif not all(c["ok"] for c in expectation):
        out["verdict"] = "expectation_mismatch"
    else:
        out["verdict"] = "verified"
    if builds:
        first = builds[0]
        out["built_from"] = {
            "repository": first.get("source_repository_uri"),
            "commit": first.get("source_repository_digest"),
            "ref": first.get("source_repository_ref"),
            "workflow": (first.get("build_signer_uri") or "").split("@", 1)[0] or None,
            "trigger": first.get("build_trigger"),
            "runner": first.get("runner_environment"),
            "run": first.get("run_invocation_uri"),
            "issuer": first.get("issuer"),
        }
        out["built_from"] = {k: v for k, v in out["built_from"].items() if v}
    out["not_checked"] = ["embedded SCTs (Certificate Transparency)", "certificate revocation"]
    out["fetches"] = state["fetches"]
    return out
