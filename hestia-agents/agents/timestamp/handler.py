"""timestamp.verify@v1: does this RFC 3161 timestamp token prove these bytes existed at that time?

Give `token`: a TimeStampResp or a TimeStampToken (DER, base64), as a TSA returns it. Give the data
it should cover as `data` (text), `data_base64`, or `hash` (hex, the digest itself); without them
the token is checked on its own and the imprint is reported, not compared.

Everything is checked here, with no network:
  - TSTInfo (RFC 3161 section 2.4.2): version, policy, the message imprint and its algorithm, serial
    number, genTime (fractions read), accuracy, ordering, nonce, the TSA's name;
  - the CMS SignedData (RFC 5652): content type id-ct-TSTInfo; the signed attributes' content type
    and message digest (over the TSTInfo bytes); signingCertificate or signingCertificateV2 (RFC
    5035) naming the signer's certificate by its hash; the signature over the signed attributes,
    with RSA (PKCS #1 v1.5 or PSS) or ECDSA (P-256, P-384), SHA-1 to SHA-512;
  - the signer's certificate: the time-stamping extended key usage (RFC 3161 2.3), valid at genTime;
    then its chain, each certificate signed by the next and valid at genTime, up to a trusted root:
    the pinned roots below (Sigstore's TSA, DigiCert Trusted Root G4, FreeTSA), matched by public
    key so a cross-signed copy counts, or the SPKI SHA-256 values you pass as `trusted_spki`.

Verdict verified (signature, chain and, when given, the data all hold), verified_untrusted (all
holds but the chain ends at a root you did not name and that is not pinned), imprint_mismatch (the
token is good but covers other data), or invalid. Not checked: revocation (CRL, OCSP), and whether
the TSA's clock was right; a timestamp is that TSA's word, signed. SHA-1 imprints are reported as
weak.
"""

import base64
import hashlib

