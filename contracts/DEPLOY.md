# Deploy Runbook — AIMarket Smart Contracts

Three contracts ship in this repo. Each is independent; deploy what you need.

| Contract | Path | Purpose | Required for |
|---|---|---|---|
| **AIMarketEscrow** | `evm/src/AIMarketEscrow.sol` | EVM payment channels (USDT/USDC) | Any chain in `payment_chains` |
| **AIMarketCapabilityNFT** | `evm/src/AIMarketCapabilityNFT.sol` | ERC-721 transferable entitlements | NFT plugin / `OnChainNFTRegistry` |
| **aimarket-escrow** | `solana/programs/aimarket-escrow/` | Solana payment channels (USDC) | Solana support |

---

## ⚠️ Breaking changes vs. earlier revisions of this repo

If you already deployed a previous version of `AIMarketEscrow.sol` or
`aimarket-escrow` (Solana), the current sources are **not** ABI-compatible.
Off-chain clients (SDK, signer, JSON-RPC tooling) need to be updated:

| Change | Old | New | Impact |
|---|---|---|---|
| `DEBIT_TYPEHASH` (EVM) | `…(bytes32 channelId,address token,uint256 amount,…)` | `…(bytes32 channelId,address hub,address token,uint256 amount,…)` | Depositor signatures now bound to a specific hub. Off-chain signers must include the hub address. |
| `computeDebitDigest(...)` (EVM) | 6 args | 7 args (added `address hub`) | Any client that prebuilds EIP-712 digests must add `hub`. |
| `settleChannel(channelId, hubRecipient)` (EVM) | 2 args | `settleChannel(channelId)` — 1 arg | The `hubRecipient` was misleading (ignored in practice). Funds go to `ch.hub`. |
| `expireChannel(...)` (EVM + Solana) | Returned full deposit to depositor | Pays `usedAmount` to hub, refunds remainder to depositor | A depositor can no longer dodge payment by waiting 24h. |
| Event `ChannelExpired(channelId,refundAmount)` | Single field | `ChannelExpiredAndSettled(channelId,usedAmount,refundAmount)` | Subgraph / log decoders must update event ABI. |
| Solana `debit_message` | No hub in payload | Includes `hub` pubkey | Off-chain Ed25519 signer must include hub. |
| Solana `AuthorizedHub` PDA | Keyed by admin pubkey (one global PDA) | Keyed by hub pubkey (one PDA per hub) | Re-run `authorize_hub` per hub after redeploy. |
| Solana CPI signer seeds | `[b"channel", channel_id, vault_bump]` (broken) | `[b"vault", channel_id, vault_bump]` | Prior deployments could never settle/refund/expire — confirm tx history is empty before reusing. |

If you have funds in an old deployment, drain them first (settle/refund),
re-deploy from current sources, and update the hub `.env` addresses.

---

## 0 · Pre-flight — do this once

```bash
# Foundry (EVM)
curl -L https://foundry.paradigm.xyz | bash
foundryup

# Solana CLI + Anchor (only if deploying Solana)
# release.solana.com is deprecated; use the Anza mirror.
sh -c "$(curl -sSfL https://release.anza.xyz/v1.18.26/install)"
cargo install --locked --tag v0.30.1 --git https://github.com/coral-xyz/anchor anchor-cli
```

**Hardware wallet STRONGLY recommended** (Ledger/Trezor) for mainnet deployer keys.
Plain `--private-key` exposes the key as an argv to `forge` / `cast` — visible in
`ps aux` on multi-user hosts for the duration of the command.

Both `deploy.sh` and `deploy-nft.sh` now support `--ledger` natively:
```bash
./deploy.sh base --ledger
./deploy.sh base --ledger --derivation "m/44'/60'/1'/0/0"
./deploy-nft.sh base --ledger
```

The script reads the deployer address from the Ledger, prints what it'll
broadcast, and pipes the deploy through `forge create` with `--ledger`.
No private-key argv anywhere on the host.

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

Watch especially for the regression tests:
- `test_debitChannel_revertsSignatureBoundToHub`
- `test_expireChannel_paysHubUsedAmountAfterDebit`
- `test_eip712_recomputesSeparatorOnFork`

If any test fails — STOP. Do not deploy.

CI runs `slither . --fail-high` after the JSON report — same gate locally:
```bash
pip install slither-analyzer==0.10.4
slither . --config-file slither.config.json --fail-high
```

---

## 2 · EVM Escrow — Deploy (testnet → mainnet)

The script reads the private key from console (hidden input) OR drives a
Ledger directly. Key never leaves device on `--ledger`.

