"""AID endpoint proof (PKA), checked for an exchange you made. AID v2.1.1, Appendix B.

A domain's `_agent` TXT record may carry `k`, an Ed25519 key. A client then asks the endpoint
to sign the response (RFC 9421, `Accept-Signature: aid-pka=...`), and accepts the endpoint only
if every rule of Appendix B.6 holds, plus B.7 when the proof is bound to a domain. This agent
applies those rules to what you send:

  k         the key from the record (or `record`: the whole TXT string)
  request   {uri, nonce, method (GET), aid_domain (the AID-Domain header, if you sent one)}
  response  {status, headers: {signature-input, signature, cache-control}}
  now       unix seconds when the response arrived: the proof is valid for at most 300 s

The sandbox makes no request itself, so it judges the exchange you describe: it cannot know
that you really sent that nonce or reached that URI. `signature_base` in the answer is the
exact text the signature must cover, which is what a signer's author needs when a proof fails.

Pure Python Ed25519 (RFC 8032), cofactorless like OpenSSL, refusing non-canonical points,
S >= L and small-order keys.
"""

import hashlib

SPEC = "AID v2.1.1, Appendix B (PKA handshake, B.7 domain binding)"
TAG = "aid-pka-v2"
BASE = ['"@method";req', '"@target-uri";req', '"@authority";req', '"@status"']
BOUND = BASE[:3] + ['"aid-domain";req', '"@status"']
PARAMS = ("created", "expires", "keyid", "alg", "nonce", "tag")
MAX_WINDOW = 300
DEFAULT_SKEW = 30

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
    if len(signature) != 64:
        return False, "the signature is " + str(len(signature)) + " bytes, Ed25519 needs 64"
    a = _decode(public)
    if a is None:
        return False, "k is not a valid curve point"
    small = a
    for _ in range(3):
        small = _double(small)
    if _same(small, _IDENTITY):
        return False, "k has small order: it verifies forged signatures"
    r = _decode(signature[:32])
    if r is None:
        return False, "signature R is not a valid curve point"
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False, "signature S is not reduced (S >= L)"
    k = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    neg_a = ((-a[0]) % _Q, a[1], a[2], (-a[3]) % _Q)
    if _same(_two_mul(s, _B, k, neg_a), r):
        return True, "Ed25519 verifies over the signature base"
    return False, "Ed25519 does not verify for this key over the signature base"


# ------------------------------------------------------------------ encodings

_STD = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_URL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _unbase64(text, alphabet):
    if not text or len(text) % 4 == 1:
        raise ValueError("wrong length")
    out, bits, count = bytearray(), 0, 0
    for char in text:
        value = alphabet.find(char)
        if value < 0:
            raise ValueError("a character outside the alphabet")
        bits = (bits << 6) | value
        count += 6
        if count >= 8:
            count -= 8
            out.append((bits >> count) & 0xFF)
            bits &= (1 << count) - 1
    return bytes(out)


def _base64url(raw):
    out, bits, count = "", 0, 0
    for byte in raw:
        bits = (bits << 8) | byte
        count += 8
        while count >= 6:
            count -= 6
            out += _URL[(bits >> count) & 63]
            bits &= (1 << count) - 1
    if count:
        out += _URL[(bits << (6 - count)) & 63]
    return out


def keyid(k):
    """RFC 7638 thumbprint of the JWK {crv, kty, x}, as Appendix B.2 spells it."""
    jwk = '{"crv":"Ed25519","kty":"OKP","x":"' + k + '"}'
    return _base64url(hashlib.sha256(jwk.encode("utf-8")).digest())


# ------------------------------------------------------------------ structured fields


class _Bad(ValueError):
    pass


def _header(headers, name):
    for key, value in headers.items():
        if str(key).strip().lower() == name:
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            if not isinstance(value, str):
                raise ValueError("response.headers." + name + " must be a string")
            return value.strip()
    return None


def _member(value, label, header):
    """The raw value of one member of a Structured Field dictionary. Commas inside quoted
    strings and inner lists do not split members."""
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
        elif char == "," and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    found = []
    for part in parts:
        name, eq, raw = part.strip().partition("=")
        if eq and name.strip() == label:
            found.append(raw.strip())
    if not found:
        raise _Bad(header + " has no " + label + " member")
    if len(found) > 1:
        raise _Bad(header + " has " + str(len(found)) + " " + label
                   + " members; which one counts is ambiguous")
    return found[0]


