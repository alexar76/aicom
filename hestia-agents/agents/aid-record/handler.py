"""AID record lookup and validation: what an AID v2.1.1 client finds for a domain.

Give `domain`. The agent asks two public DNS-over-HTTPS resolvers (Cloudflare and Google) for
the TXT records at _agent.<domain>, that exact host and no parent, and applies the client
algorithm of the specification (sections 2.1 to 2.3): parse each answer, validate it by its
version, prefer aid2, refuse two valid records of one version as ambiguous.

Or give `txt`, the TXT strings you are about to publish, to validate them with no lookup.

The sandbox has no sockets: fetch() asks the hearth, which talks only to the two resolvers
this agent's deploy names. The answer says what each resolver returned and whether it
validated DNSSEC (the AD flag). It is an observation of public DNS at the resolvers' Date,
signed by this agent, and no more than that. Not done here: the endpoint proof for `k` (send
the exchange to aid.proof.verify), the .well-known fallback, and _agent._<proto> names.
"""

import hashlib
import json

SPEC = "AID v2.1.1, sections 2.1-2.3"
RESOLVERS = (("cloudflare", "https://cloudflare-dns.com/dns-query"),
             ("google", "https://dns.google/resolve"))
PROTOCOLS = ("a2a", "graphql", "grpc", "local", "mcp", "openapi", "ucp", "websocket", "zeroconf")
AUTHS = ("apikey", "basic", "custom", "mtls", "none", "oauth2_code", "oauth2_device", "pat")
LOCAL_SCHEMES = ("docker", "npx", "pip")
ALIASES = (("uri", "u"), ("proto", "p"), ("auth", "a"), ("desc", "s"), ("docs", "d"),
           ("dep", "e"), ("pka", "k"), ("kid", "i"))
ERRORS = {1000: "ERR_NO_RECORD", 1001: "ERR_INVALID_TXT", 1002: "ERR_UNSUPPORTED_PROTO",
          1004: "ERR_DNS_LOOKUP_FAILED"}
DNS_STATUS = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 4: "NOTIMP", 5: "REFUSED"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_URL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_HOST = "abcdefghijklmnopqrstuvwxyz0123456789-"


class _Invalid(ValueError):
    """A record that fails validation: the specification's ERR_INVALID_TXT (1001)."""


class _Unsupported(_Invalid):
    """A record whose protocol token is not in the registry: ERR_UNSUPPORTED_PROTO (1002)."""


# ------------------------------------------------------------------ the key


def _key_bytes(k):
    if "=" in k or not k or any(char not in _URL for char in k):
        raise _Invalid("k must be unpadded base64url")
    if len(k) % 4 == 1:
        raise _Invalid("k is not valid base64url")
    bits, count, size = 0, 0, 0
    for char in k:
        bits = (bits << 6) | _URL.find(char)
        count += 6
        if count >= 8:
            count -= 8
            size += 1
            bits &= (1 << count) - 1
    if size != 32:
        raise _Invalid("k must decode to exactly 32 bytes, it decodes to " + str(size))
    return bits == 0


def keyid(k):
    """RFC 7638 thumbprint of the JWK {crv, kty, x}: the keyid an endpoint proof must name."""
    jwk = '{"crv":"Ed25519","kty":"OKP","x":"' + k + '"}'
    digest = hashlib.sha256(jwk.encode("utf-8")).digest()
    out, bits, count = "", 0, 0
    for byte in digest:
        bits = (bits << 8) | byte
        count += 8
        while count >= 6:
            count -= 6
            out += _URL[(bits >> count) & 63]
            bits &= (1 << count) - 1
    if count:
        out += _URL[(bits << (6 - count)) & 63]
    return out


# ------------------------------------------------------------------ one record


def _absolute(uri, scheme):
    rest = uri[len(scheme):]
    host = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    return uri.startswith(scheme) and bool(host) and " " not in uri


def _timestamp(text):
    """True for YYYY-MM-DDTHH:MM:SSZ with plausible fields."""
    if len(text) != 20 or text[4] + text[7] + text[10] + text[13] + text[16] + text[19] != "--T::Z":
        return False
    digits = text[0:4] + text[5:7] + text[8:10] + text[11:13] + text[14:16] + text[17:19]
    if not (digits.isdigit() and digits.isascii()):
        return False
    return (1 <= int(text[5:7]) <= 12 and 1 <= int(text[8:10]) <= 31 and int(text[11:13]) <= 23
            and int(text[14:16]) <= 59 and int(text[17:19]) <= 60)


