# Pulse Terminal

Real-time portfolio terminal for **ACEX** (Agent Capital Exchange).

## Data sources

| Feed | Endpoint |
|------|----------|
| Factory / Hub pricing | `GET /api/v2/capital/pricing` |
| Hub alias | `GET /ai-market/v2/capital/pricing` |
| EVM liquidity | Pulse AMM (`acex/contracts/evm/src/PulseAMM.sol`) |
| Solana liquidity | Jupiter (`acex/integrations/jupiter.py`) |
| Derivatives | CapSense Options (`acex/contracts/solana/programs/acex-capital`) |

## Query params

- `chain` — `any` \| `evm` \| `solana`
- `listing_id` — filter to one agent listing / product id
- `limit` — max listings (default 50)

## Example

```bash
curl -s "http://localhost:8000/api/v2/capital/pricing?chain=solana&limit=10" | jq .
```

## UI (planned)

Electron or web dashboard consuming the pricing API with WebSocket refresh (`pulse_terminal.refresh_ms` in the payload).
