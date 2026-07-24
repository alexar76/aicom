# Deploy the lottery with REAL ecosystem participants (server + real contracts)

How to run the Agent Lottery so its participants are the **actual ecosystem nodes**
(the 17 oracles + Hub + Mesh + Factory + ACEX) — not invented names — with each node's
on-chain wallet **deterministically bound to its node id**, on a real chain (Base).

## The model

- **Participants = real ecosystem nodes.** They're registered in the AI Service Mesh as
  verified agents (`scripts/register_ecosystem_agents.py`): real name, real public
  endpoint, real capabilities, and a node-bound EVM wallet.
- **Wallet ↔ node binding (reproducible):** the per-node private key is
  `privkey = keccak256("ailottery-uni-wallet|" + UNI_WALLET_SEED + "|" + mesh_agent_id)`
  and `wallet = address(privkey)` — same node → same wallet on every host/run, so an on-chain
  participant maps 1:1 to a real infrastructure node. Fund those wallets once (genesis) and
  they persist.
  > ⚠️ **`UNI_WALLET_SEED` MUST be a real secret in production.** The env var is
  > `UNI_WALLET_SEED` (not `WALLET_SEED`). If it is unset the relayer falls back to the
  > operator key — which in the shipped compose files is the **public Anvil dev key**, making
  > every node wallet **trivially sweepable by anyone**. With `AIFACTORY_PROD=1` the relayer
  > **fail-closes**: it refuses to start if auto-wallet is on and the seed is unset or a
  > well-known public/dev key. Always set `AIFACTORY_PROD=1` + a secret `UNI_WALLET_SEED` for
  > a real deployment.
- **The relayer seats the Mesh roster** (`MESH_URL`), pays the oracles, drives unbiasable
  draws (commit-reveal + VDF), and the Hub tithes routing fees back as machine-UBI.

## Prereqs
- `forge`/`cast` (Foundry), a funded deployer wallet, the Mesh + oracles running (or the
  live ones on the server), and the relayer.

## Steps (Base — testnet first, then mainnet)

1. **Deploy the lottery contract.**
   - Sepolia rehearsal: `./scripts/deploy_lottery_sepolia.sh broadcast`
   - Base mainnet: `OWNER=<your-wallet> ./scripts/deploy_lottery_base.sh broadcast`
   - Roles are set at deploy: admin/governance/treasury = OWNER, operator/oracle-signer =
     relayer key. Addresses are written to `lottery/docs/deployments-{sepolia,base}.md`.
   - The scripts default `OWNER` to the demonstration wallet
     `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a` (self-owned: deployer = owner = operator).
     The current live demonstration set is deployed and verified on Base — see the full
     contract list + every transaction in [docs/onchain-journal.md](onchain-journal.md)
     (live lottery `AIAgentLottery 0xbda3e32331822d525d5e7c7b51ed76132e84db61`).

2. **Register the real ecosystem nodes as participants** (against the server's real Mesh):
   ```
   MESH_URL=https://<mesh-host> MESH_ADMIN_TOKEN=<admin> UNI_WALLET_SEED=<secret> \
   python3 scripts/register_ecosystem_agents.py
   ```
   Verify: `GET {MESH_URL}/v1/agents?verified_only=true` → Platon, Chronos, …, Hub, ACEX.

3. **Genesis-fund the node wallets** (so participants can actually buy tickets):
   - Derive each node's wallet with the same `UNI_WALLET_SEED` (the script prints them), then
     run `scripts/bootstrap_economy.sh` to seed operator/sponsor/faucet; the relayer's
     faucet tops up each node wallet on its first round (`AGENT_FUND_WEI`). See
     [deploy-economy-bootstrap.md](deploy-economy-bootstrap.md).

4. **Run the relayer in LIVE mode** against the chain + real Mesh:
   ```
   LOTTERY_MODE=live AIFACTORY_PROD=1 RPC_URL=https://mainnet.base.org CHAIN_ID=8453 \
   LOTTERY_ADDRESS=<deployed> OPERATOR_KEY=<op> ORACLE_SIGNER_KEY=<op> TREASURY_KEY=<op> \
   FAUCET_KEY=<faucet> UNI_AUTO_WALLET=1 UNI_WALLET_SEED=<same SECRET seed> \
   MESH_URL=https://<mesh-host> MESH_ADMIN_TOKEN=<admin> \
   ORACLE_URL=https://oracles.modelmarket.dev MONITOR_URL=https://<monitor> \
   python -m ailottery_relayer
   ```
   (With `AIFACTORY_PROD=1` the relayer refuses to start if `UNI_AUTO_WALLET=1` and
   `UNI_WALLET_SEED` is unset or a public/dev key — your fail-closed protection against
   sweepable wallets.)
   The roster becomes the real nodes (`roster_source=mesh`); set `UNI_AUTO_WALLET=1` to make
   each node sign with its OWN derived wallet (self-custodial) instead of a relayer key.

5. **Verify**: `GET {relayer}/economy` → `roster_source: mesh` with real node names + their
   node-bound wallets; the monitor shows the live lottery node.

## Notes
- ACEX contracts are **not** part of this deploy (audit flagged AuditPool TWAP + PulseAMM
  HIGH). Lottery + escrow + NFT are the audited-safe set. The escrow's service-payment
  stablecoin is **real Base USDC** (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`); the old
  FakeUSDT test token has been de-whitelisted. See
  [onchain-journal.md](onchain-journal.md) for the real Base txs.
- For a server bring-up of the supporting stack (Hub + Mesh + oracles + monitor) in Docker,
  build the hub with the **monorepo root** as the build context (its Dockerfile COPYs
  `aimarket-hub/`, `acex/`, `plugins/`, `aimarket-protocol/`).
