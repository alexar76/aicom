# Known Issues — open items tracked outside the code

This document tracks issues that **cannot be closed by a code change in this
repo alone**. They require operator action, an external vendor, or production
telemetry that does not yet exist. Each entry lists what it is, why it can't
be closed inline, who needs to act, and what the acceptance criteria are.

Last reviewed: 2026-08-27 (security remediation audit; KI-5 dependency exception closed).

---

## KI-1 — Trusted-setup ceremony — RESOLVED (migrated to PLONK, 2026-06-07)

**Resolution:** The `input_validity` circuit now ships a **PLONK** backend
instead of Groth16. PLONK uses a **universal** structured reference string —
a single *public* Powers-of-Tau (phase 1) is sufficient, and there is **no
per-circuit, multi-party phase-2 ceremony and no toxic waste** to destroy.
This removes the entire reason KI-1 existed.

**What was done (in-repo, no ceremony):**
- `contracts/zk/scripts/setup_plonk.sh` — compiles the circuit, reuses the
  public Hermez pot14 ptau, runs `snarkjs plonk setup`, exports artifacts.
  (Also fixes the dead ptau URL the old Groth16 `setup.sh` pointed at.)
- `contracts/zk/verifier/verification_key.json` — committed (protocol `plonk`,
  curve `bn128`, 3 public signals).
- `contracts/zk/verifier/Verifier.sol` — committed (`PlonkVerifier`,
  `verifyProof(uint256[24], uint256[3])`).
- `aimarket_hub/zk_groth16.py` — prover parametrised by proof system;
  `AIMARKET_ZK_BACKEND=plonk` selects the PLONK snarkjs subcommands.
- `security/zk_artifacts.py::production_zk_issues()` — accepts `plonk`,
  checks for the PLONK artifacts (no ceremony hint).

**Verified end-to-end:** `snarkjs plonk fullprove` + `snarkjs plonk verify`
roundtrip on the committed artifacts returns `OK!` (witness built with
circomlibjs Poseidon matching the circuit).

**Trust assumption (honest):** PLONK is not *transparent* — it still relies on
the **public universal** Powers-of-Tau ceremony (Hermez/Perpetual PoT), which
thousands of projects reuse. That is a far weaker and more standard assumption
than a bespoke single-operator setup; it is **not** "no trust at all" (that
would need a STARK). Payments remain **testnet** — see the pre-mainnet banner.

**Optional Groth16 path (not required):** smaller proofs / cheaper on-chain
verify, but it *would* need a per-circuit ceremony. Tooling for that still
exists (`scripts/zk_ceremony_coordinator.sh`, `contracts/zk/scripts/setup.sh`)
for operators who choose it at mainnet scale. PLONK is the default.

**To enable the real backend:** run `setup_plonk.sh`, then set
`AIMARKET_ZK_BACKEND=plonk` + `AIMARKET_ZK_WASM/ZKEY/VKEY` and drop
`AIMARKET_ZK_SIMULATED`. `prod_startup_guard` still blocks
`AIFACTORY_PROD=1` + simulated ZK.

---

## KI-2 — External smart-contract security audit not performed

**Where:** `contracts/evm/src/`, `contracts/solana/programs/aimarket-escrow/`.

**Why it can't be fixed in-repo:** External audits by Trail of Bits,
OpenZeppelin, Spearbit, ConsenSys Diligence, etc., are independent
third-party services. The value comes from auditors having **no prior
context**, which is the opposite of in-repo work.

**Tooling already in repo (b4d64ebf):**
- `contracts/audits/audit-response.md` — disposition template (EXT-001 placeholder, status taxonomy: open / fixed / accepted / false-positive)
- `scripts/run_contract_audit.sh` — local Slither summary generator (`slither-summary-*.md`)
- `.github/workflows/contracts-ci.yml` — Slither `--fail-high` on both `contracts/evm/` and `acex/contracts/evm/`
- `.github/workflows/security-scan.yml` — Python Bandit (fail on High), pip-audit, npm audit on frontend + TS SDK
- `.github/dependabot.yml` — pip / npm×2 / actions / cargo updates
- `scripts/run_dependency_audit.sh` — one-shot local CVE scan

