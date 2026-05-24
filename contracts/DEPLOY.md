# Deploy Runbook — AIMarket Smart Contracts

Three contracts ship in this repo. Each is independent; deploy what you need.

| Contract | Path | Purpose | Required for |
|---|---|---|---|
| **AIMarketEscrow** | `evm/AIMarketEscrow.sol` | EVM payment channels (USDT/USDC) | Any chain in `payment_chains` |
| **AIMarketCapabilityNFT** | `evm/AIMarketCapabilityNFT.sol` | ERC-721 transferable entitlements | NFT plugin / `OnChainNFTRegistry` |
| **aimarket-escrow** | `solana/programs/aimarket-escrow/` | Solana payment channels (USDC) | Solana support |

---

## 0 · Pre-flight — do this once

```bash
# Foundry (EVM)
curl -L https://foundry.paradigm.xyz | bash
foundryup

# Solana CLI + Anchor (only if deploying Solana)
sh -c "$(curl -sSfL https://release.solana.com/v1.18.26/install)"
cargo install --locked --tag v0.30.1 --git https://github.com/coral-xyz/anchor anchor-cli
```

**Hardware wallet STRONGLY recommended** (Ledger/Trezor) for mainnet deployer keys.
Plain `--private-key` exposes the key as an argv to `forge` / `cast` — visible in
`ps aux` on multi-user hosts for the duration of the command.

For Foundry on Ledger:
```bash
forge script script/Deploy.s.sol \
    --rpc-url base-mainnet --broadcast \
    --ledger --mnemonic-derivation-path "m/44'/60'/0'/0/0" \
    --sender 0xYourLedgerAddress
```

Same for `cast send` / `cast wallet address`. The `deploy.sh` / `deploy-nft.sh`
scripts use `--private-key` for convenience — for production deploys, run the
underlying `forge script` directly with `--ledger`.

---

## 1 · EVM — Test locally first

```bash
cd contracts/evm
forge install OpenZeppelin/openzeppelin-contracts@v5.0.2 --no-commit
forge install foundry-rs/forge-std@v1.9.4 --no-commit
forge build                       # must succeed with 0 errors
forge test -vvv                   # all green
forge test --gas-report           # sanity-check gas
```

If `forge test` fails — STOP. Do not deploy.

---

## 2 · EVM Escrow — Deploy (testnet → mainnet)

The bundled `deploy.sh` reads the private key from console (hidden input),
deploys via Foundry script, then wipes the key from env and shell history.

### Base Sepolia (testnet — start here)
```bash
cd contracts/evm

# (optional) override defaults
export INITIAL_HUBS=0xHUB1ADDRESS,0xHUB2ADDRESS        # default: deployer
export INITIAL_TOKENS=0x036CbD53842c5426634e7929541eC2318f3dCF7e  # USDC Base Sepolia

./deploy.sh base-sepolia
# Paste private key when prompted (input hidden)
# Confirm with y
```

### Base mainnet
```bash
export INITIAL_TOKENS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913  # USDC Base mainnet
export BASESCAN_API_KEY=<your_basescan_key>                       # for verification
./deploy.sh base
```

### Other chains
- `./deploy.sh ethereum` — set `RPC_ETHEREUM` + `ETHERSCAN_API_KEY`
- `./deploy.sh arbitrum` — set `RPC_ARBITRUM` + `ARBISCAN_API_KEY`

**Token addresses cheatsheet:**
| Chain | USDC | USDT |
|---|---|---|
| Base mainnet | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | not on Base |
| Ethereum mainnet | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` | `0xdAC17F958D2ee523a2206206994597C13D831ec7` |
| Arbitrum One | `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` | `0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9` |

### After deploy

Copy the address from logs, add to hub `.env`:
```
AIMARKET_ESCROW_EVM_ADDRESS=0xDEPLOYED_ADDRESS
```

If you didn't pass `INITIAL_HUBS` and need to authorize more later:
```bash
cast send $ESCROW_ADDR "setHubAuthorization(address,bool)" 0xNEW_HUB true \
  --rpc-url https://mainnet.base.org --private-key 0xOWNER_KEY
```

---

## 3 · EVM Capability NFT — Deploy (only if using NFT entitlements)

```bash
cd contracts/evm

export INITIAL_HUBS=0xHUB1,0xHUB2     # hubs authorized to call consumeCall
./deploy-nft.sh base-sepolia          # testnet first
# verify it works end-to-end (mint → transfer → consume)
./deploy-nft.sh base                  # mainnet
```

### After deploy

```
AIMARKET_NFT_CONTRACT=0xDEPLOYED_NFT_ADDRESS
AIMARKET_NFT_CHAIN_RPC=https://mainnet.base.org
AIMARKET_NFT_CHAIN=base
AIMARKET_NFT_OWNER_KEY=0xOWNER_KEY     # for mint — KEEP IN SECRETS, not in .env on disk
```

The Python `make_nft_registry()` factory picks up these env vars and uses
`OnChainNFTRegistry`. Without them it falls back to `InMemoryNFTRegistry`
(development only, loses state on restart, logs a loud warning).

---

## 4 · Solana — Test + deploy

```bash
cd contracts/solana

# Build & test on local validator
anchor build
anchor test                            # spins up local validator

# Devnet — get free SOL
solana config set --url https://api.devnet.solana.com
solana airdrop 2

# Deploy
./deploy.sh devnet
# Paste keypair (JSON byte array) when prompted

