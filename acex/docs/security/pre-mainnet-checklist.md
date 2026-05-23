# ACEX — Pre-mainnet external audit checklist

**Gate:** No mainnet TVL above **$100k** until an external audit firm signs off.

## Scope for external auditors

| Component | Path |
|-----------|------|
| EVM contracts | `acex/contracts/evm/src/` |
| Solana program | `acex/contracts/solana/programs/acex-capital/` |
| Hub pricing oracle surface | `GET /api/v2/capital/pricing` |
| Jupiter integration | `acex/integrations/jupiter.py` |

## Deliverables required

1. Written report with severity-tagged findings
2. Re-test confirmation after fixes
3. Signed letter suitable for public disclosure
4. Review of CapSense payout math and vault authority seeds

## Internal pre-requisites (complete)

- [x] Internal audit [audit-2026-05.md](audit-2026-05.md)
- [x] Forge test suite green
- [x] Deploy scripts do not persist private keys
- [x] Pausable admin on EVM + Solana
- [x] Phase 2 CapSense + Jupiter routing documented

## External firm (TBD)

Engage before:

- Mainnet ALP listings with live collateral
- Pulse AMM pools with >$25k seed liquidity
- CapSense series with non-test premium vaults

## Contact

Security disclosures: follow repository `SECURITY.md` (if present) or factory admin security channel.