**Required action (operator / business):**
1. Budget: USD 30k-100k (Trail of Bits typically USD 80k+ for a 6-week
   engagement; OpenZeppelin USD 40k-60k for similar scope; Spearbit
   competitions in the USD 30k-50k range).
2. Scope letter covering:
   - `AIMarketEscrow.sol` (EVM payment channels)
   - `AIMarketCapabilityNFT.sol` (ERC-721 entitlements)
   - `aimarket-escrow` Solana program (Anchor)
   - The Groth16 verifier circuit (`contracts/zk/circuits/input_validity.circom`)
     and its `Verifier.sol` after KI-1 completes.
3. Run internal scans first (`slither --fail-high`, `mythril`, `cargo audit`,
   `anchor verify`) to clear the obvious findings before the audit clock starts.
4. Address all High/Critical findings + the majority of Mediums before mainnet deploy.

**Acceptance criteria:**
- Audit report PDF stored under `contracts/audits/`.
- All H/C findings fixed or formally accepted (signed off in `contracts/audits/audit-response.md`).
- Audit conclusion ("no critical findings remaining") published.

**Until done:** **do not deploy to mainnet with real funds at scale.** Testnet
(Base Sepolia / Solana devnet), small demo sums (~$2 on Base), and dry-runs are fine.

**Pet-project waiver:** external audit (KI-2) is optional for self-host demos.
Use Slither + [`docs/pet-project-trust.md`](pet-project-trust.md) + multisig (KI-4) instead.

---

## KI-3 — uvicorn supervisor: root cause of worker crash-loops not diagnosed

**Where:** `entrypoint.sh:173-280` — backend supervisor with exponential
backoff + circuit breaker.

**Symptom:** Under sustained pipeline load, uvicorn workers crash and
the supervisor restarts them. With `UVICORN_WORKERS > 1`, the
multiprocess supervisor has been observed to enter crash loops.

**Why it can't be fixed in-repo:** The supervisor with backoff is a
**mitigation**, not a fix. The actual root cause requires:
- Production-grade load (many concurrent invocations against
  `/api/health`, `/api/pipeline/*`, `/api/sandbox/*`).
- Memory profiling under that load (`py-spy dump`, `memray`).
- Inspection of `prometheus_client.multiprocess` shared-memory state
  (suspected file descriptor leak or write contention on
  `PROMETHEUS_MULTIPROC_DIR`).
- Inspection of SQLite connections forked between workers (suspected:
  workers share a `sqlite3.Connection` object that was opened before
  `fork()`, leading to write corruption and subsequent crashes).

None of those can be done from inside the repo — they need a running
production environment with realistic traffic.

**Mitigation in place:**
- Default `UVICORN_WORKERS=1` (single worker = no shared-state issue).
- **`USE_SQLITE=true` forces `UVICORN_WORKERS=1`** even if the operator overrides (2026-06).
- Cap at `UVICORN_WORKERS=4` even if operator overrides (was 2 before
  Wave 2; raised after supervisor improvements).
- Exponential backoff 5s → 60s prevents busy-loop.
- `BACKEND_MAX_RESTARTS=20` in `BACKEND_RESTART_WINDOW_SECS=1800`
  triggers fail-fast (exit 1) instead of infinite restart.
- Crash diagnostics persisted to `/app/data/logs/uvicorn-last-crash.log`
  **with structured telemetry** (workers, SQLite flag, Prometheus multiproc file count, log tail).

**Required action (dev/ops):**
1. Deploy staging with `./scripts/run_prod_compose.sh up -d --build`.
2. Run `./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 3600 --concurrency 10`.
3. Attach `py-spy record -p $UVICORN_PID -o flame.svg --duration 3600`.
4. Capture `PROMETHEUS_MULTIPROC_DIR` filesystem snapshot before / after.
5. `lsof -p $UVICORN_PID` to inventory open file descriptors over time.
6. Open a GitHub issue with the trace; link any fix back to this entry.

**Acceptance criteria:**
- Root cause identified and documented in a code comment at
  `entrypoint.sh` (replacing or augmenting the current "KNOWN ISSUE"
  block).
