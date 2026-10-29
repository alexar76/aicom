"""Strip secrets out of log-derived values without costing any analytics.

SKOPOS ingests other people's access logs, which means it ingests whatever those
sites put in a URL: session tokens, password-reset links, magic-link codes,
tracking identifiers. None of that is anything SKOPOS needs, and all of it ends
up on disk, on the dashboard, and — before this module existed — in prompts sent
to a third-party LLM.

The obvious fix, dropping query strings, is not available: the dashboard groups
by path, bot detection reads path shape, and per-parameter breakdowns are
something operators actually use. So this redacts by **the shape of the value**
rather than by throwing the whole thing away:

    /api?mode=live&limit=80        unchanged — nothing here identifies anyone
    /reset?token=eyJhbGciOiJIUzI1  ->  /reset?token=<redacted>
    /t?visitor_id=a3f9c2e1b7d4     ->  /t?visitor_id=<redacted>

Two independent rules decide, and either one is enough to redact:

* the parameter is **named** like a credential (``token``, ``password``, ``sig``);
* the value **looks** like one — long, and drawn from the alphabet of a hex
  digest, a base64 blob or a JWT, with no spaces or words in it.

The second rule is what makes this hold up against a parameter nobody thought to
put on a list. The first is what catches a short secret. Together they leave
``mode=live``, ``page=3``, ``lang=ru`` and ``west=1953`` exactly as they were,
which is the whole point: a privacy control that breaks the dashboard gets turned
off, and then it protects nobody.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

REDACTED = "<redacted>"
#: Placeholder for a path segment that is an identifier rather than a route.
REDACTED_SEGMENT = "<id>"

#: Parameter names that are redacted whatever their value looks like. Matched as
#: a substring against the lower-cased name, so ``access_token`` and
#: ``X-Csrf-Token`` are both covered by ``token``.
#:
#: ``username`` and ``psd`` were added after measuring the live database: 14 rows
#: carried ``/boaform/admin/formLogin?username=admin&psd=admin``. Those particular
#: ones are a router-exploit scan rather than anyone's real credentials, but the
#: same two parameter names are what an ordinary login form puts in a URL when it
#: is built with GET, and the shape rules never fire on them because a username
#: and a typed password are both short. Redacting them costs the abuse detector
#: nothing: what identifies that scan is the path, which survives intact.
_SECRET_NAME_PARTS = (
    "auth", "apikey", "api_key", "bearer", "code", "credential", "csrf",
    "email", "hash", "jwt", "key", "nonce", "otp", "pass", "psd", "pwd",
    "secret", "session", "sid", "sig", "signature", "state", "ticket", "token",
    "uid", "user_id", "userid", "username", "visitor", "webhook",
)

#: Names that would trip the substring rule above but are ordinary analytics.
#: ``keyword`` contains "key"; ``codepage`` contains "code"; a "state" in a
#: shipping form is a province. Precision matters here — every false positive is
#: a hole in someone's dashboard.
_NAME_EXCEPTIONS = frozenset({
    "keyword", "keywords", "codepage", "country_code", "lang_code", "currency",
    "sidebar", "considered", "usernames",
})

#: Values in these alphabets, at this length, are not something a human typed.
_HEXISH = re.compile(r"^[0-9a-fA-F]{16,}$")
_B64ISH = re.compile(r"^[A-Za-z0-9_\-+/]{20,}={0,2}$")
_JWT = re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

#: A base64-shaped value that is really a word or a slug should survive. Real
#: secrets do not read as language, so require a mix of character classes before
#: calling something opaque.
_HAS_DIGIT = re.compile(r"\d")
_HAS_UPPER = re.compile(r"[A-Z]")
_HAS_LOWER = re.compile(r"[a-z]")


def _name_is_secretish(name: str) -> bool:
    lowered = name.strip().lower()
    if lowered in _NAME_EXCEPTIONS:
        return False
    return any(part in lowered for part in _SECRET_NAME_PARTS)


def _value_is_secretish(value: str) -> bool:
    """True when the value looks like a credential rather than a setting."""
    v = value.strip()
    if len(v) < 16:
        # Short values carry too little to be a useful secret and are far too
        # likely to be a real setting. The name rule covers short credentials.
        return False
    if _EMAIL.match(v):
        return True
    if _JWT.match(v):
        return True
    if _UUID.match(v):
        return True
    if _HEXISH.match(v):
        return True
    if _B64ISH.match(v):
        # Distinguish "aGVsbG8gd29ybGQ" from "product-listing-page": an opaque
        # blob mixes cases and digits; a slug generally does not.
        classes = sum(
            bool(rx.search(v)) for rx in (_HAS_DIGIT, _HAS_UPPER, _HAS_LOWER)
        )
        return classes >= 2
    return False


def _value_embeds_secret(value: str) -> bool:
    """True when a value is itself a URL carrying a secret-shaped parameter.

    ``?url=https%3A%2F%2Fa.example%3Ftoken%3DeyJhbGci…`` is the case that gets
    missed otherwise: percent-encoding puts ``%`` and ``:`` into the value, so it
    matches none of the opaque-blob patterns, and ``url`` is a name worth keeping
    as an analytic dimension. Decoding once and re-applying the same rules keeps
    ``url=https://a.example`` while killing the nested credential.
    """
    if "%" not in value and "=" not in value:
        return False
    try:
        decoded = unquote(value)
    except Exception:  # noqa: BLE001 - a malformed escape is not worth a crash
        return False
    if decoded == value and "=" not in decoded:
        return False
    _, _, nested = decoded.partition("?")
    for part in (nested or decoded).replace("&", "?").split("?"):
        name, sep, inner = part.partition("=")
        if sep and inner and (_name_is_secretish(name) or _value_is_secretish(inner)):
            return True
    return False


def should_redact(name: str, value: str) -> bool:
    return (
        _name_is_secretish(name)
        or _value_is_secretish(value)
        or _value_embeds_secret(value)
    )


def redact_query(query: str) -> str:
    """Redact secret-shaped values in a raw query string, preserving order and keys.

    Operates on the raw text rather than parsing and re-encoding, so a value that
    was never a well-formed pair still passes through recognisably and nothing is
    silently re-written.
    """
    if not query:
        return query
    out = []
    for part in query.split("&"):
        if not part:
            out.append(part)
            continue
        name, sep, value = part.partition("=")
        if not sep or not value:
            out.append(part)
            continue
        out.append(f"{name}={REDACTED}" if should_redact(name, value) else part)
    return "&".join(out)


#: Routes that carry a credential IN THE PATH. The hub hands out `/mcp/k/<api key>` to
#: clients that can set a URL and no header (claude.ai custom connectors); every request
#: from such a client puts a spendable key into the access-log line this module reads.
_KEY_IN_PATH = re.compile(r"(/mcp/k/)[^/?#\s]+")
#: A segment that starts like a known credential is redacted whatever route it is on.
_SECRET_SEGMENT = re.compile(
    r"^(aimk_|sk-|ghp_|gho_|github_pat_|xox[baprs]-|npm_|glpat-|AKIA)[A-Za-z0-9_\-]{8,}$"
)


def _redact_segments(head: str) -> str:
    head = _KEY_IN_PATH.sub(lambda m: m.group(1) + REDACTED_SEGMENT, head)
    if "/" not in head:
        return head
    parts = head.split("/")
    return "/".join(REDACTED_SEGMENT if _SECRET_SEGMENT.match(unquote(p)) else p for p in parts)


def redact_path(path):
    """Redact a request target, keeping the route and the parameter names.

    Grouping, bot detection and per-path breakdowns all read the part that
    survives. Cardinality actually improves: a thousand distinct session tokens
    collapse into one path instead of a thousand.
    """
    if not path or not isinstance(path, str):
        return path
    head, sep, query = path.partition("?")
    head = _redact_segments(head)
    if not sep:
        return head
    # A fragment cannot reach a server in a request line, but a malformed log
    # line can contain anything; keep it attached to whatever it followed.
    return f"{head}?{redact_query(query)}"


def redact_referer(referer):
    """Reduce a referer to its origin.

    The classic leak is a password-reset or magic-link URL arriving as the
    referer of the next request. Analytics only ever reads ``referer_domain``,
    which is derived separately — so the path and query here are pure exposure
    with no consumer.
    """
    if not referer or not isinstance(referer, str):
        return referer
    text = referer.strip()
    if text == "-":
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if not parts.scheme or not parts.netloc:
        # Not a URL we can safely reduce; keep only what is unambiguously not a
        # path, which for an unparseable referer is nothing.
        return None
    return f"{parts.scheme}://{parts.netloc}"


def redact_parsed(pr) -> dict:
    """The fields of a parsed request that this policy rewrites.

    Applied in the single ingest path so every transport inherits it, and in the
    agent so the bytes never leave the monitored host at all.

    ``line_raw`` is deliberately **not** touched here. It is the input to the
    deduplication hash, and two different requests whose tokens differ redact to
    the same text — blanking or redacting it before hashing would make them
    collide and silently drop the second. It is dropped at the storage boundary
    instead, after the hash of the original has been taken. See
    :func:`skopos.db.insert_requests`.
    """
    return {
        "path": redact_path(getattr(pr, "path", None)),
        "referer": redact_referer(getattr(pr, "referer", None)),
        # Nothing reads this back: it is parsed into method/path/version at parse
        # time and never selected again. Keeping it stores a second, unredacted
        # copy of exactly what the rest of this module removes.
        "request_raw": None,
    }
