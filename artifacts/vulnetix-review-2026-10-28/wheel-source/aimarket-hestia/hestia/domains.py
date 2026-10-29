"""Owner domains: a proven domain gives its owner the names that begin with it.

A domain is unique, but a deploy body can name any domain, so it counts only once its control
is proven, the way ACME and the MCP Registry prove it — either:

  - DNS:   a TXT record on _hestia.<domain> reading  hestia-owner=<owner public key, base64>
           (read through DNS-over-HTTPS, HESTIA_DOH_URL);
  - HTTPS: https://<domain>/.well-known/hestia-owner.json  =  {"owner_pubkeys": ["<key>", …]}

On proof the hearth claims for that owner, for good (hestia/names.py), the domain as a
namespace, zone included: every family, product and publisher that BEGINS with the domain, in
either order — `attestedmemory.net.claim.weigh`, `net.attestedmemory.claim.weigh`,
`attestedmemory-net.deal`, "Attestedmemory.net Labs" — is the owner's alone, and the domain itself
is its publisher name. The bare word is nobody's: attestedmemory.com, .dev and .net can be three
owners, so `attestedmemory.deal` stays first come, like any name. A name that merely starts with
the same letters (`attestedmemorynetwork.tool`) is held for review as a look-alike.

Only a registrable ASCII domain counts: example.com or example.co.uk, not a subdomain, and not an
IDN (its letters can pass for another script's). The namespace must not cover a name another
holder already uses; the operator settles that (POST /v1/admin/names/release).

The HTTPS proof is fetched from the domain the owner names, so the hearth refuses one that
resolves to anything but public unicast addresses (loopback, RFC 1918, link-local, CGNAT,
documentation and reserved ranges), follows no redirect, and reads at most 16 KiB. What comes
back is only compared with the owner's key; nothing of it is returned to the caller.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from typing import Any

import httpx

from hestia.owners import OwnerProofError, canonical_owner_key

PROOF_PATH = "/.well-known/hestia-owner.json"
TXT_LABEL = "_hestia"
TXT_PREFIX = "hestia-owner="
DEFAULT_DOH_URL = "https://cloudflare-dns.com/dns-query"
MAX_PROOF_BYTES = 16 * 1024
TIMEOUT_S = 6.0

# ccTLD second levels under which names are registered one level down (example.co.uk). A
# suffix missing here makes such a domain refused, never misread: the list fails closed.
SECOND_LEVEL = frozenset({
    "co.uk", "org.uk", "me.uk", "ltd.uk", "plc.uk", "net.uk", "ac.uk", "gov.uk",
    "com.au", "net.au", "org.au", "edu.au", "id.au",
    "co.nz", "org.nz", "net.nz",
    "co.jp", "ne.jp", "or.jp", "ac.jp",
    "co.kr", "or.kr", "ne.kr",
    "com.br", "net.br", "org.br",
    "com.cn", "net.cn", "org.cn",
    "com.hk", "com.tw", "com.sg", "com.my", "com.ph", "co.th", "co.id",
    "co.in", "net.in", "org.in", "firm.in",
    "com.mx", "com.ar", "com.co", "com.pe", "com.tr", "com.ua", "co.il", "co.za",
    "com.eg", "com.sa", "com.pl", "co.at", "or.at", "co.hu", "com.es", "com.pt",
    "msk.ru", "spb.ru", "com.ru", "net.ru", "org.ru", "pp.ru",
})
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class DomainError(Exception):
    """A domain that cannot be bound: not registrable, or its control not proven."""


def registrable(raw: str) -> str:
    """The domain in canonical form, or DomainError when it is not one an owner can bind."""
    domain = (raw or "").strip().lower().rstrip(".")
    if not domain or len(domain) > 253 or "/" in domain or ":" in domain or "@" in domain:
        raise DomainError("send a bare domain such as example.com (no scheme, port or path)")
    labels = domain.split(".")
    if not all(_LABEL.fullmatch(label) for label in labels):
        raise DomainError("a domain is ASCII letters, digits and hyphens between dots")
    if len(labels) < 2 or labels[-1].isdigit():
        raise DomainError("send a registrable domain such as example.com")
    if labels[0].startswith("xn--"):
        raise DomainError("an internationalised (IDN) name is not bound: its letters can pass "
                          "for another script's; use the ASCII domain")
    if len(labels) == 2 and domain not in SECOND_LEVEL:
        return domain
    if len(labels) == 3 and ".".join(labels[1:]) in SECOND_LEVEL:
        return domain
    raise DomainError(f"{domain} is not a registrable domain this hearth recognises: verify the "
                      "domain itself (example.com, example.co.uk), not a subdomain")


def _keys(values: Any) -> set[str]:
    out = set()
    for value in values if isinstance(values, (list, tuple, set)) else []:
        try:
            out.add(canonical_owner_key(str(value)))
        except OwnerProofError:
            continue
    return out


def txt_strings(data: str) -> str:
    """One TXT record's text from a DNS-over-HTTPS answer: quoted strings joined."""
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', data)
    return "".join(parts) if parts else data