- Workers can safely run at `UVICORN_WORKERS=4+` without the supervisor
  having to restart them more than once per hour under steady load.
- `BACKEND_MAX_RESTARTS` cap can be lowered (e.g. to 5) without
  spuriously tripping.

**Until done:** keep `UVICORN_WORKERS=1` in production. The supervisor
absorbs crashes when they happen; users see brief HTTP 503 during the
backoff window, not infinite errors.

---

## KI-4 — Multisig owner not configured on EVM contracts

**Where:** `contracts/evm/src/AIMarketEscrow.sol`, `contracts/evm/src/AIMarketCapabilityNFT.sol`.

**What's missing:** Both contracts use `Ownable2Step` (good — accidental
transferOwnership is recoverable), but `owner` after deploy is the EOA
that ran `forge create`. A compromise of one private key reassigns hub
authorizations, token whitelists, and (on NFT) global pause.

**Why it can't be fixed in-repo:** A Safe / Squads multisig is **created
on-chain by the operator**, not declared in source. The transfer step
must happen between `forge create` and first real-money channel.

**Required action (operator):**
1. Deploy a Gnosis Safe (EVM) with 2-of-3 or 3-of-5 signers held by
   different humans / different geographies.
2. From the deployer EOA, run:
   ```bash
   cast send $ESCROW_ADDR "transferOwnership(address)" $SAFE_ADDR \
     --ledger --from $DEPLOYER --rpc-url $RPC_URL
   ```
3. From the Safe UI (or `cast send` via a Safe transaction builder),
   call `acceptOwnership()`. Repeat for the NFT contract.
4. Document the Safe address in `contracts/audits/audit-response.md`
   under the pre-mainnet checklist.

**Acceptance criteria:**
- `cast call $ESCROW_ADDR "owner()(address)"` returns the Safe address.
- `cast call $ESCROW_ADDR "pendingOwner()(address)"` returns `0x0`.
- Safe transaction history shows the `acceptOwnership` call.

**Until done:** Single-EOA owner is acceptable for testnet drills and
mainnet pilots with < $1k TVL. **Do not run without multisig past
$10k TVL on a single channel or > $100k cumulative.**

---

## KI-5 — Python dependency CVE backlog — RESOLVED (2026-08-27)

**Where:** `requirements.txt` and transitive pins.

**Status:** FastAPI/Starlette upgraded to `0.141.1`/`1.6.0`; the audit gate
contains zero ignored vulnerability IDs. A fresh Python 3.12 `pip-audit` is
required to remain green in CI.

**Removed dead dependencies (2026-06-28):**
| Package | Action | Cleared |
|---------|--------|---------|
| `langgraph` | Removed from `requirements.txt` | PYSEC-2026-83 + transitive checkpoint/langsmith |
| `langchain-core` | Removed from `requirements.txt` | 5 GHSA advisories |

**Bumped inline (cleared, non-breaking):**
| Package | From → To | Cleared |
|---------|-----------|---------|
| `aiohttp` | 3.10.5 → 3.14.0 | 25 advisories |
| `PyJWT[crypto]` | 2.10.1 → 2.13.0 | 7 (PYSEC-2025-183, PYSEC-2026-120/175-179) |
| `cryptography` | 45.0.7 → 46.0.7 | PYSEC-2026-35/36, GHSA-r6ph-v2qm-q3c2 |
| `orjson` | 3.10.7 → 3.11.6 | PYSEC-2026-107, GHSA-hx9q-6w63-j58v |
| `python-dotenv` | 1.0.1 → 1.2.2 | GHSA-mf9w-mj56-hr94 |
| `python-multipart` | → ≥ 0.0.18 | (earlier) |

Smoke-verified: jwt/crypto suites (28 passed) and LLM router/provider suites
(13 passed) green on the bumped versions; remaining test failures are the
pre-existing `/app` read-only sandbox path issue, unrelated to these bumps.

**Acceptance criteria:**
- `bash scripts/pip_audit_gate.sh` exits 0 with no `--ignore-vuln` arguments.
- Production runtime smoke (`/api/health`, `/api/pipeline/list`) green
  for ≥ 1 hour post-deploy.

The full unfiltered report remains the `pip-audit-report` CI artifact every run.