def _items(inner):
    out, start, quoted = [], 0, False
    for index, char in enumerate(inner):
        if char == '"':
            quoted = not quoted
        elif char == " " and not quoted:
            if index > start:
                out.append(inner[start:index])
            start = index + 1
    if len(inner) > start:
        out.append(inner[start:])
    return out


def _params(text):
    """Parameters after the covered list: {name: (kind, value)}, kind 'string' or 'bare'."""
    out, index, size = {}, 0, len(text)
    while index < size:
        if text[index] != ";":
            raise _Bad("unexpected text after the covered list: " + text[index:index + 20])
        index += 1
        end = index
        while end < size and text[end] not in "=;":
            end += 1
        name = text[index:end]
        if not name or name in out:
            raise _Bad("parameter '" + name + "' is empty or given twice")
        if end >= size or text[end] == ";":
            raise _Bad("parameter " + name + " has no value")
        end += 1
        if end < size and text[end] == '"':
            end += 1
            chars = []
            while True:
                if end >= size:
                    raise _Bad("parameter " + name + ": the string is not closed")
                char = text[end]
                if char == "\\":
                    if end + 1 >= size or text[end + 1] not in '"\\':
                        raise _Bad("parameter " + name + ": bad escape")
                    chars.append(text[end + 1])
                    end += 2
                elif char == '"':
                    break
                else:
                    chars.append(char)
                    end += 1
            out[name] = ("string", "".join(chars))
            index = end + 1
        else:
            stop = end
            while stop < size and text[stop] != ";":
                stop += 1
            out[name] = ("bare", text[end:stop])
            index = stop
    return out


def _signature_input(raw):
    """(covered items, parameters) of an aid-pka Signature-Input member."""
    if not raw.startswith("("):
        raise _Bad("Signature-Input aid-pka is not an inner list")
    close = raw.find(")")
    if close < 0:
        raise _Bad("Signature-Input aid-pka: the covered list is not closed")
    params = _params(raw[close + 1:])
    for name in params:
        if name not in PARAMS:
            raise _Bad("Signature-Input has a parameter the profile does not define: " + name)
    for name in PARAMS:
        if name not in params:
            raise _Bad("Signature-Input has no " + name)
    for name in ("created", "expires"):
        kind, value = params[name]
        if kind != "bare" or not value.isdigit() or not value.isascii():
            raise _Bad(name + " must be a bare integer")
    for name in ("keyid", "alg", "nonce", "tag"):
        if params[name][0] != "string":
            raise _Bad(name + " must be a quoted string")
    return _items(raw[1:close].strip()), {name: params[name][1] for name in PARAMS}


def _signature(raw):
    """(bytes, note) of an aid-pka Signature member, a Structured Field byte sequence."""
    if len(raw) < 2 or not raw.startswith(":") or not raw.endswith(":"):
        raise _Bad("Signature aid-pka is not a byte sequence (:base64:)")
    body = raw[1:-1].strip()
    stripped = body.rstrip("=")
    padding = len(body) - len(stripped)
    try:
        value = _unbase64(stripped, _STD)
    except ValueError as exc:
        raise _Bad("Signature aid-pka is not standard base64: " + str(exc)) from None
    note = None
    if padding != (-len(stripped)) % 4:
        note = ("the Signature value has wrong or missing base64 padding; RFC 8941 lets a parser "
                "accept it, the AID reference client refuses it")
    return value, note


# ------------------------------------------------------------------ the request context


def target(uri):
    """(@target-uri, @authority) for a request URI, per Appendix B.5: no fragment, lower-case
    host, default port dropped, path and query kept as sent."""
    text = uri.strip()
    cut = text.find("#")
    if cut >= 0:
        text = text[:cut]
    scheme, sep, rest = text.partition("://")
    if not sep or scheme.lower() != "https":
        raise ValueError("request.uri must be an https:// URL (the proof is an HTTPS exchange)")
    end = len(rest)
    for mark in "/?":
        at = rest.find(mark)
        if 0 <= at < end:
            end = at
    netloc, tail = rest[:end], rest[end:]
    if "@" in netloc or " " in rest:
        raise ValueError("request.uri must not carry credentials or spaces")
    host, port = netloc, ""
    if netloc.startswith("["):
        close = netloc.find("]")
        if close < 0 or (netloc[close + 1:] and not netloc[close + 1:].startswith(":")):
            raise ValueError("request.uri has a malformed IPv6 host")
        host, port = netloc[:close + 1], netloc[close + 2:]
    elif ":" in netloc:
        host, _, port = netloc.rpartition(":")
    if not host:
        raise ValueError("request.uri has no host")
    if port and not (port.isdigit() and port.isascii() and int(port) <= 65535):
        raise ValueError("request.uri has a malformed port")
    authority = host.lower() + (":" + str(int(port)) if port and int(port) != 443 else "")
    return "https://" + authority + tail, authority


