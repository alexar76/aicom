# HESTIA agent crypto.price.onchain@v1 — 2026-11-21

Owner 21.11, after reviewing CoinMarketCap's offer (pay-per-request quotes over x402; CMC does not allow
its quotes resold through another service): «Что можно сделать в HESTIA — делай, выкатывай новые капабилити на
хаб, тести, дополняй доки на 5 языках».

**What it is.** The price of ETH or BTC in USDC, read from public chain state on Base, with no exchange, data
vendor or price API.
- **Pools.** The four Uniswap v3 WETH/USDC or cbBTC/USDC pools (0.01/0.05/0.3/1 %). Each is confirmed by the
  factory's `getPool` (0x33128a8f…) at the same block.
- **Which pool.** The deepest pool whose tick moved in the window. A deep pool nobody traded only repeats its
  last trade: at 19:20Z the 0.3 % WETH pool had the most liquidity but an unchanged tick for 30 minutes.
- **Price.** The time-weighted mean tick from `observe([window, 0])`, then 1.0001^tick scaled by decimals.
  Spot comes from `slot0`, and every tier is shown as a cross-check.
- **Any pool.** `pool` takes any Uniswap v3 pool on Base. The agent checks the factory deployed it.
- **Reproducible.** Every read is pinned to one block (`block`, or the latest when the call starts).
- **Errors.** An RPC error is an error, never a zero.
- **Limits.** USDC is taken as $1. There is no volume or market capitalisation.
- **Egress and price.** It reaches `mainnet.base.org` only. Free.

**Why these sources.**
- Uniswap pool state is public chain data; the agent does the arithmetic itself.
- Chainlink Data Feeds were left out: their terms on passing feed values on outside the chain were not found
  (Data Streams, a separate product, prohibits "redistribution via proxy").
- Exchange and vendor APIs restrict redistribution, as CMC's does.

**Sandbox fit.** HESTIA allows six fetches per call, so reads go as JSON-RPC batches:
- `asset`: 2 fetches (head, then 16 calls);
- `pool`: 3 fetches.

The public Base RPC answered `eth_call` 5,000,000 blocks back, so a pinned block can be checked months later.

**Tests.**
- `tests/test_onchain_price.py` (18 tests) runs on `tests/onchain_price_vectors.json`: every batch
  mainnet.base.org answered at block 60,400,000, recorded 19:24Z.
- The ETH price is recomputed from the raw `observe()` words, independently of the handler.
- Covered: a day window falling back to the pools whose oracle reaches that far; pool mode; a contract the
  factory did not deploy; a rate-limited batch (error, not zero); a moved factory entry; bad input refused before
  any fetch.
- hestia-agents suite: all pass except `test_cli` payment-redeem (fails on main too) and
  `test_warden_scan::test_the_bundle_names_the_warden_it_was_built_from`. That one is not this change: main
  prepares WARDEN 0.36.0 (0aab20b44) and the warden.scan bundle is 0.35.0.
- ruff is clean.

**Live** (deploy 19:30:46Z, `cli verify` ok, signature repeats on the pinned probe). Called from outside at
about 19:31Z:

| input | answer | Coinbase spot at the same minute (check only) |
|---|---|---|
| `{"asset":"ETH"}` | 1682.077053 (0.05 % pool, block 60495420) | 1681.775 |
| `{"asset":"BTC"}` | 60201.604769 (0.05 % pool, block 60495428) | 60201.265 |
| `{"asset":"ETH","block":60400000,"window_s":600}` | 1700.931300, equal to the test | — |
| `{"pool":"0xd0b5…f224"}` | 1682.083033391499 USDC per WETH | — |
| `{"asset":"DOGE"}` | 400 with the reason | — |

Every answer is signed by the hearth and takes about 1.3 to 1.7 s.

**Docs.** `hestia-agents/docs/AGENTS{,.ru,.es,.fr,.zh}.md`: a table row and a section in each language.

**Hub.** The hearth is a federation peer of modelmarket.dev, so the hub lists its tenants on the next crawl
(hourly). The previous crawl was 19:18:57Z.

Rollback: delete the tenant on the hearth (owner API).
