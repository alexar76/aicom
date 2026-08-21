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

> **What "unbiasable" does and does not mean.** The winner is a pure function of
> `(roundId, blockhash(seedBlock), platonRandom)`, all three fixed before anyone can act on
> them, so the outcome does not depend on when the settlement lands. `fulfillDraw` is therefore
> **permissionless** — a valid `ORACLE_SIGNER` beacon is the only key it needs, so any
> participant can settle a round the operator is stalling, and it is deliberately *not*
> Pausable-gated. `reseed` is a rescue, not a re-roll: it is refused while the pinned blockhash
> is still readable, demands a never-before-used randomness commitment, waits out
> `RESEED_COOLDOWN` (1 h), emits `RoundReseeded`, and is capped at `MAX_RESEEDS` (2).
>
> The lever the operator **does** keep, and which cannot be closed on-chain: it alone produces
> the beacon, so it can compute the outcome privately, never publish, and let the round die into
> a refund. That costs it a full seed window, refunds every player and earns it nothing — but it
> means the last word on "does this round happen at all" belongs to whoever holds the oracle
> relay. Backstops: `cancelStalledRound` is permissionless after `STALL_CANCEL_DELAY` (7 days)
> and refunds tickets *and* sponsor funding, and `cancelRound` refuses a Drawing round whose
> pinned blockhash is already readable, so an admin cannot nullify a settleable outcome.
>
> `minDrawDelay` is bounded by `maxDrawDelay()`, derived from the declared `secondsPerBlock`
> (governance-settable) rather than a fixed wall-clock literal — on Base's 2 s blocks that is
> **260 s**, not the hour an earlier build allowed. The deploy scripts use 30 s.
>
> ⚠️ **`setSecondsPerBlock` DECLARES a block time; it cannot measure one, and nothing
> on-chain can catch a false declaration.** Declaring `60` on Base's 2 s chain inflates
> `maxDrawDelay()` to 7 800 s, so `DEFAULT_ADMIN` may then set a `minDrawDelay` of an hour
> — and the contract accepts it. The seed still only survives ~520 s, so *every* round
> would expire its seed before the draw is even valid, burn its two rescues an hour apart,
> and end cancelled and refunded. Nothing reverts at configuration time. Set
> `secondsPerBlock` to the chain's **actual** block time (2 on Base, 12 on Ethereum L1),
> keep `MIN_DRAW_DELAY` a small fraction of `260 × secondsPerBlock`, and when a chain
> changes its block time lower `minDrawDelay` **first** (`setSecondsPerBlock` refuses any
> value that leaves the current delay unsatisfiable). The relayer samples the chain's real
> block time and re-runs `maxDrawDelay()`'s own arithmetic (`260 × measured ÷ 2`) against
> it before opening a round, refusing — with both numbers in the log line — rather than
> selling tickets into a round the seed cannot outlive; on a chain it cannot sample it
> falls back to the declaration, which the contract already checks.
>
> A round whose draw the relayer has to abandon (dead VDF oracle, unrescuable seed) is
> **not** left locked: it is queued and retried at the top of every cycle, cancelled with
> `cancelRound` as soon as the contract stops treating it as settleable, and with the
> permissionless `cancelStalledRound` once `STALL_CANCEL_DELAY` is up. Either way agents
> and sponsors get their funds back through `refund` without an outsider having to notice.
>
> A prize left unclaimed for `UNCLAIMED_PRIZE_TTL` (180 days) is no longer stranded:
> anyone may call `forfeitUnclaimedPrize`, moving it into `unclaimedPool`. No role can
> withdraw that pool — its only exit is becoming a later round's prize, untaxed and capped
> at that round's own income.

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
     (live lottery `AIAgentLottery 0x701A7bd8487cd4d2EcE0E252Dbc0E67dF70a9554`).

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

## Migrating a live deployment — redeploy, never upgrade

The Base-mainnet instances listed in [onchain-journal.md](onchain-journal.md) predate
the fairness rework and **cannot take it in place**:

- **AIAgentLottery** gained storage slots (`secondsPerBlock`, `unclaimedPool`, and the
  `reseedCount` / `settledAt` / `prizeRolledIn` / `commitmentUsed` mappings). It is not
  proxied, and even behind a proxy the layout change rules out an upgrade. Wind the old
  instance down (settle or cancel + `refund` in-flight rounds, winners `claimPrize`,
  `withdrawOpex` / `withdrawOperatorFee` to zero), deploy fresh, re-grant roles, then
  re-point `config/sponsor.yaml` and `LOTTERY_ADDRESS`. There is no state migration and
  none is needed — prizes are pull-payment and history stays on the old address.
- **AIMarketEscrow** changed `ChannelSettled` from 4 to 5 parameters (`recipient` split
  into `usedRecipient` + `refundRecipient`, because one field credited the hub's revenue
  to the depositor). That changes topic0, so every indexer bound to the old signature
  silently indexes **zero** settlements. Redeploy the escrow and re-index; the subgraph
  manifest, schema and mappings are updated in `contracts/evm/subgraph/`.
- **Do not point a new relayer build at the old lottery.** Its rescue path calls
  `reseed(uint256,bytes32)`, a different selector from the deployed
  `reseed(uint256)` — the call would revert.

Deploying the escrow itself now fails closed on token decimals: `INITIAL_TOKENS` is
required (no default), and the constructor **reverts** (`UnsupportedTokenDecimals`) for
any token that does not answer `decimals()` with exactly `6`. The deposit range
(`MIN_DEPOSIT` $1, `MAX_DEPOSIT` $10 000) is hard-coded in 6-decimal units, so an
18-decimal token would silently stop bounding anything. Use the chain's real USDC/USDT
address — on Base mainnet `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` — and expect the
deploy script to abort rather than whitelist something it cannot prove compatible.

## Notes
- ACEX contracts are **not** part of this deploy (audit flagged AuditPool TWAP + PulseAMM
  HIGH). Lottery + escrow + NFT are the audited-safe set. The escrow's service-payment
  stablecoin is **real Base USDC** (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`); the old
  FakeUSDT test token has been de-whitelisted. See
  [onchain-journal.md](onchain-journal.md) for the real Base txs.
- For a server bring-up of the supporting stack (Hub + Mesh + oracles + monitor) in Docker,
  build the hub with the **monorepo root** as the build context (its Dockerfile COPYs
  `aimarket-hub/`, `acex/`, `plugins/`, `aimarket-protocol/`).
