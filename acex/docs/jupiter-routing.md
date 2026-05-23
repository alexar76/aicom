# Jupiter routing (Solana)

ACEX uses **Jupiter v6** for CapShare ↔ USDC swaps on Solana instead of an on-chain AMM (EVM uses `PulseAMM`).

## Client

Python helper: [`integrations/jupiter.py`](../integrations/jupiter.py)

```python
from acex.integrations.jupiter import fetch_jupiter_quote, build_swap_plan

quote = await fetch_jupiter_quote(
    input_mint=cap_share_mint,
    output_mint=usdc_mint,
    amount=1_000_000,  # base units
    slippage_bps=50,
)
plan = build_swap_plan(quote, user_public_key="...")
```

## Environment

| Variable | Default |
|----------|---------|
| `ACEX_JUPITER_QUOTE_URL` | `https://quote-api.jup.ag/v6/quote` |
| `ACEX_JUPITER_SWAP_URL` | `https://quote-api.jup.ag/v6/swap` |
| `ACEX_SOLANA_USDC_MINT` | mainnet USDC |

## Pulse Terminal flow

1. `GET /api/v2/capital/pricing?chain=solana` — index + share reference prices
2. Jupiter quote for execution size
3. Wallet signs swap tx from Jupiter `/swap` response

See [Pulse Terminal](../../apps/pulse-terminal/README.md).
