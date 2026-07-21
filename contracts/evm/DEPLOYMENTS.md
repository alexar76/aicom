# contracts/evm — Base mainnet (demo) deployments

Live + **source-verified on Basescan** (chainId 8453), owned by the demo wallet
`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`:

| Contract | Address |
|---|---|
| AIMarketEscrow | [`0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017`](https://basescan.org/address/0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017) |
| AIMarketCapabilityNFT | [`0xA9Af496fD4A1Dc594029Aa8Ea2dbd236Fd255033`](https://basescan.org/address/0xA9Af496fD4A1Dc594029Aa8Ea2dbd236Fd255033) |

`FakeUSDT` is **not** deployed in this demo — the escrow whitelists **real Base USDC**
`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` at deploy.

Full per-transaction breakdown (deploy, the escrow capability-channel test, agent↔agent
payment, recovery) + a mermaid contract map: [../../docs/onchain-journal.md](../../docs/onchain-journal.md).

## Networks & RPC
These contracts deploy to any EVM network via Foundry `--rpc-url` / `foundry.toml`
`[rpc_endpoints]`. The runtime services that read them live (monitor, hub, web payment) select
their network and fail over across RPC endpoints through the shared chain registry — default
**Base + these demo addresses**. See [../../docs/chain-networks.md](../../docs/chain-networks.md).
