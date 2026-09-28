# Changelog

All notable changes to AI-Factory are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Tagged releases live in
[GitHub Releases](https://github.com/alexar76/aicom/releases). The version
recorded in [`pyproject.toml`](pyproject.toml) is the source of truth.

## [Unreleased]

### Changed
- **Hub catalogue settle is seller-direct, like HESTIA.** A buyer pays USDC on-chain to the listing's `payout_address`; the hub verifies `PAYMENT-SIGNATURE` / the transfer (`aimarket_hub/settle.py`) and never holds the money. Wallet publishers are the payee. Channels remain the KI-11 custodial rail.
- **HESTIA well-known publishes `mcp_endpoint`.** Without it the Hub POSTed `/capabilities/{product}/{cap}/invoke` after a seller-direct settle; this host does not serve that path, so a paid catalogue sale 502'd. The field names `/ai-market/v2/invoke`, where agents are dispatched by `capability_id`.
- **Hub: a call that arrived without coordinates is incomplete input, not a refusal and not a miss.** `outcome=incomplete` stays on the live tape with its own counter; `refused` is a policy decision; only `ok`/`fail` move `success_rate` (API, SSR ticker, trust, i18n). Historical `fail` rows can be re-marked with `aimarket-hub/scripts/reclassify_incomplete_input.py` (dry-run default; `--apply` requires a live `--probe-url`).

### Fixed
- **One deposit could fund two channels.** The single-use deposit registry keyed a claim on the caller's chain label, while `AIMARKET_DEPOSIT_RPC_URL` verifies every label on the same node: one transfer opened a channel as `base` and another as `ethereum`. Every door now claims a transaction under the chain the verifier reads (`eip155:<chainId>`, the node's own `eth_chainId` when a label is overridden), under its own label (older claims still collide) and under every configured label of that chain; a claim file whose writer died is repaired after a minute (`channels.claim_deposit_exclusive`, `deposit_verify.registry_chain_id`).
- **The signup-grant budget failed on PostgreSQL.** `credit_ledger` windows used `datetime('now', ?)`, which the translator does not rewrite, and compared `NOW()` text in the session's zone; the 24-hour window is now read in Python from the newest rows, parsing any offset.
- **UniUSD logged its EIP-3009 authorization under the wrong topic.** The event was called `AuthorizationUsedEvent` (the error had taken the name `AuthorizationUsed`), so it logged `0x10d21bac…` where USDC — and the hub's verifier — use `0x98de5035…`: no EIP-3009 payment made inside the UNI bubble could ever have been verified (the UNI hub shows 0 settled x402 payments, 3 invoices). The event now carries USDC's name, the error is `AuthorizationAlreadyUsed`, and `contracts/evm/test/UniUSD.t.sol` pins the topic. The deployed bubble token needs a redeploy to pick it up.
- **The hub test suite crawled the live federation.** Test hubs are built from `HubConfig()`, whose seed list falls back to the committed `federation_seeds.json`, with auto-crawl on: every test hub alive past five seconds crawled `modelmarket.dev` and `independentai.network` — production traffic from a test run, and minutes spent waiting on real networks. `aimarket-hub/tests/conftest.py` now defaults `AIMARKET_AUTO_CRAWL=0`.
- **Hub A2A: a failed root still shows the bill it paid.** A root call over `/a2a` whose provider failed after its subcontractors delivered charged the buyer for those subcontractors (cost-plus, SUB/1 §6.3) but the `FAILED`/`REJECTED` Task kept only the error — no bill of materials, no `job_id`, nothing to explain the charge, while the REST answer carried both. The bill is now in the Task's `metadata.aimarket.subcontracting` in every end state (`aimarket_hub/a2a.py`).

