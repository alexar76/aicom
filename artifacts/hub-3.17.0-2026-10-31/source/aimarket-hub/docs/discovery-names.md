# Discovery names — two spellings of one document

> **Русский:** [discovery-names.ru.md](./discovery-names.ru.md) · **Español:** [discovery-names.es.md](./discovery-names.es.md) · **Français:** [discovery-names.fr.md](./discovery-names.fr.md) · **中文:** [discovery-names.zh.md](./discovery-names.zh.md)
>
> Code: [`discovery_names.py`](../aimarket_hub/discovery_names.py) · [`hub_routes/wellknown.py`](../aimarket_hub/hub_routes/wellknown.py) · [`crawler.py`](../aimarket_hub/crawler.py) · Drafts: [`aimarket-protocol/ietf/`](https://github.com/alexar76/aimarket-protocol/tree/main/ietf)

Since 2026-10-30 the hub serves its discovery document under two names, sends its crawler
header under two names, and accepts either. Nothing was renamed and nothing retired: every
peer in the network still reads the old names, and the new ones are a proposal under review.

## Why

The two Internet-Drafts in `aimarket-protocol/ietf/` describe this hub's discovery and
federation for the IETF DAWN working group. A document proposed as a standard cannot carry one
product's brand in a well-known URI, and `X-` header prefixes are deprecated (RFC 6648). So the
drafts use `/.well-known/agent-marketplace` and `Agent-Marketplace-Crawler`, and the hub that
claims to implement them has to serve those names — while every existing peer keeps working.

## What the hub does

| | Legacy (the wire contract) | Draft (proposal) |
|---|---|---|
| Discovery document | `GET`/`HEAD /.well-known/ai-market.json` | `GET`/`HEAD /.well-known/agent-marketplace` |
| Catalogue location | `manifest_url` | `catalogue_url` (same URL) |
| Signature profile | implied | `signature_profile: "ed25519-pipe-2"` |
| Admitted peers | `peers`: objects with `url`, `name`, `trust_score`, … | `peers`: discovery-document URIs |
| Crawler identifies itself | `X-AIMarket-Crawler: <hub url>` | `Agent-Marketplace-Crawler: <hub url>` |

- **Serving.** The draft document is built from the legacy one, so key, catalogue and counts
  can never disagree. It also carries `manifest_url` and `legacy_discovery_url` for a reader
  that lands there knowing only the old names. `peers` lists the discovery URI this hub
  actually reads for each admitted peer: the legacy path for a peer that serves only that, the
  draft path once a peer advertises one. A pending peer is listed in neither document.
- **Sending.** The crawler sends both headers with the same value on every fetch.
- **Accepting.** Both routes read both headers. When both arrive, the legacy value wins —
  that is the value peers have always been identified by. The rest is unchanged: recorded off
  the request path, syntactically validated, SSRF-checked before any fetch, admitted as
  *pending* under open federation and never trusted by the header alone.
- **Reading.** A peer that publishes the draft shape (`catalogue_url`, `peers` as URIs) is
  normalised to the legacy shape before validation, crawl and assay, so it is indexed like any
  other. A peer listed by a draft-path URI is dialled at that path, not at a legacy path it may
  not serve.

The signed catalogue is byte-identical under both names: the canonical string keeps the pair
name `tools_hash`, so a signature valid for one reader is valid for the other.

## Checking a hub

```bash
curl -s https://modelmarket.dev/.well-known/agent-marketplace | jq '{catalogue_url, signature_profile, peers}'
curl -sI https://modelmarket.dev/.well-known/agent-marketplace | head -1          # HEAD → 200
python3 aimarket-protocol/conformance/run.py --hub https://modelmarket.dev          # draft checks included
```

The conformance runner records the draft checks when the path answers and **skips** them on a
hub that serves only the legacy name. The drafts are proposals; the legacy path is the contract.
