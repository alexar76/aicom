# Signed A2A Agent Cards on the hosts of MCP registry remotes — 2026-11-21

Made while building HESTIA's `agent.card.verify@v1`, to test it on cards in the wild.

## How

1. Hosts: every distinct host of an `https://` remote in HISTOR's copy of the MCP registry
   (`artifacts/histor-subregistry-article-2026-11-21/merged-2026-11-21.jsonl.gz`, 69,634 entries):
   **36,014 hosts**.
2. One GET per host of `https://<host>/.well-known/agent-card.json` from this Mac on the evening (UTC) of
   2026-11-21 (32 parallel requests, 6 s timeout, user agent `agent-card-survey/1 (HISTOR research)`,
   redirects followed by urllib). A reply counts as a card when it is a JSON object with `name` and `skills` or
   `capabilities`: **2,923 cards** (`cards-found-2026-11-21.json`).
3. Cards with a non-empty `signatures` list: **183**.
4. Each of the 183 run through `agent-card/handler.py` (`hestia-agents/scripts/record_fetches.py`, the hearth's
   limits: the card host and hosts named in the call only, six requests) the same evening; result per host in
   `signed-cards-2026-11-21.json`.

## Result

| verdict | cards |
|---|---|
| `signed_verified` — a signature verifies with a key on the card's own host (JWKS at `jku`, did:web document, or `/.well-known/jwks.json`) | 109 |
| `signed_self_asserted` — only keys the signature carries itself verify (did:key, did:jwk, an embedded `jwk`) | 4 |
| `signature_failed` — no signature verifies over any of the four payload forms tried | 64 |
| `malformed` — a required field missing, or headers that break RFC 7515 | 5 |
| `not_found` — the card was gone at the second read | 1 |

Of the verified signatures, almost all cover the card as served; a few cover the card with empty values removed
(a2a-python's `signing.py`), one with default values also removed. Most failures are signatures that verify over
none of the forms with the key the host publishes now: the card or the key changed after signing. A few name their
JWKS on a parent domain (`jku` on another host), which the agent reads only when the caller names it.

Scope: hosts that serve an MCP remote listed in the official registry, read once from one address. Not a census of
A2A agents. Hosts are public endpoints; nothing here was published elsewhere.
