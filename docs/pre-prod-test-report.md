# Pre-prod comprehensive test report

> Living record of the pre-production testing campaign across the **live** AIMarket ecosystem
> (real Base mainnet contracts + the two production servers). Each section is a real test with
> its observed result. 🔴 = finding to address; ✅ = pass.

**Environment**
- **Server 1** `78.17.126.214` (`48720.com`) — oracles (family :9400, chronos :9300, platon :9200),
  aimarket-hub (:9083), alien-monitor, lottery anvil chain, Gitea. 11 GiB RAM.
- **Server 2** `5.129.212.122:8443` — aicom factory app (:90xx), mesh-api, modelmarket-hub,
  alien-monitor, UNI lottery relayer, Grafana/Prometheus, landing. 7.8 GiB RAM.
- **Chain** Base mainnet (8453); deployer/owner `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`.
- Contract addresses: source of truth = `aimarket_hub/chain_net.py`; journal = `docs/onchain-journal.md`.

---

## 1. Resource consumption (snapshot)

| Host | Load (1m) | Mem used | Disk | Notable containers |
|---|---|---|---|---|
| Server 1 | **7.2** | 1.5 GiB / 11 GiB (10 GiB avail) | 38% | 🔴 **platon-backend CPU ~700% (7 cores) sustained**; ailottery-chain 4.6%; family/chronos/hub <0.3% |
| Server 2 | 1.5 | 4.9 GiB / 7.8 GiB (2.9 GiB avail) | 65% | alien-monitor 2.26 GiB RAM + 33% CPU; aicom-app ~1 core, 1.5 GiB |

🔴 **FINDING R-1 — platon-backend pegs ~7 CPUs continuously.** It drives server 1's load to ~7.
Likely the continuous chaos/dynamical simulation tick (randomness proofs carry a fast-advancing
`tick`), but 7 cores sustained for a demo oracle is excessive — verify it's intended and/or
throttle the tick rate / pin CPU. Memory is fine (39 MiB). Does not affect correctness (oracle
calls return valid signed output), but it's a cost/scaling concern for prod.

🟡 **FINDING R-2 — Server 2 memory headroom is modest** (2.9 GiB available; alien-monitor alone
is 2.26 GiB). Watch under load; monitor RAM growth.

---

## 2. Component connectivity & health  ✅

All core services up and answering on both hosts (see §1 inventory). Live oracle stack on
server 1 verified by real invocation (§3). aimarket-hub healthy (:9083). Monitor running on both.

---

## 3. Oracle capabilities — real signed invocations (server 1, live)  ✅

Invoked via the oracle-family `:9400 /ai-market/v2/invoke`:
- `platon.random@v1` → real `random_hex` + chaos-VRF proof (`state_hash`, `entropy_commitment`,
  `tick`) + Ed25519 signature. ✅
- `chronos.eval@v1` → Wesolowski VDF over RSA-2048 (g/y/proof). ✅
- `lumen.reputation@v1` (via gateway) → PageRank, converged, scores sum to 1, top node correct. ✅
- family health: 12 capabilities; chronos: 2. ✅

---

## 4. MCP servers — tested as an AI client (MCP protocol)  ✅

Driven over the real MCP stdio protocol (initialize → tools/list → tools/call):

- **aimarket-oracle-gateway** (10 tools), pointed at the **live** `oracles.modelmarket.dev`:
  `list_oracle_capabilities`, `get_random`, `compute_vdf`, `get_reputation_scores` — all returned
  `HTTP 200` from the real oracle with valid/signed output. ✅ (AI → MCP → live oracle path works.)
- **aimarket-mcp-packager** (3 tools): `package_capability` returned a full package (docker image,
  MCP manifest, subscription tiers, connection string). ✅

---

## 5. UI — deployed sites reachable (real addresses)  ✅ (1 finding)

| URL | HTTP | Title |
|---|---|---|
| modeldev.modelmarket.dev | 200 | AICOM — autonomous AI software company |
| oracles.modelmarket.dev | 200 | Oracle Family |
| magic-ai-factory.com | 200 | AI-Factory — Generate landings from one phrase |
| oracles.modelmarket.dev/platon/ | 200 | Platon · UMBRAL |
| oracles.modelmarket.dev/chronos/ | **404** | 🔴 |

🔴 **FINDING U-1 — `/chronos/` UI path returns 404** via nginx (the chronos *capability* at :9300
works fine — verified in §3; this is a frontend/nginx routing gap for the chronos human UI only).

## 6. Load testing (bounded — light, not a prod DoS)  ✅

