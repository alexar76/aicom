"""Agent Resource Discovery (ARD): this hub's catalogue in the ARD formats.

ARD is a set of Internet-Drafts submitted to the IETF DAWN working group on 2026-10-30:

* draft-jimenez-dawn-ard-initial-contact-00 — how a client finds a manifest
  (``/.well-known/ard.json``, the ``ard`` link relation, SVCB, DNS-SD);
* draft-bu-dawn-ard-discovery-00 — the ARD entry and manifest (``application/ard+json``),
  the ``urn:air`` identifier, the signed ``trustManifest``, and the registry lookup
  interface (``POST /search``, ``POST /explore``, ``GET /agents``);
* draft-bu-dawn-ard-architecture-00 — roles and flows.

This module is a door, not a second protocol. Nothing here sells, prices or routes: every
entry describes an AIMarket Protocol v2 capability, and a buyer calls it the v2 way
(``POST /ai-market/v2/invoke``). What ARD adds is a way for a client that knows only ARD to
find this hub and what it lists.

Mapping (docs/ard.md):

* The well-known manifest lists this hub's own resources: its ARD registry
  (``application/ai-registry+json``), its A2A agent card, its MCP server card and its
  AIMarket discovery document. Each carries a digest of the bytes the hub serves at ``url``
  and a ``trustManifest`` signed with the hub's Ed25519 key under ``did:web:<host>``.
* The registry at ``/ard/v1`` lists the catalogue: one entry per sellable capability, typed
  ``application/vnd.aimarket.capability+json`` and pointing at a descriptor this hub serves.
  An entry this hub publishes (``source_hub`` = local) is signed; an entry indexed from an
  admitted peer is not, because this hub is not its publisher, and stays a discovery hint
  as the draft requires (draft-bu-dawn-ard-discovery-00 §6.2).

Search reuses the hub's own catalogue search, so ARD clients see exactly the offers the
HTTP, MCP and A2A doors show. The ``score`` is that search's relevance (lexical plus the
multilingual concept match) scaled to 0..100; it ranks text, not trust (§6.3).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlparse

# --- names ----------------------------------------------------------------------------

WELL_KNOWN_PATH = "/.well-known/ard.json"
DID_PATH = "/.well-known/did.json"
REGISTRY_PATH = "/ard/v1"

MANIFEST_MEDIA_TYPE = "application/ard+json"
REGISTRY_TYPE = "application/ai-registry+json"
A2A_CARD_TYPE = "application/a2a-agent-card+json"
MCP_CARD_TYPE = "application/mcp-server-card+json"
#: The MCP Server Card of the MCP extension (SEP-2127), at ``<streamable-http-url>/server-card``;
#: the same path as ai_catalog.SERVER_CARD_PATH (that module imports this one).
MCP_SERVER_CARD_PATH = "/mcp/server-card"
#: The older card: tools listed for scanners, the endpoint only in its description.
LEGACY_MCP_CARD_PATH = "/.well-known/mcp/server-card.json"
# The discovery document of draft-artamokhov-dawn-marketplace-discovery is plain JSON.
DISCOVERY_DOCUMENT_TYPE = "application/json"
# Not registered with IANA. Registration follows if anyone outside this protocol reads it.
CAPABILITY_TYPE = "application/vnd.aimarket.capability+json"
DID_MEDIA_TYPE = "application/did+json"
PROBLEM_MEDIA_TYPE = "application/problem+json"

ARD_CONTEXT = "https://agenticresourcediscovery.org/context/v1"
PROBLEM_BASE = "https://agenticresourcediscovery.org/problems/"
KEY_FRAGMENT = "hub-ed25519"
PQ_KEY_FRAGMENT = "hub-ml-dsa-65"

PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 100
FACET_LIMIT_DEFAULT = 10
FACET_LIMIT_MAX = 100
FEDERATION_MODES = ("auto", "referrals", "none")

#: Filter terms this registry evaluates. Anything else is refused rather than ignored: a
#: filter silently dropped returns entries the caller asked to exclude.
FILTER_TERMS = ("type", "tags", "capabilities", "publisher", "identifier", "trustManifest.identity")
FACET_FIELDS = ("type", "tags", "capabilities", "publisher")


class ArdError(Exception):
    """A request this registry refuses; rendered as RFC 9457 Problem Details."""

    _TITLES = {
        400: "Invalid Argument",
        404: "Not Found",
        501: "Not Implemented",
    }
    _CODES = {
        400: "INVALID_ARGUMENT",
        404: "NOT_FOUND",
        501: "NOT_IMPLEMENTED",
    }

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail

    def problem(self) -> dict[str, Any]:
        code = self._CODES.get(self.status, "INTERNAL_ERROR")
        return {
            "type": PROBLEM_BASE + code.lower().replace("_", "-"),
            "title": self._TITLES.get(self.status, "Error"),
            "status": self.status,
            "detail": self.detail,
            "error": code,
        }


# --- identifiers ----------------------------------------------------------------------

def publisher_host(url: str) -> str:
    """The lower-cased host of ``url`` (no port): the ``<publisher>`` of an ``urn:air`` name."""
    try:
        host = urlparse(str(url or "")).hostname or ""
    except ValueError:
        return ""
    return host.lower().rstrip(".")


# RFC 8141 NSS characters, minus ":" (it separates the ARD fields) and "/" (kept out of
# the agent-name so an identifier never reads as a path). Everything else is %-encoded.
_URN_SAFE = "-._~!$&'()*+,;=@"


def urn(publisher: str, namespace: str, name: str) -> str:
    """``urn:air:<publisher>:<namespace>:<agent-name>`` (draft-bu-dawn-ard-discovery-00 §3.4)."""
    return "urn:air:{}:{}:{}".format(
        quote(publisher, safe=_URN_SAFE),
        quote(namespace or "default", safe=_URN_SAFE),
        quote(name, safe=_URN_SAFE),
    )


def urn_publisher(identifier: str) -> str:
    """The ``<publisher>`` field of an ``urn:air`` identifier, or "" when it is not one."""
    parts = str(identifier or "").split(":")
    if len(parts) >= 5 and parts[0].lower() == "urn" and parts[1].lower() == "air":
        return parts[2].lower()
    return ""


def did_web(hub_url: str) -> str:
    """``did:web`` for a hub served at the root of its origin; "" otherwise.

    A hub mounted under a path would need its DID document at ``<path>/did.json``, which
    this hub does not serve; its entries then go unsigned rather than signed under a DID
    nobody can resolve.
    """
    parsed = urlparse(str(hub_url or ""))
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    if parsed.path not in ("", "/"):
        return ""
    host = parsed.hostname.lower()
    if parsed.port:
        host += "%3A" + str(parsed.port)
    return "did:web:" + host


def key_id(did: str) -> str:
    return f"{did}#{KEY_FRAGMENT}"


def pq_key_id(did: str) -> str:
    return f"{did}#{PQ_KEY_FRAGMENT}"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def did_document(did: str, public_key_b64: str, pq_public_key_b64: str = "") -> dict[str, Any]:
    """The DID document a ``did:web`` resolver fetches from ``/.well-known/did.json``.

    The hub's Ed25519 key, the same key its AIMarket discovery document publishes as
    ``signer_public_key``; and, when the hub signs hybrid, its ML-DSA-65 key as an RFC 9964
    ``AKP`` JWK, the same key that document publishes as its post-quantum key. Both are
    assertion methods only: this DID signs statements about the hub's catalogue and
    authenticates nothing else.
    """
    raw = base64.b64decode(public_key_b64)
    methods = [{
        "id": key_id(did),
        "type": "JsonWebKey2020",
        "controller": did,
        "publicKeyJwk": {"kty": "OKP", "crv": "Ed25519", "x": b64url(raw)},
    }]
    if pq_public_key_b64:
        methods.append({
            "id": pq_key_id(did),
            "type": "JsonWebKey2020",
            "controller": did,
            "publicKeyJwk": {"kty": "AKP", "alg": "ML-DSA-65", "pub": b64url(base64.b64decode(pq_public_key_b64))},
        })
    return {
        "@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/suites/jws-2020/v1"],
        "id": did,
        "verificationMethod": methods,
        "assertionMethod": [m["id"] for m in methods],
    }


# --- canonical bytes and digests -------------------------------------------------------

def jcs(value: Any) -> bytes:
    """RFC 8785 bytes, from the canonicalizer the ecosystem's other signed documents use."""
    import awr

    return awr.jcs.canonicalize(value)


