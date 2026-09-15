# External smart-contract audit — finding disposition

Track third-party audit findings (OpenZeppelin, Trail of Bits, etc.) here.
Internal Slither runs: `scripts/run_contract_audit.sh` → `slither-summary-*.md`.

| ID | Source | Contract / scope | Severity | Finding | Status | Fix / waiver |
|----|--------|------------------|----------|---------|--------|--------------|
| EXT-001 | _pending_ | AIMarketEscrow.sol | — | _awaiting external audit_ | open | Pre-mainnet gate (KI-2) |

## Status values

- **open** — not started
- **fixed** — patched + test added
- **accepted** — documented risk waiver with expiry
- **false-positive** — tool/auditor error with evidence link

## Pre-mainnet checklist

- [ ] Slither `--fail-high` green on `contracts/evm/` and `acex/contracts/evm/`
- [ ] Forge tests green (`make test` in each tree)
- [ ] Multisig owner on escrow + NFT contracts — set `SAFE_ADDRESS` env var during `forge script Deploy.s.sol` + `DeployNFT.s.sol` (auto-initiates Ownable2Step transfer). Safe signers then call `acceptOwnership()` via `script/AcceptOwnership.s.sol` or Safe Transaction Builder. See `scripts/transfer_contract_ownership.sh` for full flow and verification.
- [ ] External audit PDF stored in this directory
- [ ] All EXT-* rows closed or accepted with signed waiver
