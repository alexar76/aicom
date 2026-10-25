# Changelog

All notable changes to AI-Factory are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Tagged releases live in
[GitHub Releases](https://github.com/alexar76/aicom/releases). The version
recorded in [`pyproject.toml`](pyproject.toml) is the source of truth.

## [Unreleased]

### Added
- **HISTOR 0.3.0: a restart no longer costs the crawl.** A redeploy continues the interrupted cycle however long it has run, as long as it was making progress (only a process down for a whole interval starts afresh); until now a cycle was dropped once its start was a day old, and on 2026-10-22 one 42 hours and six restarts in was dialled again from the first server. A cycle plans its packages once and keeps the plan (migration 012, `crawl_plans`), so a continued run skips the hour of npm/PyPI version lookups and the sandbox budget and the classifier budget are the cycle's, not each run's. A run saves its counts every 30 s; an interrupted run is marked with its cycle's totals read back from the database; `/api/v1/stats` reports the cycle (`lastRun.cycle`) and counts progress over it (`crawl.progress.thisRun` beside it). `docs/operations.md` § A restart mid-crawl, five languages.
- **HISTOR 0.3.0: what a tool list costs, part by part, per change and in a package's CI.** Every count is split into the tool names, the descriptions, the input schemas and the keys and punctuation around them (they add up to the total; output schemas and the list as listed beside it), counted as `histor/docs/tool-list-cost.md` counts (`o200k_base`), and each top-level input property is counted too, so a diff names the field that grew. The service gives each change its cost diff (`/api/v1/changes/<id>/cost`), a server its current cost and the totals of its last changes (`/api/v1/servers/<id>/cost`) and any stored set its cost (`/api/v1/cost/toolsets/<digest>`); the image bakes the tokenizer table in, and a deployment without the new `cost` extra answers 503. `histor tool-cost snapshot | check | diff` counts a server started over stdio, a streamable HTTP endpoint or a saved tools/list, compares it with a committed baseline and exits 1 when the total, the descriptions or the input schemas grow past a limit, with a Markdown table for the job summary. The public counter at modelmarket.dev/tools/tool-list-cost shows the same split (`parts`, and description and input schema per heavy tool); the split is identical in both, checked on the same tools. Asked for by a reader of the tool-list-cost post (Raju Dandigam).
- **Hub 3.16.0: owner approval above a threshold.** A mandate's `limits.approvalAbove` makes any single call that costs more wait for a signed approval from an owner of the funding account, bound to that call's exact bytes and ceiling and used once with its reservation (`aimarket-protocol/mandates.md` §5.6, migration 054). The API key alone can deny, never approve. SDK `aimarket-agent` 2.6.0: `issue_mandate(approval_above_usd=…)`, `approval_payload()`.
- **Hub 3.16.0: A2A push notifications and `returnImmediately`.** Clients register webhooks per task (`taskPushNotificationConfig` and the four config methods) and hear every state change as a `statusUpdate`, including the ones no request of theirs causes: a detached run finishing, an owner answering an approval, the sweep expiring a task. Webhooks get the outbound SSRF rules; pushes never carry artifacts (migration 055, `docs/a2a.md`).
- **Hub 3.16.0: owners hear about approval requests in Telegram, Slack, Jira or a webhook.** The funding account registers channels (`/ai-market/v2/mandates/notify`, up to 8; migration 058) and each new request — and the answer to it — is sent there: a Telegram message from the hub's bot (`AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN`) or the owner's own, a Slack incoming webhook, a Jira Cloud issue per request with the answer as a comment, or a signed JSON webhook. A notification never approves; channel secrets are never returned; addresses get the outbound SSRF rules; a test route shows what the channel answered (`aimarket-hub/docs/mandates*.md`, five languages).
- **Hub 3.16.0: an A2A task survives a restart mid-call.** A running task holds a lease its process renews, and its call journals the reservations it makes. A task whose process died is taken over by the next A2A request or the hub's own minute sweep and settled from the ledger: an unsent or merely reserved call is released (mandate limits and approvals come back) and waits for a follow-up; a charged one fails naming its receipts; a rail the hub cannot read back fails as `unknown` (migration 059, `aimarket-hub/docs/a2a.md`). It replaces "marked FAILED after 30 minutes" and the money it left frozen.
- **Hub 3.16.0: card top-ups choose who owes the sales tax.** `AIMARKET_CARD_TOPUP_TAX` = `off` (default), `stripe_tax` (Stripe Tax computes it from the billing address; the operator stays the seller) or `managed_payments` (Stripe is the merchant of record). The mode, tax behavior and tax are kept on each checkout's row, amounts are checked as subtotal + tax, `charge.refunded` is recorded, and an unknown setting shuts the door (migration 057). The Stripe client now sends a urlencoded body: the httpx `data=` list it used was refused (found against the Stripe sandbox; a $5 sandbox payment was then credited by webhook exactly once).
- **Hub 3.16.0: card top-ups through Stripe Checkout, off by default.** The same paid-credit ledger line as a USDC top-up; the webhook is signature-checked and every figure is compared with the checkout the hub opened, credited once per session; a refresh route recovers a lost webhook (migration 056, `docs/card-topup*.md`).
- **Factory external diagnostics (opt-in).** Repeated, file-bound QA findings can trigger one bounded AIMarket purchase before an internal repair. Approved providers, source scope, pinned hybrid receipt verification, durable SQLite reservations, ambiguous-payment recovery and combined LLM/purchase cost admission preserve the normal QA gates. Includes an operator reconciliation CLI and complete EN/RU/ES/FR/ZH documentation in `docs/factory-subcontracting*.md`.
- **Hub discovery declares `credits_eligible`.** Buyers can filter out seller-direct or federated offers before making a credits-funded call; the predicate matches invoke admission.

### Changed
- **Hub catalogue settle is seller-direct, like HESTIA.** A buyer pays USDC on-chain to the listing's `payout_address`; the hub verifies `PAYMENT-SIGNATURE` / the transfer (`aimarket_hub/settle.py`) and never holds the money. Wallet publishers are the payee. Channels remain the KI-11 custodial rail.
- **HESTIA well-known publishes `mcp_endpoint`.** Without it the Hub POSTed `/capabilities/{product}/{cap}/invoke` after a seller-direct settle; this host does not serve that path, so a paid catalogue sale 502'd. The field names `/ai-market/v2/invoke`, where agents are dispatched by `capability_id`.
- **Hub: a call that arrived without coordinates is incomplete input, not a refusal and not a miss.** `outcome=incomplete` stays on the live tape with its own counter; `refused` is a policy decision; only `ok`/`fail` move `success_rate` (API, SSR ticker, trust, i18n). Historical `fail` rows can be re-marked with `aimarket-hub/scripts/reclassify_incomplete_input.py` (dry-run default; `--apply` requires a live `--probe-url`).

### Fixed
- **Local security closure (2026-10-25).** Rechecked all eight Vulnetix findings and
  closed additional paths found across the ecosystem: administrative sessions now
  track the live account and are revoked on logout or security changes, including
  concurrent password resets; customer source ZIPs exclude secrets, runtime state
  and filesystem links; WARDEN/ARGUS reject alternate IPv6 spellings of private
  destinations; HESTIA uses the same canonical tenant route for payment and dispatch;
  MCP/ARGUS/DIOSCURI bound remote response reads, and development service ports bind
  loopback. Updated affected Python, npm, Rust and Go dependencies and the Node image
  security baseline, and expanded dependency scanning to previously omitted products.
  Regression checks use local fixtures. Changes remain local; released packages and
  running services require their normal release/deployment process.
- **Our own audit for the classes Vulnetix found (2026-10-25).** The same mistakes elsewhere in the
  monorepo, found by searching for each class and fixed with tests:
  - Open without a key (CWE-306, as in aimarket-mcp): metis 0.2.2 (`metis-serve`, `metis-coordinator`,
    `metis-node`), aimarket-platon 0.1.4 (steer/project writes, both copies) and aimarket-treasury 0.1.2
    (payout routes) answered every caller when no key or token was set outside production, on ports
    bound to 0.0.0.0. Without one they now answer only callers on the machine itself (loopback peer
    and `Host`, no forwarding headers, no cross-site `Origin`).
  - Check, then connect by name again (CWE-918, as in signal-hunt): ATLAS 0.3.2 watchbox webhooks
    (checked once, then up to five posts by name over ~3 minutes), aimarket-mcp 0.6.2 `web_fetch`
    and alien-monitor peer discovery (HTTPS was never pinned), Emberline's alert webhooks and HESTIA
    0.1.3's domain-proof fetch. Each request now goes to the address that passed, with the name in
    `Host` and TLS SNI. NAT64 and 6to4 forms of private IPv4 addresses are refused by aimarket-mcp,
    EMPORION 0.4.2's page capture, HISTOR's crawler guard and HESTIA.
  - Caller headers believed from anyone (CWE-307/CWE-770, as in skopos-fleet): rate-limit and lockout
    keys in aimarket-oracle-core 0.6.1 (which also decides the paid tier), PLATON, logos 0.2.1, the
    three attested services, BASANOS, KOVA, the verified-execution hub and cite-desks took
    `X-Real-IP` / `X-Forwarded-For` from any peer. They now do so only when the peer is the local
    proxy (loopback, private or link-local), and read the right-most forwarded hop.
  - SSH host keys (CWE-295, as in skopos-fleet): SKOPOS remediation `git push` ran with
    `StrictHostKeyChecking=no`; it now pins the first key in `~/.skopos/known_hosts`.
  - No new cases of rights taken from a producer's data (CWE-863), of incomplete external lists
    (EMPORION serves OFAC 19,471 / EU 6,269 / UK 6,408 entries) or of sandbox-trace gaps beyond HISTOR.
- **Three more findings Vulnetix reported on 2026-10-24 (advisory-database issue #5), fixed.**
  - helios-broadcast 0.2.1 (GCVE-110-PYPI-2026-021897, CWE-863): a job's `youtube.privacy` from the
    shared queue decided the upload's visibility, so a queue producer could publish without
    `helios approve`. Uploads are always private; ingest drops a requested privacy and audits it.
  - skopos-fleet 0.2.1 (GCVE-110-PYPI-2026-021896, CWE-307): the login lockout keyed on a header any
    direct caller could set. Keyed on the websocket peer now, headers trusted only from the local
    proxy, plus an all-addresses failed-login budget. Host keys were already verified since 0.2.0.
  - aimarket-histor 0.4.1 (GCVE-110-PYPI-2026-022091, CWE-693): the sandbox trace did not record or
    parse rename/link/symlink/creat and never reported writes under /work. Recorded, parsed and judged
    now; .pth/sitecustomize and post-install code writes are persistence; a trace runtime missing those
    calls counts as no trace.
- **Hub home page: a dictionary that does not arrive no longer turns the page into its keys.**
  When `hub-ui-i18n.json` failed or took over 4 s, the page installed an empty dictionary and
  wrote every key over the English the server had rendered: the tab read `page_title`, the page
  NAV_WIDGET, SEARCH_BTN, S_CAPS (seen on modelmarket.dev, 2026-10-24). The server now inlines
  `ui.en` into the page, each element keeps its served text as the fallback, the fetch gets 10 s
  and the HTTP cache, and a failed load is retried three times.
- **Five findings Vulnetix reported on 2026-10-24 (advisory-database issue #5), fixed.**
  - EMPORION 0.4.1 (GCVE-110-PYPI-2026-021807, CWE-693): OFAC continues long SDN remarks in
    `SDN_COMMENTS.CSV`, sometimes mid-address; only `SDN.CSV` was read, so 538 of 1,050 listed
    wallet addresses screened as not listed and 17 cut halves were kept as addresses. Both
    files are fetched and joined before addresses are read; a load fails without the second, an
    OFAC snapshot cached before the fix is not served, and a byte-order mark is ignored.
  - aimarket-mcp 0.6.1 (GCVE-110-PYPI-2026-018883, CWE-306): with no `AIMARKET_MCP_KEY` the
    HTTP server answered any peer on `0.0.0.0`. It now binds `127.0.0.1` by default (the HTTP
    image sets `0.0.0.0`). Without a key, and unless `AIMARKET_MCP_PUBLIC=1`, it answers only
    callers on the machine: a loopback packet with a loopback `Host`, no forwarding headers (a
    proxy on the same host) and no cross-site browser `Origin` (a web page, DNS rebinding).
  - aimarket-signal-hunt 0.1.2 (GCVE-110-PYPI-2026-021946, CWE-918): the peer probe checked the
    resolved addresses, then connected by name and resolved again (DNS rebinding). It now
    connects to the checked address, with the name in `Host` and in TLS SNI so the certificate
    is still verified against it, and keeps no connection alive between probes. It keeps the
    resolver's address order (dual-stack peers), sends IDN names in ASCII, ignores proxy
    settings for probes, and refuses IPv6 forms that carry a private IPv4 (NAT64, 6to4, mapped).
  - aimarket-hestia 0.1.2 (GCVE-110-PYPI-2026-020712, CWE-863): an open-signup key's code right
    was stored while `HESTIA_OPEN_OWNER_CODE` was on and outlived a switch to the stub runtime,
    where a restart also brought that key's handlers back as plain child processes; an
    operator's routine update of such a key (quota, suspension) wrote the right again. One rule
    (`hestia.owners.code_right`) now decides an owner's deploy, the operator's deploy for an
    owner, a restart and an owner update: an open-signup key runs code only in the wasm
    sandbox, a suspended owner runs none, otherwise the operator's grant. Owner updates change
    only the fields they name, taking the right away stops the owner's running stub handlers at
    once, and migration 010 clears the rights self-admission had stored.
  - Hub (GCVE-110-PYPI-2026-004375, CWE-918): already fixed, but later than the record says. Every
    release from 3.0.0 to 3.2.1 POSTed to a peer's `mcp_endpoint` as advertised (3.0.0 and 3.1.0
    for oracle-like peers, 3.2.x for all). The same-origin check (2026-09-04) first shipped in
    3.7.0; the record's range should be 3.0.0–3.2.1, fixed in 3.7.0.
- **From an outside review of 2026-10-22** (SUB/1, the credits ledger, WARDEN `wrap`, KI-3/4/9/11; full table in `docs/known-issues.md` § Outside review fixes):
  - hub credits ledger: resolving a hold and carving a child out of an allowance each committed in two steps, so a process killed in between — or another request's failed statement on the shared SQLite connection — lost the money; every money move is now one transaction (`tests/test_ledger_crash_consistency.py`, 8 of 11 failed before);
  - SUB/1: a child could join a call that was finishing (check and insert were two transactions); a child hold left by a crash was never released; the grant was sent to plain-`http` public providers — all fixed, with races also run on PostgreSQL (`tests/test_money_races_postgres.py`, CI job `money-postgres`);
  - signup grants: budget check and grant are one serialized transaction; on PostgreSQL the two-step version minted $0.30–$0.45 against a $0.25 daily budget;
  - a mandate document unreadable mid-chain now refuses the chain instead of shifting the revocation check (found by the new ruff gate over the hub's money paths);
  - WARDEN `wrap` enforces `policy.sensitiveToolPatterns` (it accepted and ignored them): each call asks a person through MCP elicitation or is refused; ARGUS matches patterns against the MCP server's tool name too;
  - factory backend: with `UVICORN_WORKERS > 1` only one worker (a `flock` holder) runs the background loops; KI-3 crash telemetry gets its own file instead of being overwritten by the next start's log rotation; the supervisor's `/api/health` probe is no longer counted or throttled by the per-address limiter, which answered it 403 under load and got a busy backend killed, and a 403/429 reads as alive;
  - hub: `Idempotency-Key` on paid invokes (credits rail and ledger channels) — a retry after a timeout replays the first answer instead of paying again (migration 061); `aimarket-hub/scripts/load_money_path.py` puts the money path under load and audits the ledger afterwards;
  - `scripts/check_ki4_ownership.py` measures KI-4 (owner, pending owner, escrow USDC) on Base; `escrow-signer/deploy/signer-hub-only.sh` narrows the signer forward to the hub container (installed on factory-vps 2026-10-23).
- **Performance, from the 2026-10-23 public load test** (tables before and after in `docs/load-testing.md`, five languages): the pipeline worker no longer re-parses the YAML config for every product on every cycle (92% of its CPU in a live profile; ~89% of a core → 16%); the storefront grid assesses each product once per request, prunes `node_modules` from its HTML walk and reuses a built grid for 30 s (median 7.3 s → 0.22 s at 20 users); the trust strip reads products only instead of all 3,510 tasks and is cached a minute off the event loop (4.7 s → 0.18 s), which also brings factory `/api/health` p95 from 3.8 s to 0.43 s; the hub logs one warning per ACEX ledger that is off by configuration instead of 311 tracebacks a day; the director keeps a discovery cycle when one enrichment gets an empty model answer; the monitor runs its blocking satellite polls in a worker thread (written and tested, not yet deployed).
- **Hub 3.16.0, from an independent review of the approvals, push and card top-up work** (each pinned by a test that fails without its fix):
  - one owner approval paid for any number of routed calls: a peer answering below its catalogue price made the hub release the fee hold and debit the smaller fee, and the release handed the approval back although the call was charged — it now stays spent with the debit;
  - an owner was asked to approve calls the mandate's own `perCall`, `perDay`, `total` or product limit would refuse — those are now `402 mandate_limit` before any request is opened;
  - over A2A, a federated peer's `402 approval_required` was taken at its word: the task waited on a request this hub never held, for as long as the peer said, keeping the buyer's input — only a request in this hub's own store, for this mandate and these bytes, is a wait now;
  - an owner who answered while the A2A call was still running was never heard: the task waited on an answered request until it expired — the run now checks once more as it records the wait;
  - push deliveries held their slot through the retry pauses, so 16 failing webhooks delayed every other task's push by ~42 s; a slot is now held for one attempt, and the pending queue is capped;
  - outbound address checks (webhooks, peers, providers, the crawler) resolved names with a blocking `getaddrinfo` on the event loop, so one slow nameserver froze the hub — they run in a thread now; the pinning lookup applied a shorter blocklist than the validation lookup, letting a name rebind to a benchmark or documentation range between the two — both use `crawler._addr_is_blocked`;
  - concurrent card checkouts could together pass the daily limit, a refunded top-up stopped counting toward it although its credit stays, and a top-up's state writes could be rolled back by another request's failing statement on the shared SQLite connection (a paid checkout that could never be credited).
- **Card top-ups: a dispute or refund that Stripe delivers before the paid-session event was ignored.** It is now associated through the session's payment, the session is reconciled with every amount check, and the reversal recorded; a late paid event cannot credit again. Verified in the Stripe sandbox: refunds of $5.00 and $6.05 (with tax) succeeded, two disputes reached the hub as `disputed`, and redelivered events added no credit (`aimarket-hub/docs/evidence/stripe-sandbox-2026-10-21.json`).
- **The subcontracting suite hung on PostgreSQL.** A late child refused on a finished parent left the request's connection "idle in transaction" after an uncommitted insert, and the next write to that row waited forever; the insert is committed where it is made (`subcontract._ensure_node`).
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
