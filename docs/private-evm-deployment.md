# Running on your own / private EVM chain

The AICOM economy does **not** require a public blockchain. You can run the entire
on-chain layer against **any EVM-compatible chain you control** — a private
Geth/Reth/Besu network, an Anvil/Hardhat devnet, or an L2/appchain you deploy on
your own infrastructure. **No code changes are needed**; everything is env-driven.

This is distinct from two other modes:

- **UNI (default, no chain at all):** the internal credits ledger. Crypto OFF, full
  value via UNI. See [uni-corporate-usecase.md](./uni-corporate-usecase.md).
- **Public Base mainnet (the demo):** real money. See [onchain-journal.md](./onchain-journal.md).

A **private EVM chain** sits between them: real on-chain settlement and contracts,
but on infrastructure you own, with a token you control — no public chain, no real
cryptocurrency.

---

## ⚠️ Crypto disclaimer (read before enabling)

> **Crypto / blockchain features are OFF by default and are an explicit opt-in.**
> Enabling them (`AIFACTORY_CRYPTO_ENABLED=1`) turns on wallets, on-chain
> settlement, payment channels, lottery, and ACEX on-chain trading.
>
> - **You operate the chain and own the compliance.** Running a token, processing
>   payments, custody of keys, KYC/AML, securities/lottery/gambling law, and tax
>   treatment are **your responsibility** as the operator, in your jurisdiction.
> - **A private chain is still "crypto" to the platform.** It uses the same master
>   switch. The only thing the default-OFF state guarantees is that *nothing*
>   touches any chain until you consciously enable it.
> - **Keys are secrets.** Wallet keys never belong in committed config. Use the
>   ARGUS keystore vault or your secret manager; the production startup guard
>   (`AIFACTORY_PROD=1`) refuses to start with placeholder/stub payment config.
> - **No warranty.** These contracts are a reference implementation. Audit them
>   before holding real value, public or private.
>
> If you want the platform's value **without any of the above**, do nothing — UNI
> mode (the default) already delivers it.

---

## 0. Master switch

```bash
# A private EVM chain is still "crypto" to the platform — turn the on-chain economy on.
export AIFACTORY_CRYPTO_ENABLED=1
# (The UNI internal ledger stays on by default; you can run a private chain AND UNI together.)
```

## 1. Define the network — ecosystem (Hub, web/backend, Alien Monitor)

Resolved by `aimarket-hub/aimarket_hub/chain_net.py`, the single source of truth for
RPC failover + address resolution.

```bash
export AIMARKET_CHAIN=opschain                 # arbitrary network id (lowercase)
export AIMARKET_CHAIN_ID=2024                   # your chain's numeric chainId
# RPCs, comma-separated, priority order (the pool fails over across them):
export AIMARKET_RPC_OPSCHAIN="https://rpc1.internal:8545,https://rpc2.internal:8545"
# Optional tuning:
export AIMARKET_RPC_TIMEOUT=6                    # per-call seconds
export AIMARKET_RPC_COOLDOWN=30                  # seconds before re-probing a dead RPC
```

The env-var suffix is the **uppercased** value of `AIMARKET_CHAIN` (here `OPSCHAIN`).

## 2. Contract addresses (after you deploy — see §7)

Format: `AIMARKET_ADDR_<NETWORK>_<ContractName>=0x...` (network = uppercased `AIMARKET_CHAIN`).

```bash
export AIMARKET_ADDR_OPSCHAIN_USDC=0x...                  # your stablecoin / FakeUSDT
export AIMARKET_ADDR_OPSCHAIN_AIMarketEscrow=0x...
export AIMARKET_ADDR_OPSCHAIN_AIAgentLottery=0x...
export AIMARKET_ADDR_OPSCHAIN_AIMarketCapabilityNFT=0x...
export AIMARKET_ADDR_OPSCHAIN_PulseAMM=0x...              # ACEX on-chain leg (optional)
export AIMARKET_ADDR_OPSCHAIN_AgentListingRegistry=0x...
export AIMARKET_ADDR_OPSCHAIN_AgentLendingPool=0x...
```

> The committed registry [`config/deployments/base-mainnet.json`](../config/deployments/base-mainnet.json)
> only auto-loads for `chain=base`. On any other network you provide the addresses
> via these env vars (or point `AIFACTORY_DEPLOYMENTS_DIR` at your own
> `<network>-mainnet.json` of the same shape).