def stable_bytes(document: Any) -> bytes:
    """The bytes this hub serves for a document whose digest it publishes.

    Sorted keys and no whitespace, so the same document always hashes the same; the digest
    is over these bytes exactly as sent, never over a re-serialisation.
    """
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --- trustManifest --------------------------------------------------------------------

def sign_trust_manifest(signer: Any, did: str, subject: dict[str, Any], issued_at: str) -> dict[str, Any]:
    """A ``trustManifest`` for ``subject``, signed by this hub (§3.5, §3.5.1).

    ``signature`` is a detached compact JWS (RFC 7515 Appendix F): ``<header>..<signature>``,
    computed over ``base64url(header) "." base64url(JCS(trustManifest without signature))``.
    The algorithm is EdDSA (RFC 8037), the only kind of key this hub holds; the draft makes
    ES256 mandatory to implement for verifiers, so a verifier that implements only ES256
    will not check these (docs/ard.md, "Limits").
    """
    manifest = {
        "identity": did,
        "issuedAt": issued_at,
        "subject": {k: v for k, v in subject.items() if v not in (None, "")},
    }
    header = {"alg": "EdDSA", "kid": key_id(did)}
    h64 = b64url(jcs(header))
    signing_input = h64 + "." + b64url(jcs(manifest))
    manifest["signature"] = h64 + ".." + b64url(signer.sign(signing_input.encode("ascii")))
    return manifest