### Added
- **Buying hub credit with USDC** (hub 3.8.0, `aimarket_hub/topup.py`, migration 041; [`aimarket-hub/docs/credits-topup.md`](aimarket-hub/docs/credits-topup.md) in five languages). An agent that is not the operator's can open an account and fund it itself: `POST /ai-market/v2/account/topup` answers a 402 whose x402 terms pay the operator's wallet by an EIP-3009 authorization over a nonce bound to that account; the buyer sends the transaction, and `POST /ai-market/v2/topups/{nonce}` — open to anyone, because the credit goes to the quoted account — reads the chain and credits it once. The transaction is claimed in the deposit registry the channel door shares, so one payment funds one thing. Paid credit is reported apart from granted credit (`topped_up_usd`). Off by default (`AIMARKET_TOPUP_ENABLED`). The operator's `POST /accounts/{id}/credit` takes a `tx_hash` for money no quote can match. Python SDK 2.5.0: `create_account`, `topup_quote`, `topup_redeem`, `topup_status` and `aimarket_agent.topup` (typed data and calldata, no key). Proven against a real EIP-3009 token on a local chain (`tests/test_topup_chain.py`), on SQLite and PostgreSQL. An independent review of the money path confirmed nine defects before it shipped, all fixed and each pinned by a test (`TestReviewFindings`): the quote failed on PostgreSQL; one payment could fund a top-up and a channel under another chain label; a transient database error refused a paid top-up for good; a credit could be half-written on the shared SQLite connection (now one transaction, `db_backend.atomic`) and `deposit()` retried without bound; an overpayment and cycling quotes passed `max_usd` and the daily limit (credit is now capped at the quote and the limit rechecked at redemption); a redemption blocked the event loop on the chain read; anyone could lock an owner out through the nonce's rate limit; and a claim whose writer died stranded the payment. A second, own review of the result found the rate-limit fix still gave every quote a budget of its own, which free accounts and never-expiring quotes multiplied into unbounded chain reads: the owner now spends its account's budget, and everyone else — another account's key included — its address's. The token's own `decimals()` is checked before quoting.
- **`scripts/security/rollout_container.py --set NAME=VALUE`** (repeatable): a container swap can now change a setting it names — and nothing else. Names are reported, values never; a malformed argument stops the swap before anything is touched. Used to switch USDC top-ups on inside the UNI bubble.
- **Rust SDK: `fetch_trusted_hashes()` and `verify_tee_receipt()`** (`aimarket-sdks/rust`), which the TypeScript and Dart agents already had: without the first a Rust client could check TEE attestations only against hashes pinned by hand. The Rust call returns an error where the others answer -1, so a hub that is down is not mistaken for one that trusts nothing. `scripts/check_ecosystem_parity.py` now compares the agent's public methods across the three SDKs by name — it compared models by field count only, which is how the gap passed as PARITY OK.
- **Agent subcontracting documented in five languages** ([`aimarket-hub/docs/subcontracting.md`](aimarket-hub/docs/subcontracting.md) · RU · ES · FR · ZH): the flow, where the money is at every step (holds, carves, captures, releases, with the live ledger), who carries which risk, mandates on top, the hub's checks and limits, the job token and how a provider verifies it, children on other hubs, A2A, errors and operator notes, with mermaid diagrams. Terms added to the glossary (`docs/localization-glossary.md`, "Mandate and subcontracting terms").
- **Subcontract canary over A2A** (`scripts/subcontract_canary.py --a2a`): the root call is an A2A 1.0 `SendMessage`, and the Task must come back `COMPLETED` and read back unchanged through `GetTask`. Passed live on `modelmarket.dev` on 2026-09-28. The hub suite now runs the canary over REST and A2A in both funding modes.
- **Production market rail documented in five languages** ([`docs/hestia-hub-market-rail.md`](docs/hestia-hub-market-rail.md) · RU · ES · FR · ZH): live topology, every Hub/HESTIA payment key, legal configurations (Hub till vs host till vs dual nonce), and a Base mainnet purchase of `json.canonical@v1` — one `USDC.transferWithAuthorization` to the seller (`payout_address`), Hub HTTP 200 after.
- **ATLAS can be paid: prepaid credit accounts (`atlas/atlas/credits.py`).** ATLAS published a
  price list and a free allowance of five calls an hour, and had no way to take money — the
  402 pointed at a hub payment channel, and the hub's own call to ATLAS lands on that same
  anonymous allowance. Measured: four cite-desks selling paid plans were capped at five runs
  an hour for all of their customers together (closes KI-12). A credited account is charged
  the published price per call in millicents (so $0.02 stays $0.02), is not subject to the
  free allowance, and is never billed for a refusal; a crashed request's reservation is
  released rather than left frozen, a ledger that cannot be read refuses the call instead of
  serving a paid product it cannot record, and the node refuses to boot if the ledger would
  not survive a redeploy. Accounts are operator-issued (`POST /ai-market/v2/accounts` with
  `X-Atlas-Token`), and a buyer can read its own balance at `/ai-market/v2/accounts/me`.
  Verified live: eight consecutive desk runs and seven invokes from the live Emberline host,
  all debited to the right account with the trial ledger untouched.

