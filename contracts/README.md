# AIMarket payment contracts

> **Ecosystem:** [AICOM overview & live demos](https://modeldev.modelmarket.dev)

Non-custodial **USDT/USDC payment channels** for the AIMarket federation — EVM and Solana.

| Contract | Path | Purpose |
|----------|------|---------|
| **AIMarketEscrow** | [`evm/src/AIMarketEscrow.sol`](evm/src/AIMarketEscrow.sol) | EVM payment channels |
| **AIMarketCapabilityNFT** | [`evm/src/AIMarketCapabilityNFT.sol`](evm/src/AIMarketCapabilityNFT.sol) | ERC-721 entitlements |
| **aimarket-escrow** | [`solana/programs/aimarket-escrow/`](solana/programs/aimarket-escrow/) | Solana payment channels |
| **ZK verifier** | [`zk/`](zk/) | Optional ZK settlement helpers |

**Deploy runbook:** [DEPLOY.md](DEPLOY.md)

**Usage examples:** [USAGE.md](USAGE.md) — open channel, EIP-712 debit, deploy, ZK PLONK.

**Security audits:** [audits/audit-response.md](audits/audit-response.md) — external audit recommended before mainnet; run [`../scripts/run_contract_audit.sh`](../scripts/run_contract_audit.sh) (Slither) locally.

**Recovery (operators):** [../docs/recovery-mechanisms.md](../docs/recovery-mechanisms.md)

**Status:** Pre-mainnet — see [docs/known-issues.md](../docs/known-issues.md) (KI-2…KI-5; KI-1 ZK resolved).