def aid_domain(value):
    """The AID-Domain value as both sides must use it: lower-case, no trailing dot."""
    text = value.strip().lower()
    if text.endswith("."):
        text = text[:-1]
    if not text or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789.:[]_-" for char in text):
        raise ValueError("request.aid_domain is not a host name")
    return text


# ------------------------------------------------------------------ the handler


def _key_from(payload):
    k = payload.get("k")
    if k is None and isinstance(payload.get("record"), str):
        for pair in payload["record"].split(";"):
            name, eq, value = pair.partition("=")
            if eq and name.strip().lower() in ("k", "pka"):
                k = value.strip()
    if not isinstance(k, str) or not k:
        raise ValueError("give k (the key from the _agent record) or record (the TXT string "
                         "with k)")
    return k


def _uint(value, where, upper):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= upper:
        raise ValueError(where + " must be an integer from 0 to " + str(upper))
    return value


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: k, request, response, now")
    k = _key_from(payload)
    request, response = payload.get("request"), payload.get("response")
    if not isinstance(request, dict) or not isinstance(response, dict):
        raise ValueError("request and response must be objects")
    uri, nonce = request.get("uri"), request.get("nonce")
    if not isinstance(uri, str) or not isinstance(nonce, str) or not nonce:
        raise ValueError("request.uri and request.nonce (the challenge you sent) are required")
    method = str(request.get("method") or "GET").upper()
    if not method.isalpha() or not method.isascii():
        raise ValueError("request.method must be an HTTP method name")
    target_uri, authority = target(uri)
    sent_domain = request.get("aid_domain")
    if sent_domain is not None:
        if not isinstance(sent_domain, str):
            raise ValueError("request.aid_domain must be a string")
        sent_domain = aid_domain(sent_domain)
    status = _uint(response.get("status"), "response.status", 599)
    headers = response.get("headers")
    if not isinstance(headers, dict):
        raise ValueError("response.headers must be an object")
    now = _uint(payload.get("now"), "now (unix seconds when the response arrived)", 2 ** 40)
    skew = _uint(payload.get("skew", DEFAULT_SKEW), "skew", MAX_WINDOW)
    require_bound = payload.get("require_domain_binding") is True

    checks, warnings = [], []
    out = {"verified": False, "domain_bound": False, "spec": SPEC}

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    def done():
        failed = [item["check"] for item in checks if not item["ok"]]
        out["verified"] = not failed
        out["domain_bound"] = bool(out["verified"] and out.get("covers_aid_domain"))
        out["code"] = 0 if out["verified"] else 1003
        if failed:
            out["error"] = "ERR_SECURITY"
            out["failed"] = failed
        out["checks"] = checks
        if warnings:
            out["warnings"] = warnings
        out.pop("covers_aid_domain", None)
        return out

    # B.1, B.2: the key and the keyid it implies.
    public = None
    try:
        if "=" in k:
            raise ValueError("it is padded")
        public = _unbase64(k, _URL)
        if len(public) != 32:
            raise ValueError("it decodes to " + str(len(public)) + " bytes, not 32")
    except ValueError as exc:
        check("key", False, "k must be unpadded base64url of a 32-byte Ed25519 key: " + str(exc))
        return done()
    expected_keyid = keyid(k)
    out["keyid"] = expected_keyid
    check("key", True, "k is a 32-byte key; its RFC 7638 thumbprint is the expected keyid")

    check("no_redirect", not 300 <= status < 400,
          "status " + str(status) + (": a redirect is never a proof (B.5)" if 300 <= status < 400
                                     else " (any status may be signed; PKA does not need 200)"))

    cache = _header(headers, "cache-control") or ""
    no_store = any(part.strip().split(";", 1)[0].strip().lower() == "no-store"
                   for part in cache.split(","))
    check("cache_control", no_store,
          "Cache-Control has no-store" if no_store
          else "the response must carry Cache-Control: no-store, got " + (cache or "nothing"))

    # B.3: the two signature headers.
    sig_input, sig = _header(headers, "signature-input"), _header(headers, "signature")
    if not sig_input or not sig:
        refusal = ""
        if status == 403 and sent_domain:
            refusal = (" A 403 without a signature is how an endpoint refuses a domain it does "
                       "not serve (B.7).")
        check("signature_headers", False,
              "the response has no Signature-Input and Signature: no proof was given." + refusal)
        return done()
    try:
        raw_params = _member(sig_input, "aid-pka", "Signature-Input")
        covered, params = _signature_input(raw_params)
        signature, note = _signature(_member(sig, "aid-pka", "Signature"))
    except _Bad as exc:
        check("signature_headers", False, str(exc))
        return done()
    if note:
        warnings.append(note)
    check("signature_headers", True, "Signature-Input and Signature carry an aid-pka member")
    created, expires = int(params["created"]), int(params["expires"])
    out["covered"] = covered
    out["created"], out["expires"] = created, expires

    # B.4, B.6, B.7: exactly the base set, or the base set with aid-domain before @status.
    bound = covered == BOUND
    out["covers_aid_domain"] = bound
    shape_ok = bound or covered == BASE
    if bound:
        shape = 'the base set plus "aid-domain";req: a domain-bound proof'
    elif shape_ok:
        shape = "the four base components: an unbound proof"
    else:
        shape = ("the covered set must be " + " ".join(BASE) + ', or the same with '
                 '"aid-domain";req before "@status"; got ' + " ".join(covered))
    check("covered_components", shape_ok, shape)
    check("tag", params["tag"] == TAG, "tag is " + params["tag"] + ", the profile's is " + TAG)
    check("alg", params["alg"].lower() == "ed25519", "alg is " + params["alg"])
    if params["alg"] != "ed25519" and params["alg"].lower() == "ed25519":
        warnings.append("alg is not lower-case; signers MUST emit ed25519 (verifiers accept "
                        "any case)")
    check("keyid", params["keyid"] == expected_keyid,
          "keyid is the thumbprint of k" if params["keyid"] == expected_keyid
          else "keyid " + params["keyid"] + " is not the thumbprint of k (" + expected_keyid
               + "): another key signed, or the keyid hashes the raw key bytes")
    check("nonce", params["nonce"] == nonce,
          "the nonce is the challenge you sent" if params["nonce"] == nonce
          else "the nonce is not the challenge you sent: a replayed or unrelated response")
    if len(nonce) < 43:
        warnings.append("your challenge is shorter than 32 bytes in base64url; the spec asks for "
                        "at least 32 bytes of entropy")
    window_ok = expires > created and expires - created <= MAX_WINDOW
    check("window", window_ok,
          "created " + str(created) + ", expires " + str(expires) + ": "
          + (str(expires - created) + " s, within the 300 s limit" if window_ok
             else "expires must be later than created by at most 300 s"))
    fresh = created - now <= skew and now - expires <= skew
    if fresh:
        when = "now " + str(now) + " is inside the window (skew " + str(skew) + " s)"
    else:
        side = "before created" if created - now > skew else "after expires"
        when = "now " + str(now) + " is " + side + " by more than " + str(skew) + " s"
    check("freshness", fresh, when)

    # B.7: a proof that covers aid-domain only means something for the domain the client named.
    domain_line = None
    if bound:
        if sent_domain is None:
            check("domain_binding", False,
                  "the response covers aid-domain but you sent no AID-Domain: refused "
                  "(fail closed)")
        else:
            domain_line = '"aid-domain";req: ' + sent_domain
            check("domain_binding", True, "bound to " + sent_domain + " if the signature verifies")
    elif require_bound:
        check("domain_binding", False,
              "you require domain binding and the proof is unbound: an endpoint that ignores "
              "AID-Domain proves control of the key, not that it serves this domain")
    elif sent_domain is not None:
        warnings.append("you sent AID-Domain and the endpoint answered with an unbound proof: it "
                        "controls the key, but did not state that it serves " + sent_domain)

    if covered == BASE or (bound and domain_line):
        lines = ['"@method";req: ' + method, '"@target-uri";req: ' + target_uri,
                 '"@authority";req: ' + authority]
        if domain_line:
            lines.append(domain_line)
        lines += ['"@status": ' + str(status), '"@signature-params": ' + raw_params]
        base = "\n".join(lines)
        out["signature_base"] = base
        ok, reason = ed25519_verify(public, base.encode("utf-8"), signature)
        check("signature", ok, reason)
    else:
        check("signature", False, "not checked: the covered set does not allow a signature base")
    return done()