**Frontend note (npm): Next 16 / React 19 migration — DONE (2026-06-06).**
`web/frontend` now ships `next 16.2.7`, `react`/`react-dom 19.2.7`,
`eslint 9`, `eslint-config-next 16`, `recharts 2.15.4`. This cleared the
previous `next` (high) + `postcss` advisories, so the npm gate was raised from
critical to **high** (`npm audit --omit=dev --audit-level=high`, green; only 2
moderate-in-`next` remain, below the gate). The `ws` override on `^8.21.0`
still clears the `ethers → ws` advisories without downgrading `ethers`.

What the migration required (vs. the originally-feared async-params rewrite,
which turned out **not** to apply — those 9 App-Router files broke neither
typecheck nor build):
- one-line CSS fix: Google-Fonts `@import` moved to the top of
  `styles/globals.css` (Turbopack, now the default builder, enforces CSS spec
  ordering; webpack tolerated it);
- `next lint` removed → flat `eslint.config.mjs` spreading
  `eslint-config-next/core-web-vitals` directly (FlatCompat hits a
  circular-JSON bug);
- `next.config.js`: `images.domains` → `images.remotePatterns`.

Verified green: `tsc --noEmit` (0 errors), `eslint .` (0 errors), `next build`
(32/32 pages), `vitest` (7 passed) under React 19.

**Remaining tech-debt (advisory, tracked here):** `eslint-config-next 16`
promoted a wave of React-Compiler-era hook rules to error on pre-existing code
— `react-hooks/set-state-in-effect` (41), `react-hooks/refs` (19),
`react-hooks/immutability` (3), plus `@next/next/no-html-link-for-pages` (8).
These are down-leveled to **warn** in `eslint.config.mjs` (parity with the
pre-existing `exhaustive-deps` warnings) rather than mass-refactored blind;
they should be cleared incrementally with a visual/e2e pass. **React-19
runtime e2e** for `recharts` + `framer-motion` is covered by
`web/frontend/e2e/charts-motion.spec.ts` (Playwright, CI `frontend-build` job).

---

## Post-audit code fixes (2026-05-24, in-repo)

Internal review of `b4d64ebf` / `90652fd8` surfaced issues fixed in
follow-up commits (not operator blockers):

| ID | Severity | Issue | Fix |
|----|----------|-------|-----|
| NEW-1 | CRITICAL | ZK ceremony entropy in argv (`ps` leak) | `zk_ceremony_coordinator.sh`: stdin pipe, no `-e` |
| NEW-2 | HIGH | OIDC nonce optional | Strict `nonce` required in `verify_id_token` |
| NEW-3 | HIGH | OIDC role stale after group change | `_sync_oidc_user` updates role every login |
| NEW-4 | MEDIUM | Vault token over HTTP | Refuse remote HTTP; warn on loopback |
| NEW-5 | MEDIUM | `/zk/prove-input` DoS | Per-IP rate limit (`AIMARKET_ZK_PROVE_RATE_LIMIT`) |
| NEW-6 | MEDIUM | Truncated proof fields | Return full commitments/nullifier |
| NEW-7 | MEDIUM | zkey overwrite | Backup before `install-secrets` |
| NEW-8 | MEDIUM | OIDC post-login open redirect | `safe_post_login_url()` validation |

**Still operator/vendor (unchanged):** KI-1 … KI-11 above.

---

## KI-6 — Oracle family cryptographic maturity (not production-hardened)

**Where:** `oracles/` satellite — `oracle-core` signing, Chronos VDF, Sortes ECVRF, sixteen
other domain oracles, lottery on-chain consumers.

**What reviewers correctly note (2026-07):**

