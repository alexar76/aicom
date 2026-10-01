# okx-a2mcp

AIMarket's own services on [OKX.AI](https://www.okx.ai) as **A2MCP** endpoints — the marketplace's
pay-per-call mode, where an agent calls an HTTPS endpoint directly. Two services, both free for now:

| Service | Endpoint | What it answers |
|---|---|---|
| `histor-check` | `POST /a2mcp/histor-check` (or `GET ?endpoint=…`) | HISTOR's signed record of an MCP server: when its tool set was first pinned, whether it changed, what the pattern scan found. HISTOR answers from its own daily observations and never fetches the URL it is asked about. |
| `warden-scan` | `POST /a2mcp/warden-scan` | WARDEN's verdict on a `tools/list`: allow/block, a 0–1 score, every finding with the matched text, and the ruleset version and digest. No network, no state. |

Only services we run ourselves are listed. Reselling other sellers' hub listings here would make
this endpoint hold their money, which the hub's seller-direct rails exist to avoid.

## The A2MCP contract

What OKX.AI calls, and what this server answers:

- **No or missing parameters** → `200 {"status":"input_required","fields":[…]}`. OKX's self-check is a
  bare `curl -i -X POST <endpoint>` and expects `200` from a free endpoint, so this is not a 4xx.
- **A result** → `200 {"status":"ok", …}`.
- **Bad input** → `400`, **rate limit** → `429` (30 calls a minute per caller and service), **HISTOR
  down** → `502`. Every error is JSON with `status: "error"` and an `error` code.
- **Paid calls** would be `402` + `PAYMENT-REQUIRED` (x402 V2). Not used yet — see below.

`GET /a2mcp` lists the services with their fields; `GET /health` is the liveness probe.

## Run and test

```bash
npm ci
npm test                       # node:test, no network
PORT=9480 npm start            # HISTOR_URL, PUBLIC_URL, RATE_PER_MINUTE are optional
```

| Env | Default | |
|---|---|---|
| `PORT` / `HOST` | `9480` / `127.0.0.1` | the Docker image binds `0.0.0.0` |
| `HISTOR_URL` | `https://histor.modelmarket.dev` | the only host this server ever calls |
| `PUBLIC_URL` | — | used in the `/a2mcp` manifest |
| `RATE_PER_MINUTE` | `30` | per caller and service |
| `TRUST_PROXY` | `loopback, uniquelocal` | Express `trust proxy`: nginx reaches a published container via the Docker bridge |

Behind nginx the caller is read from `X-Forwarded-For`, trusted only from loopback and private
addresses — the Docker bridge nginx's traffic arrives from. HISTOR receives
a hash of the caller's address as `X-AIMarket-Buyer`, never the address.

## Paid mode (not built yet)

OKX settles A2MCP calls in **USDT0 on X Layer** (`eip155:196`) through its facilitator. Turning a
service paid means adding OKX's `@okxweb3/x402-express` middleware with a route price, a
`PAY_TO_ADDRESS` (an EOA — a Safe deployed on Base does not exist on X Layer) and the facilitator
credentials `OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE` from the OKX Developer Portal. The
credentials belong in the host's `.env`, never in the repository or a chat.

Listing texts for the OKX.AI registration: [`docs/okx-listing.md`](docs/okx-listing.md).
