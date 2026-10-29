# StallRow — a row of x402 micro-services in one deployment

Thirteen small paid endpoints under one roof, one facilitator
configuration, one Railway service. The strategy is a portfolio: many
real stalls, each independently priced, listed, and settled, expecting
one or two to hit — instead of betting the season on a single route.
Siblings: [Token Verdict](https://github.com/QuincyGB/token-verdict)
(token-risk verdicts), [RouteVerdict](https://github.com/QuincyGB/route-verdict)
(trust & liveness checks), [ListSmith](https://github.com/QuincyGB/list-smith)
(listing grade & repair). No accounts, no API keys: **payment is the
authentication** (x402 v2, exact scheme, USDC on Base).

## The row

| Route | Price | What it does |
|---|---|---|
| `POST /v1/wallet-snapshot` | $0.005 | Base wallet: ETH balance, top token holdings, first/last activity, nonce |
| `POST /v1/allowance-audit` | $0.005 | ERC-20 approvals vs a curated spender list; unlimited approvals flagged |
| `POST /v1/tx-decoder` | $0.002 | One Base tx → plain English: method, value, ERC-20 transfers, summary |
| `POST /v1/gas-oracle` | $0.001 | Gas price + base-fee trend over the last ~20 blocks + cheap-window hint |
| `POST /v1/wallet-verdict` | $0.02 | SAFE/CAUTION/AVOID: OFAC match, wallet age, activity, poisoning scan |
| `POST /v1/tube-search` | $0.01 | YouTube search results as JSON (public page scrape, no API key) |
| `POST /v1/page-to-markdown` | $0.01 | One page → clean Markdown (SSRF-guarded) |
| `POST /v1/repo-vitals` | $0.005 | GitHub repo vitals + health score |
| `POST /v1/price-check` | $0.05 | Live CDP Bazaar comps + a recommended listing price |
| `POST /v1/card-smith` | $0.10 | Generate/grade `agent-card.json` for A2A/AgentWorld registries |
| `POST /v1/job-scout` | $0.05 | Digest of open agent jobs from our own marketplace sweeps |
| `POST /v1/recheck` | $0.005 | Scheduled change detection: BASELINE / UNCHANGED / CHANGED diff for one x402 resource or web page, probed unpaid |
| `POST /v1/recheck/pack` | $1.00 | Prepaid recheck pack: 250 change-checks on ONE endpoint URL, 90-day expiry — spend via `pack_id` on `/v1/recheck` ($0.004/check) |
| `POST /v1/fleet-check` | $0.10 | One health sweep of YOUR whole fleet: per-route OK / DEGRADED / DOWN verdicts with the defect named, plus a grade per origin — unpaid probes only, never pays a route it checks |
| `POST /v1/fleet-check/pack` | $5.00 | Prepaid Fleet Check pack: 100 sweeps of ONE fixed fleet definition, 90-day expiry — run via `POST /v1/fleet-check/run`, read via `POST /v1/fleet-check/status` ($0.05/sweep) |

**Per-call or pack?** One-off check → pay $0.005 per call. Anything on
a schedule — a monitoring loop, a buyer's drift check, a daily
re-screen — → buy the $1 pack once (250 checks, one endpoint, 90
days) and spend credits. At 3+ checks a week the pack is cheaper
*and* removes 249 settlements from your loop.

**Fleet Check** is the whole-fleet form: one $0.10 sweep covers up
to 40 of your resources (named directly, or expanded from your
origins' `/.well-known/x402`), classifying each OK / DEGRADED /
DOWN with the specific defect — unreachable, 5xx, no 402,
undecodable challenge, or a live amount/payTo that disagrees with
your own discovery doc — and grading each origin. The pack form
($5.00 = 100 sweeps of one fixed fleet definition, 90 days) runs
on your interval, diffs against the previous sweep, and POSTs new
failures and recoveries to your webhook (heartbeats optional). One
credit buys a whole sweep, never one route. Every probe is unpaid:
the checker never pays, signs, or settles any route it checks.

Free: `GET /`, `/health`, `/quote`, `/.well-known/x402`, `/skill.md`,
`/llms.txt`, and `POST /v1/recheck/pack-balance` (credits + expiry for
a pack id; spends nothing). Pack semantics: minting is idempotent on
the payment's EIP-3009 authorization nonce, so a re-presented payment
returns the pack it already bought; a credit is reserved atomically
before each check and refunded when the check itself fails (our
failure never consumes one); unknown pack → 404, wrong endpoint →
403, expired → 410, exhausted → 402, and no path silently falls back
to a per-call charge.

## Failure honesty (the house rule)

If an upstream cannot supply the data, the call returns **502 — and
the x402 middleware does not settle payment on ≥ 400 responses**, so
nobody is charged for undelivered data. Fields a source cannot supply
come back `"unknown"` or omitted, never invented. This matters most
for **Blockscout**: base.blockscout.com sits behind Cloudflare and
intermittently (measured during the build: roughly half of calls from
a datacenter IP, fewer with a browser User-Agent) answers with a
challenge page instead of JSON. The client tries the v2 API, then the
legacy Etherscan-style API, then degrades per field (RPC still covers
ETH balance and nonce). Token balances, activity windows, the poisoning scan, and the
allowance audit's token-dependent fields are explorer-only and go `"unknown"` when challenged —
retrying usually fills them in.

## Data sources and their limits

- **Base RPC** (`BASE_RPC_URL`, default `https://mainnet.base.org`):
  balances, nonces, gas, blocks, transactions, `eth_call` allowance
  reads. Cannot enumerate a wallet's tokens or history — that's the
  explorer's job.
- **Blockscout** (`BLOCKSCOUT_BASE_URL`, default
  `https://base.blockscout.com`): token balances, transaction and
  token-transfer history. Cloudflare caveat above.
- **Allowance audit coverage** is bounded by the curated spender list
  in `app/data/spenders.py` (10 major Base spenders: Permit2, Uniswap
  V3/Universal routers, Aerodrome, 1inch, Odos, KyberSwap). Approvals
  to any other contract are invisible, and the response says so.
  Permit2's internal allowance map is not read.
- **Sanctions**: exact-address match against a bundled OFAC SDN
  snapshot (`app/data/ofac_crypto_addresses.json`, 91 EVM addresses
  extracted 2026-10-21 from the official Treasury `sdn.csv`
  "Digital Currency Address" entries). A snapshot ages: refresh it
  periodically. If the snapshot is ever missing/empty the check
  returns `"unknown"` — **never** a fabricated "clean".
- **YouTube search** parses the public results page (`ytInitialData`);
  YouTube can change that shape or throttle scrapers, in which case
  the route 502s rather than guessing.
- **Price-check** reads the CDP Bazaar public catalog
  (`/platform/v2/x402/discovery/resources`; live envelope is
  `{"items": [...], "pagination": {"total": …}}`, ~20/page, 28,423
  resources at build time). The catalog's own filter params are
  unreliable (cdp-sdk #765), so pages are matched client-side; only
  the first 5 pages are scanned per call, and the response says how
  many matched within them.
- **JobScout** serves `data/jobs.json`, seeded from our own Synmerco
  sweep and refreshed by `scripts/refresh_jobscout.py` (below).
  Responses carry the snapshot time and a `data_stale` flag past 24h.
- **Recheck state** lives in one sqlite store: one row per watch
  (watch_id + URL) holding the last good fingerprint, plus one row per
  watch pack. In production the store is `/data/recheck.db` on the
  service's Railway volume, and `/health` reports
  `"recheck_store": "persistent"`; watch baselines and pack credits
  therefore persist across redeploys. `STALLROW_RECHECK_DB` can set
  another path, and without a mounted volume the fallback is ephemeral
  local disk. The state remains local to this service's volume —
  deleting both the service and its volume would lose it. Failed
  probes never overwrite a stored fingerprint, so a target's outage
  does not re-baseline or fabricate a change.

## Run it

```bash
pip install -r requirements.txt
python -m app.main            # or: uvicorn app.main:app --port 3000
pytest                        # 168 tests, fully offline (MockTransport)
```

Key env vars: `X402_FACILITATOR_URL` (keyless ultravioletadao default;
`https://facilitator.payai.network` for the PayAI index; the CDP URL
plus `CDP_API_KEY_ID`/`CDP_API_KEY_SECRET` for the CDP Bazaar — see
`app/config.py`), `X402_PAY_TO`, `BASE_RPC_URL`, `BLOCKSCOUT_BASE_URL`,
`GITHUB_TOKEN` (optional, raises repo-vitals rate limits),
`STALLROW_FETCH_TIMEOUT_S`, `STALLROW_RECHECK_DB` (recheck watch
state file), per-route `X402_PRICE_<ROUTE>` overrides.

## JobScout refresh

```bash
python3 scripts/refresh_jobscout.py   # rewrites data/jobs.json
```

Reads the Synmerco API (`GET /v1/jobs`) the same way our sweeps do.
The API key comes from the `SYNMERCO_KEY` env var or `~/.synmerco/key`
when present; it is never printed and never written into the snapshot.
Redeploy (or restart) after refreshing so the running service picks up
the new file.

## Cataloging (deploy notes for the operator)

Cataloging is settlement-driven per facilitator — metadata alone
never lists a route (background:
`~/workspace/platform-signups/x402-bazaar.md`). Deploy as ONE Railway
service from this repo (Dockerfile included, healthcheck `/health`),
set `X402_FACILITATOR_URL=https://facilitator.payai.network`, then
settle **one paid call per route** so each resource catalogs in the
PayAI index: 5000+5000+2000+1000+20000+10000+10000+5000+50000+100000
+50000 = **258,000 units = $0.258 total**. Repeat under the CDP env
(once CDP keys exist) for the CDP Bazaar, and re-settle at least every
~30 days per index or listings age out.

**Recheck status (2026-10-24):** `/v1/recheck` is live in production
but **not yet cataloged in either index** — no seed call has been
made for it, by the owner's choice. Cataloging it later costs one
$0.005 settled call per index ($0.005 via the CDP facilitator for the
CDP Bazaar; for PayAI, StallRow's facilitator must first be flipped
to PayAI for that one call and flipped back, as was done for
allowance-audit). Until then the route sells nothing and appears in
no catalog — it is reachable only by direct URL.
