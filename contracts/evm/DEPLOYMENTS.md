# contracts/evm — Base mainnet (demo) deployments

Live on Basescan (chainId 8453), owned by the demo wallet
`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`. **Redeployed 2026-07-26; escrow replaced by
AIMarketEscrowV2 on 2026-10-08** ([`ESCROW-V2.md`](ESCROW-V2.md); V1 `0x12Db8FAC…62CF2` superseded, held 0 USDC).

| Contract | Address |
|---|---|
| AIMarketEscrow | [`0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb`](https://basescan.org/address/0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb) |
| AIMarketCapabilityNFT | [`0x544dcdd8B01A7ee1444bf89A5381aA981735a281`](https://basescan.org/address/0x544dcdd8B01A7ee1444bf89A5381aA981735a281) |

`FakeUSDT` is **not** deployed in this demo — the escrow whitelists **real Base USDC**
`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` at deploy.

Canonical registry: [`../../config/deployments/base-mainnet.json`](../../config/deployments/base-mainnet.json).
Full per-transaction breakdown: [`../../docs/onchain-journal.md`](../../docs/onchain-journal.md) §2c / §3h.

## Networks & RPC
These contracts deploy to any EVM network via Foundry `--rpc-url` / `foundry.toml`
`[rpc_endpoints]`. The runtime services that read them live (monitor, hub, web payment) select
their network and fail over across RPC endpoints through the shared chain registry — default
**Base + these demo addresses**. See [../../docs/chain-networks.md](../../docs/chain-networks.md).
