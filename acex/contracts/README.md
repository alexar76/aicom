# ACEX contracts (EVM + Solana)

| Chain | Path | Deploy |
|-------|------|--------|
| **EVM** (Base, Ethereum) | [`evm/`](evm/) | [`evm/deploy.sh`](evm/deploy.sh) |
| **Solana** | [`solana/`](solana/) | [`solana/deploy.sh`](solana/deploy.sh) |

## EVM stack

- `AgentListingRegistry` — ALP  
- `AgentCollateralVault` — collateral  
- `AgentShareToken` / `AgentNoteToken` — CapShares & AgentNotes  
- `AgentLendingPool` — LiquidityMesh  
- `PulseAMM` — trading  

## Solana stack

- `acex_capital` — ALP + collateral vault (SPL USDC)

## Security

[../docs/security/audit-2026-05.md](../docs/security/audit-2026-05.md)