def verify_trust_manifest(manifest: dict[str, Any], public_key_b64: str) -> bool:
    """True when ``manifest`` carries a valid detached EdDSA JWS by ``public_key_b64``
    under its own ``identity``. Strict Ed25519 via the hub's verifier."""
    try:
        token = manifest["signature"]
        h64, empty, s64 = token.split(".")
        if empty:
            return False
        header = json.loads(b64url_decode(h64))
        if header.get("alg") != "EdDSA" or header.get("kid") != key_id(str(manifest.get("identity") or "")):
            return False
        body = {k: v for k, v in manifest.items() if k != "signature"}
        signing_input = h64 + "." + b64url(jcs(body))
        from aimarket_hub.signing import Signer

        return Signer.verify(public_key_b64, base64.b64encode(b64url_decode(s64)).decode(), signing_input)
    except Exception:  # noqa: BLE001 - anything malformed is simply not a valid manifest
        return False


def subject_of(entry: dict[str, Any]) -> dict[str, Any]:
    """The release coordinates a trustManifest binds (§3.5): identifier, type, version, digest."""
    return {k: entry.get(k) for k in ("identifier", "type", "version", "digest")}


# --- entries --------------------------------------------------------------------------

def capability_descriptor(cap: Any, hub_url: str, *, display_name: str, access_mode: str,
                          identifier: str) -> dict[str, Any]:
    """What an ARD entry's ``url`` returns for one capability: its v2 terms.

    Only the facts a buyer needs to call it, and none that move on their own (measured
    success rates, latency, trust scores): the entry pins these bytes by digest, and a
    descriptor that changed every few minutes would make every published digest stale.
    """
    base = hub_url.rstrip("/")
    source = cap.source_hub or "local"
    tool = cap.tool_name()
    return {
        "identifier": identifier,
        "protocol": "aimarket-v2",
        "hub": base,
        "product_id": cap.product_id,
        "capability_id": cap.capability_id,
        "source_hub": source,
        "source_hub_name": cap.source_hub_name or None,
        "name": tool,
        "display_name": display_name,
        "description": cap.description,
        "version": cap.version,
        "input_schema": cap.input_schema or {},
        "output_schema": cap.output_schema or {},
        "price_per_call_usd": cap.price_per_call_usd,
        "routed_price_usd": cap.routed_price_usd if cap.routed_price_usd is not None else cap.price_per_call_usd,
        "routing_fee_bps": cap.routing_fee_bps,
        "access_mode": access_mode,
        "invoke": {
            "method": "POST",
            "url": f"{base}/ai-market/v2/invoke",
            "body": {"product_id": cap.product_id, "capability_id": cap.capability_id,
                     "source_hub": source, "input": {}},
        },
        "mcp": {"endpoint": f"{base}/mcp", "tool": tool},
        "a2a": {"agent_card": f"{base}/.well-known/agent-card.json"},
        "catalogue": f"{base}/ai-market/v2/manifest",
        "discovery": f"{base}/.well-known/agent-marketplace",
    }


