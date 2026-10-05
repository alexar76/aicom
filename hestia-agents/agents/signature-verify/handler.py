"""Ed25519 signature checks for the documents this ecosystem signs, and for raw bytes.

Formats (`format`, or detected from the document):

  raw            message bytes (utf8 / hex / base64) + signature + public key
  jcs            the RFC 8785 form of a JSON document (minus `exclude` keys) + signature + key
  eddsa-jcs-2022 a W3C verifiable credential with a Data Integrity proof (AWR receipts)
  histor         a HISTOR document: JCS of the body, signature {alg, verificationMethod, value}
  hestia         a HESTIA agent's answer: result + signature, over the input you sent
  hub-receipt    an AIMarket hub receipt (v1 / v2 canonical)
  hub-object     an object a hub or hearth signs whole (its .well-known, a compute receipt)

Give the signer's key as `public_key` (hex, base64, did:key or z6Mk…) to check WHO signed.
Without it the key the document carries is used, and the answer says so: a signature under
a key the document names itself proves only that nothing changed after signing.

Pure Python Ed25519 (RFC 8032), cofactorless like OpenSSL, refusing non-canonical points,
S >= L and small-order keys. Numbers in JCS documents must be integers (AWR and HISTOR are).
"""

import hashlib
import json

# ------------------------------------------------------------------ Ed25519

_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
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


def ed25519_verify(public, message, signature):
    """(ok, reason) per RFC 8032 5.1.7, cofactorless; small-order keys refused."""
    if len(public) != 32:
        return False, "public key must be 32 bytes"
    if len(signature) != 64:
        return False, "signature must be 64 bytes"
    a = _decode(public)
    if a is None:
        return False, "public key is not a valid curve point"
    small = a
    for _ in range(3):
        small = _double(small)
    if _same(small, _IDENTITY):
        return False, "public key has small order: it verifies forged signatures"
    r = _decode(signature[:32])
    if r is None:
        return False, "signature R is not a valid curve point"
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False, "signature S is not reduced (S >= L)"
    k = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    neg_a = ((-a[0]) % _Q, a[1], a[2], (-a[3]) % _Q)
    if _same(_two_mul(s, _B, k, neg_a), r):
        return True, "signature verifies"
    return False, "signature does not verify for this key and these bytes"


# ------------------------------------------------------------------ encodings

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_ED25519_MULTICODEC = b"\xed\x01"


def _b58decode(text):
    number = 0
    for char in text:
        index = _B58.find(char)
        if index < 0:
            raise ValueError("not base58btc")
        number = number * 58 + index
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + body


def _b58encode(raw):
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = _B58[rem] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def _b64decode(text):
    text = text.strip().replace("-", "+").replace("_", "/").rstrip("=")
    if len(text) % 4 == 1:
        raise ValueError("not base64")
    out, bits, count = bytearray(), 0, 0
    for char in text:
        value = _B64.find(char)
        if value < 0:
            raise ValueError("not base64")
        bits = (bits << 6) | value
        count += 6
        if count >= 8:
            count -= 8
            out.append((bits >> count) & 0xFF)
            bits &= (1 << count) - 1
    return bytes(out)


def _bytes(value, where, sizes=None):
    """Hex, base64/base64url, or multibase base58btc ('z…'): whichever decodes to a right size."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(where + " must be a non-empty string")
    text = value.strip()
    candidates = []
    body = text[2:] if text[:2] in ("0x", "0X") else text
    if len(body) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in body):
        candidates.append(bytes.fromhex(body))
    if text[0] == "z":
        try:
            candidates.append(_b58decode(text[1:]))
        except ValueError:
            pass
    try:
        candidates.append(_b64decode(text))
    except ValueError:
        pass
    for raw in candidates:
        if sizes is None or len(raw) in sizes:
            return raw
    raise ValueError(where + " does not decode (hex, base64 or base58btc) to "
                     + " or ".join(str(s) for s in (sizes or ())) + " bytes")


def _key(value, where):
    """A 32-byte Ed25519 key from hex, base64, did:key:z6Mk… (with or without #fragment), z6Mk…."""
    text = value.strip() if isinstance(value, str) else value
    if isinstance(text, str):
        text = text.split("#", 1)[0]
        if text.startswith("did:key:"):
            text = text[8:]
        if text.startswith("z6Mk"):
            raw = _b58decode(text[1:])
            if raw[:2] != _ED25519_MULTICODEC or len(raw) != 34:
                raise ValueError(where + " is not an Ed25519 did:key")
            return raw[2:]
    return _bytes(text, where, (32,))


def did_key(public):
    return "did:key:z" + _b58encode(_ED25519_MULTICODEC + public)


# ------------------------------------------------------------------ canonical forms

_SHORT = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r", 0x22: '\\"',
          0x5C: "\\\\"}