## 3. Payment settlement wallet (web/backend)

Prefer the merged YAML (`config/fragments/80-crypto.yaml`), which wins over env:

```yaml
crypto:
  wallet_addresses:
    evm: "0x<your-settlement-wallet>"   # must NOT be 0x0 / a placeholder, or payments 503
```

or env fallback: `export AIMARKET_PAYMENT_RECIPIENT=0x<your-settlement-wallet>`.

## 4. NFT registry (writes in prod need an explicit operator RPC)

```bash
export AIMARKET_NFT_CHAIN=opschain
export AIMARKET_NFT_CONTRACT=0x...
export AIMARKET_NFT_OWNER_KEY=0x...                       # secret — secret manager, not committed
export AIMARKET_NFT_CHAIN_RPC="https://rpc1.internal:8545" # required when AIFACTORY_PROD=1
```

## 5. ARGUS agent (TypeScript — uses `uni` mode as the custom-EVM path)

ARGUS has two first-class modes: `live` (hard-bound to Base mainnet) and `uni` (a
generic, env-configured EVM chain). **For a private chain, use `uni` mode:**

```bash
export ARGUS_MODE=uni
export AIFACTORY_CRYPTO_ENABLED=1                # or ARGUS_CRYPTO_ENABLED=1 (back-compat)
export ARGUS_UNI_RPC="https://rpc1.internal:8545"
export ARGUS_UNI_CHAIN_ID=2024
export ARGUS_UNI_USDC=0x...
export ARGUS_UNI_ESCROW=0x...
export ARGUS_UNI_LOTTERY=0x...
export ARGUS_UNI_ACEX_AMM=0x...
export ARGUS_UNI_ACEX_REGISTRY=0x...
export ARGUS_UNI_LENDING_POOL=0x...
export ARGUS_UNI_CAPABILITY_NFT=0x...
# Wallet (only if the agent should spend on your chain) — use the vault:
#   argus keystore create     (then ARGUS_KEYSTORE_PASSPHRASE), or ARGUS_WALLET_KEY=0x...
```

> ARGUS `live` mode is wired to viem's `base` chain object; for a non-Base chain use
> `uni` mode as above. In `uni` mode ARGUS builds the chain and exposes `acex_status`
> and `lottery_status` even with public crypto off — trading/buying still requires a
> wallet and WARDEN approval.

## 6. Lottery relayer (Python)

```bash
export LOTTERY_MODE=live          # 'live' = a real chain (yours); 'uni' = local Anvil; 'demo' = mock
export RPC_URL="https://rpc1.internal:8545"
export CHAIN_ID=2024
export LOTTERY_ADDRESS=0x<deployed-lottery>      # or LOTTERY_ADDRESS_FILE=/path
# Distinct keys, all secret, never committed:
export OPERATOR_KEY=0x... ORACLE_SIGNER_KEY=0x... TREASURY_KEY=0x... SPONSOR_KEY=0x...
```

## 7. Deploy runbook (operator)

1. Stand up your EVM node; note the RPC URL + chainId.
2. Deploy the contracts with Foundry (`contracts/DEPLOY.md`): `AIMarketEscrow`,
   `AIMarketCapabilityNFT`, a stablecoin (`contracts/evm/src/FakeUSDT.sol` for a
   test token, or wire a real one), `lottery/contracts/AIAgentLottery.sol`, and
   (optional) the ACEX leg (`PulseAMM`, registry, lending/collateral pools).
3. Record each deployed address into the env vars from §2 / §5 / §6.
4. Set the settlement wallet (§3); confirm it is not a placeholder.
5. Fund the operator/relayer keys with native gas on your chain.
6. Start the stack with `AIFACTORY_CRYPTO_ENABLED=1` and your env loaded. Verify a
   test invoke settles and (if enabled) a lottery draw executes.

## Notes

- Reads use the failover RPC pool; production NFT/lottery **writes** require an
  explicit operator-chosen RPC (never a public preset).
- Testnet shortcut: `AIMARKET_TESTNET=1` switches the stack to Sepolia-family
  testnets if you'd rather not self-host.
- Cross-reference: [chain-networks.md](./chain-networks.md) (RPC failover + the env
  conventions) and [uni-corporate-usecase.md](./uni-corporate-usecase.md) (the
  no-chain default).