- **A thinning balance is visible before it stops the work.** The rail above still let an
  operator find out the same way as before: a customer's run failing on `supply_unpaid`. A
  charged response now carries `X-Atlas-Credit-Charged-Usd` / `-Balance-Usd` (and `-Low` at or
  under `ATLAS_CREDITS_LOW_BALANCE_USD`, default `$1.00`), ATLAS warns its operator in the log
  once per account per ten minutes — counted in remaining calls, not just dollars, since that
  is the number that says how long there is to act — and every desk in the family publishes
  what it last paid and has left at `/api/public/health` → `supply.credit`. The headers are
  parsed once in `desk_kernel.supply`, because the kernel and Emberline each run their own hub
  client and a balance visible in only one of them is a balance nobody watches. A desk that
  has bought nothing reports `null` rather than a balance of zero. Verified live: the low flag
  and the throttled warning on a deliberately small account, and the real balance appearing in
  tideline's and Emberline's health after real purchases.

- **The credit rail is documented in five languages
  ([`atlas/docs/CREDIT-ACCOUNTS.md`](atlas/docs/CREDIT-ACCOUNTS.md) · RU · ES · FR · ZH).** A
  paid rail that only its author can read is a rail nobody else can adopt: what a buyer sends,
  what the response headers mean, the `402` body it has to parse, every operator route, the four
  switches with their real defaults, and the rules the money keeps — reserved before the work,
  refusals unbilled, millicents so $0.02 stays $0.02, a fail-closed ledger against the
  deliberately fail-open free meter, no boot on an ephemeral ledger. It also states the limit
  plainly in all five: a prepaid balance is custody, with no escrow and no automatic refund.
  Guarded by [`atlas/tests/test_credit_docs.py`](atlas/tests/test_credit_docs.py), which reads
  the header and env names **out of the code** (a rename that missed the docs fails there),
  matches structure per language, and asserts the custody and rollout-order clauses survive
  translation — a localized `ATLAS_CREDITS_DB_PATH` is a rail that silently does not work. New
  glossary section in [`docs/localization-glossary.md`](docs/localization-glossary.md) for the
  prepaid vocabulary. ATLAS's advertised test count was stale in four places (`514`, and `101`
  in the RU README) and now says 624 everywhere.

### Fixed
- **A desk buys each SKU from whoever actually sells it (`GAIA_HUB_URL`).** Pointing the desks
  straight at ATLAS is what made prepaid accounts work, but ATLAS sells only `atlas.*` and
  answers `404 unknown capability` for a sensor relay: seamark's every run failed on
  `gaia.ais.public.read@v1` while its ATLAS balance sat untouched and the desk looked fully
  configured. `gaia.*` now goes to a second upstream with its own prepaid key; a URL without a
  key refuses instead of dropping to the anonymous five-an-hour allowance, a payment channel is
  only ever sent to the origin that issued it, and a desk with one seller is untouched.
  `supply.credit` names the `seller` whose balance it is, since one healthy account is not
  evidence that the other is funded. Verified live: seamark now completes with
  `evidence_status: live_evidence` off both sellers.

- **`https://modelmarket.dev/mcp` — the hub's MCP gateway at the apex, with the trial tier
  reaching it.** The gateway already existed at `/ai-market/mcp`, but it sent no visitor
  header, so a stranger's first `market_invoke` met the payment wall instead of the free
  trial, and it forwarded no `source_hub`, so federated capabilities — most of the
  catalogue — answered 404. Both fixed, the identity derived **per caller** (a shared one
  would spend the whole allowance on whoever arrived first), and the endpoint advertised
  first in `mcp_servers`. Docs: [`docs/hosted-mcp-endpoint.md`](docs/hosted-mcp-endpoint.md).
  An adversarial review of the first cut found and fixed four more: the trial identity is
  attached only to **priced** capabilities (the hub consumes a trial before it reads the
  price, so a free capability was capped at three calls); a spent allowance is re-asked
  without the identity so the caller gets the **402 with a price** instead of a bare `429
  trial_quota_exhausted`; the internal invoke goes to **loopback**, because routing it
  through the public URL let nginx append its own hop and the named caller was discarded,
  putting every visitor in one rate-limit bucket; and `GET /mcp` now answers **405** to a
  stream probe rather than a JSON body the client reads as a dropped stream.