# Program ID is printed — copy it to .env
```

### After deploy

```
AIMARKET_ESCROW_SOLANA_PROGRAM_ID=<base58_program_id>
```

### Initialize program config (one-time, fixes admin)

```bash
# Use anchor CLI or a small TS script — example:
anchor run init-config       # if you've added an Anchor task for it
# OR direct call:
solana program show <PROGRAM_ID>
```

This calls `initialize_config` which fixes the admin pubkey. After this,
`authorize_hub` can only be called by that admin.

### Mainnet

```bash
solana config set --url https://api.mainnet-beta.solana.com
solana balance                  # need real SOL for rent + tx
./deploy.sh mainnet
```

---

## 5 · Post-deploy verification

```bash
# EVM
cast call $ESCROW_ADDR "owner()(address)" --rpc-url $RPC_URL
cast call $ESCROW_ADDR "authorizedHubs(address)(bool)" 0xHUB --rpc-url $RPC_URL
cast call $ESCROW_ADDR "whitelistedTokens(address)(bool)" 0xTOKEN --rpc-url $RPC_URL

cast call $NFT_ADDR "owner()(address)" --rpc-url $RPC_URL
cast call $NFT_ADDR "authorizedHubs(address)(bool)" 0xHUB --rpc-url $RPC_URL

# Solana
solana program show <PROGRAM_ID> --url <RPC>
anchor idl fetch <PROGRAM_ID> --provider.cluster mainnet > deployed-idl.json
```

---

## 6 · Hub `.env` template (after deploy)

```bash
# ── Payment channels (set after EVM Escrow deploy) ─────────────────
AIMARKET_ESCROW_EVM_ADDRESS=0x...
AIMARKET_ESCROW_SOLANA_PROGRAM_ID=...   # if Solana deployed

# ── NFT entitlements (optional — only if NFT deployed) ─────────────
AIMARKET_NFT_CONTRACT=0x...
AIMARKET_NFT_CHAIN_RPC=https://mainnet.base.org
AIMARKET_NFT_CHAIN=base
AIMARKET_NFT_OWNER_KEY=0x...            # keep in docker secrets, not in .env file

# ── Production switches (CRITICAL — flip these for real $ payments) ─
AIFACTORY_PROD=1                         # enables prod_startup_guard
AIFACTORY_PAYMENT_VERIFY_STUB=0          # real on-chain verification
AIFACTORY_PAYMENT_TESTNET=0              # real chain (not testnet fixtures)
AIMARKET_PAYMENT_RECIPIENT=0x...         # where settle payments land

# ── Auth tokens (REQUIRED — fail-closed without these) ─────────────
AIMARKET_ADMIN_TOKEN=<32-byte random hex>           # /federation/announce, /crawl
AIMARKET_PROVENANCE_API_TOKEN=<32-byte random hex>  # /attest endpoint

# ── ZK simulation (DO NOT set in prod — fail-loud guard) ───────────
# AIMARKET_ZK_SIMULATED=1                # ONLY for dev/test
```

Generate tokens:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 7 · Pre-mainnet checklist (you really should)

- [ ] `forge test` green, including `AIMarketEscrowTest` and `AIMarketCapabilityNFTTest`
- [ ] `forge test --gas-report` — gas within expected bounds
- [ ] `anchor test` green for Solana program
- [ ] `slither contracts/evm/` clean (or all findings triaged)
- [ ] External audit completed (Trail of Bits / OpenZeppelin / Spearbit) — **strongly recommended before any real funds**
- [ ] Deployer key generated on air-gapped machine or hardware wallet
- [ ] Contract owner transferred to multisig (Safe / Squads) after deploy
- [ ] Bug bounty live on Immunefi for ≥ 2 weeks on testnet before mainnet
- [ ] Hub running with `AIFACTORY_PROD=1` (triggers `prod_startup_guard` checks)
- [ ] All env-var auth tokens set (`AIMARKET_ADMIN_TOKEN`, `AIMARKET_PROVENANCE_API_TOKEN`)
- [ ] `AIMARKET_ZK_SIMULATED` is NOT set
- [ ] CORS origins explicitly listed (`AIMARKET_CORS_ORIGINS=https://app.yours.com`)
- [ ] DR runbook tested — you've actually restored from a backup
- [ ] Monitoring/alerts wired (Grafana, see `monitoring/`)
- [ ] On-call rotation defined; incident response runbook reviewed

---

## 8 · Rollback / kill-switch

EVM Escrow & NFT both have `Ownable` admin functions. Worst case:
```bash
# Deauthorize all hubs (pauses all debits / consumeCalls)
cast send $ESCROW_ADDR "setHubAuthorization(address,bool)" 0xHUB false \
  --private-key $OWNER_KEY --rpc-url $RPC_URL

# Remove token from whitelist (pauses new channels for that token)
cast send $ESCROW_ADDR "setTokenWhitelist(address,bool)" 0xTOKEN false \
  --private-key $OWNER_KEY --rpc-url $RPC_URL
```

Open channels remain — users can still settle / expire / refund themselves.
There is **no rugpull function** — contract cannot move user funds without
their signed authorization.

For Solana: same shape via `authorize_hub(false)`.

---

## 9 · If something goes wrong

1. `deploy.sh` clears the private key from env automatically on success and
   on failure. If your shell crashed mid-deploy, run `history -c && history -w`
   manually and rotate the key just in case.
2. Forge dry-run before broadcast: drop `--broadcast` from the command and
   inspect the trace.
3. Check basescan/etherscan/solscan for the actual deployed code matches.
   If it doesn't — DO NOT use that deployment.

Questions: `security@aimarket.org` (or whatever address you've put in `SECURITY.md`).
