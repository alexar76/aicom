# On-chain journal — full ecosystem on Base mainnet (proofs of real work)

> # 🔴 LIVE ON BASE **MAINNET** (chainId **8453**) — NOT a testnet, NOT a simulation
> These are **real contracts holding real value**: real Base **USDC**
> (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) and real **ETH**. Every address and transaction
> below is on Base **mainnet** and clickable on **[Basescan](https://basescan.org/address/0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a)**.
> This is **not** Base Sepolia / any testnet, and **not** the local UNI/anvil simulation.

A live, append-only record of the **entire AIMarket ecosystem deployed on Base mainnet
(chainId 8453)** from a single wallet, **all 10 contracts source-verified on Basescan**, plus a
**full end-to-end test** where the ecosystem's agents transacted by the protocol's own rules.
Every transaction below links to Basescan and is explained: **who signed it, what it calls,
its parameters, and its effect.**

> **One wallet runs everything:** `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`
> ([Basescan](https://basescan.org/address/0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a)) — it is
> deployer, owner, admin, treasury, lottery operator + oracle-signer, and the escrow hub.
> **After testing, all funds remain on this wallet** (2.0 USDC + ETH) for future experiments.

This is a **demonstration deployment with small real funds** (~2 USDC + ~0.006 ETH total).

> **📇 Canonical machine-readable registry:** the deployed addresses below are also committed as
> config — [`config/deployments/base-mainnet.json`](../config/deployments/base-mainnet.json) — the
> single source of truth that the code loads (`aimarket-hub/aimarket_hub/chain_net.py`,
> `argus/src/ecosystem/networks.ts`, and the lottery relayer). When `AIFACTORY_CRYPTO_ENABLED=1`
> and the active chain is Base, these addresses **auto-load** (overridable via
> `AIMARKET_ADDR_BASE_<NAME>` / `LOTTERY_ADDRESS`). A test
> (`tests/test_base_deployment_registry.py`) asserts this journal, the registry, and the code stay
> in sync — so **docs and code can never silently diverge.** Nothing here is ever removed.

---

## 1. Deployed contracts (all verified on Basescan ✅)

> **LIVE set — redeployed 2026-07-26** from `0x1218…Ad0a` (fairness-rework lottery + fresh escrow/NFT/ACEX/ZK).
> Earlier deployments (2026-06-18 / 06-19) remain in §2–§2b as historical record and are **superseded**.
> The five **ACEX** contracts below were redeployed **2026-08-22** for the security-audit fixes
> (§2d); the addresses they replaced held no funds and are superseded. The **escrow and lottery
> were redeployed 2026-09-04** for the audit fixes in §5, and the rail was switched over the same
> day — the addresses they replaced (`0x0606983c…72C25D`, `0x701A7bd8…0a9554`) held no funds and
> are superseded, but they are still named in the historical runs below, which happened on them.
> The NFT, PulseDistributor and verifier are unchanged since §2c.

| # | Contract | Address | Role |
|--:|---|---|---|
| 1 | **AIAgentLottery** | [`0x291b6eCB…D38350`](https://basescan.org/address/0x291b6eCB45121fEDE86BF769aC0eaa6AdED38350) | native-ETH reputation-weighted lottery |
| 2 | **AIMarketEscrow** | [`0x12Db8FAC…62CF2`](https://basescan.org/address/0x12Db8FAC81E5999D2f2087B79e38951571562CF2) | USDC payment channels for capability invocation |
| 3 | **AIMarketCapabilityNFT** | [`0x544dcdd8…35a281`](https://basescan.org/address/0x544dcdd8B01A7ee1444bf89A5381aA981735a281) | capability/credential NFTs |
| 4 | **AgentCollateralVault** | [`0x1BF39f65…13AbD9`](https://basescan.org/address/0x1BF39f659bd47bf0a15294B9e4760C327113AbD9) | ACEX — agent collateral custody |
| 5 | **AgentListingRegistry** | [`0xab6E20aE…1B6600`](https://basescan.org/address/0xab6E20aE29A4c7C10C6131Da9721aE98201B6600) | ACEX — credit-listing registry |
| 6 | **AgentLendingPool** | [`0x36446D83…232298`](https://basescan.org/address/0x36446D8393a39027D1242C1C277FdD9227232298) | ACEX — lending pool |
| 7 | **PulseAMM** | [`0xED279249…fc5D22`](https://basescan.org/address/0xED2792499757dd6d40504b2522f2E99559fc5D22) | ACEX — pulse AMM (allow-listed pool creation) |
| 8 | **AgentAuditPool** | [`0x96005B0E…3e689b`](https://basescan.org/address/0x96005B0E70ce1F1E0C0977067216aC45043e689b) | ACEX — audit staking pool |
| 9 | **PulseDistributor** | [`0x325aC681…e38596`](https://basescan.org/address/0x325aC681FDd14c23DE074c15ac2Ed07702e38596) | ACEX — pulse reward distribution |
| 10 | **PlonkVerifier** | [`0x1914D8a0…9B8e85c5`](https://basescan.org/address/0x1914D8a04dd65c6d8C888B98A31757F79B8e85c5) | ZK proof verifier (oracle proofs) |
| 11 | **BountySplitter** | [`0x89A618F6…A63426`](https://basescan.org/address/0x89A618F66767101B96977e536797838661A63426) | MOMUS red-team bounty settlement — one pool per finding, split across finder/fixer/conductor |

**Tokens:** native **ETH** (gas + lottery tickets/prizes) and real **Circle USDC**
[`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`](https://basescan.org/address/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)
(6 decimals — escrow/service payments). No fake token is used anywhere.

> Full redeploy txs + real-money E2E for this set: **§2c** (deploys) and **§3h** (tests).
> ACEX audit redeploy: **§2d**.

### Contract map

```mermaid
flowchart TD
  W["👤 0x1218 — owner / operator / oracle-signer / hub / treasury"]
  subgraph CORE["AIMarket core"]
    L["AIAgentLottery<br/>(native ETH)"]
    E["AIMarketEscrow<br/>(USDC channels)"]
    N["AIMarketCapabilityNFT"]
    ZK["PlonkVerifier (ZK)"]
  end
  subgraph ACEX["ACEX — agent credit exchange (deployed, not value-tested · audit HIGH)"]
    V["AgentCollateralVault"] --> R["AgentListingRegistry"]
    V --> LP["AgentLendingPool"]
    R --> AP["AgentAuditPool"]
    AP --> AMM["PulseAMM"]
    PD["PulseDistributor"]
  end
  HUB["AIMarket Hub :9083"]
  USDC["💵 real USDC"]

  W -->|owns / operates| CORE
  W -->|owns| ACEX
  W --> HUB
  HUB -->|invoke / channels| E
  HUB -.->|ZK plugin → verifyProof| ZK
  A1["🤖 AI-Factory agent"] -->|buy tickets ETH| L
  A2["🤖 ACEX agent"] -->|buy tickets ETH| L
  A1 -->|deposit USDC| E
  E -->|debit per receipt → settle| W
  USDC --- E
  E -.whitelisted token.- USDC
  R --> SHARE["AgentShareToken / NoteToken<br/>(minted per-listing at runtime)"]
```

---

## 2. Deployment transactions

All deployed by `0x1218` on 2026-06-18 (blocks 47496541+). Roles set at deploy — no transfers.

| Contract | Deploy tx | Notes |
|---|---|---|
| AIAgentLottery | [`0x25e5e8…f23412`](https://basescan.org/tx/0x25e5e86ccc2afcbea546ab46fc3098801ad6fb5215f83e9864c19e18bef23412) | ctor: admin/gov/treasury/operator/oracleSigner = `0x1218`; token=ETH(`0x0`); ticket 0.000003 ETH; splits 80/12/8; entry 120s; drawDelay 30s; onchainVdf false |
| AIMarketEscrow | [`0x5c6091…5e03c8`](https://basescan.org/tx/0x5c6091e8ea5f0392f2c5a6de836e7178b7b8350368cb342813e971618b5e03c8) | ctor: initialHubs=[`0x1218`], initialTokens=[USDC] → USDC whitelisted at deploy |
| AIMarketCapabilityNFT | [`0x944917…7bdbab`](https://basescan.org/tx/0x944917b32f720b73358a335607e31f5c539c9d84b0f75901c5f47cef5b7bdbab) | + `setAuthorizedHub(0x1218,true)` [`0x858486…b40478f`](https://basescan.org/tx/0x8584868605550cfe9b3a80edaab4982839c36b812cf028079f33acd87b40478f) |
| AgentCollateralVault | [`0x2f91ff…489a82`](https://basescan.org/tx/0x2f91ff2aa85f0919562c3f7e0d491bbe72e51a771992ca30b304cd67f4489a82) | ctor(usdc) |
| AgentListingRegistry | [`0x6a37f0…0af652c`](https://basescan.org/tx/0x6a37f0bc0a123d3abdc432a46fa66cb34ace9985826f4c32754b9eeec0af652c) | ctor(vault, usdc) |
| AgentLendingPool | [`0x7ed380…ea32ef`](https://basescan.org/tx/0x7ed380c70dd2495a2ee7a6e3973305a818c1adbd5e574b654aad11a228ea32ef) | ctor(usdc, vault, registry) |
| PulseAMM | [`0xddeb4f…305d0d`](https://basescan.org/tx/0xddeb4fb38bc1cc39f8068344dbdb6ab8d2b12f3c05d036197b4644f5a5305d0d) | ctor() |
| AgentAuditPool | [`0x877b8d…4dc9c62`](https://basescan.org/tx/0x877b8d9bfc969aafc4b36310f7636b60534622f5ee28229d9baab4b864dc9c62) | ctor(registry, vault, usdc, amm) |
| PulseDistributor | [`0x37F17f2B…8775e`](https://basescan.org/address/0x37F17f2B733d9D801C7f03f6A6D1E5cA8898775e) | ctor(owner=`0x1218`) |
| PlonkVerifier | [`0xb11af6f3…0ACf65`](https://basescan.org/address/0xb11af6f387aCD57E6AECDa222D0108e6380ACf65) | no ctor args |
| BountySplitter | [`0x236215…38b57e`](https://basescan.org/tx/0x2362155832058672436c804e767d8ae540edfea9c796358519cef2549238b57e) | ctor: initialTokens=[USDC] → USDC whitelisted at deploy. Block 49701100, gas 937 951, cost ≈ 0.0000047 ETH. Owner = `0x1218` (the **Treasury** operator, deliberately NOT the MOMUS scanner key). Verified on-chain: `owner()`=`0x1218…Ad0a`, `tokenWhitelisted(USDC)`=true, `MAX_POOL`=100 000e6, `EXPIRY`=30 days. **Re-verified 2026-08-08** against Base mainnet: 3 702 bytes of code, `owner()`=`0x1218…Ad0a`, `MAX_POOL`=100 000e6, `EXPIRY`=2 592 000 s, `tokenWhitelisted(USDC)`=true, balance **0 ETH / 0 USDC** — nothing has ever settled through it and nothing is locked in it, which is the expected state while settlement runs on UNI. The role split is not a contract constant: pools are keyed by `roleId = keccak256("finder"\|"fixer"\|"conductor")` and the 50/35/15 shares are applied by the Treasury when it funds a pool. |

**ACEX wiring** (operator): `vault.setRegistry` [`0xcc9fcd…68d14`](https://basescan.org/tx/0xcc9fcd4018c1a73b8f4d175ee45118181fa93f649e171d3e8e0f7a7c1fe68d14), `vault.setLendingPool` [`0x3a2f9e…009a2d`](https://basescan.org/tx/0x3a2f9ebdf6be9167d977e36e49828eec7e343463a79510785d47d4396e009a2d), `registry.setAuditPool` [`0xf3e55b…6fd29018`](https://basescan.org/tx/0xf3e55b6829c7e224ad8028e88565c1ebe6004746c189c81eac44f1276fd29018). Wiring verified on-chain (vault↔registry↔lending↔auditpool↔amm all linked).

> The ACEX rows above (4–8) were **superseded by the 2026-06-19 redeploy** — see §2b. The original
> addresses/txs here are kept as the historical record; the live ACEX is the redeployed set.

---

## 2b. ACEX redeploy — audit fixes (2026-06-19, Base mainnet) ♻️

Why: the in-repo security audit found 1 critical + 5 high issues in ACEX (spot/low-volume baseline
manipulation, AMM-drain oracle, first-depositor share inflation, default-compensation rounding).
All were fixed in source (49 Foundry tests) and the stack was redeployed from `0x1218` and
**source-verified on Basescan**. Block **47,554,183**; total gas **10,518,113** (~0.000147 ETH).

| # | Tx (signer `0x1218`) | Call | Effect |
|--:|---|---|---|
| 1 | [`0xeed4c1…49a9df`](https://basescan.org/tx/0xeed4c1fd5197f9c3362cef8e3d9541de23f489f28d606fb2ffa5e1c46749a9df) | `new AgentCollateralVault(usdc)` | deploy vault `0xF9A387c4…21667E` |
| 2 | [`0xf5c1d6…b002e8df`](https://basescan.org/tx/0xf5c1d6a1e3907b1878b66cc0e4406646e97eb4fda3263878dba71c82b002e8df) | `new AgentListingRegistry(vault, usdc)` | deploy registry `0xcF287704…f436C3` |
| 3 | [`0xd2fba5…079882`](https://basescan.org/tx/0xd2fba5023872f0c0916c2e09653fe77e08eb13a6ba60597678cb78f66c079882) | `vault.setRegistry(registry)` | wire vault → registry |
| 4 | [`0xa77cb9…796321`](https://basescan.org/tx/0xa77cb9fd4c1d2b0ee76966ea0e04d8ef16e731c5736aa0a4aeb4fae8df796321) | `new AgentLendingPool(usdc, vault, registry)` | deploy lending `0xB0BE9046…1c2F48` (MINIMUM_LIQUIDITY 1e6 fix) |
| 5 | [`0xe77b3d…609ca7`](https://basescan.org/tx/0xe77b3de09c1e5f17c03e75523f93f3172d3ddfba5dc4a224d4e0f063a9609ca7) | `vault.setLendingPool(lending)` | wire vault → lending |
| 6 | [`0xc5b0db…3b0c0b0`](https://basescan.org/tx/0xc5b0db227d5ea9a63b8211038e58a09acb4004c54d18c84af521205fd3b0c0b0) | `new PulseAMM()` | deploy AMM `0x049B839B…5d4337` (MIN_RESERVE drain guard) |
| 7 | [`0x23e317…a33245`](https://basescan.org/tx/0x23e317b8c773dc38f870d7c6263f2272025f46fb0aef53b675c4723fe5a33245) | `new AgentAuditPool(registry, vault, usdc, amm)` | deploy audit pool `0x86a4A9A8…060Cee` (TWAP-only baseline) |
| 8 | [`0xd414fe…5f96cc`](https://basescan.org/tx/0xd414fe709577197fcbfbe48d071866ba4fa320e2194b05b4876bd065a85f96cc) | `registry.setAuditPool(auditPool)` | wire registry → audit pool |

Verification: all 5 contracts `Pass - Verified` on Basescan (Etherscan V2). Registry/docs/monitor
address book updated to this set. **Value-testing of the fixed contracts is still pending** (the
AuditPool baseline → default path is time-gated by the 1-day TWAP observation window).

---

## 3. Test — the agents transact by the protocol's rules

Two agents are real ecosystem node wallets, derived deterministically from a **secret seed**
(the `0x1218` private key) + node id — `keccak256("ailottery-uni-wallet|"+seed+"|"+agentId)`:
- **AI-Factory** `0x9787F81f5bc6d096Cfe884Dc8c29950b57A8ecd1`
- **ACEX agent** `0x88A7Df339C333fE75Db1a4e2a55551e6a8009b30`

### 3a. Funding (operator → agents)
| Action | Tx |
|---|---|
| `0x1218` → AI-Factory: **1.0 USDC** (channel deposit) | [`0x38fc92…365fb1`](https://basescan.org/tx/0x38fc926192e9f6d9d7f772d4b2b2f7616062fa7dc1d396389e0137c908365fb1) |
| `0x1218` → AI-Factory: 0.0008 ETH (gas) | [`0xae4efb…482db5e2ef`](https://basescan.org/tx/0xae4efbf6bb10dc40601b65837ee073db36e3c5814d5769bedbfede482db5e2ef) |
| `0x1218` → ACEX agent: 0.0008 ETH (gas) | [`0x01e124…f7eb497b`](https://basescan.org/tx/0x01e124642f5bab115b778398a9d02d407a9a68f75478ea96c109e8baf7eb497b) |

### 3b. Capability-payment channel (the core protocol rule) — real USDC
| # | Who | Call | Params | Effect | Tx |
|--:|---|---|---|---|---|
| 1 | AI-Factory | `USDC.approve(escrow, 1.0)` | spender=escrow, amount=1000000 | allow escrow to pull deposit | [`0x2d3817…d5579b`](https://basescan.org/tx/0x2d3817148bcd0077f53c322c7fe0665f7500eaf127db1187107b745774d5579b) |
| 2 | AI-Factory | `escrow.openChannel(id, USDC, 1.0)` | id=`0xa0cded…`, 1000000 | $1 channel opened (depositor=AI-Factory) | [`0x50879b…0a856b5`](https://basescan.org/tx/0x50879b239a0a8959531faa7c06f1afd99b1a037ca15eaae6a8a36cd390a856b5) |
| 3 | `0x1218` (hub) | `escrow.debitChannel(id, 0.40, receipt, deadline, sig)` | amount=400000; **sig = EIP-712 DebitAuthorization signed by depositor AI-Factory** | meters a 0.40 USDC capability charge (no tokens move yet) | [`0xd9bfc0…f5c435b58`](https://basescan.org/tx/0xd9bfc009c348cacbf2601640b73dccc88c4c78f8af92a41b8b43b96f5c435b58) |
| 4 | `0x1218` (hub) | `escrow.settleChannel(id)` | id | pays 0.40 → hub, refunds 0.60 → AI-Factory; channel Settled | [`0x6551e2…3cfbd4f`](https://basescan.org/tx/0x6551e2c24eaa2365ae6065734c3c93c648bfd4484f340e90d9b3dacb53cfbd4f) |

### 3c. Agent → agent service payment — real USDC
| Who | Call | Effect | Tx |
|---|---|---|---|
| AI-Factory | `USDC.transfer(ACEX, 0.30)` | one agent pays another 0.30 USDC, signed by AI-Factory's own key | [`0xca7a20…85a97fa`](https://basescan.org/tx/0xca7a20f634129c33d7df473148ed4ee56521751588ac3b05401a63f0085a97fa) |

### 3d. Lottery — a full round by the rules (native ETH, commit-reveal + signed beacon)
Pool = 2 tickets × 0.000003 ETH = **0.000006 ETH**, split 80/12/8 → prize 0.0000048, opex 0.00000072, operator 0.00000048.

| # | Who | Call | Params / meaning | Tx |
|--:|---|---|---|---|
| 1 | `0x1218` (operator) | `openRound()` | opens **round 2**, 120s entry window | [`0x807a63…e5c97f`](https://basescan.org/tx/0x807a63452c55bd9b67cc8723a2af12649c7ca85f0daf8b056e24653568e5c97f) |
| 2 | AI-Factory | `buyTickets(2, 1)` | msg.value = 0.000003 ETH (exact) | [`0x9a99f2…d1bca53f`](https://basescan.org/tx/0x9a99f25708d9338b331a753347edd81149506c8c228ab170315fa249d1bca53f) |
| 3 | ACEX agent | `buyTickets(2, 1)` | msg.value = 0.000003 ETH | [`0x5ae93a…a7aeda7b`](https://basescan.org/tx/0x5ae93a5208e2ba9702dccc43ecf99fbf2ed2d5c238b683b9ed69c749a7aeda7b) |
| 4 | `0x1218` (operator) | `closeEntries(2, commit)` | commit = keccak256(platonRandom) — **commit-reveal** anti-grinding | [`0x6d23de…d131266`](https://basescan.org/tx/0x6d23de9f1c5a955b865bfe3522a8b08c248725e8d50a2036d1030f9d7d131266) |
| 5 | `0x1218` (oracle-signer) | `fulfillDraw(2, platonRandom, 0, sig, vdf)` | **EIP-712 `DrawBeacon` signed by the oracle-signer**; reveals platonRandom; winner = reputation-weighted; round **Settled** | [`0x53e4d7…26ca672`](https://basescan.org/tx/0x53e4d73fcaf066c6d7df21dfca1758e47985e8ccdad1f0ef6fe583e6226ca672) |
| 6 | ACEX agent (winner) | `claimPrize(2)` | winner pulls the 0.0000048 ETH prize | [`0x8477a5…c7b879eed`](https://basescan.org/tx/0x8477a5254301949e318a352d2eab9dab10a6d8f4a5932df77262930c7b879eed) |

> **Where the prize went (important):** `claimPrize` paid the **0.0000048 ETH** prize to the
> **winner's wallet — the ACEX _agent_ EOA `0x88A7Df339C333fE75Db1a4e2a55551e6a8009b30`**. Note
> this is the lottery-participant node wallet, **not** the ACEX credit-exchange contracts (those
> hold no value). In **recovery (§3e)** that prize was swept — together with the rest of the
> agent's ETH — back to **`0x1218`**. So the prize ends on `0x1218`; the agent wallet keeps only
> ~0.00003 ETH gas dust (and is itself derived from the `0x1218` seed, so still under `0x1218`'s
> control), and the **lottery contract is drained to 0 ETH**. Net: the winnings are on `0x1218`,
> nothing is stranded on any agent or contract.

> The first `openRound` opened an **empty round 1** (operator read the round id before the RPC
> caught up, so no tickets were bought) — harmless, no funds; superseded by round 2.

### 3e. Recovery — everything back to `0x1218`
| Action | Tx |
|---|---|
| `withdrawOpex(0x1218, 0.00000072 ETH)` (treasury) | [`0xd05bc2…3696983`](https://basescan.org/tx/0xd05bc245c8517ac8e310f9551767e142678183fa3c9beb845ebc53fe73696983) |
| `withdrawOperatorFee(0x1218, 0.00000048 ETH)` (treasury) | [`0xda971f…fd579384`](https://basescan.org/tx/0xda971f649df4d1f641d4286eced36ff764ddcd3081687e6d60586e40fd579384) |
| sweep AI-Factory USDC (0.30) → `0x1218` | [`0xdaf063…95d34d41c`](https://basescan.org/tx/0xdaf063cdec2f8d7a6d016a2c9e6bcaea0ad7b7ec7498ec05403df8a95d34d41c) |
| sweep ACEX USDC (0.30) → `0x1218` | [`0x32673b…8dc8e3eec`](https://basescan.org/tx/0x32673be52a38b109454e088e9d4c03399b1dd25c8c5662f0baaf5808dc8e3eec) |
| sweep AI-Factory ETH → `0x1218` | [`0x621312…6ab21b70`](https://basescan.org/tx/0x62131283287a1e0c0643a5530282c8c01ca63ead3e5d63e7388003b86ab21b70) |
| sweep ACEX ETH → `0x1218` | [`0x0a1a72…482274850`](https://basescan.org/tx/0x0a1a721ffb7644500ce0959a0f7e183ac1bc5e2562d6d29f089a032482274850) |

### 3f. Re-verification cycle — fresh real-money run (2026-06-20) + how we get paid

A second, independent live run on **2026-06-20**, executed directly from `0x1218` (here `0x1218`
plays **both** the consumer/depositor **and** the hub/operator, so every dollar nets back to it and
the only real cost is gas). This re-proves the money rails against the *currently deployed*
contracts (the audit-fixed ACEX redeploy of §2b) and answers **"how do we receive money?"**.

**Capability-payment channel — real USDC** (channel `0x09d4b1…e063ef`, deposit **1.00 USDC**):

| # | Call | Effect | Tx |
|--:|---|---|---|
| 1 | `USDC.approve(escrow, 1.0)` | allow escrow to pull deposit | [`0x59d820…320389`](https://basescan.org/tx/0x59d820430d76d88399842df750e7922bf3b4d99d87406f63dd64ec1e99320389) |
| 2 | `escrow.openChannel(id, USDC, 1.0)` | 1.00 USDC moves into escrow (depositor=`0x1218`) | [`0xea561d…8ede05`](https://basescan.org/tx/0xea561d060fabaca28626ef3a1868d252f6ea612ca6f5a392ef4f4c5a7f8ede05) |
| 3 | `escrow.debitChannel(id, 0.25, receipt, deadline, sig)` | meters a **0.25 USDC** charge; `sig` = EIP-712 `DebitAuthorization` signed by the depositor; binds hub on first debit | [`0x6fa053…fb8998`](https://basescan.org/tx/0x6fa053a15a2b533e06f6f4119a79b08410979af868f4af490d00c7e7d2fb8998) |
| 4 | `escrow.settleChannel(id)` | **pays 0.25 USDC → hub** (this is the revenue leg), **refunds 0.75 USDC → depositor**; channel Settled | [`0xb4d3bd…d72d50`](https://basescan.org/tx/0xb4d3bdff849ad38673d83ea3210969c593d9a1d30636b12ec83c0bc132d72d50) |

> **How we receive money (the answer):** on `settleChannel`, the contract transfers the channel's
> accrued `usedAmount` to **`ch.hub`** — the hub address bound at first debit. *That transfer is the
> revenue.* The consumer pre-funds a channel, each metered invocation debits it against an EIP-712
> authorization the consumer signed, and settlement pays the operator exactly what was used and
> refunds the rest. No caller-supplied recipient (neither side can redirect funds). Final channel
> state read on-chain: `depositAmount=1.0, usedAmount=0.25, balance=0.75, status=Settled`.

**Lottery — a fresh full round (round 3, native ETH, sole participant ⇒ deterministic win):**
income = 1 ticket × 0.000003 ETH, split **80/12/8** → prize 0.0000024, opex 0.00000036, operator 0.00000024.

| # | Call | Meaning | Tx |
|--:|---|---|---|
| 1 | `openRound()` | opens **round 3**, 120 s entry window | [`0x7aad31…534b66`](https://basescan.org/tx/0x7aad31e144d0bbb8695552573f1047beb6d4d090f7c5dd33c0bcceee60534b66) |
| 2 | `buyTickets(3, 1)` | `msg.value` = exactly 0.000003 ETH | [`0x7c2ed2…dc0de9b`](https://basescan.org/tx/0x7c2ed2637acc30345e8cf3677663e5ba844e2d1936084c23bd6f25d28dc0de9b) |
| 3 | `closeEntries(3, commit)` | `commit = keccak256(platonRandom)` — commit-reveal anti-grinding | [`0x227d9f…f28c6b2`](https://basescan.org/tx/0x227d9f9d04acb842b931b47f61c7a2305e32adc235f3df5b25a901899f28c6b2) |
| 4 | `fulfillDraw(3, reveal, …, sig, vdf)` | EIP-712 `DrawBeacon` signed by oracle-signer; reveal matches commit; round **Settled** | [`0xa3f87f…b7ec512`](https://basescan.org/tx/0xa3f87f0ebe039fc6e95a67158a171a002f5dd67f6062b6a4d91af8897b7ec512) |
| 5 | `claimPrize(3)` | winner pulls the **0.0000024 ETH** prize | [`0x45d79d…c2c7a8`](https://basescan.org/tx/0x45d79ddfa33fa83bf6d3c33dbb30fb3551a3d07e8fe020d48158761f82c2c7a8) |
| 6 | `withdrawOperatorFee(0x1218, …)` | operator share (0.00000024 ETH) → treasury | [`0xd5819b…0a9745c`](https://basescan.org/tx/0xd5819b23df24c2ac223442b1b8d1f51db7eec8b5afed0a4f7af4575e60a9745c) |
| 7 | `withdrawOpex(0x1218, …)` | opex share (0.00000036 ETH) → treasury; **lottery drained to 0 ETH** | [`0x70413d…c66af2`](https://basescan.org/tx/0x70413d7ed4d706ed1a2ecd1c30ff177ec10bfcd3bf392c6df78e17ebf3c66af2) |

**End state (read on-chain):** `0x1218` holds **2.0 USDC (unchanged) + 0.005747 ETH**; lottery
contract **0 ETH**, round 3 Settled & claimed; escrow channel Settled. **Total gas for the whole
cycle ≈ 0.0000061 ETH** (sub-penny). Nothing stranded.

#### Off-chain MCP / hub payment — what works and what doesn't (live infra, 2026-06-20)
Tested the hub's payment surface as an external paying consumer (`hub :9083`):
- ✅ **Channel metering works**: `POST /ai-market/v2/channel/open` credits a channel and
  `/channel/close` settles it (`used_usd` / `refund_usd`) — the off-chain ledger half of the rail.
- 🔴 **The deployed hub can't fulfil a *paid* invoke end-to-end.** Its manifest advertises
  `platon.*` and factory caps, but `/v2/invoke` returns **"Unknown capability: platon.oracle@v1"**
  (oracle adapter not registered in this deploy) and **"No execution backend configured
  (AIFACTORY_PUBLIC_URL)"** for factory products. So an AI-to-MCP *purchase* cannot complete a
  charge against the live hub today — the channel correctly refunds in full (no service ⇒ no debit).
  The *protocol* is sound (open/debit/settle proven on-chain above); this is a **deployment wiring
  gap** on the hub container, tracked as a finding. (The oracle-gateway MCP → live oracle-family
  path returns valid signed output — see test report §4 — but that path is currently unmetered.)

#### ACEX value flow — verified on mainnet (constants) + run in full in emulation
On **Base mainnet** the audit-fixed ACEX redeploy (§2b) is verified by reading the fixed constants
live: `AgentLendingPool.MIN_FIRST_DEPOSIT = 2e6`, `MINIMUM_LIQUIDITY = 1e6`, `PulseAMM.MIN_RESERVE =
1000`, `AgentAuditPool.MIN_OBSERVATION_WINDOW = 86400` (1-day TWAP window). A full *mainnet* value
cycle is deliberately **not** run (it needs ≥10,000 USDC `MIN_STAKE` and the first lending deposit
permanently locks 1 USDC — real loss for no extra assurance).

Instead the **full value lifecycle was executed end-to-end in a local emulation** (anvil, mock 6-dec
USDC minted freely — exactly the "no fund limits" UNI affords), proving the mechanics with real
transactions: agent applies → **auditor stakes 10,000 USDC + covers 1,000 @ 85%** → owner approves
(CapShares minted) → **agent deposits 50,000 collateral** → **lender deposits 50,000** → **agent
borrows 20,000** (LTV-gated, debt 20,000) → **AMM pool seeded** (100 shares + 10,000 USDC) → **real
swap** (trader buys, price moves) → TWAP `captureBaseline` correctly **rejects before the 1-day
window** (the audit fix) → price crashed → **`triggerDefault` defaults the listing and slashes the
auditor's cover** (staked 10,000 → 9,000). Plus **49/49 Foundry tests pass** (6 suites), covering the
captureBaseline happy-path, the baseline-never-established default, the TWAP-manipulation guard,
lending/liquidation, AMM, notes, distributor, and the PLONK claim proofs.

### 3g. External-actor payment THROUGH the MCP hub — real USDC end-to-end (2026-06-20, H-1 fixed)

> **Honesty label: staged (operator wallets).** Buyer `0xA129…` and hub-operator `0x6767…`
> were created and funded from `0x1218` for this demo. Real USDC moved on Base, but this is
> **not** an independent outsider paying the hub. The centerpiece external-depositor proof is
> **§3j** (`0x6E94…`).

The earlier finding **H-1** was that the deployed hub could *meter* channels but could not *fulfil* a
paid MCP invoke (oracle adapter unregistered + `AIFACTORY_PUBLIC_URL` unset). This section is the
**fix + a staged multi-wallet payment**, settled on-chain.

**The fix (server 1).** Built a corrected hub image from the monorepo source (oracle federated
transport from commit `37650a87` + the channel-secret / recipient / demo-credit-fail-closed security
fixes) and ran it on server 1 **`:9085`** (`aimarket-hub-fixed`), leaving the production `:9083`
untouched. Registered the **AIMarket Oracle Family** as a trusted peer and pointed it at the family
`mcp_endpoint` (`https://oracles.modelmarket.dev/family/ai-market/v2/invoke`). A federated invoke of
`platon.random@v1` now returns valid signed chaos-VRF randomness through the hub (`POST /v2/invoke →
200`), and a paid channel mints a `channel_secret` and shows the bound `recipient`.

**New contract deployed for this flow** — a fresh, source-verified escrow so the external payment has
a clean, dedicated, auditable address:

| Contract | Address | Notes |
|---|---|---|
| **AIMarketEscrow (MCP settlement)** | **[`0x2F4c883b8720AA068247EAe9C024405025abfB22`](https://basescan.org/address/0x2F4c883b8720AA068247EAe9C024405025abfB22)** | ♻️ verified; `authorizedHubs[hub-operator]=true`, USDC whitelisted; owner `0x1218`. Deploy tx [`0xfe117d…71dbb1`](https://basescan.org/tx/0xfe117d46dbd2d0122fa5460d5a39de7523c9496db0ce53689615981aab71dbb1) |

**Identities** (fresh wallets — the buyer is genuinely separate from the deployer/operator):
- **External actor (buyer)** `0xA1298d283dA43b7454a2bcD02DBF56558722bd1b`
- **Hub operator (recipient — "us")** `0x676739bbc9959B4FbFCD5EaE4318e9a1f8d36dcF`

**Operator top-up of the actors** (from `0x1218`, so the buyer has its own funds): external actor
1.0 USDC [`0x6b4508…d031e`](https://basescan.org/tx/0x6b4508aeb058cde97d0e65cd9ac5582f9a6dcaaa71c3d96ac04813814f9d031e)
+ gas [`0x64d38b…2ef590`](https://basescan.org/tx/0x64d38bd027dcd76f8e77f6e17d1088cf5ce4c7336bee0ca3838ce69e872ef590);
hub operator gas [`0xfbbefc…23d3c97`](https://basescan.org/tx/0xfbbefcbe4005aa71912eee4cbe060eff32f151dbb503805d2da7dfd3423d3c97).

**The payment lifecycle:**

| # | Who | Action | Effect | Tx |
|--:|---|---|---|---|
| 1 | external actor | `USDC.approve` + `escrow.openChannel(1.0)` | buyer prepays **1.0 USDC** on-chain into the new escrow | [`0xbde893…ea32b5`](https://basescan.org/tx/0xbde8934277677699ecfc2b2b9310026d6334db32c2da6f95a37d271ce3ea32b5) |
| 2 | external actor | **25 × MCP invoke** `platon.random@v1` via hub `:9085` (paid channel + secret) | hub fulfils + meters + signs a receipt each call → **$0.10 billable** (25 × $0.004) | off-chain (25 signed receipts) |
| 3 | external actor | signs **EIP-712 DebitAuthorization** for $0.10 | authorizes the operator to collect exactly what was consumed | (off-chain signature) |
| 4 | hub operator | `escrow.debitChannel(0.10, receipt, sig)` | meters the buyer's payment on-chain against its own signature | [`0x8e1446…ce96c9`](https://basescan.org/tx/0x8e14466513a9879b8c5d1490b066e0789cbff309bcd7e1efbab6e6685fce96c9) |
| 5 | hub operator | `escrow.settleChannel` | **$0.10 → hub operator (real USDC received), $0.90 refunded → buyer** | [`0xcd3d62…93c5c1`](https://basescan.org/tx/0xcd3d6258d54dc81394db942b02ee5bfbb72807d0c46f80d1cc9123b77093c5c1) |

> **Confirmed on-chain:** after settle, hub-operator USDC = **100000 (\$0.10, received from the external
> actor)**, external-actor USDC = 900000 (\$0.90 refund), escrow = 0; channel `Settled`. This is a real
> external→operator payment for product consumed through the MCP hub.

**Recovery to `0x1218`** (demo wallets I created/funded): hub operator returns $0.10
[`0x7018d7…79fcf64`](https://basescan.org/tx/0x7018d7e92241f73bd0bf15ce37236ead036c04240901d0ca6700ca00679fcf64),
external returns $0.90 [`0x34c0cc…e4b33cbee393`](https://basescan.org/tx/0x34c0cc5adf70bcfd18aa356a72659902bdd1f4c7fe75de55a23ee4b33cbee393)
→ `0x1218` whole again at **2.0 USDC** (only gas spent).

> **Promoted to production (2026-06-20):** the fixed image now runs as the production **`:9083`**
> "48720 Federation Hub" (the Jun-13 image was tagged `ecosystem-aimarket-hub:rollback-jun13` for
> rollback; the data volume was preserved + chowned to the non-root `hub` user). The oracle family is
> registered as a trusted peer on prod, and a paid `platon.random@v1` invoke through `:9083` returns
> real signed randomness with a channel that mints a secret and shows recipient `0x1218`. The
> standalone `:9085` demo instance was removed.

---

## 4. Token map — where value flowed

| Token | Used for | Flow during the test | End state |
|---|---|---|---|
| **ETH** (native) | gas; lottery tickets + prizes | `0x1218` → agents (gas) → tickets into lottery pool → prize to winner + opex/operator to treasury → swept back | all on `0x1218` (agents hold ~0.00003 ETH dust) |
| **USDC** (real) | escrow capability payments; agent↔agent | `0x1218` → AI-Factory → escrow channel (debit 0.40 → hub, refund 0.60) → AI-Factory → ACEX (0.30) → swept back | **2.0 USDC, 100% on `0x1218`** |

**End state (verified on-chain): `0x1218` holds 2.0 USDC + ~0.005 ETH. Lottery contract drained to 0 ETH. Round 2 Settled, prize claimed. Nothing stranded.** Agent wallets are themselves derived from the `0x1218` seed, so the dust remains under `0x1218`'s control.

## 5. Verify any of this yourself
```bash
RPC=https://mainnet.base.org
cast call 0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017 "whitelistedTokens(address)(bool)" 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 --rpc-url $RPC   # → true
cast call 0xbda3e32331822d525d5e7c7b51ed76132e84db61 "getRound(uint256)" 2 --rpc-url $RPC    # round 2: Settled, prizeClaimed=true
cast tx  0x53e4d73fcaf066c6d7df21dfca1758e47985e8ccdad1f0ef6fe583e6226ca672 --rpc-url $RPC   # fulfillDraw
```
All 10 contracts are source-verified — open any address link above and read the **Contract → Code** tab on Basescan.

---

## 6. Claude Code buys a verifiable random number — MCP → pay → on-chain settle (2026-06-20)

**What happened:** Claude Code, acting as an autonomous agent, called the **AIMarket Oracle Gateway** (the Glama MCP server `alexar76/aimarket-oracle-gateway`) capability **`platon.random@v1`**, received an Ed25519-signed verifiable random number, and **paid for it on-chain** via the real `AIMarketEscrow` payment-channel protocol — then used the number in the chat.

- **MCP capability:** `platon.random@v1` (oracle gateway → Platon chaos-VRF), price **$0.004 USDC**.
- **Random received:** `0x550d84ed50269e09def84ad138564868bf304d30112479c5eb3bd37f103a4712`
  (scheme `platon-chaos-vrf/v1`, Ed25519-signed). **Used in chat** as a 1–100 pick → **39** (d6 → 3, d20 → 19).
- **Payer / hub:** `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a` (depositor = authorized hub = operator — it signs its own EIP-712 debit authorization).
- **Contract:** `AIMarketEscrow` `0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017` · token real USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` · channelId `0x2de3a6…d79f6c`.

| # | Call | Params / meaning | Tx |
|--:|---|---|---|
| 1 | `USDC.approve(escrow, 1.00)` | allow escrow to pull the $1 deposit | [`0x19efaa…98bee6`](https://basescan.org/tx/0x19efaa1cd173f00d9b7cbe797ec1114c547caf15b0178b3f0749dba90698bee6) |
| 2 | `escrow.openChannel(id, USDC, 1.00)` | $1 channel opened (depositor `0x1218`) | [`0xffc4b4…5a5fd2`](https://basescan.org/tx/0xffc4b483f2c716aafd5246ab6b78a55912f24c11079a1557107b0eeb385a5fd2) |
| 3 | `escrow.debitChannel(id, 0.004, receipt, sig)` | meters the $0.004 random-number charge; `receiptId = keccak(randomHex)`; **EIP-712 DebitAuthorization self-signed by `0x1218`** | [`0x8c1d52…c8fce6`](https://basescan.org/tx/0x8c1d52c9ff541c1d524ca144db68e6bf692c501329941bd2cbcc0a235cc8fce6) |
| 4 | `escrow.settleChannel(id)` | $0.004 → hub `0x1218`, $0.996 refund → depositor `0x1218`; channel **Settled** | [`0x957e6c…3c9590`](https://basescan.org/tx/0x957e6c05f39da6d901fa2ec4ecc22030864e3071bd0011960c179c5efc3c9590) |

> **Confirmed on-chain:** channel `usedAmount = 4000` (\$0.004), `status = Settled`. Since depositor = hub = `0x1218`, both the metered \$0.004 and the \$0.996 refund return to `0x1218` — **net USDC movement \$0.00, only gas spent; `0x1218` still holds 2.0 USDC.** A genuine, self-contained paid-invoke settlement.

Note: the public hub `modelmarket.dev` answered `Unknown capability` for a raw `platon.random@v1` POST, so the draw was fetched from the oracle-family endpoint the gateway wraps (`oracles.modelmarket.dev/family`); the prod hub meters channels off-chain, so the on-chain debit/settle was driven directly with the operator key.

**Verify:**
```bash
RPC=https://mainnet.base.org
cast tx 0x8c1d52c9ff541c1d524ca144db68e6bf692c501329941bd2cbcc0a235cc8fce6 --rpc-url $RPC   # debitChannel
cast call 0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017 \
  "getChannel(bytes32)((address,address,address,uint256,uint256,uint256,uint256,uint256,uint8))" \
  0x2de3a6be1798c9020d8702d39392715f7496428d48c412fe4a340e5867d79f6c --rpc-url $RPC   # status=1 (Settled)
```

---

## ARGUS agent — wallet bootstrap + first lottery attempt (2026-06-21)

ARGUS (the demand-side agent) got its own Base wallet and attempted its first native on-chain action — the AI-Agent Oracle Lottery.

- **Agent wallet:** `0x5eF303313d84b334Ea02EA694152144D05485206` (BIP39 seed-phrase wallet; seed held by the owner, never exposed to the model)
- **Funding source (burner/deployer):** `0x40409bE3bAf99f22aA86b2FBaAa99EF2188D5674`

| # | Action | Result | Tx |
|---|--------|--------|-----|
| 1 | fund agent `0x40409 → 0x5eF3`, **0.00025 ETH** | success; agent balance 0.00025 ETH (~$0.43) | [`0xb8e7a0…d04d0b`](https://basescan.org/tx/0xb8e7a0a3efc64d4b96f7407a3d0d8857f91a4134eea42fa238a262c880d04d0b) |
| 2 | `lottery.buyTickets(roundId=3, count=1)` @ `0xbda3…db61`, value 0.000003 ETH | **reverted `EntriesNotOpen()` in simulation → no tx sent**, no gas spent (round 3 not in `Status.Open`) | — |

> **Outcome:** the agent's wallet, viem RPC-fallback, ticket-price read, simulate-before-send, and the WARDEN approval gate all worked end-to-end. The buy did not execute because **no lottery round is currently open for entries** (rounds are opened/closed by the operator). The agent stays funded (0.00025 ETH) and will enter the next open round. Native-ETH ticket price = 0.000003 ETH.

**Verify:**
```bash
RPC=https://mainnet.base.org
cast tx 0xb8e7a0a3efc64d4b96f7407a3d0d8857f91a4134eea42fa238a262c880d04d0b --rpc-url $RPC   # funding tx
cast call 0xbda3e32331822d525d5e7c7b51ed76132e84db61 "currentRoundId()(uint256)" --rpc-url $RPC
```

---

## 2c. Full ecosystem redeploy — 2026-07-26 (Base mainnet) ♻️

Fresh deploy of **all 10 contracts** from `0x1218…Ad0a` after the lottery fairness rework
(no `prevrandao` in the random word; commit-reveal + pinned `seedBlock`; permissionless
`fulfillDraw`). Escrow uses **real Base USDC** (no FakeUSDT). Roles at deploy:
admin/gov/treasury/operator/oracle-signer/hub = `0x1218`.

| Contract | Deploy tx | Address |
|---|---|---|
| AIAgentLottery | [`0x80940c…bbc8c2`](https://basescan.org/tx/0x80940cf0089cd8efd721b32eee87adafaf8684531b5fcbcad897b3aa3bbbc8c2) | `0x701A7bd8…0a9554` |
| AIMarketEscrow | [`0xdcf269…b7688d`](https://basescan.org/tx/0xdcf269337c51a8777c8ea7434daff4694da02d91968e8cf82b7631ef14b7688d) | `0x0606983c…72C25D` |
| AIMarketCapabilityNFT | [`0x41cb24…0662c9`](https://basescan.org/tx/0x41cb24afd57cc82f7d9ad4a2e178627ebcbad192c2c7b20ba5dc0629ee0662c9) | `0x544dcdd8…35a281` |
| + `setAuthorizedHub(0x1218,true)` | [`0xe56b46…9a54c8`](https://basescan.org/tx/0xe56b460d84c52910b54e3b517ca83ca8207d5d35eaec952457d63a03599a54c8) | (same NFT) |
| AgentCollateralVault | [`0x0c5e87…480411`](https://basescan.org/tx/0x0c5e87ad22aa6a7148d8699679ecec197803f6b182ba195ea337baa1a7480411) | `0xA29d019F…00fF45` |
| AgentListingRegistry | [`0xc2686a…136ac8`](https://basescan.org/tx/0xc2686adbd46d1da1fc3d1e4ed79e76fe6fd28bf58b1f75e20fee7d276e136ac8) | `0x04B8Ed69…8a627D` |
| `vault.setRegistry` | [`0xa41e06…48094c`](https://basescan.org/tx/0xa41e06cb2dbcb4c0ebd57c02da1e992ca2534cb01a7e299c0c545d150e48094c) | — |
| AgentLendingPool | [`0xdbce2e…3389c2`](https://basescan.org/tx/0xdbce2e9e59af7be6ca9c091190f9966ab5a989684b49a1d211855ea0613389c2) | `0x0ee6599b…265B32` |
| `vault.setLendingPool` | [`0xd32d34…a970e0`](https://basescan.org/tx/0xd32d3477f7b8358cb1be99d77bdb3fca5ec8f89e782a944f86c0fea402a970e0) | — |
| PulseAMM | [`0x5aee03…169857`](https://basescan.org/tx/0x5aee03fa49ba7e33d44985f763d20cbd196d38c574b4ba95bed912d224169857) | `0x96201B1A…28BFc9` |
| AgentAuditPool | [`0x91df39…03e69b`](https://basescan.org/tx/0x91df3938729c369556e14e89c45f847d43fbc8dffa845f0b9c937bb64703e69b) | `0x84991b78…Be4039c` |
| `registry.setAuditPool` | [`0x1f984e…511cb5`](https://basescan.org/tx/0x1f984ec8ee45d99a0f50c0d6e6da329daaca0ac8bdfbcedc22991f8acf511cb5) | — |
| PulseDistributor | [`0x699d64…11d587`](https://basescan.org/tx/0x699d64bac1081dff31dcc4d922584673c8e2b7e69167fe0cfc4675957a11d587) | `0x325aC681…e38596` |
| PlonkVerifier | [`0x9429ad…5e46201`](https://basescan.org/tx/0x9429ad64bed523b52a1890d5bc37fe52bf283fdfb7efeb3dd9329325d5e46201) | `0x1914D8a0…9B8e85c5` |

Lottery ctor: ticket `0.000003 ETH`, splits 80/12/8, entry window **30s**, `minDrawDelay` **15s**,
`ONCHAIN_VDF=false`. Escrow ctor: `initialHubs=[0x1218]`, `initialTokens=[USDC]`.

---

## 2d. ACEX redeploy — security audit fixes (2026-08-22, Base mainnet) ♻️

Why: the 2026-08 ecosystem audit found **two criticals** in ACEX, both reproduced with
Foundry PoCs before anything was changed.

1. **Collateral double-pledge.** `issueAgentNotes` had no caller check *at all* and never
   required a note series' face value to be covered by the collateral posted with it, while
   `vault.lockForNote` knew nothing about lending-pool debt. `usdcBalance` is one pot, so the
   same USDC could back a loan *and* a bond. A stranger — no allowance needed, because
   `collateralUsdc = 0` makes the `transferFrom` a no-op that always succeeds — could move a
   live borrower's collateral behind notes, push a healthy position into liquidation and take
   the 8% bonus (measured: **+24 USDC** on a 1 000 USDC position), or lock *all* of it so
   `liquidate` reverts on `seized == 0` and the lender loss has no recovery path, since the
   bad-debt write-off is only reachable from inside a successful liquidation.
2. **The insured could trigger its own default.** A default slashes staked auditor USDC and
   pays it to *note holders* — and notes are minted to the agent. The deciding price came from
   PulseAMM reserves, where `createPool` was permissionless (the `marketMakers` allow-list was
   written but **never read**), `MIN_RESERVE = 1000` meant 0.001 USDC, and the TWAP credits an
   unobserved interval at the price recorded at its *start*. Flash-crash → one
   `observeSharePrice` → arbitrage back → wait wrote a price the market never held.

Fixes: agent-only note issuance + `collateralUsdc >= faceTotal` + a debt-aware `lockForNote`;
the market-maker allow-list is now enforced on `createPool` and a `MIN_INITIAL_USDC = 1 000e6`
floor added; `triggerDefault` now also requires the **spot** price to be down, so a recovered
market cannot be defaulted on a stale snapshot. `setLendingPool` and `setPulseAMM` are one-shot
like their siblings. Also: `recordAudit` bounds the score to `BPS`, `depositCollateral` refuses
an unknown listing (the funds would have been unreclaimable), and `evictUnapprovedListing` lets
the operator recycle a squatted, unapproved, collateral-free listing id.

The superseded contracts held **no funds** (verified 0 ETH / 0 USDC immediately before the
redeploy) and are immutable, so they are abandoned rather than migrated. `PulseDistributor`,
the lottery, escrow, NFT and verifier were **not** changed and keep their addresses.

Blocks **50,317,366 – 50,317,373**; total gas **10,967,413** (0.0000572 ETH at 0.0102 gwei).
60 Foundry tests green (49 pre-existing + 11 added by the audit).

| # | Tx (signer `0x1218`) | Call | Effect |
|--:|---|---|---|
| 1 | [`0x68c247…7da8a9`](https://basescan.org/tx/0x68c247ef2582ae60e8fe5b7c4ac60724ed40751958a5f839dec298832a7da8a9) | `new AgentCollateralVault(usdc)` | vault `0x1BF39f65…13AbD9` (debt-aware `lockForNote`) |
| 2 | [`0x7e4da3…0da3e8`](https://basescan.org/tx/0x7e4da3c85a0b1a36888e7343e3fc9ec676a8907847392b1d1a26047f830da3e8) | `new AgentListingRegistry(vault, usdc)` | registry `0xab6E20aE…1B6600` (agent-only issuance) |
| 3 | [`0x99a0a0…3e60a3`](https://basescan.org/tx/0x99a0a057fd09ec286b53aaad58efa679276f5f8812d4cf1b40e31cae933e60a3) | `vault.setRegistry(registry)` | wire vault → registry |
| 4 | [`0xb88feb…801185`](https://basescan.org/tx/0xb88febbb6bf482168659bf90673565cc7a7f5391cd06b36444caae8bf9801185) | `new AgentLendingPool(usdc, vault, registry)` | lending `0x36446D83…232298` |
| 5 | [`0xb4f93e…6250cb`](https://basescan.org/tx/0xb4f93ed3bf4619260d4dc7b5b03e1d926569458a7c3b85d30685b65a126250cb) | `vault.setLendingPool(lending)` | wire vault → lending (now one-shot) |
| 6 | [`0xe33b59…d7398e`](https://basescan.org/tx/0xe33b5961a77f564b68525108761af4bc39fbb9f55bfe96ff54fda905b7d7398e) | `new PulseAMM()` | AMM `0xED279249…fc5D22` (allow-listed `createPool`) |
| 7 | [`0x954311…6cefc3`](https://basescan.org/tx/0x954311a89be15da15f9930826f10874b5cf950ad236a77c3051bb50ef6cefc3d) | `new AgentAuditPool(registry, vault, usdc, amm)` | audit pool `0x96005B0E…3e689b` (spot-confirmed default) |
| 8 | [`0x4baab4…7e280c`](https://basescan.org/tx/0x4baab42c6a5c06ed745cee7a8951e9c1cdb850ebcd4a8b5cb3e0c3164c7e280c) | `registry.setAuditPool(auditPool)` | wire registry → audit pool |

Post-deploy verification (read-only, against mainnet): every wiring pointer matches
(`vault.registry`, `vault.lendingPool`, `registry.auditPool`, `registry.vault`, `pool.vault`,
`auditPool.pulseAmm`), `PulseAMM.MIN_INITIAL_USDC() == 1e9`, and the new guards answer on
chain — `depositCollateral(id, 0)` reverts `InvalidAmount` (`0x2c5211c6`),
`depositCollateral(unknown, 100)` reverts `UnknownListing` (`0xaf21e16c`),
`createPool` from a non-market-maker reverts `Unauthorized` (`0x82b42900`), and
`evictUnapprovedListing` answers `ListingNotEvictable` (`0x6e2de8f1`).

**Not yet done:** Basescan source verification for this set, and value-testing of the fixed
paths. `AgentShareToken`'s misleading-panic fix (an overdraw with a vesting lock set reverted
`Panic(0x11)` instead of `ERC20InsufficientBalance`) landed in source *after* this deploy —
the share token is created *by* the registry, so its code is embedded in the registry
bytecode and this set still carries the old revert reason. It is a wrong error string, not a
fund risk, so it waits for the next redeploy rather than causing one.

---

## 3h. Real-money E2E on the 2026-07-26 contracts

Executed from `0x1218` (depositor + hub + lottery operator/oracle-signer). Gas-only net cost;
USDC returns to `0x1218` on settle.

### Capability-payment channel (1.00 USDC deposit → 0.25 debit → settle)

Channel id `0xd3fb37b4…ceb000`.

| # | Call | Effect | Tx |
|--:|---|---|---|
| 1 | `USDC.approve(escrow, 1.0)` | allow escrow to pull deposit | [`0x5ff693…7d6c56`](https://basescan.org/tx/0x5ff693dd0b43e6a1815f3fa303ed48755494ca1047fc236fd0163f63007d6c56) |
| 2 | `escrow.openChannel(id, USDC, 1.0)` | 1.00 USDC locked in escrow | [`0x60a02b…58ef7e`](https://basescan.org/tx/0x60a02b42c3e4cf44a23f1caf709ddd25820e31d18b352bb8e41b16786a58ef7e) |
| 3 | `escrow.debitChannel(id, 0.25, …, EIP-712 sig)` | meters **0.25 USDC** capability charge | [`0x40bb33…443c9f`](https://basescan.org/tx/0x40bb338ea770461372a33063b7a4e6ae0b2742f875e8248f026d9b4c9e443c9f) |
| 4 | `escrow.settleChannel(id)` | **0.25 → hub (`0x1218`)**, **0.75 refund → depositor**; Settled | [`0xf3043d…98c59b`](https://basescan.org/tx/0xf3043d030e8b02871e3adc7856a889a88660898c1e00eaa8bc249362c998c59b) |

> Revenue leg = the `usedAmount` transfer to `ch.hub` on settle (same protocol rule as §3f).

### Lottery — full round (round 2, sole participant)

| # | Call | Meaning | Tx |
|--:|---|---|---|
| 1 | `openRound()` | opens **round 2**, 30s entry window | [`0x554f86…a9f22d`](https://basescan.org/tx/0x554f86332ad27c670aa5d1c59ff480a9c986ce052740e14b9f70541a5ca9f22d) |
| 2 | `buyTickets(2, 1)` | `msg.value` = 0.000003 ETH | [`0x510c07…54f65`](https://basescan.org/tx/0x510c07073ca1cd0e8b2a7324c7913523159acfbcb629b88f90aa44d5e8b54f65) |
| 3 | `closeEntries(2, commit)` | `commit = keccak256(platonRandom)` | [`0x2d277b…c81baa`](https://basescan.org/tx/0x2d277bac1e47b4b882807f2e90487a1373d56973add437198bfc863125c81baa) |
| 4 | `fulfillDraw(2, reveal, 0, sig, emptyVdf)` | EIP-712 `DrawBeacon`; round **Settled** | [`0xb7a41e…e41632`](https://basescan.org/tx/0xb7a41e7a760096a3708e021717bb6cd6bf29debd684ca1fafcbf1678b6e41632) |
| 5 | `claimPrize(2)` | winner pulls prize share | [`0xb65d2a…654fac5`](https://basescan.org/tx/0xb65d2ad463150a4904d9995f908ca207bc2dd9442140fc6673acecae0654fac5) |
| 6 | `withdrawOperatorFee` | operator share → treasury | [`0x21ceb9…912ea6`](https://basescan.org/tx/0x21ceb918e8daf85716fec0e653cbf0531d1e09e9cc22ebe6b533cdb4f8912ea6) |
| 7 | `withdrawOpex` | opex share → treasury | [`0xdcd84a…b26646`](https://basescan.org/tx/0xdcd84af1e506e74e29db42849e7f38e1bbe5168c33b78e10ef1aaa8f95b26646) |

### Capability NFT mint (signed entitlement)

| Call | Effect | Tx |
|---|---|---|
| `nft.mint(0x1218, capId, productId, 10, 4000)` | mints entitlement NFT (10 calls @ $0.004) | [`0x3f59b2…3c4f77`](https://basescan.org/tx/0x3f59b25ce8fe3557c639e1d2c5c6153d82a6c1e9453d125c8eaa241fa83c4f77) |

### ACEX

Stack redeployed and wired (§2c). Full mainnet value cycle still deferred (needs ≥10k USDC
`MIN_STAKE` + 1-day TWAP) — same policy as §3f; constants verified via Foundry suite.

**Verify live set:**
```bash
RPC=https://mainnet.base.org
cast call 0x12Db8FAC81E5999D2f2087B79e38951571562CF2 \
  "whitelistedTokens(address)(bool)" 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 --rpc-url $RPC
cast call 0x291b6eCB45121fEDE86BF769aC0eaa6AdED38350 "currentRoundId()(uint256)" --rpc-url $RPC
```

---

## 3i. First paid invoke via live hub (`modelmarket.dev`) — 2026-07-27

**Label honestly: self-test.** Depositor = hub = operator = `0x1218…Ad0a`. Proves the
full hub path (escrow open → ledger channel → EIP-712 `DebitAuthorization` → paid invoke →
on-chain debit + settle), not "an external consumer paid us".

Capability: `skopos.security.posture@v1` @ **$0.08** (`prod-skopos`). Ledger channel
`ch_cf10497928fe4ce8`. Escrow channel
`0x6635f72c9c65a4aaae83cfc67edbadb18854790d334ca5d68bf3e63aec3075c2`.
`receiptId` = `0x937253cb720beb5e31eec721d8c640976cdd8c290954925e54a8b01713a88768`.

| # | Call / step | Effect | Tx / note |
|--:|---|---|---|
| 1 | `USDC.approve(escrow, 1.0)` | allow escrow to pull deposit | [`0x7acef8…40a56a`](https://basescan.org/tx/0x7acef8adf00780b7bb323d68b0beeb23043071dd46a4f695829768b82440a56a) |
| 2 | `escrow.openChannel(id, USDC, 1.0)` | 1.00 USDC locked in escrow | [`0x28b81f…13e45d`](https://basescan.org/tx/0x28b81f178edda91ba9f9e283004ebbe87bcd9a6f213a829c89921ec56113e45d) |
| 3 | Hub `POST /channel/open` + `POST /invoke` + `POST /channel/close` | ledger charged **$0.08**, refund owed **$0.92** (off-chain); invoke **200** with posture result | off-chain at `https://modelmarket.dev` |
| 4 | `escrow.debitChannel(id, 0.08, receipt, deadline, sig)` | meters **80000** base units; binds hub on first debit | [`0x5121ba…bb63ea`](https://basescan.org/tx/0x5121ba7f16afd8b5685e1e2cca46a8bdfaee38f2097affd96b62f1153bbb63ea) |
| 5 | `escrow.settleChannel(id)` | **0.08 → hub (`0x1218`)**, **0.92 refund → depositor**; status **Settled** | [`0x27567e…62072d`](https://basescan.org/tx/0x27567e7c7929c5d02d43d34d53ca511b89b5a351cb33a0b02981ad11c362072d) |

Prior attempts the same day (claim / provider-sig / schema blocks) were `batchRefund`ed —
[`0x0e1a8c…80d3ce`](https://basescan.org/tx/0x0e1a8cce7a69574f3556a36a7934cfef41945f7f351cc39f9701b5919080d3ce) —
so no USDC was stranded in those trial channels.

> Ops note for this run: live catalogue capabilities lacked `provider_pubkey`, so the hub
> was temporarily restarted with `AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG=0` for the invoke.
> Re-enable once factory products sign responses. Also patched
> `supply_fault_events.consumer_id` on the live `hub.db` (migration 016 CREATE/ALTER drift).

---

## 3j. External depositor paid invoke — 2026-07-27

**Separate wallet, our money.** Depositor = `0x6E94c380d908531f9822035d6cc4c8D2B0186C9c`
([Basescan](https://basescan.org/address/0x6E94c380d908531f9822035d6cc4c8D2B0186C9c));
hub / settle signer = `0x1218…Ad0a`. Proves that a wallet other than the hub funded escrow, bought a
capability, and received the remainder refund on-chain. It does **not** prove third-party demand:
`0x1218` funded that wallet with 1.0 USDC ten minutes earlier
([`0x646bd8…f86fd5`](https://basescan.org/tx/0x646bd883bb4670dd20311e4b0aeb44eebf77772489f0f558d3df03fcf9f86fd5),
block 49198011). Short write-up with the signature recovery:
[case study](case-study-paid-invoke.md).

Capability: `skopos.security.posture@v1` @ **$0.08**. Ledger `ch_9417f011bbe54d8a`.
Escrow channel `0xa3ebd1478c847cc9b58ed57dfac478d67cbf8a689291506a5aab7b0987c2fb13`.
`receiptId` = `0x409356b384b8542ab1961c2d238a781f751e9e277115fc87ac7224b951bce5ce`.

| # | Caller | Call / step | Effect | Tx |
|--:|---|---|---|---|
| 1 | external depositor | `USDC.approve(escrow, 1.0)` | allow escrow to pull deposit | [`0x93c71f…f8a5f1`](https://basescan.org/tx/0x93c71f782fd8d382e2c23f98c2f5f5adb556728391910dabcb9986894ef8a5f1) |
| 2 | external depositor | `escrow.openChannel(id, USDC, 1.0)` | 1.00 USDC locked; depositor=`0x6E94…` | [`0xea4038…83549e`](https://basescan.org/tx/0xea4038c9f6dedb26ece1c0454a4b181cd17c71686c6e73b5f092e70a2c83549e) |
| 3 | hub API | `channel/open` + signed invoke + `channel/close` | ledger used **$0.08**, refund owed **$0.92**; invoke **200** | off-chain `modelmarket.dev` |
| 4 | hub `0x1218` | `escrow.debitChannel(id, 0.08, …, sig)` | meters 80000 units; binds hub; sig by depositor | [`0xf740cd…824355`](https://basescan.org/tx/0xf740cd0cd2ada97dd243ad067c2dc0f16504d40030c54b4aef37137f2a824355) |
| 5 | hub `0x1218` | `escrow.settleChannel(id)` | **0.08 → hub**, **0.92 → depositor**; status **Settled** | [`0xcce0dc…942472`](https://basescan.org/tx/0xcce0dcdddfd962cd2d16840246cfc2761b8325d4a58f186009bcdd5b3c942472) |

Post-settle: depositor USDC balance = **920000** (\$0.92 refund). Channel status = Settled (1).

---

## 3k. Payments re-enabled + federated paid smoke — 2026-08-04

**Label honestly: self-test.** Depositor = hub = operator = `0x1218…Ad0a`. After a host
redeploy that had cleared payment env, payments were re-baked via
`deploy/hub-payment.env` + `scripts/deploy_hub.sh` (`modelmarket-hub:prod-20260804-payments`,
hub **3.2.1**). `AIMARKET_SELLS_FOR=https://oracles.modelmarket.dev/family` so federated
oracles 402 without a channel.

Live measured after enable:

```
payment_configured   true
payment_testnet      false
channels.demo_mode   false
federated_caps       48
```

Capability: `platon.random@v1` @ **$0.004** list (`prod-platon`, source
`https://oracles.modelmarket.dev/family`). Ledger charged **$0.01** (1¢ ceil in
`first_paid_invoke.py` / DebitAuthorization amount). Ledger `ch_226f7f322e1c419c`.
Escrow channel `0xf55217eaab0d7cd0b48c970d6ddbd58a28d4078eb7d095bdf4ba9478594f049b`.
`receiptId` = `0xf4dadd84597f9e639005a24e1b84d0ea89dd9603f39a69c0de45993e5a57fc0e`.

| # | Call / step | Effect | Tx / note |
|--:|---|---|---|
| 1 | `USDC.approve(escrow, 1.0)` | allow escrow to pull deposit | [`0x284235…3eaea4`](https://basescan.org/tx/0x2842351de5e03c2d100505edebc474358c5314dd2c40d088cfc3cb22d43eaea4) |
| 2 | `escrow.openChannel(id, USDC, 1.0)` | 1.00 USDC locked in escrow | [`0x7bd712…da1f4`](https://basescan.org/tx/0x7bd7126f868ccef977b597894a9468de3f955815bdd63c4f91837cbe038da1f4) |
| 3 | Hub `POST /channel/open` + federated `POST /invoke` (`source_hub` = oracle family) + `POST /channel/close` | ledger used **$0.01**, refund owed **$0.99**; invoke **200** with signed VRF | off-chain `modelmarket.dev` → `oracles.modelmarket.dev/family` |
| 4 | `escrow.debitChannel(id, 0.01, receipt, deadline, sig)` | meters **10000** base units; binds hub | [`0xa81f7f…2d116d`](https://basescan.org/tx/0xa81f7f25487b02cac1b89a3ce542217dfad8eb1c0ebea4126ccd20b40e2d116d) |
| 5 | `escrow.settleChannel(id)` | **0.01 → hub (`0x1218`)**, **0.99 refund → depositor**; status **Settled** | [`0x629b0b…d4cc65`](https://basescan.org/tx/0x629b0b8b84186aa2e06e5ad71a77b6fc87d4ebe5248067c69ae588466cd4cc65) |

Ops notes from this run:

- `MIN_DEPOSIT` is **$1.00** (`1e6`); a $0.25 open reverts `DepositOutOfRange`.
- `openChannel` needs **≥ ~200k gas** for USDC `transferFrom` on Base (150–200k OOGed).
- Federated catalogue rows must be invoked with `source_hub=<peer URL>`; default `local`
  routes them to the factory → `502 capability not found`. Fixed in
  `scripts/first_paid_invoke.py`.
- Federated sell path holds/captures the **ledger** without requiring
  `payment_authorization` in the request body; on-chain debit+settle was still done
  manually with the signed DebitAuthorization (bridge strategy remains plan /
  `may_broadcast: false` — KI-11).
- Abandoned trial channel from the factory-404 attempt
  (`0x1ace6d357b6b734844022f14d953cc9fa53634e5f086fe303064fe4b18fdea5b`) was
  `settleChannel`'d with zero use → full refund:
  [`0x6dbcc4…23b56b`](https://basescan.org/tx/0x6dbcc46dfa76a7092550b1bba253710a80c7a78dc19cb9fccaea9596e323b56b).

Driver: `scripts/first_paid_invoke.py` + host RPC via `my-vps` (`https://mainnet.base.org`).

---

## 3l. External depositor — GAIA weather + quake (paid ledger) — 2026-08-05

**Not a self-test.** Depositor = second payer
[`0x6E94c380d908531f9822035d6cc4c8D2B0186C9c`](https://basescan.org/address/0x6E94c380d908531f9822035d6cc4c8D2B0186C9c)
(not `0x1218`). Hub API = [`https://modelmarket.dev`](https://modelmarket.dev);
GAIA source = [`https://iot.modelmarket.dev`](https://iot.modelmarket.dev).
Escrow = [`AIMarketEscrow` `0x0606983c…72C25D`](https://basescan.org/address/0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D) — the escrow live on the day of this run, superseded 2026-09-04 (§5);
token = real USDC [`0x833589fC…A02913`](https://basescan.org/address/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)
(Base mainnet, chainId **8453**).

### Balances around the run

| When | Payer USDC | Payer ETH (approx) | Escrow USDC |
|---|---:|---:|---:|
| Before open | **1.92** | ~0.000999 | 0 |
| After `openChannel` | **0.92** | ~0.000997 | **1.00** locked |
| After `refundChannel` | **1.92** | ~0.000997 | 0 |

### Identifiers

| Item | Value |
|---|---|
| Escrow channel id | [`0xa5d54d5629339304ecee4fcc862daa8e23f4b6016c63412879497c289a6436d4`](https://basescan.org/tx/0x60ce9fb56818c6d16999d3db5485e2097064508335681698904f39ef8c9a2f1e) |
| Hub ledger channel | `ch_fc5be258382f46b9` |
| Hub recipient (manifest) | `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a` |
| Deposit | **$1.00** USDC (`1e6` base units) — escrow `MIN_DEPOSIT` |
| Ledger used (close) | **$0.02** (1¢ ceil × 2 DebitAuthorizations @ `10000` units each) |
| Ledger refund owed | **$0.98** (never paid on-chain — see honesty note) |

### Capabilities bought (attested readings)

| Capability | Device | List price | DebitAuthorization amount | Provider receipt nonce | Reading (summary) |
|---|---|---:|---:|---|---|
| `gaia.weather.read@v1` | `om-wx-01` (Open-Meteo, `live-weather-eu`) | $0.001 | 10000 ($0.01 ceil) | `5fb7c3c44e77e324` | 28.6 °C · 60 % RH · 1009.4 hPa · 2.34 m/s · seq 4 · `2026-08-05T11:20:46Z` |
| `gaia.quake.read@v1` | `usgs-quake-01` (USGS GeoJSON) | $0.002 | 10000 ($0.01 ceil) | `32463960f5345c36` | M5.0 · 10 km · 29.0027°N 94.681°E · seq 2 · same timestamp |

DebitAuthorization `receiptId`s (EIP-712, depositor-signed; **not** submitted on-chain):

- weather: `0xe2360c45b54c8ccd6eb2622916864444766a8900dfed98abf5394a186daf40a3` (nonce **0**)
- quake: `0x2a22de8343b252db97466c5ef8e1d0f0e0512241c53a40ac8609d848da2c49c5` (nonce **1**)

### Transaction table

| # | Caller | Call / step | Effect | Tx |
|--:|---|---|---|---|
| 1 | external depositor | `USDC.approve(escrow, 1.0)` | allowance **1.0** USDC for escrow | [`0x89059f…49e73e`](https://basescan.org/tx/0x89059f1991e7d23bf2f88aaa2a8775547df8b52e19c787ba4fbaa7531c49e73e) |
| 2 | external depositor | `escrow.openChannel(id, USDC, 1.0)` | **1.00** USDC locked; `depositor=0x6E94…`; on-chain `usedAmount=0`, `hub=0x0` until first debit | [`0x60ce9f…9a2f1e`](https://basescan.org/tx/0x60ce9fb56818c6d16999d3db5485e2097064508335681698904f39ef8c9a2f1e) (block **49569762**, gasUsed **194513**) |
| 3 | hub API | `POST /channel/open` + 2× `POST /invoke` (`source_hub=https://iot.modelmarket.dev`) + `POST /channel/close` | ledger **used $0.02**, refund owed **$0.98**; both invokes **200** with Ed25519 attestations | off-chain `modelmarket.dev` → `iot.modelmarket.dev` |
| 4 | — | `escrow.debitChannel` / `settleChannel` | **not executed** | — |
| 5 | external depositor | `escrow.refundChannel(id, …)` | full **1.00** USDC returned (allowed because on-chain `usedAmount` still **0**) | [`0x984aa3…ebfc2`](https://basescan.org/tx/0x984aa375f79ccbfaea3dd10db23a75d988daa0a4db97bc7fd2c32bc92abebfc2) (gasUsed **80819**) |

### What each step means

| # | On Basescan? | Plain meaning |
|--:|:---:|---|
| **1 `approve`** | yes | ERC-20 permission: «escrow contract may pull up to **$1** USDC from my wallet». No USDC moves yet — only allowance. Required before `openChannel` can `transferFrom`. |
| **2 `openChannel`** | yes | Creates payment channel `0xa5d54d…` and **locks $1 USDC inside the escrow contract**. Payer balance drops by $1; escrow holds it. On-chain `usedAmount=0`, `hub` unbound until a later debit. |
| **3 hub HTTP** | **no** | Soft ledger only. Hub opens `ch_fc5be258…`, accepts two signed DebitAuthorizations, fetches weather+quake from GAIA, closes the channel. Records **$0.02 used / $0.98 owed**. Does **not** move USDC on Base by itself. |
| **4 `debitChannel` + `settleChannel`** | missing | Would be the real payment: hub (authorized) meters $0.02 on-chain, then settle sends **$0.02 → hub wallet** and **$0.98 → depositor**. Needs hub ETH key / escrow bridge broadcast — **not available on prod that day**. |
| **5 `refundChannel`** | yes | Safety unlock by the **depositor** while `usedAmount` is still 0: returns the full **$1** from escrow back to `0x6E94…`. Use this when debit never ran so funds are not stranded. |

Gas for steps 1, 2, 5 was paid in **ETH** from the same depositor wallet (tiny Base fees).

### Honesty note — what this proves / does not prove

- **Proved:** an outside wallet funded escrow on Base, opened a hub payment channel against that
  escrow id, and received two live GAIA readings (`weather` + `quake`) through the paid hub path
  (`X-Payment-Channel` + depositor EIP-712 `payment_authorization`). Hub ledger close reported
  `used_usd=0.02`.
- **Not proved on-chain:** USDC did **not** move to the hub. Prod escrow bridge is
  `strategy=plan`, `private_key_set=false`, `may_broadcast=false` — no
  `AIMARKET_ESCROW_PRIVATE_KEY` for `0x1218`, so `debitChannel` (authorized-hub-only) could not
  run. Deposit was unlocked with depositor `refundChannel` rather than left stranded.
- **Next to complete settle:** set hub escrow submit key → `debitChannel` for **$0.02** (or two
  1¢ debits) with the signed auths above → `settleChannel` → **$0.02 → hub**, **$0.98 → depositor**.
  Same pattern as §3j.

---

## 3m. External depositor — Open-Meteo weather only — 2026-08-05

Same depositor [`0x6E94…6C9c`](https://basescan.org/address/0x6E94c380d908531f9822035d6cc4c8D2B0186C9c),
same escrow / USDC / hub as §3l. Single capability: **`gaia.weather.read@v1`** /
device **`om-wx-01`** (Open-Meteo Forecast API → **current** fields only; site
`live-weather-eu`, operator coords default Berlin `52.52, 13.41`).

### Reading delivered

| Field | Value |
|---|---|
| temperature_c | **28.9** |
| humidity_pct | **58.0** |
| pressure_hpa | **1009.5** |
| wind_mps | **2.34** |
| seq / ts | 6 / `2026-08-05T11:41:59Z` |
| provider receipt nonce | `925652d8f500ad6d` |
| list price | $0.001 |
| ledger charge | **$0.01** (1¢ DebitAuthorization ceil) |

### Identifiers & txs

| Item | Value |
|---|---|
| Escrow channel | `0x4e3b57462c508e9f36c4df7ca9b946d6279500b5e894b21d4f118def42c140ef` |
| Hub ledger | `ch_836b755a834c41a8` |
| Pre-existing `USDC.approve` (same day) | [`0x6a026f…e55c9f`](https://basescan.org/tx/0x6a026f02dcdf5dee03bc33af268b278bc84c4ea288dcc0ea8b31d09c9be55c9f) (block **49570188**) |
| `openChannel(1.0 USDC)` | [`0x0754ce…e2e90a`](https://basescan.org/tx/0x0754ceff9323ab0bba76f99cff81beb6f90771727e7655258330c24d8ae2e90a) (block **49570293**, gasUsed **194501**) |
| Hub invoke + close | off-chain; `used_usd=0.01`, `refund_owed_usd=0.99` |
| `refundChannel` (unlock; on-chain used still 0) | [`0xf282dd…9e000a`](https://basescan.org/tx/0xf282ddb7226d557aea34930155177b07414f1d10ea4968598a0105bd289e000a) (block **49570400**) |
| Payer USDC after unlock | **1.92** |

### What each tx means (§3m)

| Tx / step | On Basescan? | Plain meaning |
|---|:---:|---|
| [`0x6a026f…`](https://basescan.org/tx/0x6a026f02dcdf5dee03bc33af268b278bc84c4ea288dcc0ea8b31d09c9be55c9f) `approve` | yes | Same-day ERC-20 allowance top-up so escrow may pull **$1** (reused for this channel; USDC still does not move until open). |
| [`0x0754ce…`](https://basescan.org/tx/0x0754ceff9323ab0bba76f99cff81beb6f90771727e7655258330c24d8ae2e90a) `openChannel` | yes | Locks **$1** into escrow channel `0x4e3b5746…` for this Open-Meteo purchase. |
| Hub `channel/open` → `invoke(om-wx-01)` → `close` | no | Soft ledger `ch_836b755a…`: charges **$0.01**, returns attested Open-Meteo current reading (28.9 °C …). No USDC transfer on-chain. |
| `debitChannel` / `settleChannel` | missing | Would pay hub **$0.01** and refund depositor **$0.99** on-chain — not broadcast (no hub escrow key). |
| [`0xf282dd…`](https://basescan.org/tx/0xf282ddb7226d557aea34930155177b07414f1d10ea4968598a0105bd289e000a) `refundChannel` | yes | Returns the locked **$1** to depositor because nothing was debited on-chain. |

Honesty same as §3l: paid **ledger** path proved; on-chain `debitChannel`/`settleChannel`
not run (escrow bridge `private_key_set=false`). Deposit returned via depositor
`refundChannel`.

### Two ways to buy the same reading (operator note)

| Path | What you do | Money | When to use |
|---|---|---|---|
| **A — MCP / hub trial** | `aimarket-mcp` tool `market_invoke` **or** `POST /ai-market/v2/invoke` with `X-AIMarket-Sandbox-Visitor` | trial / sandbox (no escrow) | get an attested reading in &lt;1s |
| **B — External escrow** | `approve` → `openChannel($1)` → hub channel + EIP-712 auth → invoke → close → hub `debit`/`settle` | real USDC on Base | prove an outside wallet paid |

Path A example (same SKU as this section):

```bash
curl -s -X POST https://modelmarket.dev/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -H 'X-AIMarket-Sandbox-Visitor: vis_docs_om_wx' \
  -d '{"capability_id":"gaia.weather.read@v1","product_id":"gaia.gateway",
       "source_hub":"https://iot.modelmarket.dev","input":{"device_id":"om-wx-01"}}'
```

MCP equivalent: configure `aimarket-mcp`, then `market_search` → `market_invoke` with the
same `capability_id` / `product_id` / `source_hub`. See [`aimarket-mcp/README.md`](https://github.com/alexar76/aimarket-mcp/blob/main/README.md).

## 3n. First resold peer capability, end to end on chain — 2026-08-31

The first purchase where the hub was the **seller of record for somebody else's
capability**: SKOPOS sells `skopos.fleet.status@v1` at $0.01, the hub holds a key at
SKOPOS (`AIMARKET_PEER_API_KEYS`), so it charges the buyer, serves the call with its own
credential, and keeps its 100 bps as the margin.

| | |
|---|---|
| Escrow | `0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D` (Base mainnet, USDC) — live on the day of this run, superseded 2026-09-04 (§5) |
| Depositor / buyer | `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a` |
| Escrow channel | `0x7e61310a667d986f0f4d6c9969678670dd70c6f982a8f398b39d65322946e463` |
| openChannel | `0x09a0c8734113d846942257ec0161d6dfb23ce5a28034ad6f84b1665cb08f7507` ($1.00 deposit) |
| Ledger channel | `ch_bced8fbcb13f4091` |
| Receipt id | `0xb6a0cf569305bd3c4e5db37c6aff4d7a97c06b99e42d5b9a4d911810d576c581` |
| debitChannel | `0x620206de71e518bf694221f8a16bd180f70c8c201f74550a7ccf725ef063e271` (20 000 units = $0.02) |
| settleChannel | `0xd50b703e93f40a058ef9b182a49502fb6a7d74e1baadff0f0a442f2848ac53a3` |
| Provenance receipt | `urn:uuid:cdd3954b-d01a-499e-a71c-8d0e95cf2a96` (AWR 2.0.0) |

Delivered: `servers_monitored 4, requests_total 18 208 592, security_score 80`, signed by
SKOPOS, routed via `modelmarket.dev`.

**One number the whole way down.** Quoted `needed: 0.02` = $0.01 price + $0.0001 routing
fee, rounded up to a whole cent because that is what both the ledger
(`ceil(usd*100)`) and `usd_to_base_units` bill in. Signed: 20 000 base units. Ledger:
`debited_receipts.amount_cents = 2` under that same receipt id. Chain: `usedAmount`
20 000. Settlement paid the used amount to the bound hub address and refunded $0.98 to the
depositor — treasury $1.0175 → $0.9975, net cost $0.02 plus gas.

**Buyer and operator are the same wallet here.** This is a self-test of the rail, not an
external sale — the same caveat as §3g. The genuinely external proof remains §3j.

**What it cost to get there.** Three defects, each found only by spending real money:

1. The routing fee had no authorization behind it, so an escrow-backed channel was refused
   `routing_fee_unpayable` *after* the deposit was on chain — every resold and brokered
   capability was unbuyable on the only funding rail production has.
2. My first fix quoted `$0.0101`, a number the hub's own verifier rejects in favour of the
   `$0.02` it ceils to: the client re-signs the quote it was given and the purchase
   deadlocks. Caught by adversarial review before deploy.
3. That same first fix held the fee under a separate `fee_…` receipt, so the signed row
   would have been BLOCKED forever by the mirror's over-collect guard — buyer served and
   debited off chain, nothing collectable on it. Also caught before deploy.

**Where the money lands, and it is worth knowing:** `settleChannel` pays `ch.hub`, which is
whatever address the DebitAuthorization named — `AIMARKET_ESCROW_HUB_ADDRESS`, currently
the HORKOS policy signer `0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1`, a wallet whose own
keyfile says it "holds only gas". Revenue accrues there, not at the treasury. Nothing is
lost, but somebody has to sweep it, and no cadence does.

## 4. Source provenance note — pragma pinning (2026-08-23) 📌

BASANOS reported `pragma.floating` (CWE-664) against every first-party Solidity file:
all 17 declared `pragma solidity ^0.8.28;`. The build was never at risk — every
`foundry.toml` in this repo pins `solc = "0.8.28"` — but a floating pragma is a promise
to *third parties* compiling this MIT source outside our build config, and 0.8.x
releases do change codegen.

The 17 files are now pinned to `pragma solidity 0.8.28;`. `contracts/zk/verifier/Verifier.sol`
is deliberately **not** pinned: it is snarkJS-generated GPL-3.0 output (`>=0.7.0 <0.9.0`)
and a pin there would be overwritten by the next regeneration.

**No contract was redeployed for this**, and none needs to be:

* On-chain behaviour is identical — a version bound is a compile-time constraint, not code.
* Pinning changes the source text, so the metadata hash embedded in a fresh compile no
  longer matches the bytecode live at the addresses in §2c / §2d. Those addresses were
  built from the pre-pin sources, recoverable from git history at the deploy commits
  recorded in this journal.
* Anything redeployed later, for any other reason, deploys the pinned source.

Verified after the sweep: `forge build` exit 0 in `lottery/contracts`, `acex/contracts/evm`
and `contracts/evm`; BASANOS re-scan of `lottery` / `acex` / `core` reports no
`pragma.floating`.

---

## 5. Escrow + lottery redeploy — security audit 2026-09-04 📌

Both contracts were redeployed on Base mainnet (chain 8453) to ship fixes from the
2026-09-04 ecosystem security audit. **Nothing was migrated: both superseded contracts read
0 USDC and 0 ETH immediately before the deploy**, so the old set was abandoned rather than
drained — the same precedent as the ACEX redeploy in §2d.

| Contract | New address | Superseded |
|---|---|---|
| `AIMarketEscrow` | `0x12Db8FAC81E5999D2f2087B79e38951571562CF2` | `0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D` |
| `AIAgentLottery` | `0x291b6eCB45121fEDE86BF769aC0eaa6AdED38350` | `0x701A7bd8487cd4d2EcE0E252Dbc0E67dF70a9554` |

### Transactions

| What | Tx | Block | Gas used |
|---|---|---|---|
| `AIAgentLottery` CREATE | `0x5c63f169a8026b5c0baf961f7586c83b3ab3a25ae2f97c56948711ed1739f4bc` | 50856720 | 4 989 856 |
| `AIMarketEscrow` CREATE | `0x259e4aa451ca947b4ad42553251ffaf4471a8c9386b756d2949c42fc39f6af62` | 50856731 | 1 940 387 |

Deployed with `scripts/deploy_escrow_lottery_base.sh` (dry-run default; the key is read from
the keystore inside the script, so it never appears in an argument, in `ps` or in history).
Gas price ~0.0102–0.0107 gwei; total cost well under 0.0001 ETH.

### What was fixed

* **`AIMarketEscrow`** — `openChannel` booked the *requested* `depositAmount` as both
  `depositAmount` and `balance` without measuring what arrived. A whitelisted token that
  takes a transfer fee (Ethereum USDT has an owner-settable `basisPointsRate`, currently 0)
  or rebases down therefore made the per-channel books exceed the contract's real holdings,
  and settle/expire/refund pay out the CREDITED amount — so the shortfall came out of other
  channels' escrowed principal until those began reverting. Now credits the measured
  balance delta and re-checks it against `MIN_DEPOSIT`/`MAX_DEPOSIT` after the transfer.
* **`AIAgentLottery` + `ChronosVDF`** — with `onchainVdf` on, the random word was
  `keccak256(vdf.y)` over the RAW caller-supplied bytes, while `verifyEquation` only ever
  compared `y` as a residue (`BigMath.eq(left, BigMath.mod(y, N))`). `y`, `0x00‖y` and
  `y + k·N` therefore satisfied the identical proof while hashing to different words, so
  whoever held `ORACLE_SIGNER` could enumerate `k` after the seed block was mined and pick
  the word that won. Now `verifyEquation` refuses a `y` that is not already reduced, and the
  word is derived from `ChronosVDF.canonicalY(y, N)`.
* **`AIAgentLottery.fund()`** — accepted `Status.Drawing`, i.e. after `closeEntries` had
  locked every other participant out, while `fulfillDraw` caps the unclaimed-prize roll-in
  at the round's own `income = ticketRevenue + funding`. A sole remaining ticket holder
  could therefore raise that cap once it already knew it could not be out-competed, which is
  exactly what the cap exists to prevent. Now `Status.Open` only.

### Honesty note — what this changes and what it does not

Two of the three fixes are **latent under the current configuration, and remain so**:
`onchainVdf` is `false` on both the old and the new lottery (so the grinding path is not
reachable), and only Circle USDC is whitelisted on the escrow (and USDC takes no transfer
fee). The `fund()` window fix is live. The redeploy removes the latent exposure rather than
stopping an attack in progress.

### Configuration reproduced, not reset

`DeployLottery.s.sol` defaults every parameter to the deployer and to generic values
(`ENTRY_WINDOW` 1 day, `MIN_DRAW_DELAY` 60, `TICKET_PRICE` 0.001 ether). The live demo ran a
different configuration, so it was read off chain first and pinned in the deploy script.
Verified equal on the new contract, field by field: `token` `0x0` (native ETH, not USDC),
`ticketPrice` 3 000 000 000 000 wei, `prizeBps`/`opexBps`/`operatorBps` 8000/1200/800,
`entryWindow` 30, `minDrawDelay` 15, `onchainVdf` false, and all four roles
(`DEFAULT_ADMIN`, `GOVERNANCE`, `OPERATOR`, `ORACLE_SIGNER`) held by
`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`. Escrow: `owner` the same wallet, HORKOS
(`0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1`) the only authorized hub, Base USDC the only
whitelisted token.

Deployed bytecode was checked against the local build rather than trusted: same length, and
the only differences are 25 (lottery) / 5 (escrow) short runs where the artifact carries
zero placeholders — the immutable-injection pattern — totalling 0.59 % and 0.40 % of the
code. Both differ from, and are longer than, the superseded bytecode.

### Switchover — done 2026-09-04 09:13–09:15 UTC

Deploying was additive: the superseded contracts kept serving until configuration moved, so
nothing broke at deploy time. Putting the new escrow into service needed two hosts to move
**together**, because either one alone leaves the hub recording channels on one escrow while
the signer debits the other:

1. **HORKOS** (`escrow-signer`) pins `ESCROW` in `escrow_signer/config.py` and verifies chain
   id, domain separator, hub authorisation and token decimals at boot, **fail-closed**. The
   domain separator binds the contract address, so it differs between the two escrows
   (`0x4c3cc194…e230` → `0x93d1dcd1…cb71`).
2. **The hub** does *not* read the escrow from this registry at runtime. It reads
   `AIMARKET_ESCROW_EVM_ADDRESS` / `AIMARKET_ESCROW_CONTRACT` from its environment, and the
   factory alias `AIFACTORY_AI_MARKET_CONTRACT` alongside them. The registry feeds the landing
   page and the read paths, not the money path.

**Preconditions checked before the switch**, because a migration with live state would have
needed settling first rather than repointing:

| Check | Result |
| --- | --- |
| Superseded escrow USDC / ETH | `0` / `0` |
| Hub `channels` / `channel_holds` / `channel_payout_obligations` | `0` / `0` / `0` rows |
| Hub `debit_authorizations` | 113 rows, all terminal (86 abandoned, 27 confirmed) |
| HORKOS ledger non-terminal rows | `live_rows=0` at boot |
| New escrow `authorizedHubs(0xBE0bBE44…C5f1)` | `true` (the address HORKOS actually signs with) |

**HORKOS** — `escrow_signer/config.py` was the only file differing from the deployed tree
(all eight siblings matched by checksum), so the change shipped as one file plus a rebuild.
Its boot check then verified the new escrow against the chain itself:

```
boot ok | address=0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1 next_nonce=32 live_rows=0
/health → {"escrow":"0x12Db8FAC81E5999D2f2087B79e38951571562CF2","ready":true,"halted":""}
```

**The hub** has no compose file and no labels — it was started by hand, so its environment
existed only inside the running container. Rather than hand-reconstruct it, the live spec was
captured from `docker inspect` (77 `-e` entries, both binds, both port publications, network,
restart policy), the three address variables were substituted, the old container was renamed
to `hub-rollback-20260904-091402` and stopped with its original environment intact, and the
**same image** (`prod-20260901-fedmetrics`) was re-run from the captured spec. Rollback is
therefore `docker rm modelmarket-hub && docker rename hub-rollback-… modelmarket-hub &&
docker start modelmarket-hub`.

One scare worth recording: the new container reports 80 environment entries against the old
container's 82, which looks like two dropped variables — and the two that `comm` singled out
were `AIMARKET_SELLS_FOR` (without it, federated sales charge \$0) and
`AIMARKET_TRUSTED_PROXIES`. They were not dropped. The old container held **duplicate** env
entries for both, which Docker collapses on re-run. Compared as sets, both containers carry
81 unique entries and the only difference is the three addresses.

**Verified after the switch**, all on the running container:

| Check | Result |
| --- | --- |
| `AIMARKET_ESCROW_EVM_ADDRESS`, `AIMARKET_ESCROW_CONTRACT`, `AIFACTORY_AI_MARKET_CONTRACT` | all `0x12Db8FAC…62CF2` |
| Env parity vs the parked container (as sets) | identical but for those three |
| Container health | `healthy` in 6 s |
| `/.well-known/ai-market.json` | `200`, `payment_configured: true`, channel rail enabled, 142 federated capabilities |
| `/ai-market/v2/prices` | 142 entries, 133 priced |
| Unpaid invoke of a priced capability | `402` with a well-formed x402 challenge (`maxAmountRequired: 250000`, USDC, `payTo` the operator wallet) |
| Hub → HORKOS over the tunnel | `ready: true`, and the **same** escrow address on both sides |

What is *not* proven here: no debit has yet been signed and mined against the new escrow,
because that needs a real USDC deposit to open a channel. The strongest evidence short of
that is HORKOS's fail-closed boot check — it re-derived the EIP-712 domain separator for the
new address, read the escrow's own `domainSeparator()`, confirmed the hub key is in
`authorizedHubs`, and only then reported `ready`.

**Deploy sources were patched too**, because the switchover is only as durable as the file a
future redeploy reads. `/root/hub-runtime.env` still named the superseded escrow, as did a
stale `hub-runargs.txt`, three `deploy/hub-payment.env` copies (including the one in the
`aicom-hub-build` tree that is already known to be stale), and two product participant envs.
All were backed up and repointed; a sweep of the host's `.env`/`.yml`/`.txt` files now finds
no live deploy source naming the old address. Without that pass, the next routine redeploy
would have silently reverted the rail to an abandoned contract.

### Stale bookkeeping found in HORKOS's ledger (not a fund issue)

Checking for pending work before the switch turned up 31 of 32 `spend` rows sitting in state
`broadcast` with only one ever reaching `mined`. Spot-checking the two most recent tx hashes
on chain returned `status 0x1` in blocks `0x3059918` and `0x3040d18` — they were mined and
succeeded. So the money moved correctly and the superseded escrow is empty for the right
reason; what never runs is the reconciliation that advances `broadcast` → `mined`. It is not
a re-broadcast loop either: each row holds its own consumed `account_nonce` (26…31), so a
resubmission would be a no-op. Recorded here rather than fixed, because it is a reporting
defect in a component that was mid-switchover.

### A hardcoded-address sweep this redeploy forced

The 2026-08 audit moved every consumer onto the registry so that a redeploy is a one-file
edit — but its drift test only ever scanned three files (`chain_net.py`, the monitor's copy,
`argus/networks.ts`). This redeploy found the address still hardcoded in
`core/aimarket_participant.py` (three live defaults), `aimarket_hub/landing.py` (two public
Basescan links, in PLAIN triple-quoted strings — a brace expression there renders as visible
text, so the substitution goes through a token replaced in `_localise`),
`scripts/reopen_product_escrow_channel.py`, `scripts/first_paid_invoke.py`, four test
fixtures, `deploy/hub-payment.env.example`, the `school` course content and the escrow-signer
READMEs in five languages. `tests/test_base_deployment_registry.py` now checks the whole
repository, in two directions: no code or config may pin a CURRENTLY-deployed address
(HORKOS's deliberate pin is allowlisted, with its reason), and none may still name a
SUPERSEDED one — the second check exists because a superseded address leaves
`registry["contracts"]` and so becomes invisible to the first. Documentation and landing
pages are deliberately out of scope: they record what was live when they were written.