- **`scripts/payment_canary.py`** — external check that a priced capability still answers
  402, that the manifest still reports `payment_configured`, and that `/mcp` still answers
  with a per-caller trial. Probes behaviour rather than the manifest's self-report, because
  those came apart once already. Non-zero exit for cron; `--publish` writes a status JSON.
- **`scripts/deploy_hub_rebuild.sh`** — hub redeploy that copies the live container's
  environment forward, refuses to start if the payment interlock did not survive, verifies
  `/mcp` + `payment_configured`, and rolls back automatically. Payment enforcement has been
  silently dropped by a redeploy twice (2026-07-31, 2026-08-04).

### Changed
- `aimarket-mcp` HTTP mode is safe to expose publicly: per-caller trial identity via a
  context variable (stdio keeps its per-install one), client address read only from a
  declared proxy and from the rightmost hop, `AIMARKET_MCP_PUBLIC` as the explicit opt-in
  for anonymous access in production, CORS + spec-correct `GET`/`DELETE` handling, and
  uvicorn's own `proxy_headers` disabled — it trusts the leftmost, caller-written
  `X-Forwarded-For` entry, which would have made every allowance forgeable with one header.

### Changed
- **KI-1 resolved — ZK migrated to PLONK.** The `input_validity` circuit now
  uses a PLONK backend (universal setup, public Powers-of-Tau) — **no
  per-circuit trusted-setup ceremony**. Committed `verifier/Verifier.sol`
  (`PlonkVerifier`) + `verification_key.json`; new `setup_plonk.sh` (also fixes
  the dead ptau URL); `AIMARKET_ZK_BACKEND=plonk` in the prover and prod guard.
  Verified end-to-end (`snarkjs plonk verify → OK!`). Groth16 path kept optional.

### Fixed
- **`atlas/docker-compose.yml` stopped blanking the secrets the operator had configured.**
  Six `environment:` entries were written as `${VAR:-}`, and an `environment:` entry
  overrides `env_file` while `${...}` interpolates from the shell or the project directory —
  never from the `../.env` those values actually lived in. So a 48-character
  `ATLAS_OPERATOR_TOKEN` became `""` on every deploy and `_operator_ok` refused everyone (the
  watchbox registry admin path and credit issuance were locked out), the analyst ran with no
  LLM provider at all while a working DeepSeek key sat in `../.env`, and the federation
  signing identity depended on a volume file instead of the configured seed. A test now
  fails on any `environment:` entry with an empty default.
- hub cross-hub local invoke returned 503 without a backend — `AIMARKET_SANDBOX_STUB_INVOKE`
  now also covers local invoke; hub test suite green out-of-the-box (302 passed).
- hub version aligned to `3.0.0` across `__init__`, config default, and README.
- root README: 14 satellite links repointed to standalone repos (404'd on the
  trimmed public GitHub mirror).

## [2.1.0] — 2026-06-06

Public trust & reproducibility release for the factory line.

### Added
- **Honest factory CI** (`.github/workflows/ci.yml`): backend pytest + coverage badge
  generated in Actions, strict frontend `typecheck` / `lint` / `build` (no
  `continue-on-error`), security benchmark, customer API smoke.
- **Security scan workflow** (`.github/workflows/security-scan.yml`): Bandit High
  blocks; pip-audit + npm audit reports uploaded as artifacts.
- **`scripts/quickstart.sh`** — clone → one command → Docker + demo enqueue.
- **`docs/sample-output/`** — static build replay JSON (see without running Docker).
- **`scripts/export_sample_build_replay.py`** — regenerate sample replay from code.

### Changed
- Coverage badge (`docs/badges/coverage.svg`) refreshed by CI on `main`, not
  hand-edited locally.
- `python-multipart` bumped to ≥ 0.0.18 (KI-5 partial).
- KI-3: `USE_SQLITE=true` forces `UVICORN_WORKERS=1`; crash telemetry appended to
  `uvicorn-last-crash.log`.

### Removed
- CI lint `continue-on-error` escape hatch (ROADMAP “Now”).

[Unreleased]: https://github.com/alexar76/aicom/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/alexar76/aicom/releases/tag/v2.1.0