def descriptor_url(hub_url: str, cap: Any) -> str:
    query = urlencode({"product_id": cap.product_id, "capability_id": cap.capability_id,
                       "source_hub": cap.source_hub or "local"})
    return f"{hub_url.rstrip('/')}{REGISTRY_PATH}/capability?{query}"


def capability_identifier(cap: Any, hub_url: str) -> str:
    """The ``urn:air`` name of one capability.

    ``<publisher>`` is the host that publishes the listing: this hub for a local row, the
    peer hub for a federated one. ``<namespace>`` is the v2 ``product_id`` and
    ``<agent-name>`` the ``capability_id``, so the name maps back to a v2 invoke unchanged.
    """
    source = cap.source_hub or "local"
    publisher = publisher_host(hub_url if source == "local" else source) or "localhost"
    return urn(publisher, cap.product_id, cap.capability_id)


@dataclass(frozen=True)
class CapabilityEntry:
    entry: dict[str, Any]
    descriptor: bytes
    source: str
    local: bool


def capability_entry(cap: Any, hub_url: str, *, display_name: str, access_mode: str,
                     tags: list[str]) -> CapabilityEntry:
    """One catalogue capability as an ARD entry, with the descriptor bytes it pins."""
    identifier = capability_identifier(cap, hub_url)
    descriptor = stable_bytes(capability_descriptor(
        cap, hub_url, display_name=display_name, access_mode=access_mode, identifier=identifier))
    source = cap.source_hub or "local"
    entry: dict[str, Any] = {
        "identifier": identifier,
        "displayName": display_name,
        "type": CAPABILITY_TYPE,
        "url": descriptor_url(hub_url, cap),
        "description": cap.description or "",
        "capabilities": [cap.tool_name()],
        "version": cap.version or "v1",
        "digest": digest(descriptor),
        "metadata": {"aimarket": {
            "protocol": "aimarket-v2",
            "product_id": cap.product_id,
            "capability_id": cap.capability_id,
            "source_hub": source,
            "price_per_call_usd": cap.price_per_call_usd,
            "access_mode": access_mode,
            "invoke_url": f"{hub_url.rstrip('/')}/ai-market/v2/invoke",
        }},
    }
    if tags:
        entry["tags"] = tags
    if not entry["description"]:
        del entry["description"]
    return CapabilityEntry(
        entry=entry,
        descriptor=descriptor,
        source=hub_url.rstrip("/") if source == "local" else source.rstrip("/"),
        local=source == "local",
    )


