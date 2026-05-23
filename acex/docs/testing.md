# Testing

## EVM (Foundry)

```bash
cd contracts/evm
forge install foundry-rs/forge-std OpenZeppelin/openzeppelin-contracts --no-git
forge test -vv
```

**Coverage:** ALP listing, audit/reject/pause, CapShares lock, AgentNotes redeem, LiquidityMesh borrow/repay, Pulse AMM swaps.

## Python (monorepo root)

```bash
pytest tests/test_acex_docs.py tests/test_desktop_sku_manifest.py tests/test_killer_features_docs.py tests/test_ai_market_protocol_v2.py -q
```

## Solana

```bash
cd contracts/solana
anchor build
# anchor test when local validator available
```