def parse(txt):
    """(record, warnings) for one TXT string, or raises _Invalid. Canonical field names."""
    raw = {}
    for pair in txt.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        name, eq, value = pair.partition("=")
        name, value = name.strip().lower(), value.strip()
        if not eq:
            raise _Invalid("not a key=value pair: " + pair[:40])
        if not name or not value:
            raise _Invalid("empty key or value in: " + pair[:40])
        if name in raw:
            raise _Invalid("key given twice: " + name)
        raw[name] = value
    version = raw.get("v") or raw.get("version")
    if "v" in raw and "version" in raw:
        raise _Invalid("both version and its alias v are given")
    if version is None:
        raise _Invalid("no v: not an AID record")
    if version not in ("aid1", "aid2"):
        raise _Invalid("version " + version + " is not aid1 or aid2")
    fields, long_keys = {"v": version}, ["version"] if "version" in raw else []
    for full, alias in ALIASES:
        if full in raw and alias in raw:
            raise _Invalid("both " + full + " and its alias " + alias + " are given")
        if full in raw:
            long_keys.append(full)
        value = raw.get(full) or raw.get(alias)
        if value is not None:
            fields[full] = value
    if "uri" not in fields:
        raise _Invalid("no u (uri): required")
    if "proto" not in fields:
        raise _Invalid("no p (proto): required")
    proto, uri = fields["proto"], fields["uri"]
    if proto not in PROTOCOLS:
        raise _Unsupported("protocol " + proto + " is not in the registry ("
                           + ", ".join(PROTOCOLS) + ")")
    if "auth" in fields and fields["auth"] not in AUTHS:
        raise _Invalid("auth " + fields["auth"] + " is not in the registry ("
                       + ", ".join(AUTHS) + ")")
    if len(fields.get("desc", "").encode("utf-8")) > 60:
        raise _Invalid("s (desc) is " + str(len(fields["desc"].encode("utf-8")))
                       + " UTF-8 bytes; the limit is 60")
    if "docs" in fields and not _absolute(fields["docs"], "https://"):
        raise _Invalid("d (docs) must be an absolute https:// URL")
    if "dep" in fields and not _timestamp(fields["dep"]):
        raise _Invalid("e (dep) must be an ISO 8601 UTC time such as 2027-01-01T00:00:00Z")
    canonical_key = True
    if version == "aid2":
        if "kid" in fields:
            raise _Invalid("kid / i is not allowed in an aid2 record")
        if "pka" in fields:
            canonical_key = _key_bytes(fields["pka"])
    elif "pka" in fields and "kid" not in fields:
        raise _Invalid("an aid1 record with k needs i (kid)")
    if proto == "local":
        scheme = uri.split(":", 1)[0] if ":" in uri else ""
        if scheme not in LOCAL_SCHEMES:
            raise _Invalid("a local agent's u must start with one of "
                           + ", ".join(LOCAL_SCHEMES) + ":")
    elif proto == "zeroconf":
        if not uri.startswith("zeroconf:"):
            raise _Invalid("a zeroconf agent's u must start with zeroconf:")
    elif proto == "websocket":
        if not _absolute(uri, "wss://"):
            raise _Invalid("a websocket agent's u must be an absolute wss:// URL")
    elif not _absolute(uri, "https://"):
        raise _Invalid("a remote agent's u must be an absolute https:// URL")
    warnings = []
    if len(txt.encode("utf-8")) > 255:
        warnings.append("the record is " + str(len(txt.encode("utf-8"))) + " bytes; above 255 it "
                        "is split into several strings, which some DNS panels handle badly")
    if long_keys:
        warnings.append("uses the long key " + ", ".join(long_keys) + "; providers should "
                        "publish the one-letter aliases")
    if "auth" not in fields:
        warnings.append("no a (auth): recommended, so a client knows how to authenticate")
    if version == "aid1":
        warnings.append("an aid1 record: the legacy format, read only when no valid aid2 "
                        "record exists")
    elif "pka" not in fields:
        warnings.append("no k: a client cannot check that the endpoint belongs to this record")
    elif not canonical_key:
        warnings.append("k has non-zero spare bits in its last character: it decodes, but two "
                        "spellings of one key give two different keyids")
    return fields, warnings