def own_entries(hub_url: str, hub_name: str, documents: dict[str, bytes]) -> list[dict[str, Any]]:
    """The entries of this hub's well-known manifest, unsigned.

    ``documents`` maps a card path this hub serves to the exact bytes it serves there; a
    card absent from it is left out rather than listed without a digest.
    """
    base = hub_url.rstrip("/")
    host = publisher_host(base) or "localhost"
    out: list[dict[str, Any]] = [{
        "identifier": urn(host, "registry", "catalogue"),
        "displayName": f"{hub_name} catalogue",
        "type": REGISTRY_TYPE,
        "url": base + REGISTRY_PATH,
        "description": (
            "The capabilities this AIMarket hub sells and indexes from admitted peer hubs. "
            "ARD lookup: POST /search, POST /explore, GET /agents. Calls and payment use "
            "AIMarket Protocol v2."
        ),
        "tags": ["aimarket", "registry"],
    }]
    # The MCP entry names the Server Card of the MCP extension (SEP-2127) when the hub serves it:
    # its remotes[].url states the endpoint as a field, which a client can compare with the URI of
    # the domain's AID record. The older card (tools listed for scanners, the endpoint only in its
    # description) is the fallback for a hub that does not serve the newer one.
    mcp_card = MCP_SERVER_CARD_PATH if MCP_SERVER_CARD_PATH in documents else LEGACY_MCP_CARD_PATH
    specs = (
        ("/.well-known/agent-card.json", A2A_CARD_TYPE, urn(host, "agent", "a2a"),
         f"{hub_name} (A2A)", "This hub as an A2A agent: catalogue search and paid calls as Tasks."),
        (mcp_card, MCP_CARD_TYPE, urn(host, "mcp", "gateway"), f"{hub_name} (MCP)",
         "This hub as an MCP server: its Server Card gives the endpoint in remotes[].url; "
         "tools/list there gives catalogue search and every listed capability as a tool."
         if mcp_card == MCP_SERVER_CARD_PATH else
         "This hub as an MCP server: catalogue search and every listed capability as a tool."),
    )
    for path, media_type, identifier, name, description in specs:
        data = documents.get(path)
        if data is None:
            continue
        out.append({
            "identifier": identifier,
            "displayName": name,
            "type": media_type,
            "url": base + path,
            "description": description,
            "digest": digest(data),
        })
    out.append({
        "identifier": urn(host, "index", "agent-marketplace"),
        "displayName": f"{hub_name} discovery document",
        "type": DISCOVERY_DOCUMENT_TYPE,
        "url": base + "/.well-known/agent-marketplace",
        # No digest: the document is re-signed every minute (its generated_at is inside its
        # own Ed25519 signature), so a pinned digest would be stale within the minute.
        "description": (
            "AIMarket discovery document (draft-artamokhov-dawn-marketplace-discovery): the "
            "hub's signing key, its signed catalogue and its admitted peers. It carries its own "
            "Ed25519 signature and is re-signed every minute, so it is not pinned by digest."
        ),
    })
    return out


# --- queries --------------------------------------------------------------------------

@dataclass(frozen=True)
class Query:
    text: str
    filter: dict[str, list[str]]


def parse_query(raw: Any, *, text_required: bool) -> Query:
    """The ``query`` object of a search or explore request (§4.2.1), validated."""
    if raw is None and not text_required:
        return Query(text="", filter={})
    if not isinstance(raw, dict):
        raise ArdError(400, "query must be an object")
    text = raw.get("text", "")
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise ArdError(400, "query.text must be a string")
    if len(text) > 2000:
        raise ArdError(400, "query.text is longer than 2000 characters")
    if text_required and not text.strip():
        raise ArdError(400, "query.text is required for POST /search")
    return Query(text=text.strip(), filter=parse_filter(raw.get("filter")))


