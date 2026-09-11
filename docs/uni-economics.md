# UNI economics — spec alignment

## Fixed peg (not a tradable token)

| Rule | Spec | Implementation |
|------|------|----------------|
| Peg | **1 UNI = $0.01 USDT** (100 UNI per $1) | `core/uni/pricing.py`, `AIFACTORY_UNI_USD_CENTS_PER_UNI=1` |
| Type | Integer store credit | Balances rounded to whole UNI in `UniWalletService` |
| Top-up spread | **0%** recommended (psy-friendly) | `AIFACTORY_UNI_TOPUP_SPREAD_BPS=0` (default) |
| Invoke fee | **5%** to platform | `AIFACTORY_UNI_PLATFORM_FEE_BPS=500`, `charge()` / `spend_hold()` |
| Withdraw fee | **1%**, min **$20** | `AIFACTORY_UNI_WITHDRAW_FEE_BPS=100`, `AIFACTORY_UNI_MIN_WITHDRAW_UNI=2000` |

Legacy env `AIFACTORY_UNI_USDT_RATE=100` is equivalent to the fixed peg.

## Treasury invariant

```
totalUSDT_in_treasury ≥ Σ(user balance_uni + hold_uni) × $0.01
```

Background job: `core/uni/treasury.py` → `snapshot_treasury_audit()`  
Cron hook: `core/uni/jobs.py` → `run_treasury_audit_job()`  
Ops override: `AIFACTORY_UNI_TREASURY_USDT_OBSERVED=<usd>`

## Money flow

1. **Top-up** — on-chain USDT → `topup_from_chain()` → buyer wallet (spread optional).
2. **Channel open** — top-up + `hold()` (replaces prepaid channel balance).
3. **Invoke** — `spend_hold()` or `charge()`: buyer −gross, seller +net, platform +fee.
4. **Withdraw** — `withdraw_to_chain()` → `uni_withdrawals` queue (dispatcher stub in jobs).

Platform wallet: `owner_id=PLATFORM_FEES`, `owner_type=platform`.

## Schema

Tables in `data/store/uni_ledger.db` by default, or `data/store/commerce.db` when `AIFACTORY_UNI_USE_COMMERCE_DB=1`.

| Table | Status |
|-------|--------|
| `uni_wallets` | ✅ (+ `owner_type`, `status` via migration) |
| `uni_ledger` | ✅ append-only triggers (SQLite) |
| `uni_receipts` | ✅ (+ buyer/seller/fee columns, tx replay index) |
| `uni_holds` | ✅ (`channel_id` = legacy channel) |
| `uni_withdrawals` | ✅ |
| `uni_treasury_audit` | ✅ |

## API (`/api/uni/*`)

| Endpoint | Status |
|----------|--------|
| `GET /wallet` | ✅ |
| `GET /receipts` | ✅ |
| `POST /topup/intent` | ✅ |
| `POST /topup/confirm` | ✅ |
| `POST /withdraw` | ✅ (queued; on-chain dispatcher TBD) |
| `GET /treasury/audit` | ✅ |
| `POST /grant` | ✅ (monitor) |

## Adapters

| Path | Behavior |
|------|----------|
| `channels.open` | UNI top-up + hold when enabled |
| `invoke` | `charge()` with 5% platform fee |
| `payment.confirm` | UNI top-up shadow credit |
| Old orders | Unchanged (`uni_receipt_id` optional future column) |

## Gaps / roadmap

- On-chain treasury balance indexer (auto `usdt_observed`)
- `uni_withdraw_dispatcher` production hot-wallet transfers
- KYC monthly caps ($1k top-up / $500 withdraw without KYC)
- Federation batch settle between hubs
- Commerce `orders.uni_receipt_id` column (optional link)

## Configuration (Admin + env)

| Setting | Default | Where |
|---------|---------|--------|
| UNI enabled | on | `AIFACTORY_UNI_ENABLED=1` |
| Peg | 100 UNI / $1 | `AIFACTORY_UNI_USD_CENTS_PER_UNI=1` |
| Top-up spread | 0% | `AIFACTORY_UNI_TOPUP_SPREAD_BPS=0` |
| Invoke fee | 5% | `AIFACTORY_UNI_PLATFORM_FEE_BPS=500` |
| Withdraw fee | 1%, min $20 | `AIFACTORY_UNI_WITHDRAW_FEE_BPS`, `AIFACTORY_UNI_MIN_WITHDRAW_UNI` |
| AI Market demo pay | off | `AIFACTORY_AI_MARKET_DEMO_PAYMENT=0` |

In-app docs (EN / RU / ES): **Documentation → UNI credit bus**.

## Prod env (defaults — no need to set unless overriding)

```bash
AIFACTORY_UNI_ENABLED=1
AIFACTORY_AI_MARKET_DEMO_PAYMENT=0          # already default
# Per-product LLM cap: Admin Settings → quality.max_pipeline_cost_usd (0 = off)
# AIFACTORY_MAX_PIPELINE_COST_USD=25      # optional Docker override
# AIFACTORY_MIGRATE_AUTO_ROLLBACK=0       # off unless 1
```

Explicit overrides only when you want non-default economics:

```bash
AIFACTORY_UNI_TOPUP_SPREAD_BPS=0
AIFACTORY_UNI_PLATFORM_FEE_BPS=500
AIFACTORY_UNI_MIN_WITHDRAW_UNI=2000
```