### Base Sepolia (testnet — start here)
```bash
cd contracts/evm

# REQUIRED — no safe defaults anymore. A typo here is much better than
# silently shipping a "0x111…111 placeholder hub" or a mainnet-only USDC
# address on a testnet.
export INITIAL_HUBS=0xHUB1ADDRESS,0xHUB2ADDRESS                  # comma-separated
export INITIAL_TOKENS=0x036CbD53842c5426634e7929541eC2318f3dCF7e  # USDC Base Sepolia

# Ledger flow (recommended)
./deploy.sh base-sepolia --ledger
# OR private key paste
./deploy.sh base-sepolia
```

### Base mainnet
```bash
export INITIAL_HUBS=0xHUB1ADDRESS                                # one or more
export INITIAL_TOKENS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913  # USDC Base mainnet
export BASESCAN_API_KEY=<your_basescan_key>                       # for verification
./deploy.sh base --ledger
```

### Other chains
- `./deploy.sh ethereum [--ledger]` — set `RPC_ETHEREUM` + `ETHERSCAN_API_KEY`
- `./deploy.sh arbitrum [--ledger]` — set `RPC_ARBITRUM` + `ARBISCAN_API_KEY`

**Token addresses cheatsheet:**
| Chain | USDC | USDT |
|---|---|---|
| Base mainnet | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | not on Base |
| Base Sepolia | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` | n/a |
| Ethereum mainnet | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` | `0xdAC17F958D2ee523a2206206994597C13D831ec7` |
| Arbitrum One | `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` | `0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9` |

### After deploy

Copy the address from logs, add to hub `.env`:
```
AIMARKET_ESCROW_EVM_ADDRESS=0xDEPLOYED_ADDRESS
```

To authorize additional hubs later (Ledger-friendly form):
```bash
cast send $ESCROW_ADDR "setHubAuthorization(address,bool)" 0xNEW_HUB true \
  --ledger --mnemonic-derivation-path "m/44'/60'/0'/0/0" \
  --from 0xOWNER_ADDR --rpc-url https://mainnet.base.org
```

---

## 3 · EVM Capability NFT — Deploy (only if using NFT entitlements)

```bash
cd contracts/evm

export INITIAL_HUBS=0xHUB1,0xHUB2     # hubs authorized to call consumeCall
./deploy-nft.sh base-sepolia --ledger # testnet first
# Verify end-to-end (mint → transfer → consume) before mainnet
./deploy-nft.sh base --ledger         # mainnet
```

### After deploy

```
AIMARKET_NFT_CONTRACT=0xDEPLOYED_NFT_ADDRESS
AIMARKET_NFT_CHAIN_RPC=https://mainnet.base.org
AIMARKET_NFT_CHAIN=base
# Owner key path (encrypted at rest) — never commit the raw key.
AIMARKET_NFT_OWNER_KEY_FILE=/app/data/secrets/nft_owner_key
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

# Deploy (key piped via stdin, never interpolated into shell)
./deploy.sh devnet
# Paste keypair (JSON byte array OR base58 string) when prompted

# Real Program ID is now parsed from `solana program deploy` output —
# copy the printed `Program ID: <pubkey>` line to .env.
```

### After deploy

```
AIMARKET_ESCROW_SOLANA_PROGRAM_ID=<base58_program_id>   # from deploy.sh output
```

### Initialize program config (one-time, fixes admin)

```bash
# Use Anchor CLI or a small TS script:
anchor run init-config       # if you've added an Anchor task for it
# OR direct CPI from a TS script with the IDL.
```

This calls `initialize_config`, which fixes the admin pubkey. After this,
`authorize_hub(hub, true)` can only be called by that admin.

### Authorize hubs (one PDA per hub)

```bash
# Pseudocode — actual call goes through the Anchor IDL or a TS script:
#   program.methods.authorizeHub(hubPubkey, true).accounts({ ... }).rpc()
```

Each hub gets its own `AuthorizedHub` PDA at
`[b"authorized_hub", hub_pubkey]`. Deauthorize the same way with `false`.

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
cast call $ESCROW_ADDR "domainSeparator()(bytes32)" --rpc-url $RPC_URL

cast call $NFT_ADDR "owner()(address)" --rpc-url $RPC_URL
cast call $NFT_ADDR "authorizedHubs(address)(bool)" 0xHUB --rpc-url $RPC_URL

# Solana
solana program show <PROGRAM_ID> --url <RPC>
anchor idl fetch <PROGRAM_ID> --provider.cluster mainnet > deployed-idl.json
```

A correct EVM deploy should emit `HubAuthorized(<hub>, true)` and
`TokenWhitelisted(<token>, true)` events in the deploy tx.

---

## 6 · Hub `.env` template (after deploy)

```bash
# ── Payment channels (set after EVM Escrow deploy) ─────────────────
AIMARKET_ESCROW_EVM_ADDRESS=0x...
AIMARKET_ESCROW_SOLANA_PROGRAM_ID=...   # base58 from solana program deploy