def select(strings, at):
    """The specification's section 2.3 over the TXT strings found at one name."""
    seen, valid = [], {"aid1": [], "aid2": []}
    for txt in strings:
        entry = {"txt": txt}
        try:
            record, warnings = parse(txt)
        except _Invalid as exc:
            entry.update(valid=False, problem=str(exc),
                         code=1002 if isinstance(exc, _Unsupported) else 1001)
        else:
            entry.update(valid=True, version=record["v"])
            valid[record["v"]].append((txt, record, warnings))
        seen.append(entry)
    out = {"found": bool(strings), "valid": False}
    chosen = valid["aid2"] or valid["aid1"]
    if not strings:
        out.update(code=1000, detail="no TXT record at this name")
    elif not chosen:
        codes = [entry["code"] for entry in seen]
        out.update(code=1002 if codes and all(code == 1002 for code in codes) else 1001,
                   detail="no TXT record at this name is a valid AID record")
    elif len(chosen) > 1:
        out.update(code=1001, detail=str(len(chosen)) + " valid " + chosen[0][1]["v"]
                   + " records: ambiguous, a client must not pick one by answer order")
    else:
        txt, record, warnings = chosen[0]
        out.update(valid=True, code=0, txt=txt, record=record, warnings=list(warnings))
        if "pka" in record and record["v"] == "aid2":
            out["pka"] = {"k": record["pka"], "keyid": keyid(record["pka"]),
                          "next": "a client MUST verify the endpoint proof (Appendix B) before "
                                  "using this endpoint; aid.proof.verify checks an exchange"}
        if "dep" in record and at:
            if record["dep"] <= at:
                out["deprecated"] = True
                out["warnings"].append("deprecated since " + record["dep"]
                                       + ": a client should stop using this endpoint")
            else:
                out["warnings"].append("will be deprecated at " + record["dep"])
    if out["code"]:
        out["error"] = ERRORS[out["code"]]
    others = [entry for entry in seen if not (out["valid"] and entry["txt"] == out["txt"])]
    if others:
        out["other_records"] = others
    return out


# ------------------------------------------------------------------ DNS over HTTPS


def host(value):
    """The exact host to look up: lower-case ASCII (A-label for an IDN), no dot at the end."""
    text = value.strip().lower()
    if text.endswith("."):
        text = text[:-1]
    if text.startswith("_agent."):
        text = text[len("_agent."):]
    if not text.isascii():
        raise ValueError("give the domain in its A-label form (xn--...), not in Unicode")
    labels = text.split(".")
    if len(text) > 245 or len(labels) < 2:
        raise ValueError("domain must be a host name such as example.com")
    for label in labels:
        if not 1 <= len(label) <= 63 or any(char not in _HOST for char in label) \
                or label.startswith("-") or label.endswith("-"):
            raise ValueError("domain must be a host name with no scheme, port or path")
    return text


def character_strings(data):
    """One TXT answer as a resolver's JSON gives it. Quoted character-strings (Cloudflare) are
    unescaped and joined in order, as the specification requires for a split record; an
    unquoted value (Google) is taken as it is."""
    text = data.strip()
    if not text.startswith('"'):
        return text
    out, index, size = bytearray(), 0, len(text)
    while index < size:
        if text[index] in " \t":
            index += 1
            continue
        if text[index] != '"':
            return text
        index += 1
        while index < size and text[index] != '"':
            if text[index] == "\\" and index + 1 < size:
                number = text[index + 1:index + 4]
                if len(number) == 3 and number.isdigit() and number.isascii() and int(number) < 256:
                    out.append(int(number))
                    index += 4
                else:
                    out += text[index + 1].encode("utf-8")
                    index += 2
            else:
                out += text[index].encode("utf-8")
                index += 1
        index += 1
    return bytes(out).decode("utf-8", "replace")


def http_date(text):
    """An HTTP Date header as YYYY-MM-DDTHH:MM:SSZ, or None."""
    parts = (text or "").replace(",", " ").split()
    if len(parts) != 6 or parts[5] != "GMT" or parts[2] not in MONTHS:
        return None
    clock = parts[4].split(":")
    if not (parts[1].isdigit() and parts[3].isdigit() and len(parts[3]) == 4 and len(clock) == 3
            and all(len(item) == 2 and item.isdigit() for item in clock)):
        return None
    stamp = (parts[3] + "-" + str(MONTHS.index(parts[2]) + 1).zfill(2) + "-" + parts[1].zfill(2)
             + "T" + ":".join(clock) + "Z")
    return stamp if _timestamp(stamp) else None


