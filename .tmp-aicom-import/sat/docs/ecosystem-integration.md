# Ecosystem integration — Factory → Hub → ACEX → Widget → UNI

This document describes **cross-repo flows** that tie the AI-Factory monorepo and satellites into one product surface, not isolated folders.

## North-star (Agent IPO) — now shipped end-to-end

**Agent IPO** — single pipeline, all four steps now wired:

1. AI-Factory completes a product → capability manifest ✅
2. AIMarket Hub auto-lists (`auto_listing` / factory bridge) ✅
3. ACEX CapShares listing + Pulse Terminal live quote ✅
4. Invoke revenue routed to share holders ✅

Off-chain reference ledger (`aimarket_hub/acex_ipo.py`) mirrors the on-chain
contracts (`AgentListingRegistry` + `AgentShareToken`) and computes exact pro-rata
payouts. Settlement has **two rails**: an off-chain claim ledger, and on-chain via
`PulseDistributor.sol` (Merkle epoch claims). The off-chain `distribute()` snapshot
feeds the Merkle root that the contract verifies — same leaf encoding, proven by
`aimarket_hub/acex_merkle.py` (pure-Python keccak256, no deps).
Run the whole leg offline: `python scripts/demo_agent_ipo.py`.

## Shipped integration (this milestone)

### Try-before-buy (widget ↔ hub)

| Layer | Path | Role |
|-------|------|------|
| Embed | `aimarket-widget/widget.js` | "Try free (N)" uses `X-AIMarket-Sandbox-Visitor` |
| Hub | `GET /ai-market/v2/sandbox/quota` | Remaining trials per visitor |
| Hub | `POST /ai-market/v2/invoke` + header | Zero debit; signed receipt with `list_price_usd` |
| Ledger | `aimarket_hub/sandbox_trials.py` | Per-visitor + per-IP rate limits |

Env (hub):

- `AIMARKET_SANDBOX_MAX_PER_VISITOR` (default `3`)
- `AIMARKET_SANDBOX_STUB_INVOKE=1` — offline/CI deterministic output when factory is down

Paid widget flow uses **v2 channel** routes:

- `POST /ai-market/v2/channel/open`
- `POST /ai-market/v2/invoke` + `X-Payment-Channel`
- `POST /ai-market/v2/channel/close`

### Agent-to-agent demo

```bash
# Hub running on 9083 with factory URL or stub
python scripts/demo_agent_to_agent.py --hub http://127.0.0.1:9083
```

Uses `aimarket-agent` (`AIMarketAgent.run`) — same protocol surface as production agents.

### Agent IPO (factory → hub → ACEX)

When the factory ships a product and the hub auto-lists it, the product is floated
as an ACEX CapShares listing, and every **paid** invoke routes a configurable slice
of revenue into a distributable pool that holders claim. Sandbox trials (`price == 0`)
accrue nothing.

| Layer | Path | Role |
|-------|------|------|
| Factory→Hub | `aimarket_hub/auto_listing.py` | Lists caps, then floats on ACEX if `ACEX_AUTO_IPO=1` |
| ACEX ledger | `aimarket_hub/acex_ipo.py` | Listing + CapShares cap table + revenue pool (micro-USD, exact pro-rata) |
| Revenue routing | `aimarket_hub/api.py` `/invoke` | Paid invoke → `accrue_revenue(product_id, price)` |
| Float / inspect | `POST /…/capital/ipo`, `GET /…/capital/listings[/{id}]` | Admin-gated float; open cap-table reads |
| Distribute / claim | `POST /…/capital/listings/{id}/distribute`, `GET /…/capital/holdings` | Pro-rata payout + holder positions |
| Pulse overlay | `acex/integrations/pricing.py` | `acex_listed`, `shares_outstanding`, `distributed_usd` per listing |

On-chain parity:
- Listing/CapShares: `acex/contracts/evm/{AgentListingRegistry,AgentShareToken}.sol`
  (apply → audit ≥ 70% → approve → mint to treasury → enable trading).
- Revenue settlement: `acex/contracts/evm/src/PulseDistributor.sol` (Merkle epoch claims,
  pull pattern). Bridge: `acex_ipo.build_onchain_claimset(listing_id, address_map)` →
  `postEpoch(root, total)` + holder `claim(index, account, amount, proof)`.
  micro-USD == USDC base units (6 dp), so amounts map 1:1.

Env (hub):

- `ACEX_AUTO_IPO=1` — auto-float on auto-listing
- `ACEX_REVENUE_SHARE_BPS` (default `5000` = 50% of each paid invoke to shareholders)
- `ACEX_DEFAULT_MAX_SUPPLY` (default `1_000_000` CapShares), `ACEX_MIN_AUDIT_SCORE_BPS` (default `7000`)
- `AIMARKET_ADMIN_TOKEN` — required for `/capital/ipo`, `/distribute`, and `/capital/audit/…/sync`

