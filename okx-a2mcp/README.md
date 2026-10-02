# okx-a2mcp

AIMarket's own services on [OKX.AI](https://www.okx.ai) as **A2MCP** endpoints — the marketplace's
pay-per-call mode, where an agent calls an HTTPS endpoint directly. Two services, both free for now:

| Service | Endpoint | What it answers |
|---|---|---|
| `histor-check` | `POST /a2mcp/histor-check` (or `GET ?endpoint=…`) | HISTOR's signed record of an MCP server: when its tool set was first pinned, whether it changed, what the pattern scan found. HISTOR answers from its own daily observations and never fetches the URL it is asked about. |
| `warden-scan` | `POST /a2mcp/warden-scan` | WARDEN's verdict on a `tools/list`: allow/block, a 0–1 score, every finding with the matched text, and the ruleset version and digest. Every member of each tool reaches WARDEN as sent; a description or title over 20 000 characters is refused (`400 bad_tool`), never cut — a cut would hide whatever follows it. No network, no state. |

Only services we run ourselves are listed. Reselling other sellers' hub listings here would make
this endpoint hold their money, which the hub's seller-direct rails exist to avoid.

## The A2MCP contract

What OKX.AI calls, and what this server answers:

- **No or missing parameters** → `200 {"status":"input_required","fields":[…]}`. OKX's self-check is a
  bare `curl -i -X POST <endpoint>` and expects `200` from a free endpoint, so this is not a 4xx.
- **A result** → `200 {"status":"ok", …}`.
- **Bad input** → `400`, **rate limit** → `429` (30 calls a minute per caller and service), **HISTOR
  down** → `502`. Every error is JSON with `status: "error"` and an `error` code.
- **Paid calls** on OKX.AI would be `402` + `PAYMENT-REQUIRED` (x402 V2). Not used yet — see below.

`GET /a2mcp` lists the services with their fields (and their x402 twin when one is configured);
`GET /health` is the liveness probe.

## x402 twins (Base, CDP Bazaar)

The same two services are also sold per call over x402, independent of OKX:
`POST /x402/histor-check` and `POST /x402/warden-scan`, $0.001 each in USDC on Base mainnet,
verified and settled by the Coinbase CDP facilitator. Each route declares the Bazaar discovery
extension (input example, input schema, output example), so the CDP Bazaar lists it after its first
settled payment. Without a valid payment the answer is `402` with the V2 `PAYMENT-REQUIRED` header.
The middleware settles only answers below 400, and a paid call with missing parameters gets `400`
(not the free endpoint's `input_required`), so a refused request costs the buyer nothing.

| Env | | |
|---|---|---|
| `CDP_KEY_FILE` | path to the CDP secret API key JSON (`{id, privateKey}`, as the portal downloads it) | read into memory, so the key is never in the container's environment; mount it read-only |
| `X402_PAY_TO` | the receiving address | must differ from any wallet you test-pay from: the facilitator refuses payer = payTo (`self_send_not_allowed`) |
| `X402_PRICE` | `$0.001` | per call, for routes without a price of their own |

### The hub's capabilities, over x402

With `HUB_API_KEY_FILE` set, four more paid routes resell the AIMarket hub's direct capabilities at
the hub's own price, so the Bazaar lists what the hub sells too:

| Route | Hub capability | Price |
|---|---|---|
| `POST /x402/weather-now` | `gaia.weather.read@v1` (latitude+longitude or city) | $0.001 |
| `POST /x402/air-quality-now` | `gaia.air.read@v1` (latitude+longitude or city) | $0.001 |
| `POST /x402/nearby-sensors` | `atlas.nearest.read@v1` (latitude, longitude, layers, max_km) | $0.03 |
| `POST /x402/fair-random` | `sortes.draw@v1` (seed up to 4096 bytes, num_bytes) | $0.006 |

The buyer pays this gateway; the gateway then buys the call from the hub with its own credit
account (the key in `HUB_API_KEY_FILE`, mounted like the CDP key) and returns the hub's result and
signed receipt. These routes have no free twin: `/a2mcp/<id>` answers `402`, because a free route
would spend the gateway's account for anyone. A call the hub refuses is not settled. The gateway's
account is a relay for outside buyers, so the hub's `ecosystem.json` must not list it under `self`.
`HUB_URL` defaults to `https://modelmarket.dev`.

The account is kept funded by `deploy/credit-topup.sh` (installed as `okx-a2mcp-credit-topup.timer` on
the apex host, hourly): below $1 it grants $5 through the hub's operator endpoint from inside the hub
container, at most $20 a UTC day; past the cap it refuses and says so in the journal.

x402 is off unless both `CDP_KEY_FILE` and `X402_PAY_TO` are set; the free `/a2mcp` routes do not
change either way. Building the paywall contacts the facilitator; if that fails (an outage, a revoked
key) the gateway still starts, the paid routes answer `503` and the build is retried in the background.
The per-caller limit runs before the paywall, so a flood of copied payment headers never reaches the
facilitator under our key.

## Deploy

`./deploy.sh` ships the committed sources to the apex host, builds there and swaps the container
(`deploy/remote.sh`): `127.0.0.1:9485 → 9480`, network `okx-a2mcp`, secrets in
`/opt/okx-a2mcp-secrets` (uid 1000, mode 400, mounted read-only: the CDP key and the caller-id key,
which the script generates on the host the first time), read-only root filesystem, all capabilities
dropped, 256 MB. The previous container is kept stopped as `okx-a2mcp-prev` and restored if the new
one fails `/health`. nginx routes `/a2mcp` and `/x402/` to port 9485
([`deploy/nginx/modelmarket.dev.conf`](../deploy/nginx/modelmarket.dev.conf)).

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
| `CALLER_ID_SECRET_FILE` | — | file holding the key of the buyer id sent to HISTOR (or `CALLER_ID_SECRET`); without one, a random key per process |
| `FREE_HISTOR_PER_MINUTE` | `200` | free `histor-check` calls across all callers; HISTOR allows us 300 a minute, the rest is the paid route's headroom |

Behind nginx the caller is read from `X-Forwarded-For`, trusted only from loopback and private
addresses — the Docker bridge nginx's traffic arrives from. HISTOR receives an HMAC of the caller's
address under a key it never sees as `X-AIMarket-Buyer`: a plain hash of an IPv4 address can be
reversed by trying all of them.

## Paid mode (not built yet)

OKX settles A2MCP calls in **USDT0 on X Layer** (`eip155:196`) through its facilitator. Turning a
service paid means adding OKX's `@okxweb3/x402-express` middleware with a route price, a
`PAY_TO_ADDRESS` (an EOA — a Safe deployed on Base does not exist on X Layer) and the facilitator
credentials `OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE` from the OKX Developer Portal. The
credentials belong in the host's `.env`, never in the repository or a chat.

Listing texts for the OKX.AI registration: [`docs/okx-listing.md`](docs/okx-listing.md).
