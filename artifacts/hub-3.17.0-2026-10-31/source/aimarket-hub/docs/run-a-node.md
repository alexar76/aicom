# Make the API you already run a node

[English](run-a-node.md) · [Русский](run-a-node.ru.md) · [Español](run-a-node.es.md) · [Français](run-a-node.fr.md) · [中文](run-a-node.zh.md)

You sell something over HTTP already — an x402 route, a REST endpoint. To be found by the hubs
of the federation you do not need to run a hub: `aimarket node` is a small process that stands
beside your API and speaks the protocol for it.

- It publishes a signed `/.well-known/ai-market.json` and a signed manifest of the routes you
  name, signed fresh on every read.
- It answers `POST /ai-market/v2/invoke` by calling **your** route — GET with the input as
  query parameters, or POST with it as JSON — and passes x402 payment headers through both
  ways: your 402 reaches the buyer as it is, and the paid retry reaches your route with its
  payment. x402 V1 (offer in the body) and V2 (offer in `PAYMENT-REQUIRED`) both work.
- It signs a receipt for every 2xx answer of your route.

Your money stays where it is: the node never holds, verifies or moves payments. Your route keeps
doing that exactly as today.

## 1. Describe your routes

```bash
pip install "aimarket-hub[pqc]"            # Python 3.11+, or: uvx --from "aimarket-hub[pqc]" aimarket …
aimarket node init                         # writes node.toml
```

```toml
name = "Acme weather"
url = "https://api.acme.example"           # where other hubs reach the node
upstream = "http://127.0.0.1:8000"         # your API, as it runs now

[[capability]]
id = "weather.now@v1"
product = "acme-weather"
description = "Current weather for a city"
price_usd = 0.002                          # must equal what your route's 402 asks
method = "GET"
path = "/weather"
input_schema = { type = "object", required = ["city"], properties = { city = { type = "string" } } }
```

A free route, if you have one, is the quickest evidence for admission: the sandbox calls it and
checks the node's signature on the receipt. A paid-only node is admitted on its door instead:
an unpaid call must answer 402 with an offer that names your wallet and the same price as
`price_usd`.

## 2. Run it beside your API

```bash
aimarket node serve --config node.toml     # → 127.0.0.1:9090 by default (--host, --port)
```

Send two paths of your public domain to it and leave everything else as it is. Caddy:

```
api.acme.example {
    handle /.well-known/ai-market.json { reverse_proxy 127.0.0.1:9090 }
    handle /ai-market/* { reverse_proxy 127.0.0.1:9090 }
    handle { reverse_proxy 127.0.0.1:8000 }
}
```

nginx: `location = /.well-known/ai-market.json` and `location /ai-market/`, both
`proxy_pass http://127.0.0.1:9090;`. The node's key (`data/node_signing_key` by default, and
`_mldsa` beside it) is its identity: back it up.

## 3. Check, then knock

```bash
aimarket doctor --url https://api.acme.example   # the admission check other hubs will run
aimarket node knock                               # announce to modelmarket.dev (--hub for another)
```

The answer carries `assay_url`, where the verdict appears. On a `pass`, hubs with automatic
admission index your capabilities: they appear in their search, in their MCP endpoint
(`market_search` / `market_invoke` at `https://modelmarket.dev/mcp`) and on their `/hubs`
page. A buyer routed through a hub meets your route's 402 as it is — header and all — and pays
you directly; hubs take no routing fee on a direct x402 sale (the node declares
`payment_rails.seller_direct`, which is how they know).

## What it does not do

- It does not decide prices or take a cut, and neither do the hubs that relay a direct x402 sale
  to you: what a buyer pays your route is yours in full.
- It does not make your route safe or correct, and it does not vouch for the answer: the receipt,
  signed by the node, records that your route answered (capability, price, time, latency,
  success) — not what it answered.
- Buyer traffic through the federation is still small. The live counters are public:
  `https://verify.modelmarket.dev/demand.json`.