# ── NFT entitlements (optional — only if NFT deployed) ─────────────
AIMARKET_NFT_CONTRACT=0x...
AIMARKET_NFT_CHAIN_RPC=https://mainnet.base.org
AIMARKET_NFT_CHAIN=base
AIMARKET_NFT_OWNER_KEY_FILE=/app/data/secrets/nft_owner_key

# ── Production switches (CRITICAL — flip for real $ payments) ──────
AIFACTORY_PROD=1                         # enables prod_startup_guard
AIFACTORY_PAYMENT_VERIFY_STUB=0          # real on-chain verification
AIFACTORY_PAYMENT_TESTNET=0              # real chain (not testnet fixtures)
AIMARKET_PAYMENT_RECIPIENT=0x...         # where settle payments land

# ── Auth tokens (REQUIRED — fail-closed without these) ─────────────
AIMARKET_ADMIN_TOKEN=<32-byte random hex>           # /federation/announce, /crawl
AIMARKET_PROVENANCE_API_TOKEN=<32-byte random hex>  # /attest endpoint

# ── ZK Backend ──────────────────────────────────────────────────────
AIMARKET_ZK_BACKEND=groth16              # real proofs; ZKProverSimulated is dev-only
AIMARKET_ZK_WASM=/app/contracts/zk/build/input_validity_js/input_validity.wasm
AIMARKET_ZK_ZKEY=/app/data/secrets/zk/input_validity_0001.zkey
AIMARKET_ZK_VKEY_JSON=/app/contracts/zk/verifier/verification_key.json
AIMARKET_ZK_NULLIFIER_DB=/app/data/zk_nullifiers.db   # SQLite WAL on shared volume

# DO NOT set in prod — fail-loud guard rejects this combination:
# AIMARKET_ZK_SIMULATED=1
```

Generate tokens:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

> ⚠️ Long-standing items that **cannot be closed by a code change** —
> ZK ceremony, external audit, uvicorn supervisor root cause — are
> tracked in [`docs/known-issues.md`](../docs/known-issues.md) (KI-1,
> KI-2, KI-3). Review them before flipping `AIFACTORY_PROD=1`.

## 7 · ZK trusted setup (operator-only — one-time per circuit version)

The Groth16 backend needs a circuit-specific proving key (`input_validity_0001.zkey`)
that is generated via a trusted-setup ceremony. A single-contributor zkey
is cryptographically weak — the contributor's `tau` (toxic waste) lets them
forge proofs forever. **For mainnet, run a multi-party ceremony.**

Minimum production setup:

1. **At least three unrelated contributors** (different orgs, different
   physical locations, different OS install media).
2. Each contributor runs the entropy step on an air-gapped or freshly-imaged
   machine, **destroys the machine afterward**, and publicly attests to
   destruction (signed tweet / commit / DNS TXT record).
3. The final zkey is verified by every contributor against the prior zkey.
4. `verification_key.json` and `Verifier.sol` (auto-generated from the final
   zkey) are committed to the repo.
5. The zkey (`build/input_validity_0001.zkey`) is **not** committed — it's
   distributed to the operator(s) via encrypted channels and stored under
   `data/secrets/zk/` (chmod 600).

Run:
```bash
cd contracts/zk
npm install                          # circomlib
./scripts/setup.sh                   # walks through contributions one-by-one
```

Set the resulting paths in the hub `.env` per Section 6. The first hub
process that reads `AIMARKET_ZK_BACKEND=groth16` will fail loud if any
artifact is missing.

The `contracts/zk/verifier/` directory ships empty in this repo by design —
`Verifier.sol` is auto-generated from your final zkey. It's not safe to
commit a Verifier.sol generated by someone else.

---

## 8 · Pre-mainnet checklist (you really should)

- [ ] `forge test` green, including the regression tests listed in Section 1.
- [ ] `forge test --gas-report` — gas within expected bounds
- [ ] `anchor test` green for Solana program
- [ ] `slither contracts/evm/ --fail-high` clean
- [ ] External audit completed (Trail of Bits / OpenZeppelin / Spearbit) — **strongly recommended before any real funds** (tracked as KI-2 in [`docs/known-issues.md`](../docs/known-issues.md))
- [ ] Deployer key on hardware wallet (Ledger/Trezor) — used via `--ledger`
- [ ] Contract owner transferred to multisig (Safe / Squads) **after** deploy
- [ ] Bug bounty live on Immunefi for ≥ 2 weeks on testnet before mainnet
- [ ] Hub running with `AIFACTORY_PROD=1` (triggers `prod_startup_guard` checks)
- [ ] All env-var auth tokens set (`AIMARKET_ADMIN_TOKEN`, `AIMARKET_PROVENANCE_API_TOKEN`)
- [ ] `AIMARKET_ZK_SIMULATED` is NOT set
- [ ] `AIMARKET_ZK_BACKEND=groth16` AND artifacts (wasm/zkey/vkey) present
- [ ] ZK trusted-setup ceremony has ≥ 3 unrelated contributors with public attestations (tracked as KI-1 in [`docs/known-issues.md`](../docs/known-issues.md))
- [ ] `AIMARKET_ZK_NULLIFIER_DB` is on a persistent volume (not a tmpfs)
- [ ] CORS origins explicitly listed (`AIMARKET_CORS_ORIGINS=https://app.yours.com`)
- [ ] Container running as UID 10001 (see `docker-compose.yml` — `data-init`
      sidecar fixes `./data` ownership automatically; verify with
      `docker compose exec app id`)