def parse_filter(raw: Any) -> dict[str, list[str]]:
    """``filter``: term → string or array of strings. Values OR, terms AND (§4.2.1)."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ArdError(400, "query.filter must be an object")
    out: dict[str, list[str]] = {}
    for term, value in raw.items():
        if term not in FILTER_TERMS:
            raise ArdError(400, f"unsupported filter term {term!r}; this registry evaluates "
                                f"{', '.join(FILTER_TERMS)}")
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
            raise ArdError(400, f"filter {term!r} must be a string or a non-empty array of strings")
        out[term] = values
    return out


def _term_values(entry: dict[str, Any], term: str) -> list[str]:
    if term == "publisher":
        return [urn_publisher(entry.get("identifier", ""))]
    if term == "trustManifest.identity":
        manifest = entry.get("trustManifest")
        return [manifest.get("identity", "")] if isinstance(manifest, dict) else []
    value = entry.get(term)
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value is not None else []


def matches_filter(entry: dict[str, Any], flt: dict[str, list[str]]) -> bool:
    for term, wanted in flt.items():
        have = {v.lower() for v in _term_values(entry, term)}
        if not have.intersection(w.lower() for w in wanted):
            return False
    return True


def parse_page(page_size: Any, page_token: Any, fingerprint: str) -> tuple[int, int]:
    """``(size, offset)`` from ``pageSize`` and an opaque ``pageToken`` bound to the query."""
    if page_size is None or page_size == "":
        size = PAGE_SIZE_DEFAULT
    else:
        try:
            size = int(page_size)
        except (TypeError, ValueError):
            raise ArdError(400, "pageSize must be an integer") from None
        if isinstance(page_size, bool) or size < 1:
            raise ArdError(400, "pageSize must be a positive integer")
        size = min(size, PAGE_SIZE_MAX)
    if not page_token:
        return size, 0
    if not isinstance(page_token, str):
        raise ArdError(400, "pageToken must be a string")
    try:
        token = json.loads(b64url_decode(page_token))
        offset = int(token["o"])
        bound = str(token["q"])
    except Exception:  # noqa: BLE001
        raise ArdError(400, "pageToken is not one this registry issued") from None
    if bound != fingerprint or offset < 0:
        raise ArdError(400, "pageToken belongs to a different query")
    return size, offset


def page_token(offset: int, fingerprint: str) -> str:
    return b64url(json.dumps({"o": offset, "q": fingerprint}, separators=(",", ":")).encode())


def fingerprint(*parts: Any) -> str:
    """A short hash binding a page token to the query that produced it."""
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def score(relevance: float) -> int:
    """The hub's search relevance (0..1) as ARD's informational 0..100 integer."""
    try:
        value = float(relevance)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, round(value * 100)))


def search_item(entry: dict[str, Any], *, score_value: int, source: str) -> dict[str, Any]:
    """A search result item (§4.2.2.2): the entry's identity and pointer, plus score and source.

    ``version`` is not among the item's listed members, but a signed entry's ``trustManifest``
    binds it (§3.5), and a verifier checks the subject against the item it holds (§3.5.1).
    Without it a correctly signed result would fail that check.
    """
    item = {k: entry[k] for k in ("identifier", "displayName", "type", "url", "version", "digest") if k in entry}
    if "trustManifest" in entry:
        item["trustManifest"] = entry["trustManifest"]
    item["score"] = score_value
    item["source"] = source
    return item


def parse_facets(raw: Any) -> list[tuple[str, int]]:
    """``resultType.facets`` of an explore request (§4.2.3.1)."""
    if not isinstance(raw, dict):
        raise ArdError(400, "resultType must be an object with a facets array")
    facets = raw.get("facets")
    if not isinstance(facets, list) or not facets:
        raise ArdError(400, "resultType.facets must be a non-empty array")
    out: list[tuple[str, int]] = []
    for spec in facets:
        if not isinstance(spec, dict) or not isinstance(spec.get("field"), str):
            raise ArdError(400, "each facet needs a field")
        field = spec["field"]
        if field not in FACET_FIELDS:
            raise ArdError(400, f"unsupported facet field {field!r}; this registry counts "
                                f"{', '.join(FACET_FIELDS)}")
        limit = spec.get("limit", FACET_LIMIT_DEFAULT)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ArdError(400, f"facet {field!r} limit must be a positive integer")
        out.append((field, min(limit, FACET_LIMIT_MAX)))
    return out


def facet_counts(entries: list[dict[str, Any]], facets: list[tuple[str, int]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field, limit in facets:
        counts: dict[str, int] = {}
        for entry in entries:
            for value in dict.fromkeys(_term_values(entry, field)):
                if value:
                    counts[value] = counts.get(value, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        out[field] = {
            "buckets": [{"value": v, "count": c} for v, c in ranked[:limit]],
            "otherCount": sum(c for _, c in ranked[limit:]),
        }
    return out
