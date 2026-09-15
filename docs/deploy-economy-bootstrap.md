# Deploying the AI-agent economy — genesis token distribution

How to bring the lottery/agent economy up on a real EVM chain (Base Sepolia → Base
mainnet) with a small budget, and the **initial token distribution** that makes it run.

> **Two parallel ecosystems, one codebase.** UNI runs on local Anvil (play-money); LIVE
> runs on Base with the same relayer/contracts — only `RPC_URL` / `CHAIN_ID` /
> `LOTTERY_ADDRESS` and the funding source differ. Internally they're indistinguishable.

## Why a genesis distribution is needed

On Anvil/UNI every account is pre-funded (`anvil --balance 1000`), so agents can buy
tickets out of the box. On a **real chain the deployer holds all the funds** — an agent
with a zero balance literally cannot buy a ticket or a service. So a one-time **genesis
distribution** seeds the operational keys + a faucet; the relayer then auto-seeds each
agent wallet, and from there the economy is **circular**.

```
deployer ($20) ──seed──▶ operator (round gas) + sponsor/Hub (tithe) + faucet
       faucet ──relayer auto-seed──▶ each agent wallet
       agents ──tickets / service fees──▶ lottery + providers
      lottery ──prizes──▶ winners
          Hub ──routing fee──▶ tithe (20%) ──▶ lottery ──machine-UBI──▶ agents
```

An agent refills three ways: (1) the genesis seed, (2) winnings / service revenue,
(3) the machine-UBI tithe. After genesis it's a closed loop — value circulates, it
doesn't burn (only gas leaks, and Base gas is sub-cent).

## Budget split (~$20 / testnet)

| Bucket | ~Share | Purpose |
|---|---|---|
| Gas reserve (deploys) | ~$3 | deploy ~4 contracts (Base deploys are sub-cent–cents) |
| Operator key | ~$2 | `openRound`/`closeEntries`/`fulfillDraw`/`withdraw` gas |
| Sponsor / Hub | ~$3 | the Hub needs a balance to push its tithe to the lottery |
| Faucet → agents | ~$8 | each agent gets a crumb of ETH to start buying |
| First-round `fund()` | ~$4 | optional seed of the opening prize pool |

## Steps

1. **Generate a burner** (deploy wallet, key kept outside the repo):
   `cast wallet new --json > ~/.aicom-sepolia-burner.json`
2. **Fund it** from a Base-Sepolia faucet (Coinbase CDP / Alchemy / QuickNode). Testnet
   is free; for mainnet send the real ~$20.
3. **Deploy contracts**: [`scripts/deploy_lottery_sepolia.sh`](../scripts/deploy_lottery_sepolia.sh)
   (Base Sepolia) — native-ETH tickets, fast rounds, instant admin handover. It writes
   the addresses to `lottery/docs/deployments-sepolia.md`.
4. **Genesis distribution**: [`scripts/bootstrap_economy.sh`](../scripts/bootstrap_economy.sh)
   — seeds operator / sponsor / faucet from the deployer.
5. **Run the relayer in LIVE mode** pointed at the chain:
   ```
   LOTTERY_MODE=live RPC_URL=https://sepolia.base.org CHAIN_ID=84532 \
   LOTTERY_ADDRESS=<deployed> OPERATOR_KEY=.. ORACLE_SIGNER_KEY=.. TREASURY_KEY=.. \
   FAUCET_KEY=<faucet> MESH_URL=<mesh> MONITOR_URL=<monitor>
   ```
   The relayer drives rounds, the faucet auto-seeds agents (`AGENT_FUND_WEI`), real Mesh
   agents are seated when `MESH_URL` is set.
6. **(Optional) Transfer ownership** to your wallet — the contract uses OZ
   `AccessControlDefaultAdminRules` (2-step): `beginDefaultAdminTransfer(you)` →
   `acceptDefaultAdminTransfer()` (set `ADMIN_TRANSFER_DELAY=0` for an instant demo handover).

## Mainnet (Base) — same, with real funds
Identical flow with `RPC_URL=https://mainnet.base.org CHAIN_ID=8453` and the real ~$20
burner. Audit posture: deploy only the audited-safe set (lottery + escrow + NFT +
FakeUSDT); **do not** deploy ACEX with value (audit flagged AuditPool TWAP + PulseAMM).