1. **Chronos (Wesolowski VDF)** — parameters and modulus choice are documented in source
   ([`oracles/chronos/SECURITY.md`](https://github.com/alexar76/oracles/blob/main/oracles/chronos/SECURITY.md)),
   but there is **no external audit**, **no formal verification**, and **no published
   parameter-selection guide** (iteration count `T` ↔ wall-clock, hardware profiles, security
   margins). Links to third-party review do not exist yet.
2. **Signing & oracle-core** — Ed25519 + optional hybrid ML-DSA-65 is implemented
   ([`core/oracle_core/signing.py`](https://github.com/alexar76/oracles/blob/main/core/oracle_core/signing.py)),
   but the hybrid extension is **implementation-defined** (not frozen in `aimarket-protocol`),
   **off by default**, Hub verifies **Ed25519 only**, and there is **little proof-of-correctness
   beyond unit tests** — no independent crypto review.
3. **Overall tier** — seventeen oracles with real math in ~two months of focused work is
   **ambitious research/prototype** quality (demos, testnet lottery, Hub integration), **not** a
   fully hardened cryptographic service suitable as the sole trust anchor for mainnet-scale TVL.

**Why it can't be fixed in-repo alone:** External cryptographic audits, formal methods, and
published operator attestation programs require third-party engagement and calendar time — the
same class of blocker as KI-2 (smart-contract audit).

**In-repo honesty (done):**
- [`oracles/docs/crypto-maturity.en.md`](https://github.com/alexar76/oracles/blob/main/docs/crypto-maturity.en.md)
  (+ RU) — ecosystem-facing maturity statement.
- [`oracles/core/docs/SIGNING.md`](https://github.com/alexar76/oracles/blob/main/core/docs/SIGNING.md)
  — what hybrid signing does today (not a normative spec).
- Banner in [`oracles/README.md`](https://github.com/alexar76/oracles/blob/main/README.md).

**Required action (operator / business):**
1. Commission external crypto audit (scope: `oracle-core` signing, Chronos VDF, Sortes ECVRF
   minimum; budget similar order of magnitude to KI-2, narrower scope).
2. Publish Chronos parameter guide + operator attestation checklist (modulus fingerprint, `T`
   policy, reference hardware).
3. Freeze hybrid PQC fields in `aimarket-protocol` with negative test vectors; extend Hub to
   verify both layers when present.
4. Oracle key-management runbook (rotation, compromise, HSM option).

**Acceptance criteria:**
- Audit report PDF linked from `oracles/docs/crypto-maturity.en.md`.
- Chronos parameter guide committed under `oracles/chronos/docs/`.
- Protocol PR merged in `aimarket-protocol` for PQ extension + Hub parity.
- KI-6 entry deleted; one-line `CHANGELOG.md` note.

**Until done:** Oracles are fine for **testnet, demos, bounded pilots, and education**
(including courses that map to `lottery/` code). **Do not** market the family as
production-hardened crypto or rely on it alone for large real-money flows — same pre-mainnet
posture as KI-2.

---

## KI-7 — AI-Factory production maturity (pipeline debt & MVP outputs)

**Where:** Root factory — `pipeline_worker.py`, `config/fragments/`, `web/backend/services/`,
`entrypoint.sh`, shipped demos under `docs/sample-output/`.

**What reviewers correctly note (2026-07):**

1. **Volume vs time** — full multi-agent factory with quality gates in ~two months implies
   **technical debt** (supervisor KI-3, conditional agent graph, director re-queue paths).
2. **Over-engineered default** — twelve config fragments and many stages are heavy for simple
   landing/MVP outputs; fair critique for pet-project scope.
3. **Shipped products** — public build replays and live demos skew to **MVP storefronts**, not
   complex long-lived software — honest tier labeling required.
4. **Production readiness** — load testing, multisig, external audit acknowledged open (KI-2–4).

**In-repo actions (done / ongoing):**
- [`docs/factory-pipeline-profiles.md`](factory-pipeline-profiles.md) — minimal vs full profiles.
- [`docs/ecosystem-maturity-review.en.md`](ecosystem-maturity-review.en.md) — scorecard + matrix.
- [`docs/sample-output/README.md`](sample-output/README.md) — MVP-tier label.

**Required action (operator):**
1. Run KI-3 soak: `./scripts/load_test_factory.sh --duration 3600 --concurrency 10`
2. Prefer **minimal pipeline profile** for landing-only builds.
3. Complete KI-4 multisig before >$10k TVL.

**Acceptance criteria:**
- KI-3 closed (workers stable at `UVICORN_WORKERS=4+` under load).
- Documented default profile choice in operator guide.
- At least one non-landing sample replay OR honest “MVP only” banner on all public demos.

**Until done:** Present Factory as **self-host research/prototype** — powerful demo pipeline,
not proven SaaS factory at scale.

---

## KI-8 — Metis distributed mode & adversarial verification gap

**Where:** `metis/` — distributed coordinator, confidence gate, verifier-with-retry, economy
metering hooks.

**What reviewers correctly note:**

1. **Distributed cluster** — TLS+HMAC multi-node path exists but ** lacks production soak**
   (partition, stale registry, clock skew, partial node compromise).
2. **Confidence gate** — fail-closed on structured `TaskSpec`, but **trusts council-assigned
   confidence**; high-score subtle hallucinations can proceed if ambiguities omit
   `needs_user_input`.
3. **Verifier-with-retry** — strong concept; **limited adversarial/red-team benchmark** coverage
   vs encoding tricks, contradictory evidence, or confident wrong answers.
4. **Economy metering** — interesting; **enforcement is consumer-side** (Factory/Hub debit), not
   a hard kernel-level cap inside Metis alone.

**In-repo actions:**
- [`metis/docs/en/MATURITY.md`](https://github.com/alexar76/metis/blob/main/docs/en/MATURITY.md)
- `metis/tests/test_adversarial_gates.py` — regression seeds for known gate bypass patterns
- Benchmark docs already state confidence ≠ accuracy ceiling

**Required action (dev/ops):**
1. Multi-node soak test script (48h, 3+ workers, inject node failure).
2. Expand `metis/benchmarks/` with trap/adversarial suite; publish scores in `docs/benchmarks/`.
3. Wire Factory architect stage to **hard-fail** on `verified: false` when configured.

**Acceptance criteria:**
- Soak report committed under `metis/docs/benchmarks/`.
- Adversarial benchmark ≥ N cases with documented pass/fail thresholds.
- Distributed mode labeled **beta** until soak green.

**Until done:** Use Metis for **cognition + confidence signal** on bounded tasks; do not treat
distributed Metis as HA production inference mesh without soak evidence.

---

## KI-9 — ARGUS WARDEN vs sophisticated MCP attacks

**Where:** `warden/src/`, policy defaults in `argus.config.example.json`.

**What reviewers correctly note:**

1. **WARDEN is real** — static scan, threat feed, pinning, egress guard; unit tests on textbook
   poisoning.
2. **Two months is short** for a firewall against **sophisticated** attacks: obfuscated
   injections, multi-hop tool chains, runtime-only exfil, model-side compliance with smuggled
   instructions after vetting, compromised benign servers post-pin approval.
3. **Permissive defaults** — `allowUnknownServers` and LUMEN **degrade-to-neutral** preserve
   autonomy but weaken fail-closed posture when oracle unreachable.

**In-repo actions:**
- §Limitations in [`argus/docs/security-warden.md`](https://github.com/alexar76/argus/blob/main/docs/security-warden.md)
- `argus/test/adversarial-warden.test.ts` — documents known bypass class (obfuscated injection)

**Required action (dev/security):**
1. Red-team fixture corpus (≥20 cases) in `argus/test/fixtures/warden-adversarial/`.
2. Tighten default policy doc for high-security profile (`allowUnknownServers: false`).
3. Optional Immunefi / private bug bounty before claiming “production firewall”.

**Acceptance criteria:**
- Red-team report or CI job with adversarial fixtures; regressions tracked.
- High-security preset documented and tested.

**Until done:** WARDEN is **strong default for casual MCP** — not a guarantee against targeted
attack; combine with egress allowlists, human approval on sensitive tools, encrypted keystore.

---

## KI-10 — Hub federation & micropayments unproven at adoption scale

**Where:** `aimarket-hub/` — federation crawler, channels, invoke, slash sync, plugin registry.

**What reviewers correctly note:**

1. **Protocol v2** — solid normative base + reference hub.
2. **Federation + micropayments** — implemented but **early**; almost no third-party hub mesh or
   external invoke volume → real-world edge cases (stale manifests, channel races, slash
   disagreements, plugin ordering) mostly untested in the wild.
3. **Adoption ≈ 0** outside operator deployments — fair critique.

**In-repo actions:**
- [`aimarket-hub/docs/MATURITY.md`](https://github.com/alexar76/aimarket-hub/blob/main/docs/MATURITY.md)

**Required action (ecosystem):**
1. Publish federation testnet playbook (2+ hub peers, cross-crawl, slash pull).
2. Chaos tests: invoke during channel close, manifest rotation mid-flight.
3. First external peer hub (even read-only mirror) to validate crawl/slash sync.

**Acceptance criteria:**
- Documented federation drill with logs committed.
- Negative test vectors in `aimarket-protocol` for channel edge cases.
- At least one non-operator peer listed in ecosystem map.

**Until done:** Hub is **reference implementation + demo deployment** — not proven multi-operator
marketplace at scale.

---

## KI-11 — Hub payment channels are off-chain and custodial (collection is a human act)

**Where:** [`aimarket-hub/aimarket_hub/channels.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/channels.py),
[`aimarket-hub/aimarket_hub/escrow_bridge/`](https://github.com/alexar76/aimarket-hub/tree/main/aimarket_hub/escrow_bridge),
[`contracts/evm/src/AIMarketEscrow.sol`](../contracts/evm/src/AIMarketEscrow.sol).

**What is actually true today** (re-verified 2026-07-29 against the code *and* the live
`modelmarket.dev` container — the 2026-07-25 wording said "no runtime code path calls
`debitChannel`", which is no longer the whole story in either direction):

| Step | Where it happens |
|------|------------------|
| Deposit | **On-chain**, but by default as a plain transfer to the **platform settlement wallet** (`on_chain.platform_recipient`) — *not* into `AIMarketEscrow`. Verified for recipient, amount, token, confirmations and sender before credit. A client may instead fund the contract and pass `escrow_channel_id`; that branch exists, but the custodial one is still the default and cannot be switched off. |
| Payer binding | On-chain sender **plus** an EIP-191 proof-of-control signature, required by default in every mode (`AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER=1` opts out; non-EVM payers are refused). |
| Debit **authorization** | **Live runtime path.** On a paid invoke against an escrow-bound channel the hub captures and verifies the depositor's EIP-712 `DebitAuthorization` *before* the provider runs, and returns **402 on failure** — fail-closed. The buyer's `receiptId` is reused as the ledger receipt so the on-chain and off-chain replay keys cannot drift. |
| Debit **submission** (`debitChannel`) | **Human-initiated only.** The one submission site (`escrow_bridge/mirror.py`) is reachable from `python -m aimarket_hub.escrow_bridge.cli submit --yes` and from nothing else: `GET /ai-market/v2/escrow/plan` is hardcoded to `PlanOnlySigner`, no route broadcasts, and there is no scheduler or timer. |
| Prod's actual capability | **Cannot broadcast at all.** `config.describe()` on the live container returns `strategy: "plan"`, `may_broadcast: false`, `private_key_set: false`, `signer_url_set: false`. No hot wallet is keyed into the hub. |
| `channel/close`, remainder | **Off-chain only.** The unspent remainder is recorded as a payout obligation (`channel_payout_obligations`, migration 017); `refund_executed_usd` is still `0.0` on the ledger rail. |

**The three mainnet settlements in the journal (§3h, §3i, §3j) were made by hand, not by
the hub.** Proof, not inference: the production bridge store held exactly three rows, all
`pending` with an empty `tx_hash`, and two of their receipt ids
(`0x937253cb…`, `0x409356b3…`) return `usedReceipts() == true` on
`0x0606983c…72C25D`. The chain had collected those debits while the hub still reported
$0.16 owed on them. The hub did not know it had been paid, because it was not the payer.

**Bug found and fixed while verifying this (2026-07-29).** The store's forward-only state
machine had no `pending → confirmed` edge, so a debit collected out of band could never be
resolved — and because submission is strictly nonce-ordered per channel, each stuck row
blocked *every later row on its channel permanently*. Head-of-line blocking on money.
Fixed by guard 0 in the mirror: read `usedReceipts(receiptId)` first, before the queue and
deadline guards, and resolve an already-collected receipt as `confirmed` (a read failure
blocks rather than assuming "unpaid"). Verified against Base: the two collected receipts
resolve, the genuinely-unpaid third stays queued.

Consequences that must not be papered over:

1. **Custodial by default.** The default deposit lands in the operator's wallet, so channel
   balances are an operator liability, not escrowed funds. `AIMarketEscrow`'s non-custodial
   guarantees describe the *contract*, which the default rail does not use.
2. **The two rails are mutually exclusive.** If a contract channel and a ledger channel back
   the same money, on-chain `usedAmount` stays `0` however much the ledger consumed, so
   `refundChannel` / `expireChannel` would return a fully-consumed deposit **in full**.
3. **Collection depends on a person.** A verified, collectable claim is captured on every
   paid invoke, but nothing collects it unless an operator runs the CLI. An unattended hub
   accrues claims it never presents.

**Required action (dev + operator) — what is left:**
1. ~~Land an escrow bridge that signs/submits `debitChannel` per settled receipt.~~ The
   bridge, its guards, its store and its CLI exist. What remains: (a) an unattended trigger
   — a bounded background pass in the hub's lifespan, or a host timer invoking
   `cli submit --yes`; (b) an operator hot wallet keyed into prod (`SUBMIT_STRATEGY`,
   `SUBMIT_CONFIRM`, and a key or signer URL — all absent today; `debitChannel` needs ETH
   for gas, not USDC, and must NOT reuse the `0x1218` funds key). ~~(c) a value bound.~~
   **Done 2026-07-29** — `AIMARKET_ESCROW_MAX_USD_PER_PASS` ($5 default) and
   `AIMARKET_ESCROW_MAX_USD_PER_DAY` ($25 default, rolling, read from the store so it
   survives a restart), both reported by `config.describe()`. Debits collected out of band
   and refused submissions do not consume the budget. What remains unbounded is the hot
   wallet's own ETH balance, which is an operational choice (fund it thinly) rather than
   something the hub can enforce.
2. Point `/channel/open` at `AIMarketEscrow.openChannel` **instead of** the settlement
   wallet. Today escrow is available *in addition to*, at the client's option; an
   `escrow_required` switch is needed so an operator can make the custodial branch
   unreachable.
3. ~~Reconcile the two rails so the double-refund case is unreachable.~~ **Done
   2026-07-29** — `payment_readiness()` refuses a configuration where
   `AIMARKET_PAYMENT_RECIPIENT` equals the escrow address, which is the one setting that
   backs both rails with the same money. The reverse direction was already unreachable and
   is now asserted rather than re-implemented: a transfer *into* escrow cannot be claimed as
   a ledger deposit, because verification requires the tx to pay `payment_recipient`, which
   this interlock keeps distinct. 14 tests, where there had been none for the list behind
   `payment_configured`.
4. ~~Expose the outstanding obligation total on an operator surface.~~ **Done** — served
   over HTTP and admin-gated.

**Acceptance criteria:**
- A hub-issued invoke produces an on-chain `ChannelDebited` event for its receipt id
  *without a human at a shell*. (Events of the right shape exist; nothing the hub runs
  produced them.)
- `channel/close` produces a `ChannelSettled` event whose `refundRecipient` leg matches
  the depositor, and `refund_executed_usd` stops being hardcoded to `0.0`.
- `channel_payout_obligations` holds no *owed* obligation for a contract-settled channel.
- This entry deleted; one-line `CHANGELOG.md` note.

**Until done:** describe the hub rail as an **off-chain, custodial metering ledger with
verified on-chain funding and operator-initiated on-chain collection** — never as
"escrowed", "non-custodial" or "mirrored on-chain", and never as if collection were
automatic. Keep deployments below the value ceiling in KI-4.

---

## How to close an entry

When one of these is resolved:
1. Delete the entry from this file in the same commit that resolves it.
2. Add a one-line entry to `CHANGELOG.md` (create if missing):
   `- KI-1 closed: ZK ceremony complete, Verifier.sol committed (see docs/zk-ceremony.md).`
3. If the resolution itself introduces new tracked work, open a new KI
   entry here for that.

If a new "can't be fixed in-repo" item appears, add it as `KI-N` with
the same shape: **Where / Why / Required action / Acceptance / Until done**.