def txt_proofs(domain: str, *, doh_url: str = DEFAULT_DOH_URL,
               transport: httpx.BaseTransport | None = None) -> set[str]:
    """Owner keys named by the TXT records of _hestia.<domain>."""
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, transport=transport) as client:
        res = client.get(doh_url, params={"name": f"{TXT_LABEL}.{domain}", "type": "TXT"},
                         headers={"accept": "application/dns-json"})
    if res.status_code != 200 or len(res.content) > 64 * 1024:
        return set()
    answers = res.json().get("Answer") or []
    named = []
    for answer in answers if isinstance(answers, list) else []:
        if isinstance(answer, dict) and answer.get("type") == 16:
            text = txt_strings(str(answer.get("data") or "")).strip()
            if text.startswith(TXT_PREFIX):
                named.append(text[len(TXT_PREFIX):].strip())
    return _keys(named)


def resolve(domain: str) -> list[str]:
    # The resolver's own order, which puts the family this host can reach first.
    infos = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(info[4][0] for info in infos))


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Global unicast, and so is any IPv4 address it carries: IPv4-mapped, 6to4 and NAT64
    (64:ff9b::/96, which Python calls global) reach that IPv4 address on a host routing them."""
    if ip.version == 6:
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is None and ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None:
            ip = embedded
    return ip.is_global and not ip.is_multicast


def require_public(domain: str) -> str:
    """Refuse a domain that resolves to anything but public unicast addresses; return the
    address to connect to."""
    try:
        addresses = resolve(domain)
    except (OSError, UnicodeError) as exc:
        raise DomainError(f"{domain} does not resolve") from exc
    if not addresses:
        raise DomainError(f"{domain} does not resolve")
    for address in addresses:
        if not _public(ipaddress.ip_address(address.split("%", 1)[0])):
            raise DomainError(f"{domain} resolves to a non-public address; it is not fetched")
    return addresses[0]


def https_proofs(domain: str, *, transport: httpx.BaseTransport | None = None) -> set[str]:
    """Owner keys listed at https://<domain>/.well-known/hestia-owner.json.

    The GET goes to the address that passed, not to the name: fetching by name let httpx
    resolve it again, and a domain that answered public for the check and 127.0.0.1 a moment
    later was fetched (DNS rebinding, the class of Vulnetix GCVE-110-PYPI-2026-021946).
    ``Host`` and TLS SNI carry the name, so the certificate is still verified against it.
    """
    url, headers, extensions = f"https://{domain}{PROOF_PATH}", {"accept": "application/json"}, {}
    if transport is None:
        address = require_public(domain)
        try:
            ascii_domain = domain.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise DomainError(f"{domain} is not a valid name") from exc
        url = f"https://{f'[{address}]' if ':' in address else address}{PROOF_PATH}"
        headers["Host"] = ascii_domain
        extensions = {"sni_hostname": ascii_domain}
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, transport=transport,
                      trust_env=False) as client:
        with client.stream("GET", url, headers=headers, extensions=extensions or None) as res:
            if res.status_code != 200:
                return set()
            body = b""
            for chunk in res.iter_bytes():
                body += chunk
                if len(body) > MAX_PROOF_BYTES:
                    return set()
    try:
        data = json.loads(body)
    except ValueError:
        return set()
    return _keys(data.get("owner_pubkeys")) if isinstance(data, dict) else set()


def prove(domain: str, owner: str, *, doh_url: str = DEFAULT_DOH_URL) -> str:
    """How `owner` proved control of `domain` ("dns" or "https"), or DomainError."""
    problems = []
    for method, read in (("dns", lambda: txt_proofs(domain, doh_url=doh_url)),
                         ("https", lambda: https_proofs(domain))):
        try:
            if owner in read():
                return method
        except DomainError as exc:
            problems.append(f"{method}: {exc}")
        except (httpx.HTTPError, ValueError, OSError) as exc:
            problems.append(f"{method}: {type(exc).__name__}")
    note = f" ({'; '.join(problems)})" if problems else ""
    raise DomainError(
        f"no proof that this key controls {domain}{note}. Publish either a TXT record on "
        f'{TXT_LABEL}.{domain} reading "{TXT_PREFIX}{owner}", or '
        f'https://{domain}{PROOF_PATH} with {{"owner_pubkeys": ["{owner}"]}}')