TRUSTED_ROOTS = {
    "Sigstore TSA (sigstore-tsa-selfsigned, sigstore/root-signing trusted_root.json)": (
        "MIIB9zCCAXygAwIBAgIUV7f0GLDOoEzIh8LXSW80OJiUp14wCgYIKoZIzj0EAwMwOTEVMBMGA1UEChMMc2lnc3Rv"
        "cmUuZGV2MSAwHgYDVQQDExdzaWdzdG9yZS10c2Etc2VsZnNpZ25lZDAeFw0yNTA0MDgwNjU5NDNaFw0zNTA0MDYw"
        "NjU5NDNaMDkxFTATBgNVBAoTDHNpZ3N0b3JlLmRldjEgMB4GA1UEAxMXc2lnc3RvcmUtdHNhLXNlbGZzaWduZWQw"
        "djAQBgcqhkjOPQIBBgUrgQQAIgNiAAQUQNtfRT/ou3YATa6wB/kKTe70cfJwyRIBovMnt8RcJph/COE82uyS6Fmp"
        "pLLL1VBPGcPfpQPYJNXzWwi8icwhKQ6W/Qe2h3oebBb2FHpwNJDqo+TMaC/tdfkv/ElJB72jRTBDMA4GA1UdDwEB"
        "/wQEAwIBBjASBgNVHRMBAf8ECDAGAQH/AgEAMB0GA1UdDgQWBBSY7AHvf7tR/9SVHm+KiJhTB4nOvzAKBggqhkjO"
        "PQQDAwNpADBmAjEAwGEGrfGZR1cen1R8/DTVMI943LssZmJRtDp/i7SfGHmGRP6gRbuj9vOK3b67Z0QQAjEAuT2H"
        "673LQEaHTcyQSZrkp4mX7WwkmF+sVbkYY5mXN+RMH13KUEHHOqASaemYWK/E"
    ),
    "DigiCert Trusted Root G4 (cacerts.digicert.com, sha256 552F7BDC...9988)": (
        "MIIFkDCCA3igAwIBAgIQBZsbV56OITLiOQe9p3d1XDANBgkqhkiG9w0BAQwFADBiMQswCQYDVQQGEwJVUzEVMBMG"
        "A1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3d3cuZGlnaWNlcnQuY29tMSEwHwYDVQQDExhEaWdpQ2VydCBU"
        "cnVzdGVkIFJvb3QgRzQwHhcNMTMwODAxMTIwMDAwWhcNMzgwMTE1MTIwMDAwWjBiMQswCQYDVQQGEwJVUzEVMBMG"
        "A1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3d3cuZGlnaWNlcnQuY29tMSEwHwYDVQQDExhEaWdpQ2VydCBU"
        "cnVzdGVkIFJvb3QgRzQwggIiMA0GCSqGSIb3DQEBAQUAA4ICDwAwggIKAoICAQC/5pBzaN675F1KPDAiMGkz7MKn"
        "JS7JIT3yithZwuEppz1Yq3aaza57G4QNxDAf8xukOBbrVsaXbR2rsnnyyhHS5F/WBTxSD1Ifxp4VpX6+n6lXFllV"
        "cq9ok3DCsrp1mWpzMpTREEQQLt+C8weE5nQ7bXHiLQwb7iDVySAdYyktzuxeTsiT+CFhmzTrBcZe7FsavOvJz82s"
        "NEBfsXpm7nfISKhmV1efVFiODCu3T6cw2Vbuyntd463JT17lNecxy9qTXtyOj4DatpGYQJB5w3jHtrHEtWoYOAMQ"
        "jdjUN6QuBX2I9YI+EJFwq1WCQTLX2wRzKm6RAXwhTNS8rhsDdV14Ztk6MUSaM0C/CNdaSaTC5qmgZ92kJ7yhTzm1"
        "EVgX9yRcRo9k98FpiHaYdj1ZXUJ2h4mXaXpI8OCiEhtmmnTK3kse5w5jrubU75KSOp493ADkRSWJtppEGSt+wJS0"
        "0mFt6zPZxd9LBADMfRyVw4/3IbKyEbe7f/LVjHAsQWCqsWMYRJUadmJ+9oCw++hkpjPRiQfhvbfmQ6QYuKZ3AeEP"
        "lAwhHbJUKSWJbOUOUlFHdL4mrLZBdd56rF+NP8m800ERElvlEFDrMcXKchYiCd98THU/Y+whX8QgUWtvsauGi0/C"
        "1kVfnSD8oR7FwI+isX4KJpn15GkvmB0t9dmpsh3lGwIDAQABo0IwQDAPBgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB"
        "/wQEAwIBhjAdBgNVHQ4EFgQU7NfjgtJxXWRM3y5nP+e6mK4cD08wDQYJKoZIhvcNAQEMBQADggIBALth2X2pbL4X"
        "xJEbw6GiAI3jZGgPVs93rnD5/ZpKmbnJeFwMDF/k5hQpVgs2SV1EY+CtnJYYZhsjDT156W1r1lT40jzBQ0CuHVD1"
        "UvyQO7uYmWlrx8GnqGikJ9yd+SeuMIW59mdNOj6PWTkiU0TryF0Dyu1Qen1iIQqAyHNm0aAFYF/opbSnr6j3bTWc"
        "fFqK1qI4mfN4i/RN0iAL3gTujJtHgXINwBQy7zBZLq7gcfJW5GqXb5JQbZaNaHqasjYUegbyJLkJEVDXCLG4iXqE"
        "I2FCKeWjzaIgQdfRnGTZ6iahixTXTBmyUEFxPT9NcCOGDErcgdLMMpSEDQgJlxxPwO5rIHQw0uA5NBCFIRUBCOhV"
        "Mt5xSdkoF1BN5r5N0XWs0Mr7QbhDparTwwVETyw2m+L64kW4I1NsBm9nVX9GtUw/bihaeSbSpKhil9Ie4u1Ki7wb"
        "/UdKDd9nZn6yW0HQO+T0O/QEY+nvwlQAUaCKKsnOeMzV6ocEGLPOr0mIr/OSmbaz5mEP0oUA51Aa5BuVnRmhuZyx"
        "m7EAHu/QD09CbMkKvO5D+jpxpchNJqU1/YldvIViHTLSoCtU7ZpXwdv6EM8Zt4tKG48BtieVU+i2iW1bvGjUI+iL"
        "UaJW+fCmgKDWHrO8Dw9TdSmq6hN35N6MgSGtBxBHEa2HPQfRdbzP82Z+"
    ),
    "Free TSA Root CA (freetsa.org/files/cacert.pem, sha256 A6379E7C...AABC)": (
        "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"
        "2AWv2pk="
    ),
}


class _Bad(ValueError):
    """The token or a certificate in it cannot be read or does not verify."""


# ------------------------------------------------------------------ DER


def _tlv(data, i):
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
    out, i = [], start
    while i < end:
        tag, cs, ce = _tlv(data, i)
        out.append((tag, cs, ce, i))
        i = ce
    return out