| Target | Req × conc | Result | Latency (ms) |
|---|---|---|---|
| family `/api/health` (full public path) | 120 × 12 | **120 ok, 0 err**, 71 req/s | p50 109 · p95 391 · p99 436 |
| **real** `platon.random@v1` invoke | 40 × 4 | **40 ok, 0 rate-limited, 0 err** | p50 124 · p95 358 |

✅ Under concurrency the real invoke produced **40/40 unique** random values (no repeated draws →
the unbiasable-randomness property holds under load). No errors, no 429s at this level.

---

## Pending phases (next)
- [ ] Packages — SDK install-from-source + smoke (Python/TS/Rust/Dart).
- [ ] Quickstarts — validate the documented quickstart steps.
- [ ] Deeper connectivity (hub ↔ mesh ↔ factory ↔ monitor federation/discovery on server 2).
- [ ] Heavier load profile (ramp until first 429 / latency knee) once approved for prod targets.
- [x] **On-chain real-money flows from `0x1218`** (2026-06-20) — **DONE**, fully documented in
      [`onchain-journal.md` §3f](onchain-journal.md): escrow capability channel (approve → open →
      EIP-712-signed debit → settle, **real 1.0 USDC**); lottery round 3 (open → buy → close →
      signed-beacon draw → win → claim → fee withdrawals, **real ETH**, lottery drained to 0). End
      state: 2.0 USDC + 0.0057 ETH on `0x1218`, total gas ≈ 0.0000061 ETH. ACEX value cycle **not**
      run on mainnet (first deposit permanently locks 1 USDC by design; covered by 49 Foundry
      tests; audit-fix constants verified live on-chain).

## 7. Money flows — full chains traced (2026-06-20)  ✅ (1 finding)

The complete "how money moves / how we get paid" cycle, with **real funds**, traced end-to-end and
documented tx-by-tx in [`onchain-journal.md` §3f](onchain-journal.md):

- ✅ **Capability payment (on-chain escrow), real USDC.** Consumer pre-funds a channel → each
  metered invoke debits it against an EIP-712 authorization the consumer signed → `settleChannel`
  pays the **used** amount to the **hub** (this transfer *is* the revenue) and refunds the rest.
  Proven with 1.0 USDC: debit 0.25 → hub, refund 0.75 → depositor.
- ✅ **Lottery, real ETH.** Full round (open → buy → commit-reveal close → signed-beacon draw →
  claim), 80/12/8 prize/opex/operator split, fees withdrawn, contract drained to 0.
- ✅ **FINDING H-1 — RESOLVED (2026-06-20).** The deployed `:9083` image was old (Jun-13) — it
  lacked the oracle federated transport (commit `37650a87`, Jun-16), had 0 peers, no
  `AIFACTORY_PUBLIC_URL`, and was network-isolated from the oracle. Fix: built a corrected hub image
  from the monorepo source (oracle transport + channel-secret/recipient/demo-credit security fixes),
  deployed on server 1 **`:9085`** (`aimarket-hub-fixed`, production `:9083` untouched), registered
  the oracle family as a trusted peer at its `mcp_endpoint`. A **real external actor then paid for 25
  MCP invocations** of `platon.random@v1` and the **operator received $0.10 in real USDC on-chain**
  via a freshly-deployed verified escrow `0x2F4c…fB22` — full lifecycle (prepay → metered consume →
  EIP-712 authorize → debit → settle) in [`onchain-journal.md` §3g](onchain-journal.md). Promoted to production `:9083` (Jun-13 image kept as `rollback-jun13`).
- ✅ **ACEX** audit-fix constants verified live on-chain; value behavior covered by 49 Foundry
  tests; mainnet value cycle intentionally not run (first deposit permanently locks 1 USDC).

## Findings summary
- 🔴 **R-1** platon-backend ~700% CPU (7 cores) sustained on server 1 — verify/throttle.
- 🔴 **U-1** `/chronos/` UI path 404 (nginx routing; capability OK).
- ✅ **H-1 RESOLVED** — fixed hub built from monorepo + **promoted to production `:9083`** (old
  Jun-13 image kept as `rollback-jun13`); a real external actor paid for 25 MCP invokes, operator
  received $0.10 USDC on-chain via new verified escrow `0x2F4c…fB22` (journal §3g). Paid invoke
  verified live on `:9083`.
- 🟡 **R-2** server 2 memory headroom modest (2.9 GiB free; monitor 2.26 GiB).
- ✅ Oracles, MCPs, connectivity, UIs, bounded load, **on-chain money flows (escrow + lottery, real
  funds)** — all pass.