def resolve(name):
    """Ask each resolver for TXT at `name`. One fetch round per resolver."""
    answers = []
    for label, base in RESOLVERS:
        seen = {"resolver": label, "ok": False}
        answers.append(seen)
        try:
            reply = fetch(base + "?name=" + name + "&type=TXT&do=1",  # noqa: F821 — the sandbox provides fetch()
                          headers={"accept": "application/dns-json"})
        except Exception as exc:  # the hearth refused the request (budget); never the fetch signal
            seen["problem"] = str(exc)[:160]
            continue
        if not reply.ok:
            seen["problem"] = reply.error or ("the resolver answered HTTP " + str(reply.status))
            continue
        try:
            body = json.loads(reply.text)
            status = int(body["Status"])
        except (ValueError, KeyError, TypeError):
            seen["problem"] = "the resolver's answer is not DNS JSON"
            continue
        seen["dns_status"] = DNS_STATUS.get(status, "RCODE " + str(status))
        seen["date"] = http_date(reply.headers.get("date"))
        if status not in (0, 3):
            seen["problem"] = "the resolver could not answer (" + seen["dns_status"] + ")"
            continue
        rows = [row for row in body.get("Answer") or [] if isinstance(row, dict)]
        texts = [row for row in rows if row.get("type") == 16 and isinstance(row.get("data"), str)]
        seen["ok"] = True
        seen["dnssec_validated"] = body.get("AD") is True
        seen["txt"] = [character_strings(row["data"]) for row in texts]
        ttls = [row["TTL"] for row in texts if isinstance(row.get("TTL"), int)]
        if ttls:
            seen["ttl"] = min(ttls)
        cnames = [str(row.get("data")).rstrip(".") for row in rows if row.get("type") == 5]
        if cnames:
            seen["cname"] = cnames
    return answers


# ------------------------------------------------------------------ the handler


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object with domain, or with txt")
    at = payload.get("at")
    if at is not None and not (isinstance(at, str) and _timestamp(at)):
        raise ValueError("at must be an ISO 8601 UTC time such as 2026-11-19T20:00:00Z")
    txt = payload.get("txt")
    if txt is not None:
        strings = [txt] if isinstance(txt, str) else txt
        if not isinstance(strings, list) or not strings or len(strings) > 16 \
                or not all(isinstance(item, str) and len(item) <= 4096 for item in strings):
            raise ValueError("txt must be one TXT string or a list of up to 16")
        out = select([item.strip() for item in strings], at)
        out.update(mode="validate", spec=SPEC)
        return out
    if not isinstance(payload.get("domain"), str):
        raise ValueError("give domain (a host name) or txt (the TXT strings to validate)")
    domain = host(payload["domain"])
    name = "_agent." + domain
    answers = resolve(name)
    usable = [seen for seen in answers if seen["ok"]]
    dns = {"resolvers": answers}
    if not usable:
        out = {"found": False, "valid": False, "code": 1004, "error": ERRORS[1004],
               "detail": "neither resolver gave a usable answer"}
    else:
        first = usable[0]
        observed = at or first.get("date")
        out = select(first["txt"], observed)
        if observed and not at:
            out["observed_at"] = observed
        dns["dnssec_validated"] = all(seen["dnssec_validated"] for seen in usable)
        if len(usable) > 1:
            dns["resolvers_agree"] = all(sorted(seen["txt"]) == sorted(first["txt"])
                                         for seen in usable)
            if not dns["resolvers_agree"]:
                out.setdefault("warnings", []).append(
                    "the two resolvers returned different records: one of them may still hold "
                    "the previous version in its cache (see ttl); the verdict uses "
                    + first["resolver"])
        if out["valid"] and not dns["dnssec_validated"]:
            out["warnings"].append("the answer is not DNSSEC-validated (AD flag not set): the "
                                   "record can be forged on the way from the zone to a client")
        if out["code"] == 1000:
            out["detail"] += "; the .well-known fallback of Appendix C is not checked here"
    out.update(mode="lookup", domain=domain, query=name, dns=dns, spec=SPEC)
    return out