def _oid_text(raw):
    if not raw:
        return ""
    parts = [str(min(raw[0] // 40, 2)), str(raw[0] - 40 * min(raw[0] // 40, 2))]
    value = 0
    for byte in raw[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(str(value))
            value = 0
    return ".".join(parts)


OID = {
    "rsa": "2a864886f70d010101",
    "rsa-pss": "2a864886f70d01010a",
    "ec": "2a8648ce3d0201",
    "signed-data": "2a864886f70d010702",
    "tst-info": "2a864886f70d0109100104",
    "content-type": "2a864886f70d010903",
    "message-digest": "2a864886f70d010904",
    "signing-time": "2a864886f70d010905",
    "signing-cert": "2a864886f70d010910020c",
    "signing-cert-v2": "2a864886f70d010910022f",
    "eku": "551d25",
    "basic": "551d13",
    "time-stamping": "2b06010505070308",
    "mgf1": "2a864886f70d010108",
}
HASHES = {
    "2b0e03021a": "sha1",
    "608648016503040201": "sha256",
    "608648016503040202": "sha384",
    "608648016503040203": "sha512",
}
SIGNATURES = {  # signature algorithm OID -> (key type, hash)
    "2a864886f70d010105": ("rsa", "sha1"),
    "2a864886f70d01010b": ("rsa", "sha256"),
    "2a864886f70d01010c": ("rsa", "sha384"),
    "2a864886f70d01010d": ("rsa", "sha512"),
    "2a8648ce3d0401": ("ec", "sha1"),
    "2a8648ce3d040302": ("ec", "sha256"),
    "2a8648ce3d040303": ("ec", "sha384"),
    "2a8648ce3d040304": ("ec", "sha512"),
}
CURVE_OIDS = {"2a8648ce3d030107": "P-256", "2b81040022": "P-384"}
DIGEST_INFO = {
    "sha1": bytes.fromhex("3021300906052b0e03021a05000414"),
    "sha256": bytes.fromhex("3031300d060960864801650304020105000420"),
    "sha384": bytes.fromhex("3041300d060960864801650304020205000430"),
    "sha512": bytes.fromhex("3051300d060960864801650304020305000440"),
}


def _days(year, month, day):
    year -= month <= 2
    era = year // 400
    yoe = year - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def _time(tag, raw):
    """UTCTime or GeneralizedTime (fractions allowed, Z only) as (unix seconds, fraction text)."""
    text = raw.decode("ascii", "replace")
    if not text.endswith("Z"):
        raise _Bad("a time is not in UTC (no Z)")
    body, fraction = text[:-1], ""
    if "." in body:
        body, fraction = body.split(".", 1)
        if not fraction.isdigit():
            raise _Bad("a time has a bad fraction")
    if tag == 0x17 and len(body) == 12 and body.isdigit():
        year = int(body[:2])
        year += 2000 if year < 50 else 1900
        rest = body[2:]
    elif tag == 0x18 and len(body) == 14 and body.isdigit():
        year, rest = int(body[:4]), body[4:]
    else:
        raise _Bad("a time is not UTCTime or GeneralizedTime")
    mo, d, h, mi, s = (int(rest[k : k + 2]) for k in range(0, 10, 2))
    if not (1 <= mo <= 12 and 1 <= d <= 31 and h <= 23 and mi <= 59 and s <= 60):
        raise _Bad("a time is out of range")
    return _days(year, mo, d) * 86400 + h * 3600 + mi * 60 + s, fraction


def _iso(seconds, fraction=""):
    days, rem = divmod(int(seconds), 86400)
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + 3 if mp < 10 else mp - 9
    year = yoe + era * 400 + (month <= 2)
    stamp = (
        f"{year:04d}-{month:02d}-{day:02d}T{rem // 3600:02d}:{rem // 60 % 60:02d}:{rem % 60:02d}"
    )
    return stamp + ("." + fraction if fraction else "") + "Z"


def _name_text(data, start, end):
    """A distinguished name as CN=..., O=... for reading (the bytes are what is compared)."""
    short = {"550403": "CN", "55040a": "O", "55040b": "OU", "550406": "C"}
    parts = []
    try:
        for rdn in _items(data, start, end):
            for attr in _items(data, rdn[1], rdn[2]):
                fields = _items(data, attr[1], attr[2])
                label = short.get(data[fields[0][1] : fields[0][2]].hex())
                if label:
                    parts.append(
                        label + "=" + data[fields[1][1] : fields[1][2]].decode("utf-8", "replace")
                    )
    except _Bad:
        return ""
    return ", ".join(parts)


def _key(data, start, end):
    """(key, SPKI DER) of a SubjectPublicKeyInfo."""
    spki = None
    parts = _items(data, start, end)
    if len(parts) != 2 or parts[0][0] != 0x30 or parts[1][0] != 0x03:
        raise _Bad("not a SubjectPublicKeyInfo")
    algo = _items(data, parts[0][1], parts[0][2])
    kind = data[algo[0][1] : algo[0][2]].hex()
    bits = data[parts[1][1] + 1 : parts[1][2]]
    if kind in (OID["rsa"], OID["rsa-pss"]):
        tag, s, e = _tlv(bits, 0)
        nums = _items(bits, s, e)
        return (
            "rsa",
            int.from_bytes(bits[nums[0][1] : nums[0][2]], "big"),
            int.from_bytes(bits[nums[1][1] : nums[1][2]], "big"),
        ), spki
    if kind == OID["ec"]:
        curve = CURVE_OIDS.get(data[algo[1][1] : algo[1][2]].hex()) if len(algo) > 1 else None
        if curve is None:
            raise _Bad("an EC key on a curve this agent does not read (P-256 and P-384 only)")
        size = CURVES[curve]["size"]
        if len(bits) != 1 + 2 * size or bits[0] != 4:
            raise _Bad("an EC key that is not an uncompressed point")
        return (
            "ec",
            curve,
            int.from_bytes(bits[1 : 1 + size], "big"),
            int.from_bytes(bits[1 + size :], "big"),
        ), spki
    raise _Bad("a key type this agent does not read")


def parse_cert(der):
    tag, start, end = _tlv(der, 0)
    if tag != 0x30:
        raise _Bad("a certificate is not a DER SEQUENCE")
    der = der[:end]
    top = _items(der, start, end)
    if len(top) != 3:
        raise _Bad("a certificate needs tbsCertificate, algorithm and signature")
    tbs = _items(der, top[0][1], top[0][2])
    if tbs and tbs[0][0] == 0xA0:
        tbs = tbs[1:]
    validity = _items(der, tbs[3][1], tbs[3][2])
    alg = _items(der, top[1][1], top[1][2])
    spki_item = tbs[5]
    key, _ = _key(der, spki_item[1], spki_item[2])
    cert = {
        "der": der,
        "tbs": der[top[0][3] : top[0][2]],
        "sig_alg": der[alg[0][1] : alg[0][2]].hex(),
        "sig_params": der[alg[1][3] : alg[1][2]] if len(alg) > 1 else b"",
        "signature": der[top[2][1] + 1 : top[2][2]],
        "serial": der[tbs[0][1] : tbs[0][2]],
        "issuer": der[tbs[2][3] : tbs[2][2]],
        "subject": der[tbs[4][3] : tbs[4][2]],
        "subject_text": _name_text(der, tbs[4][1], tbs[4][2]),
        "issuer_text": _name_text(der, tbs[2][1], tbs[2][2]),
        "not_before": _time(validity[0][0], der[validity[0][1] : validity[0][2]])[0],
        "not_after": _time(validity[1][0], der[validity[1][1] : validity[1][2]])[0],
        "key": key,
        "spki_sha256": hashlib.sha256(der[spki_item[3] : spki_item[2]]).hexdigest(),
        "eku": [],
        "eku_critical": False,
        "ca": None,
    }
    for item in tbs[6:]:
        if item[0] != 0xA3:
            continue
        seq = _items(der, item[1], item[2])[0]
        for ext in _items(der, seq[1], seq[2]):
            fields = _items(der, ext[1], ext[2])
            oid = der[fields[0][1] : fields[0][2]].hex()
            critical = len(fields) == 3 and der[fields[1][1] : fields[1][2]] == b"\xff"
            value = der[fields[-1][1] : fields[-1][2]]
            if oid == OID["eku"]:
                t, s, e = _tlv(value, 0)
                cert["eku"] = [value[p[1] : p[2]].hex() for p in _items(value, s, e)]
                cert["eku_critical"] = critical
            elif oid == OID["basic"]:
                t, s, e = _tlv(value, 0)
                inner = _items(value, s, e)
                cert["ca"] = (
                    bool(inner)
                    and inner[0][0] == 0x01
                    and value[inner[0][1] : inner[0][2]] == b"\xff"
                )
    return cert


# ------------------------------------------------------------------ signatures

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
    m = 3 * (x - zsq) * (x + zsq) % p
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


def _ecdsa(key, digest, signature):
    _, curve, x, y = key
    c = CURVES[curve]
    p, n = c["p"], c["n"]
    try:
        tag, s0, e0 = _tlv(signature, 0)
        parts = _items(signature, s0, e0)
        r, s = (int.from_bytes(signature[t[1] : t[2]], "big") for t in parts)
    except (_Bad, ValueError):
        return False
    if tag != 0x30 or len(parts) != 2 or not (0 < r < n and 0 < s < n):
        return False
    if (y * y - x * x * x + 3 * x - c["b"]) % p:
        return False
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


def _mgf1(seed, length, name):
    out, counter = b"", 0
    while len(out) < length:
        out += hashlib.new(name, seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:length]


def _rsa(key, name, message, signature, pss=None):
    _, n, e = key
    k = (n.bit_length() + 7) // 8
    if n.bit_length() < 2048 or len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False
    m = pow(s, e, n)
    digest = hashlib.new(name, message).digest()
    if pss is None:
        t = DIGEST_INFO[name] + digest
        return m.to_bytes(k, "big") == b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    mgf_name, salt_len = pss
    h_len = len(digest)
    em_bits = n.bit_length() - 1
    em_len = (em_bits + 7) // 8
    if m.bit_length() > em_bits:
        return False
    em = m.to_bytes(em_len, "big")
    if em_len < h_len + salt_len + 2 or em[-1] != 0xBC:
        return False
    masked, h = em[: em_len - h_len - 1], em[em_len - h_len - 1 : -1]
    zero_bits = 8 * em_len - em_bits
    if zero_bits and masked[0] >> (8 - zero_bits):
        return False
    db = bytearray(a ^ b for a, b in zip(masked, _mgf1(h, len(masked), mgf_name), strict=True))
    if zero_bits:
        db[0] &= 0xFF >> zero_bits
    pad = em_len - h_len - salt_len - 2
    if any(db[:pad]) or db[pad] != 0x01:
        return False
    salt = bytes(db[len(db) - salt_len :]) if salt_len else b""
    return hashlib.new(name, b"\x00" * 8 + digest + salt).digest() == h


def _pss_params(raw):
    """(hash, mgf hash, salt length) of RSASSA-PSS-params; defaults SHA-1, MGF1-SHA-1, 20."""
    name, mgf, salt = "sha1", "sha1", 20
    if not raw or raw[0] != 0x30:
        return name, mgf, salt
    tag, s, e = _tlv(raw, 0)
    for item in _items(raw, s, e):
        inner = raw[item[1] : item[2]]
        if item[0] == 0xA0:
            t, s1, e1 = _tlv(inner, 0)
            name = HASHES.get(
                inner[_items(inner, s1, e1)[0][1] : _items(inner, s1, e1)[0][2]].hex(), name
            )
        elif item[0] == 0xA1:
            t, s1, e1 = _tlv(inner, 0)
            parts = _items(inner, s1, e1)
            if len(parts) > 1:
                t2, s2, e2 = _tlv(inner, parts[1][3])
                hp = _items(inner, s2, e2)
                mgf = HASHES.get(inner[hp[0][1] : hp[0][2]].hex(), mgf)
        elif item[0] == 0xA2:
            t, s1, e1 = _tlv(inner, 0)
            salt = int.from_bytes(inner[s1:e1], "big")
    return name, mgf, salt


def verify(key, sig_alg, sig_params, message, signature, digest_name=None):
    """Does `signature` by `key` cover `message` under the named algorithm?"""
    if sig_alg == OID["rsa-pss"]:
        if key[0] != "rsa":
            return False
        name, mgf, salt = _pss_params(sig_params)
        return _rsa(key, name, message, signature, (mgf, salt))
    if sig_alg == OID["rsa"]:  # a CMS signer's rsaEncryption: the hash is the digest algorithm's
        return (
            key[0] == "rsa"
            and digest_name in DIGEST_INFO
            and _rsa(key, digest_name, message, signature)
        )
    kind = SIGNATURES.get(sig_alg)
    if kind is None or kind[0] != key[0]:
        return False
    if kind[0] == "rsa":
        return _rsa(key, kind[1], message, signature)
    return _ecdsa(key, hashlib.new(kind[1], message).digest(), signature)


# ------------------------------------------------------------------ CMS and TSTInfo


def _b64(text, where):
    if not isinstance(text, str) or not text.strip():
        raise ValueError(where + " must be base64")
    t = "".join(text.split()).replace("-", "+").replace("_", "/")
    try:
        return base64.b64decode(t + "=" * (-len(t) % 4), validate=True)
    except ValueError:
        raise ValueError(where + " is not base64") from None


def unwrap(raw):
    """(status text, TimeStampToken DER) from a TimeStampResp, or the token itself."""
    tag, s, e = _tlv(raw, 0)
    if tag != 0x30:
        raise _Bad("the token is not a DER SEQUENCE")
    top = _items(raw, s, e)
    if top and top[0][0] == 0x06:
        return None, raw[:e]
    if not top or top[0][0] != 0x30:
        raise _Bad("neither a TimeStampResp nor a TimeStampToken")
    status = _items(raw, top[0][1], top[0][2])
    code = int.from_bytes(raw[status[0][1] : status[0][2]], "big")
    text = {
        0: "granted",
        1: "grantedWithMods",
        2: "rejection",
        3: "waiting",
        4: "revocationWarning",
        5: "revocationNotification",
    }.get(code, "status " + str(code))
    if code not in (0, 1) or len(top) < 2:
        raise _Bad("the TSA did not grant this request: " + text)
    return text, raw[top[1][3] : top[1][2]]


def parse_token(token):
    tag, s, e = _tlv(token, 0)
    info = _items(token, s, e)
    if token[info[0][1] : info[0][2]].hex() != OID["signed-data"] or info[1][0] != 0xA0:
        raise _Bad("the token is not CMS SignedData")
    tag, s, e = _tlv(token, info[1][1])
    sd = _items(token, s, e)
    encap = _items(token, sd[2][1], sd[2][2])
    if token[encap[0][1] : encap[0][2]].hex() != OID["tst-info"]:
        raise _Bad("the signed content is not id-ct-TSTInfo")
    t, os_, oe = _tlv(token, encap[1][1])
    content = token[os_:oe]
    certs, rest = [], sd[3:]
    if rest and rest[0][0] == 0xA0:
        for c in _items(token, rest[0][1], rest[0][2]):
            if c[0] == 0x30:
                certs.append(token[c[3] : c[2]])
        rest = rest[1:]
    if rest and rest[0][0] == 0xA1:
        rest = rest[1:]
    if not rest or rest[0][0] != 0x31:
        raise _Bad("no signerInfos")
    signers = _items(token, rest[0][1], rest[0][2])
    if len(signers) != 1:
        raise _Bad(
            "a timestamp token has exactly one signer (RFC 3161 2.4.2); this one has "
            + str(len(signers))
        )
    si = _items(token, signers[0][1], signers[0][2])
    sid = token[si[1][3] : si[1][2]]
    digest_alg = HASHES.get(
        token[
            _items(token, si[2][1], si[2][2])[0][1] : _items(token, si[2][1], si[2][2])[0][2]
        ].hex()
    )
    if si[3][0] != 0xA0:
        raise _Bad("the signer has no signed attributes")
    attrs_der = b"\x31" + token[si[3][3] + 1 : si[3][2]]
    attrs = {}
    for a in _items(token, si[3][1], si[3][2]):
        parts = _items(token, a[1], a[2])
        values = _items(token, parts[1][1], parts[1][2])
        attrs[token[parts[0][1] : parts[0][2]].hex()] = (
            token[values[0][3] : values[0][2]] if values else b""
        )
    sig_alg_items = _items(token, si[4][1], si[4][2])
    sig_alg = token[sig_alg_items[0][1] : sig_alg_items[0][2]].hex()
    sig_params = token[sig_alg_items[1][3] : sig_alg_items[1][2]] if len(sig_alg_items) > 1 else b""
    signature = token[si[5][1] : si[5][2]]
    return {
        "content": content,
        "certs": certs,
        "sid": sid,
        "digest_alg": digest_alg,
        "attrs": attrs,
        "attrs_der": attrs_der,
        "sig_alg": sig_alg,
        "sig_params": sig_params,
        "signature": signature,
    }


def parse_tst_info(content):
    tag, s, e = _tlv(content, 0)
    f = _items(content, s, e)
    imprint = _items(content, f[2][1], f[2][2])
    alg = _items(content, imprint[0][1], imprint[0][2])
    gen = _time(f[4][0], content[f[4][1] : f[4][2]])
    out = {
        "version": int.from_bytes(content[f[0][1] : f[0][2]], "big"),
        "policy": _oid_text(content[f[1][1] : f[1][2]]),
        "hash_algorithm": HASHES.get(content[alg[0][1] : alg[0][2]].hex(), "unknown"),
        "imprint": content[imprint[1][1] : imprint[1][2]].hex(),
        "serial_number": content[f[3][1] : f[3][2]].hex(),
        "gen_time": _iso(gen[0], gen[1]),
        "gen_time_unix": gen[0],
        "ordering": False,
    }
    for item in f[5:]:
        body = content[item[1] : item[2]]
        if item[0] == 0x30:
            acc, labels = {}, {0x02: "seconds", 0x80: "millis", 0x81: "micros"}
            for part in _items(content, item[1], item[2]):
                acc[labels.get(part[0], "?")] = int.from_bytes(content[part[1] : part[2]], "big")
            out["accuracy"] = acc
        elif item[0] == 0x01:
            out["ordering"] = body == b"\xff"
        elif item[0] == 0x02:
            out["nonce"] = body.hex()
        elif item[0] == 0xA0:
            inner = _items(content, item[1], item[2])
            if inner and inner[0][0] == 0xA4:
                name = _items(content, inner[0][1], inner[0][2])[0]
                out["tsa"] = _name_text(content, name[1], name[2])
    return out


def _ess_hash(attrs, kind):
    """(hash name, cert hash) the signingCertificate(V2) attribute names, or None."""
    raw = attrs.get(OID[kind])
    if raw is None:
        return None
    tag, s, e = _tlv(raw, 0)
    ids = _items(raw, _items(raw, s, e)[0][1], _items(raw, s, e)[0][2])
    first = _items(raw, ids[0][1], ids[0][2])
    if kind == "signing-cert":
        return "sha1", raw[first[0][1] : first[0][2]]
    name = "sha256"
    if first[0][0] == 0x30:
        name = HASHES.get(
            raw[
                _items(raw, first[0][1], first[0][2])[0][1] : _items(raw, first[0][1], first[0][2])[
                    0
                ][2]
            ].hex(),
            "?",
        )
        first = first[1:]
    return name, raw[first[0][1] : first[0][2]]


def _matches_sid(cert, sid):
    tag, s, e = _tlv(sid, 0)
    if (
        tag == 0x80
    ):  # subjectKeyIdentifier: compared through the certificate's own SKI extension bytes
        return sid[s:e] in cert["der"]
    parts = _items(sid, s, e)
    return (
        len(parts) == 2
        and sid[parts[0][3] : parts[0][2]] == cert["issuer"]
        and sid[parts[1][1] : parts[1][2]] == cert["serial"]
    )


def _roots():
    out = []
    for name, chunks in TRUSTED_ROOTS.items():
        cert = parse_cert(base64.b64decode("".join(chunks)))
        cert["pinned_as"] = name
        out.append(cert)
    return out


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: token, and data, data_base64 or hash")
    raw = _b64(payload.get("token"), "token")
    if len(raw) > 64 * 1024:
        raise ValueError("token is larger than 64 KiB")
    given = [k for k in ("data", "data_base64", "hash") if payload.get(k) is not None]
    if len(given) > 1:
        raise ValueError("give at most one of data, data_base64 or hash")
    trusted = payload.get("trusted_spki") or []
    if not isinstance(trusted, list) or not all(
        isinstance(t, str) and len(t) == 64 for t in trusted
    ):
        raise ValueError(
            "trusted_spki must be a list of SHA-256 hex digests of SubjectPublicKeyInfo"
        )
    trusted = {t.lower() for t in trusted}
    checks = []
    out = {"checks": checks}

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    try:
        status, token = unwrap(raw)
        if status:
            out["status"] = status
        cms = parse_token(token)
        tst = parse_tst_info(cms["content"])
    except (_Bad, IndexError) as exc:
        out.update(verdict="invalid", detail="the token cannot be read: " + str(exc)[:200])
        return out
    out["tst_info"] = {k: v for k, v in tst.items() if k != "gen_time_unix"}
    gen = tst["gen_time_unix"]
    attrs = cms["attrs"]
    check(
        "content_type",
        attrs.get(OID["content-type"], b"")[2:] == bytes.fromhex(OID["tst-info"]),
        "the signed content type attribute is id-ct-TSTInfo",
    )
    digest = hashlib.new(cms["digest_alg"], cms["content"]).digest() if cms["digest_alg"] else b""
    check(
        "message_digest",
        attrs.get(OID["message-digest"], b"")[2:] == digest and digest,
        "the signed message digest is the " + str(cms["digest_alg"]) + " of the TSTInfo",
    )

    pool = [parse_cert(c) for c in cms["certs"]]
    roots = _roots()
    signer = next((c for c in pool if _matches_sid(c, cms["sid"])), None)
    if signer is None:
        signer = next((c for c in roots if _matches_sid(c, cms["sid"])), None)
    if not check(
        "signer_certificate",
        signer is not None,
        "the token carries its signer's certificate"
        if signer
        else "the signer's certificate is not in the token (ask the TSA with certReq true)",
    ):
        out.update(verdict="invalid")
        return out
    out["signer"] = signer["subject_text"]
    ess = _ess_hash(attrs, "signing-cert-v2") or _ess_hash(attrs, "signing-cert")
    check(
        "signing_certificate",
        ess is not None
        and ess[0] in ("sha1", "sha256", "sha384", "sha512")
        and hashlib.new(ess[0], signer["der"]).digest() == ess[1],
        "the signed attributes name this certificate by its " + (ess[0] if ess else "hash"),
    )
    check(
        "signature",
        verify(
            signer["key"],
            cms["sig_alg"],
            cms["sig_params"],
            cms["attrs_der"],
            cms["signature"],
            cms["digest_alg"],
        ),
        "the TSA's signature over the signed attributes verifies",
    )
    check(
        "time_stamping_key_usage",
        signer["eku"] == [OID["time-stamping"]] and signer["eku_critical"],
        "the certificate is for time stamping only, critical (RFC 3161 2.3)"
        if signer["eku"] == [OID["time-stamping"]] and signer["eku_critical"]
        else "the certificate's extended key usage is not exactly a critical id-kp-timeStamping",
    )
    check(
        "signer_valid_at_gen_time",
        signer["not_before"] <= gen <= signer["not_after"],
        "valid " + _iso(signer["not_before"]) + " to " + _iso(signer["not_after"]),
    )

    chain, current, anchor = [signer["subject_text"]], signer, None
    for _ in range(6):
        if current["spki_sha256"] in trusted:
            anchor = "your trusted_spki " + current["spki_sha256"][:16] + "…"
            break
        pinned = next((r for r in roots if r["spki_sha256"] == current["spki_sha256"]), None)
        if pinned is not None and current is not signer:
            anchor = pinned["pinned_as"]
            break
        issuer = None
        for cand in pool + roots:
            if (
                cand["subject"] == current["issuer"]
                and cand is not current
                and verify(
                    cand["key"],
                    current["sig_alg"],
                    current["sig_params"],
                    current["tbs"],
                    current["signature"],
                )
            ):
                issuer = cand
                break
        if issuer is None:
            if current["issuer"] == current["subject"] and verify(
                current["key"],
                current["sig_alg"],
                current["sig_params"],
                current["tbs"],
                current["signature"],
            ):
                out["untrusted_root"] = {
                    "subject": current["subject_text"],
                    "spki_sha256": current["spki_sha256"],
                }
            else:
                check(
                    "chain",
                    False,
                    "no certificate in the token or the pinned roots signs "
                    + current["subject_text"],
                )
            break
        if not check(
            "chain_valid_at_gen_time",
            issuer["not_before"] <= gen <= issuer["not_after"] or "pinned_as" in issuer,
            issuer["subject_text"] + " valid at genTime",
        ):
            break
        if issuer.get("ca") is False:
            check("issuer_is_ca", False, issuer["subject_text"] + " is not a CA")
            break
        chain.append(issuer["subject_text"])
        current = issuer
        if "pinned_as" in issuer:
            anchor = issuer["pinned_as"]
            break
    out["chain"] = chain
    if anchor:
        out["trusted_root"] = anchor

    if given:
        if given[0] == "hash":
            want = str(payload["hash"]).lower().removeprefix("0x")
        else:
            data = (
                payload["data"].encode("utf-8")
                if given[0] == "data"
                else _b64(payload["data_base64"], "data_base64")
            )
            want = (
                hashlib.new(tst["hash_algorithm"], data).hexdigest()
                if tst["hash_algorithm"] != "unknown"
                else ""
            )
        out["imprint_matches"] = want == tst["imprint"]
    if tst["hash_algorithm"] == "sha1":
        out["warning"] = "the imprint is SHA-1: a collision can make two documents share it"
    failed = [c for c in checks if not c["ok"]]
    if failed:
        out["verdict"] = "invalid"
    elif out.get("imprint_matches") is False:
        out["verdict"] = "imprint_mismatch"
    elif not anchor:
        out["verdict"] = "verified_untrusted"
    else:
        out["verdict"] = "verified"
    out["not_checked"] = ["revocation (CRL, OCSP)", "the TSA's clock"]
    return out