- [ ] DR runbook tested — you've actually restored from a backup
- [ ] Monitoring/alerts wired (Grafana, see `monitoring/`)
- [ ] Pre-deploy: confirm `INITIAL_HUBS` and `INITIAL_TOKENS` for the chain
      are correct (the deploy script aborts if either is unset, but the
      contents are not validated against the chain — set them yourself)
- [ ] On-call rotation defined; incident response runbook reviewed

---

## 9 · Rollback / kill-switch

EVM Escrow & NFT both have `Ownable` admin functions. Worst case:
```bash
# Deauthorize all hubs (pauses all debits / consumeCalls)
cast send $ESCROW_ADDR "setHubAuthorization(address,bool)" 0xHUB false \
  --ledger --mnemonic-derivation-path "m/44'/60'/0'/0/0" \
  --from 0xOWNER --rpc-url $RPC_URL

# Remove token from whitelist (pauses new channels for that token)
cast send $ESCROW_ADDR "setTokenWhitelist(address,bool)" 0xTOKEN false \
  --ledger --mnemonic-derivation-path "m/44'/60'/0'/0/0" \
  --from 0xOWNER --rpc-url $RPC_URL

# NFT — bulk emergency deauth + global pause
cast send $NFT_ADDR "setAuthorizedHubBulk(address[],bool)" "[0xHUB1,0xHUB2]" false \
  --ledger --from 0xOWNER --rpc-url $RPC_URL
cast send $NFT_ADDR "pause()" \
  --ledger --from 0xOWNER --rpc-url $RPC_URL
```

Open channels remain — users can still settle / expire / refund themselves.
There is **no rugpull function** — contract cannot move user funds without
their signed authorization.

For Solana: same shape via `authorize_hub(hub, false)` per-hub.

---

## 9b · Production ownership — multisig (required before mainnet)

`AIMarketEscrow` and `AIMarketCapabilityNFT` use **Ownable2Step** — the
deployer EOA should **not** remain the long-term owner on mainnet.

1. Deploy a [Gnosis Safe](https://safe.global/) (or equivalent multisig) on
   the target chain with ≥2-of-N operator keys.
2. Call `transferOwnership(safeAddress)` on each contract, then have the Safe
   execute `acceptOwnership()` (two-step prevents fat-finger bricking).
3. Route all admin calls (`setHubAuthorization`, `setTokenWhitelist`, NFT
   `authorizeHub`, pause/unpause) through the Safe — never from a hot EOA.

Track status: [`docs/audit-remediation.md`](../docs/audit-remediation.md).

---

## 10 · If something goes wrong

1. The deploy scripts no longer try to clean parent shell history (that was
   security theatre; subshell `history -c` doesn't reach the parent). If
   you pasted a key, rotate it and clear your own shell:
   `history -d <line>` or `shred -u ~/.bash_history`.
2. Forge dry-run before broadcast: drop `--broadcast` from the command and
   inspect the trace.
3. Check basescan/etherscan/solscan that the deployed code matches your
   build. If it doesn't — DO NOT use that deployment.
4. uvicorn backend in supervisor restart-loop: check
   `/app/data/logs/uvicorn-last-crash.log` inside the container for the
   tail of the crashed process. The supervisor caps restarts at
   `BACKEND_MAX_RESTARTS` (default 20) in `BACKEND_RESTART_WINDOW_SECS`
   (default 1800) — after that it exits 1 and lets your container manager
   apply its restart policy instead of busy-looping.

Questions: `security@aimarket.org` (or whatever address you've put in `SECURITY.md`).