```bash
# Offline end-to-end: factory ship → auto-list → IPO → revenue → distribute → claim
python scripts/demo_agent_ipo.py
```

### Proof-of-Audit (factory → hub → ACEX)

Staked auditor economics mirror `AgentAuditPool`: a slice of each **paid** invoke funds auditor rewards; Pulse Terminal shows cover, aggregate score, and default risk per listing.

| Layer | Path | Role |
|-------|------|------|
| Hub ledger | `aimarket_hub/acex_audit.py` | Coverage + reward accrual (micro-USD, pro-rata by cover) |
| Revenue routing | `aimarket_hub/api.py` `/invoke` | After IPO accrue → `accrue_audit_rewards(product_id, price)` |
| Inspect / sync | `GET /…/capital/audit[/{id}]`, `POST /…/audit/{id}/sync` | Open reads; admin sync from chain |
| Claim | `POST /…/capital/audit/{id}/claim` | Auditor pulls pending rewards (off-chain ledger) |
| Pulse overlay | `acex/integrations/pricing.py` | `proof_of_audit` on each listing + snapshot totals |
| Pulse UI | `apps/pulse-terminal/` DetailRail + Audit column | Cover, score, default risk, auditors |

On-chain parity:

- EVM: `acex/contracts/evm/src/AgentAuditPool.sol` — full stake / cover / slash / compensation.
- Solana: `acex_capital` PoA instructions in `programs/acex-capital/src/lib.rs`.
- Hub bridge to EVM `fundAuditRewards`: planned worker when `ACEX_AUDIT_BRIDGE_MODE=onchain`.

Env (hub, in addition to IPO vars):

- `ACEX_AUDIT_FEE_BPS` (default `100` = 1% of gross invoke to auditors)
- `ACEX_AUDIT_DB_PATH`, `ACEX_AUDIT_BRIDGE_MODE` (`offchain` \| `onchain` \| `both`)
- `ACEX_AUDIT_POOL_ADDRESS` — optional EVM pool for indexer

Spec: [`acex/protocol/proof-of-audit.md`](https://github.com/alexar76/acex/blob/main/protocol/proof-of-audit.md)

```bash
cd aimarket-hub && pytest tests/test_acex_audit.py tests/test_acex_ipo_api.py -q
```

### UNI virtual economy (alien-monitor)

| Component | File | Notes |
|-----------|------|-------|
| Anvil + contracts | `alien-monitor/backend/universe.py` | Bootstrap USDT / Escrow / NFT |
| Hub liquidity | `universe_funding.py` | Hub float + external funding stream |
| Autonomous buyer | `universe_external_buyer.py` | v2 search → channel → invoke (channel id fix) |
| Live metrics | `chain_metrics.py` | Maps hub `price_usd` from `/stats/live` |

Verify after deploy:

```bash
./scripts/verify_uni_ecosystem.sh
```

See also `docs/uni-economy.md`, `docs/uni-troubleshooting.md`.

## Observability bridge

`GET /ai-market/v2/stats/live` returns invocation rows (`price_usd`) and summary including `open_channels` from the channel ledger. **alien-monitor** maps these into 3D activity pulses when `ALIEN_MODE=universe`.

## Next integrations (planned)

| Feature | Repos | Status |
|---------|-------|--------|
| Agent IPO auto-listing + revenue routing | aicom pipeline + hub + acex | **Shipped** |
| Proof-of-Audit hub ledger + Pulse UI + Solana mirror | hub + pulse-terminal + acex | **Shipped** |
| On-chain `PulseDistributor` (Merkle settlement) | acex contracts | **Shipped** (forge-verified in acex CI) |
| Signed receipt reputation score | hub + provenance + widget | Planned |
| `aimarket verify <url>` | aimarket-protocol test vectors | Planned |
| Hub WebSocket → alien-monitor | hub events stream | Planned |

## Professional checklist for releases

1. Hub unit tests: `cd aimarket-hub && pytest tests/test_sandbox.py tests/test_acex_ipo.py tests/test_acex_audit.py tests/test_acex_ipo_api.py tests/test_api.py -q`
2. Widget: hard-refresh storefront; confirm Try free decrements quota
3. Agent demo: `demo_agent_to_agent.py` exit 0
4. Agent IPO demo: `demo_agent_ipo.py` exit 0 (factory → hub → ACEX reconciles)
5. UNI: `verify_uni_ecosystem.sh` — `blockchain_ready`, bootstrap, buyer rounds, capital pricing/listings
6. Update this doc when adding a new cross-repo contract