def _jcs_string(text):
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


def jcs(value, where="$"):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) > 9007199254740991:
            raise ValueError("integer at " + where + " is past 2^53-1")
        return str(value)
    if isinstance(value, float):
        raise ValueError("number at " + where + " is not an integer; JCS floats need ECMAScript "
                         "formatting, which this checker does not reproduce")
    if isinstance(value, str):
        return _jcs_string(value)
    if isinstance(value, list):
        return "[" + ",".join(jcs(v, where + "[" + str(i) + "]") for i, v in enumerate(value)) + "]"
    if isinstance(value, dict):
        names = sorted(value, key=lambda n: n.encode("utf-16-be"))
        return "{" + ",".join(_jcs_string(n) + ":" + jcs(value[n], where + "." + n)
                              for n in names) + "}"
    raise ValueError("unsupported value at " + where)


def _py_canonical(value):
    """The hub's and the hearth's json.dumps canonical (sorted keys, compact, UTF-8)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


_RECEIPT_V2_FIELDS = ("type", "channel_id", "category", "plugin", "reason", "verify_score",
                      "delivery_reasons", "trace_id", "refunded")


def _receipt_canonicals(receipt, version):
    def base(r):
        return ("nonce:" + str(r.get("nonce", "")) + "|product_id:" + str(r.get("product_id", ""))
                + "|capability_id:" + str(r.get("capability_id", ""))
                + "|price_usd:" + str(r.get("price_usd", 0)) + "|timestamp:"
                + str(r.get("timestamp", "")) + "|success:" + ("1" if r.get("success") else "0")
                + "|latency_ms:" + str(r.get("latency_ms", 0)))

    def full(r):
        if version < 2:
            return base(r)
        fields = {name: r.get(name) for name in _RECEIPT_V2_FIELDS}
        digest = hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False,
                                           separators=(",", ":")).encode()).hexdigest()
        return base(r) + "|v:2|fields:" + digest

    out = [full(receipt)]
    price = receipt.get("price_usd", 0)
    # A JSON round trip may turn 0.0 into 0: the hub tries the other integral spelling too.
    integral = False
    if not isinstance(price, bool) and isinstance(price, (int, float)):
        try:
            integral = float(price) == int(price)
        except (OverflowError, ValueError):
            integral = False
    if integral:
        twin = dict(receipt, price_usd=float(price) if isinstance(price, int) else int(price))
        if full(twin) != out[0]:
            out.append(full(twin))
    return out


# ------------------------------------------------------------------ formats


class _Invalid(ValueError):
    """The signed material itself is bad: the answer is valid=false, not a refused request."""


def _sig(value, where, sizes=(64,)):
    try:
        return _bytes(value, where, sizes)
    except ValueError as exc:
        raise _Invalid(str(exc)) from None


def _carried_key(value, where):
    try:
        return _key(value, where)
    except ValueError as exc:
        raise _Invalid(str(exc)) from None


def _encoded(text, where):
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        raise _Invalid(where + " contains a lone surrogate: not a Unicode string") from None


def _canonical_jcs(value, where):
    try:
        return _encoded(jcs(value), where)
    except _Invalid:
        raise
    except ValueError as exc:
        raise _Invalid(str(exc)) from None


def _pinned(payload):
    return _key(payload.get("public_key"), "public_key") if payload.get("public_key") else None


def _settle(pinned, carried, where):
    """(key, source): a pinned key must be the key the document names, when it names one."""
    if pinned is not None:
        if carried is not None and carried != pinned:
            raise _Invalid("the document's " + where + " names a different key than the one "
                           "you pinned")
        return pinned, "pinned"
    if carried is None:
        raise ValueError("send public_key: this document does not name its signer's key")
    return carried, "document (self-asserted: proves integrity, not who signed)"


def _detect(payload):
    if "message" in payload:
        return "raw"
    doc = payload.get("document")
    if isinstance(doc, dict):
        if isinstance(doc.get("proof"), (dict, list)):
            return "eddsa-jcs-2022"
        sig = doc.get("signature")
        if isinstance(sig, dict) and "verificationMethod" in sig:
            return "histor"
        if isinstance(sig, dict) and "nonce" in doc and "capability_id" in doc:
            return "hub-receipt"
        if isinstance(sig, dict):
            return "hub-object"
        if "result" in doc and isinstance(sig, str):
            return "hestia"
        return "jcs"
    raise ValueError("send 'message' (raw bytes) or 'document' (a signed JSON object)")


def _issuer_id(doc):
    issuer = doc.get("issuer")
    return issuer.get("id") if isinstance(issuer, dict) else issuer


def _vc(doc, pinned, purpose):
    """W3C VC Data Integrity, eddsa-jcs-2022 (Verify Proof, section 3.3.2)."""
    proof = doc.get("proof")
    if not isinstance(proof, dict):
        raise _Invalid("no single proof object (a proof array is not supported here)" if
                       isinstance(proof, list) else "the document carries no proof")
    if proof.get("type") != "DataIntegrityProof":
        raise _Invalid("proof.type is " + str(proof.get("type")) + ", not DataIntegrityProof")
    if proof.get("cryptosuite") != "eddsa-jcs-2022":
        raise _Invalid("cryptosuite is " + str(proof.get("cryptosuite")) + ", not eddsa-jcs-2022")
    if proof.get("proofPurpose") != purpose:
        raise _Invalid("proofPurpose is " + str(proof.get("proofPurpose")) + ", expected "
                       + purpose)
    value = proof.get("proofValue")
    if not isinstance(value, str) or not value.startswith("z"):
        raise _Invalid("proofValue must be multibase base58btc (it starts with z)")
    try:
        signature = _b58decode(value[1:])
    except ValueError:
        raise _Invalid("proofValue is not base58btc") from None
    if len(signature) != 64:
        raise _Invalid("proofValue decodes to " + str(len(signature)) + " bytes, not 64")
    options = {k: v for k, v in proof.items() if k != "proofValue"}
    unsecured = {k: v for k, v in doc.items() if k != "proof"}
    if "@context" in options:
        ctx, own = options.get("@context"), unsecured.get("@context")
        ctx = ctx if isinstance(ctx, list) else [ctx]
        own = own if isinstance(own, list) else [own]
        if own[:len(ctx)] != ctx:
            raise _Invalid("the proof's @context is not a prefix of the document's @context")
        unsecured["@context"] = options.get("@context")
    method = options.get("verificationMethod")
    if not isinstance(method, str) or not method.startswith("did:key:"):
        raise _Invalid("verificationMethod must be a did:key")
    carried = _carried_key(method, "proof.verificationMethod")
    issuer = _issuer_id(doc)
    if isinstance(issuer, str) and issuer.startswith("did:key:"):
        if _carried_key(issuer, "issuer") != carried:
            raise _Invalid("the proof was made with a key that is not the issuer's")
    key, source = _settle(pinned, carried, "proof.verificationMethod")
    config_hash = hashlib.sha256(_canonical_jcs(options, "proof")).digest()
    doc_hash = hashlib.sha256(_canonical_jcs(unsecured, "document")).digest()
    extra = {"proofConfigHash": config_hash.hex(), "transformedDocumentHash": doc_hash.hex()}
    return key, source, [config_hash + doc_hash], signature, extra


def _material(fmt, payload, doc, pinned):
    """(key, source, candidate signed byte strings, signature, extra) for one format."""
    if fmt == "raw":
        encoding = payload.get("message_encoding", "utf8")
        message = payload.get("message")
        if not isinstance(message, str):
            raise ValueError("message must be a string")
        if encoding == "utf8":
            signed = message.encode("utf-8")
        elif encoding == "hex":
            signed = _bytes(message, "message")
        elif encoding == "base64":
            signed = _b64decode(message)
        else:
            raise ValueError("message_encoding must be utf8, hex or base64")
        key, source = _settle(pinned, None, "public_key")
        return key, source, [signed], _sig(payload.get("signature"), "signature"), {}
    if fmt == "jcs":
        exclude = payload.get("exclude", [])
        if not isinstance(exclude, list):
            raise ValueError("exclude must be a list of top-level keys")
        body = {k: v for k, v in doc.items() if k not in exclude}
        key, source = _settle(pinned, None, "public_key")
        return (key, source, [_canonical_jcs(body, "document")],
                _sig(payload.get("signature"), "signature"), {})
    if fmt == "eddsa-jcs-2022":
        purpose = payload.get("proof_purpose", "assertionMethod")
        return _vc(doc, pinned, purpose)
    if fmt == "histor":
        sig = doc.get("signature") if isinstance(doc.get("signature"), dict) else {}
        if sig.get("alg") not in (None, "Ed25519"):
            raise _Invalid("signature.alg is " + str(sig.get("alg")) + ", not Ed25519")
        carried = _carried_key(sig.get("verificationMethod"), "signature.verificationMethod") \
            if sig.get("verificationMethod") else None
        key, source = _settle(pinned, carried, "signature.verificationMethod")
        body = {k: v for k, v in doc.items() if k != "signature"}
        return (key, source, [_canonical_jcs(body, "document")],
                _sig(sig.get("value"), "signature.value"), {})
    if fmt == "hestia":
        for name in ("capability_id", "product_id"):
            if not isinstance(payload.get(name), str):
                raise ValueError("format hestia needs '" + name + "' of the call")
        if not isinstance(payload.get("input"), dict):
            raise ValueError("format hestia needs 'input': the payload you sent")
        carried = _carried_key(doc.get("provider_pubkey"), "document.provider_pubkey") \
            if doc.get("provider_pubkey") else None
        key, source = _settle(pinned, carried, "provider_pubkey")
        input_sha = hashlib.sha256(_py_canonical(payload.get("input")).encode()).hexdigest()
        signed = _py_canonical({"capability_id": payload.get("capability_id"),
                                "product_id": payload.get("product_id"),
                                "input_sha256": input_sha, "result": doc.get("result")}).encode()
        return (key, source, [signed], _sig(doc.get("signature"), "document.signature"),
                {"input_sha256": input_sha})
    if fmt in ("hub-receipt", "hub-object"):
        sig = doc.get("signature")
        if not isinstance(sig, dict) or sig.get("algorithm", "ed25519") != "ed25519":
            raise _Invalid("signature must be {algorithm: ed25519, value}")
        carried = _carried_key(sig.get("public_key"), "signature.public_key") \
            if sig.get("public_key") else None
        key, source = _settle(pinned, carried, "signature.public_key")
        body = {k: v for k, v in doc.items() if k != "signature"}
        if fmt == "hub-object":
            return (key, source, [_py_canonical(body).encode()],
                    _sig(sig.get("value"), "signature.value"), {})
        version = sig.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int):
            raise _Invalid("signature.version must be an integer")
        signed = [c.encode() for c in _receipt_canonicals(body, version)]
        return (key, source, signed, _sig(sig.get("value"), "signature.value"),
                {"receipt_version": version})
    raise ValueError("format must be raw, jcs, eddsa-jcs-2022, histor, hestia, hub-receipt or "
                     "hub-object")


def _proof_set(payload, doc, pinned):
    """A proof array: every proof is checked and reported; valid iff one verifies and none is
    of a kind this checker cannot verify (one that could would name a different signer)."""
    reports, unsupported = [], False
    for i, proof in enumerate(doc.get("proof")):
        single = dict(doc, proof=proof)
        try:
            report = _verify_one("eddsa-jcs-2022", payload, single, pinned)
        except ValueError as exc:
            report = {"valid": False, "reason": str(exc)}
        if isinstance(proof, dict) and (proof.get("type") != "DataIntegrityProof" or
                                        proof.get("cryptosuite") != "eddsa-jcs-2022"):
            unsupported = True
        report["index"] = i
        report.pop("format", None)
        reports.append(report)
    good = [r for r in reports if r.get("valid")]
    if unsupported:
        reason = "a proof of a kind this checker cannot verify is in the set"
    elif good:
        reason = str(len(good)) + " of " + str(len(reports)) + " proofs verify"
    else:
        reason = "no proof in the set verifies"
    return {"format": "eddsa-jcs-2022", "valid": bool(good) and not unsupported,
            "reason": reason, "proofs": reports}


def _verify_one(fmt, payload, doc, pinned):
    try:
        key, source, signed, signature, extra = _material(fmt, payload, doc, pinned)
    except _Invalid as exc:
        return {"format": fmt, "valid": False, "reason": str(exc)}
    ok, reason, used = False, "", signed[0]
    for candidate in signed:
        ok, reason = ed25519_verify(key, candidate, signature)
        if ok:
            used = candidate
            break
    out = {"format": fmt, "valid": ok, "reason": reason,
           "key": {"hex": key.hex(), "did": did_key(key), "source": source},
           "signed_bytes_sha256": hashlib.sha256(used).hexdigest(),
           "signed_bytes_length": len(used)}
    out.update(extra)
    return out


def handle(payload):
    fmt = payload.get("format") or _detect(payload)
    pinned = _pinned(payload)
    doc = payload.get("document")
    if fmt != "raw" and not isinstance(doc, dict):
        raise ValueError("format " + str(fmt) + " needs 'document' (an object)")
    if fmt == "eddsa-jcs-2022" and isinstance(doc.get("proof"), list):
        return _proof_set(payload, doc, pinned)
    return _verify_one(fmt, payload, doc, pinned)
