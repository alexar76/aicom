# Token mode of crypto.price.onchain@v1 — second check after the rollout (2026-11-22, about 17:30Z)

A check by the session that wrote the token-mode extras (main 8ef0a5784), after the rollout in `README.md`. Owner:
«Доделай ты»; by then everything in `README.md` was already live, so nothing was deployed or switched here.

**Live code equals main.** Roster handler digests at 17:31Z equal `main:hestia-agents/agents/<slug>/handler.py` for
onchain-price (36d81a8b595e…), x402-seller (2150f4a97f7a…), mcp-money-changes (0d53c0d0fdf1…), x402-preflight
(2c6c2fea7e00…), x402-settlement (45be0afb33ae…), evm-signature (7b89bfb66d61…) and base-gas (cf934e3fa7de…); 35
tenants. `/agents/catalog.json` lists 31 agents with the same digests for the three above.

**Live token calls** (`POST /t/onchain-price/invoke` with `{"token": …}`, free, each answer signed by the hearth,
`source` = the pool `https://base-rpc.hestia.modelmarket.dev`, 2.2–2.3 s). Coinbase spot is a check only, taken right
after; the agent's price is a 30-minute average, so a few tenths of a percent apart is expected.

| token | block | price_usd | basis | route, fee | dollars to move 1 % | Coinbase spot |
|---|---|---|---|---|---|---|
| DEGEN | 60,891,829 | 0.000704311533314 | twap | WETH pool × ETH/USDC, 0.3 % | 1,643.00 | 0.000703 |
| EURC | 60,891,842 | 1.095483085885 | last_trade (flagged) | direct USDC pool, 0.05 % | 36,592.67 | 1.094959 |
| AERO | 60,891,855 | 0.424642640659 | twap, routes_agree ok | WETH pool × ETH/USDC, 0.3 % | 14,289.28 | 0.422555 |
| no-code address (0x1218…Ad0a) | 60,891,867 | error "there is no contract at …" | — | — | — | — |

**Hub.** modelmarket.dev search: "token price Base ERC-20" → crypto.price.onchain@v1 first; "x402 seller payments" →
x402.seller.record@v1 first; "money tools changes" → mcp.money_tools.changes@v1 first; `external: []` for all three
(CoinMarketCap removed at 15:22Z, `../hub-cmc-removal-2026-11-22/`).

**Host note (competing-lab).** This session had started the same hearth rollout from main 8ef0a5784 at about the
same time. Its candidate build (17:01–17:02Z, never switched to) reused the tag `aicom-security:hestia-hearth-rpcpool-20261122`
and held it for about a minute while the live container already ran `20c3c610…` by ID. The tag was put back on
`20c3c6100d93…` at 17:02:41Z; that build (`1aa93c0e…`), its base tag `rpcbase-hestia-hearth:20261122` and its kit folder
`/root/hestia-rpc-pool-rollout-20261122` (created by it, mounted by no container) were removed. `hestia-hestia-1`, the
`rpcpoolbase-hestia-hearth:20261122` tag and `/root/hestia-rpc-pool-20261122` were not touched.
