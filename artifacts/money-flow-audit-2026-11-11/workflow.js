export const meta = {
  name: 'aicom-money-flow-audit',
  description: 'Audit aicom: 13 zone finders (payments, stuck funds, flow errors, holes) + 6 adversarial verifiers',
  phases: [
    { title: 'Find', detail: '13 read-only finders, one per money/flow zone' },
    { title: 'Verify', detail: '6 adversarial verifiers, one per zone group' },
  ],
}

const REPO = args.repo
const SCR = args.scratch

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
          category: { type: 'string', enum: ['money-loss', 'money-stuck', 'double-charge', 'unpaid-service', 'security-hole', 'flow-error', 'logic-inconsistency', 'doc-code-mismatch', 'reliability'] },
          file: { type: 'string' },
          line: { type: 'integer' },
          mechanism: { type: 'string' },
          failure_scenario: { type: 'string' },
          evidence: { type: 'string' },
          prod_reachability: { type: 'string' },
          reproduced: { type: 'boolean' },
          repro_notes: { type: 'string' },
          suggested_fix: { type: 'string' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
        required: ['title', 'severity', 'category', 'file', 'line', 'mechanism', 'failure_scenario', 'evidence', 'confidence'],
      },
    },
    files_read: { type: 'array', items: { type: 'string' } },
    not_covered: { type: 'string' },
  },
  required: ['findings', 'files_read', 'not_covered'],
}

const VERDICTS = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          verdict: { type: 'string', enum: ['CONFIRMED', 'PLAUSIBLE', 'REFUTED', 'DUPLICATE'] },
          duplicate_of: { type: 'string' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
          reasoning: { type: 'string' },
          reproduction: { type: 'string' },
          prod_reachability: { type: 'string' },
        },
        required: ['id', 'verdict', 'severity', 'reasoning'],
      },
    },
  },
  required: ['verdicts'],
}

const RULES = `
REPO = ${REPO} (a git worktree of the aicom monorepo on main, commit 4dd2c4a0f). This is the alexar76 AI-market ecosystem: federated "hubs" (aimarket-hub, Python/FastAPI, SQLite or Postgres) that sell agent capabilities for credits, USDC deposits, payment channels, an on-chain escrow on Base (AIMarketEscrowV2) with a separate escrow signer (HORKOS), x402 payments, Pay-on-Verified settlement with a Metis jury, mandates/A2A/subcontracting, plus satellite services (desks with Stripe card checkout, lottery, treasury, HISTOR Watch paid tier, esim/domain stores, OKX A2MCP x402 gateway).
The owner asked (in Russian): audit the ecosystem; look for bugs, holes, logical inconsistencies, payment failures, money hanging/stuck on nodes, flow errors.

HARD RULES
- READ-ONLY on the repo: do not edit, create, move or delete any file under REPO; no git commit/checkout/switch/stash/reset/branch/push/merge; no ssh; no HTTP requests to production hosts (modelmarket.dev etc.); no on-chain transactions. Reading branches is fine via \`git show <branch>:<path>\`.
- You MAY write throwaway scripts/tests ONLY under your scratch dir (given below; create it with mkdir -p) and run them. Python hub tests: \`cd ${REPO}/aimarket-hub && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q <scratch>/test_x.py\` (the hub venv has the package deps; import the module from ${REPO}/aimarket-hub). Other components: use their own venv/node_modules if present, otherwise trace by reading. Keep each run bounded (< 3 minutes). Never put secrets in output.
- Production note: the six live hubs do not run main exactly (apex modelmarket.dev = 3.17.0 + overlays incl. the x402 bridge from branch x402-bridge-20261108; others on older 3.15/3.16 lines). Audit main (and that branch where your zone says so). In prod_reachability say which env flag/default the path depends on.
- Many previous audits fixed issues. Before reporting, check \`git log --oneline -8 -- <file>\` and look for guards (caller-side check, DB unique index or constraint in migrations.py, transaction/lock, middleware, config default, a sweep/reaper elsewhere that grep finds for the same table/state). A finding must name code that is wrong TODAY.

WHAT TO LOOK FOR (priority order)
1. Money lost or created: balance minted, double credit, double payout, charge without delivery, payout without debit.
2. Money stuck: reserved/held/escrowed/deposited/channel funds with a path where nothing ever releases, refunds, sweeps or pays them (missing timeout, sweep query that skips a state, crash between two writes, exception path, restart losing in-memory state).
3. Security holes on money-moving or state-changing paths: missing auth, IDOR (acting on another account's id), replay (tx hash, signature, receipt, idempotency key across accounts/hubs/chains/contracts), SSRF, trusting client- or peer-supplied amounts/addresses.
4. Flow errors: state machines that dead-end, retries that double-apply, success not recorded, error responses that make a client retry an already-charged call, background jobs that can silently stop.
5. Logic inconsistencies between components: units/decimals (USDC 6 decimals vs cents vs micro-credits vs float), price used for quote vs charge, rounding direction, spec/docs vs code, SQLite vs Postgres behavior differences.
Check these invariants systematically: conservation (each debit has exactly one matching credit/payout/refund); idempotency under retry AND concurrency (two identical requests at once; check-then-act across an await; SELECT then UPDATE without a row lock or conditional UPDATE ... WHERE balance >= x); atomicity (two writes not in one transaction); every failure/timeout/cancel/client-disconnect path releases reservations; every held state has an exit; negative/zero/NaN/huge amounts.

DO NOT REPORT: style, missing tests/docs alone, theoretical issues with no reachable path, dependency CVEs, attacks that need a compromised server or stolen operator keys.

OUTPUT: concrete findings with repo-relative file, line, a short code quote as evidence, and a failure scenario (state/inputs -> wrong outcome). Try to reproduce the 2-4 most serious ones with a scratch test (reproduced=true + repro_notes). Severity: critical = funds can be stolen/minted or many users' funds stuck with no recovery; high = real money loss/stuck for a user in a plausible flow, or an auth hole on money; medium = edge-case money error or flow dead-end with a workaround; low = minor inconsistency. Precision over volume: 3-15 well-evidenced findings is a good result; zero is fine if the zone is sound. Fill files_read with files you actually read and not_covered with what you skipped.`

const H = 'aimarket-hub/aimarket_hub/'
const ZONES = [
  { key: 'credits', title: 'Hub credit ledger, top-ups, accounts, idempotency',
    focus: `Files: ${H}credits.py, ${H}topup.py, ${H}card_topup.py, ${H}hub_routes/accounts.py, ${H}hub_routes/payments.py, ${H}idempotency.py, ${H}deposit_claims.py, ${H}payment_profiles.py, ${H}time_locked_promo.py, ${H}sandbox_trials.py, credit tables in ${H}database.py / ${H}db_backend.py / ${H}migrations.py. Docs: aimarket-hub/docs/credits-topup.md, card-topup.md, money-rails.md.
Questions: can a balance go negative or be debited twice concurrently (SQLite vs Postgres: is the debit a conditional UPDATE or read-modify-write)? Is the idempotency key scoped per account and bound to the request body, and what happens on a replay with a different body or while the first is in flight? Card top-up (Stripe): webhook signature, double credit on webhook retry or on both redirect+webhook, refunds/chargebacks/disputes clawback, amount/currency taken from the client. Signup grants / trial credits: farmable? Promo codes: reusable/raceable? Account deletion or key rotation with a positive balance or open reservations.` },
  { key: 'invoke-local', title: 'Local invoke funding: reserve, charge, release',
    focus: `Files: ${H}invoke_funding.py, ${H}hub_routes/invoke.py, ${H}hub_routes/invoke_parts/local_admission.py, ${H}hub_routes/invoke_parts/local_delivery.py, ${H}invoke_outcome.py, ${H}streaming.py, ${H}safety_gate.py, ${H}request_guards.py, ${H}hub_routes/rate_limits.py, ${H}spot_auction.py, ${H}native_price.py. Docs: aimarket-hub/docs/money-rails.md, traffic-classes.md, agent-first-call.md.
Questions: trace a paid invoke end to end — where is the allowance reserved, when is it captured, and does EVERY exit (provider error, timeout, exception, client disconnect mid-stream, safety-gate block after reserve, asyncio cancellation, process restart) release or refund it? Is there a reaper for orphaned reservations? Can the same call be charged twice on client retry (idempotency)? Is the charged price the quoted/listed price at admission or re-read later (price change race)? Free-SKU / trial quota paths: can paid work run free? approvalAbove / returnImmediately (async) billing.` },
  { key: 'federation', title: 'Federated invoke money between hubs',
    focus: `Files: ${H}hub_routes/invoke_parts/federated_admission.py, ${H}hub_routes/invoke_parts/federated_delivery.py, ${H}peer_routing.py, ${H}peer_operations.py, ${H}hub_routes/federation.py, ${H}refund_client.py, ${H}pipeline_payments.py, ${H}pipeline_refunds.py, ${H}pipeline_relay.py, ${H}pipeline_client.py, ${H}pipeline_provider.py, ${H}pipeline_references.py, ${H}payer_proof.py, ${H}revenue_proofs.py, ${H}observed_sellers.py, ${H}federation_transport.py. Docs: aimarket-hub/docs/federation-admission.md, money-rails.md, one-call-pipelines.md, aimarket-protocol/ (payment and receipt sections).
Questions: buyer hub debits its user then forwards to a peer — what happens when the peer fails, times out, returns garbage, or succeeds after the buyer hub gave up (double outcome)? Are refunds idempotent and is a refund request authenticated (can a peer or user trigger refunds/credits they are not owed)? Who settles inter-hub balances and can they diverge forever? Is the price the peer charges bounded by what the buyer was quoted? Pipelines: multi-step paid pipelines where step N fails — are steps 1..N-1 refunded or paid, and consistently?` },
  { key: 'channels', title: 'Payment channels and channel ledger',
    focus: `Files: ${H}channels.py, ${H}channel_ledger/opening.py, ${H}channel_ledger/spending.py, ${H}channel_ledger/storage.py, ${H}channel_ledger/sweeps.py, ${H}hub_routes/channels.py, ${H}provider_buyer_ref.py, ${H}provider_request_auth.py, ${H}wallet_coordinator.py, ${H}factory_wallet.py. Docs: aimarket-hub/docs/money-rails.md.
Questions: channel open from a deposit (double open from one deposit?), spending (monotonic voucher/nonce, concurrent spends on one channel — a race once lost 120/240 debits; check the fix covers every spend path), channel expiry/close: do unspent funds go back to the buyer or stay stuck? Sweeps to chain: what if a sweep tx fails or is never mined — is the ledger marked swept anyway? Secretless channels, chref refs, 402 responses leaking balances. Provider payouts from channels.` },
  { key: 'escrow', title: 'Escrow bridge, settlement sweep, escrow signer (HORKOS), seller-direct settle',
    focus: `Files: ${H}escrow_bridge/*.py (authorization, chain, collector, config, eip712, escrow_verify, mirror, signer, store, cli), ${H}settle.py, ${H}settlement_service/scheduling.py, ${H}settlement_service/finalizing.py, ${H}slash_sync.py, ${H}contracts_declaration.py, ${H}deployments/base-mainnet.json, and the separate signer escrow-signer/escrow_signer/*.py (policy.py, ledger.py, server.py, eip712.py, chainio.py, calldata.py). Docs: aimarket-hub/docs/money-rails.md, escrow-signer/README.md, escrow-signer/docs.
Questions: debit authorized/signed but never submitted on-chain (crash between DB write and tx; sweep skipping states); nonce handling and stuck pending txs; EIP-712 domain binding (chainId, verifyingContract, escrow version V1 vs V2) and signature replay; signer policy limits (per-debit/per-day caps, who may request a signature, can the hub get a signature for more than the user authorized); mirror vs chain divergence; seller-direct settle (two Transfer legs, receiveWithAuthorization) — replay of a tx hash for two orders, wrong token contract, partial amounts.` },
  { key: 'contracts', title: 'Smart contracts (EVM, Solana, lottery)',
    focus: `Files: contracts/evm/src/AIMarketEscrowV2.sol, AIMarketEscrow.sol (V1, superseded but deployed), MarketSplitter.sol, BountySplitter.sol, AIMarketCapabilityNFT.sol, UniUSD.sol, plus contracts/evm/test, contracts/evm/script, contracts/solana (if programs exist), lottery/contracts/src and lottery/contracts/test, contracts/audits (previous findings — do not re-report fixed ones). If foundry (forge) is available locally you may run \`forge test\` in a COPY of the contracts dir under your scratch dir (never in REPO).
Questions: any path where user funds are locked with no exit (withdraw/refund requires a party who can disappear; timeouts; paused contract with no withdraw path — the Base lottery contract is PAUSED today: can players/LPs get money out?), signature replay (missing nonce, chainId, contract address), signature malleability, rounding in fee splits, reentrancy with callback tokens, non-standard ERC20 returns (USDT), access control on admin functions, upgradeability/owner powers that can take user funds, V1 escrow balances after V2 migration.` },
  { key: 'deposits-x402', title: 'On-chain deposits, deposit watcher, x402 payments',
    focus: `Files: ${H}deposit_watch.py, ${H}deposit_verify.py, ${H}topup.py (USDC path), ${H}x402.py, ${H}x402_offer_receipt.py, ${H}chain_net.py, ${H}payer_proof.py, ${H}native_price.py, and the OKX A2MCP gateway okx-a2mcp/src/x402.js, okx-a2mcp/src/app.js, okx-a2mcp/src/hub.js. Docs: aimarket-hub/docs/credits-topup.md, money-rails.md.
Questions: tx-hash replay (one deposit credited to two accounts, or twice on two hubs), logs from a wrong token contract or wrong chain, Transfer to a different recipient, confirmation depth and reorgs, block-scanning cursor gaps when an RPC fails or rotates (missed deposits = money stuck), restart behavior, partial/over payments, decimals. x402: is payment settled before or after delivery, what if the facilitator settle fails after delivery or delivery fails after settle, nonce/validBefore reuse, amount/asset/payTo checks against the offer, receipt binding.` },
  { key: 'x402-bridge', title: 'x402 bridge (branch x402-bridge-20261108, LIVE on modelmarket.dev)',
    focus: `This code is NOT on main. Read it with git show, e.g. \`git -C ${REPO} show x402-bridge-20261108:aimarket-hub/aimarket_hub/x402_bridge.py\`, and \`git -C ${REPO} diff main...x402-bridge-20261108 -- aimarket-hub/aimarket_hub\` for credits.py, database.py, migrations.py, hub_routes/bridge.py, hub_routes/invoke.py, invoke_parts/federated_admission.py, invoke_parts/federated_delivery.py, peer_routing.py, peer_liveness.py; tests in aimarket-hub/tests/test_x402_bridge.py on that branch. To run its tests, extract the branch tree into your scratch dir (\`git -C ${REPO} archive x402-bridge-20261108 aimarket-hub | tar -x -C <scratch>\`) and run pytest there with ${REPO}/aimarket-hub/.venv/bin/python.
What it does: the hub pays outside x402 sellers from its own bridge wallet on behalf of credit buyers, debiting their credits. Questions: order of debit vs on-chain payment and what happens on each failure in between (seller 402 again after payment, seller 5xx after settle, timeout, hub crash) — refund? double debit? double pay on retry? Is the amount the hub signs bounded by the buyer's quote/cap, and are payTo/asset/network taken from the seller's 402 trusted blindly (seller raising price between quote and pay)? Granted-accounts gate. Concurrency: two buyers draining the wallet / nonce reuse. Empty-wallet path. Bridge accounting: can the hub's bridge wallet outflow diverge from buyers' debits with no record?` },
  { key: 'mandates-a2a', title: 'Mandates, A2A tasks, subcontracting billing',
    focus: `Files: ${H}mandates.py, ${H}hub_routes/mandates.py, ${H}subcontract.py, ${H}a2a.py, ${H}a2a_tasks.py, ${H}a2a_push.py, ${H}orchestrator_capability.py, ${H}hub_routes/agents.py, ${H}hub_routes/capital.py, ${H}agent_personas.py. Docs: aimarket-hub/docs/mandates.md, subcontracting.md, a2a.md.
Questions: mandate budget/caps enforced atomically under concurrency (two sub-calls racing past the cap)? approvalAbove bypass (splitting a payment into small ones, async tasks)? Failed/canceled/expired A2A tasks: billed or refunded, and is that consistent with docs? Subcontract chains A->B->A loops or depth explosion multiplying charges; who pays when a subcontractor fails; mandate revocation while tasks are in flight; push-notification URLs (SSRF to internal hosts).` },
  { key: 'pay-on-verified', title: 'Pay-on-Verified, verified settlement, appeals, Metis jury',
    focus: `Files: ${H}verified_settlement.py, ${H}settlement_service/verifying.py, ${H}settlement_service/appeals.py, ${H}settlement_service/finalizing.py, ${H}settlement_service/scheduling.py, ${H}hub_routes/verification.py, ${H}answer_dependence.py, ${H}trust.py, ${H}reputation_oracle.py, ${H}hub_routes/reputation.py, and the client side of the jury in metis/ (grep for the verify endpoint the hub calls), pov-demo/. Docs: aimarket-hub/docs/pay-on-verified.md, money-rails.md.
Questions: funds held pending verification — is there always an exit when the jury is silent/unreachable, a seat times out, or quorum math is borderline (e.g. 0.6 vs 0.7 threshold, ties, NaN scores)? Appeals: windows, double finalize, both refund AND pay, appeal after payout. Scheduling: jobs that stop after an exception, rows left in 'verifying' forever. Can the seller influence the jury input to force payment?` },
  { key: 'satellites', title: 'Satellite money services: treasury, lottery relayer, studio, IPO/NFT, PingBlip, UNI',
    focus: `Files: treasury/treasury/*.py, lottery/relayer/ailottery_relayer/*.py (economy.py, economy_draw.py, treasurer.py, sponsor.py, eligibility.py, chain.py), lottery/agent/ailottery_agent, ${H}studio_paid.py, ${H}acex_ipo.py, ${H}capability_nft.py, ${H}spot_auction.py, ${H}subcontract.py only where it touches studio, uni/ (UniUSD buyer flow), pingblip (grep for charge/credit/debit/x402/balance in pingblip/ non-test Python/TS code), helios (if it charges). Lottery README notes it is an experiment and the Base contract is paused.
Questions: rounds/draws/payouts that can stall with funds inside (Drawing state, cancelled rounds — refunds?), relayer restarts, sponsor/gas wallets draining, treasury accounting vs chain, double payouts, prize computation rounding, studio paid jobs charged when generation fails, PingBlip feed charges (a double-charge race was fixed 09-26 — check it holds on every path).` },
  { key: 'desks-stripe', title: 'Desks and stores: Stripe card checkout, Base Pay, HISTOR Watch paid, esim/domain orders, factory commerce',
    focus: `Files: cite-desks/kernel/desk_kernel/service/{card,pay,api,models,config}.py, cite-desks/emberline/backend/app/{card,basepay,ops,models,config}.py and routers/basepay.py, histor/histor/watch_paid.py, histor/histor/payer_collect.py, esim-kit/store/src/{payments/stripe.js,orders.js,app.js,server.js}, domain-kit/src (orders, payments), web/backend/services/commerce.py, web/backend/api/customer.py.
Questions: webhook signature verification and replay; idempotency of fulfillment (webhook retries, redirect + webhook both fulfilling); order fulfilled without a successful payment (status checked? amount and currency checked against the order, not the client?); paid but never fulfilled (exception after payment, no retry, no refund); demo vs live mode switches (demo flag letting real orders through free, or live keys in demo); Base Pay / on-chain checkout tx replay across orders; subscription periods (HISTOR Watch $29/30 d) extension math and double extension.` },
  { key: 'cross-cutting', title: 'Cross-cutting: config defaults, background jobs, docs/spec vs code, multi-hub consistency',
    focus: `Files: ${H}config.py, ${H}envfile.py, ${H}hub_lifespan.py (which background loops start, under which env, what happens when one raises), ${H}settlement_service/scheduling.py, ${H}owner_notify.py, ${H}metrics.py, deploy/ (systemd units/timers for the settlement sweep and payment canary; grep for canary, sweep, settle), scripts/ (canary/sweep scripts), aimarket-hub/docs/money-rails.md, aimarket-hub/docs/production-deployment.md (section 15 host-side companions), aimarket-protocol/ (payment, refund, receipt sections), aimarket-sdks/ (how SDKs compute and send amounts — do units match the hub?), aimarket-hub/docs/value.md.
Questions: money-relevant background jobs that only run when an env var is set or only on one host, or die silently on the first exception (no restart, no alert); fail-open defaults on money paths (mock payments, demo modes, skipped verification) that could be active in production; places where docs or the protocol spec promise behavior the code does not implement (refund semantics, receipt binding, timeouts); unit mismatches between SDKs, hub, desks and contracts; inconsistent currency handling across hubs of different versions.` },
]

const GROUPS = [
  { name: 'hub-ledger', zones: ['credits', 'invoke-local'] },
  { name: 'federation', zones: ['federation', 'x402-bridge'] },
  { name: 'rails', zones: ['channels', 'escrow'] },
  { name: 'chain', zones: ['contracts', 'deposits-x402'] },
  { name: 'settlement', zones: ['mandates-a2a', 'pay-on-verified'] },
  { name: 'satellites', zones: ['satellites', 'desks-stripe', 'cross-cutting'] },
]

const zoneByKey = {}
ZONES.forEach(z => { zoneByKey[z.key] = z })

function finderPrompt(z) {
  return `You are a read-only auditor for one zone of a money-flow audit.
${RULES}

YOUR ZONE: ${z.title}
Your scratch dir: ${SCR}/audit/${z.key}
${z.focus}

Read the zone's code thoroughly (follow calls into other modules where money state changes), then return your findings.`
}

function verifyPrompt(groupName, items) {
  return `You are the adversarial verifier for audit findings in zone group "${groupName}" of the aicom monorepo. Other agents produced the findings below. Try to REFUTE each one independently by reading the actual code; keep only what survives.
${RULES}

Your scratch dir: ${SCR}/audit/verify-${groupName}

For EACH finding:
1. Open the cited file/line plus callers and callees. Is the quoted code real (allow small line drift)? For ids starting with "x402-bridge" the code lives on branch x402-bridge-20261108 (use git show / git archive into scratch).
2. Look for a guard that already prevents it: caller-side check, DB unique index/constraint (grep migrations.py), transaction/lock/conditional UPDATE, middleware, a config default that disables the path in production, a sweep/reaper elsewhere that releases the held state (grep the table/status name across the repo).
3. Is the failure scenario reachable with realistic inputs and production-like config? Who can trigger it (anonymous, any account, a peer hub, only the operator)?
4. For critical/high: attempt a minimal reproduction (scratch pytest importing the real module, or a precise step-by-step trace with line numbers). Record what you ran in reproduction.
5. Verdict: CONFIRMED (wrong outcome verified by test or airtight trace), PLAUSIBLE (code supports it but reachability/impact depends on something you could not confirm — say what), REFUTED (guard exists, misread code, unreachable, or claim wrong), DUPLICATE (same root cause as another id in this list; set duplicate_of). Re-rate severity honestly: money loss/stuck must be real to stay high/critical.
Default to REFUTED when the code does not support the claim. Return a verdict for EVERY id below.

FINDINGS (JSON):
${JSON.stringify(items, null, 1)}`
}

const out = await parallel(GROUPS.map(g => async () => {
  const finds = await parallel(g.zones.map(k => () =>
    agent(finderPrompt(zoneByKey[k]), { label: `find:${k}`, phase: 'Find', schema: FINDINGS })))
  const items = []
  const coverage = []
  finds.forEach((r, i) => {
    const k = g.zones[i]
    if (!r) { log(`finder ${k} returned nothing`); coverage.push({ zone: k, failed: true }); return }
    coverage.push({ zone: k, files_read: r.files_read, not_covered: r.not_covered, count: r.findings.length })
    r.findings.forEach((f, j) => items.push(Object.assign({ id: `${k}-${j + 1}`, zone: k }, f)))
  })
  log(`group ${g.name}: ${items.length} findings to verify`)
  if (!items.length) return { group: g.name, items, verdicts: [], coverage }
  const v = await agent(verifyPrompt(g.name, items), { label: `verify:${g.name}`, phase: 'Verify', schema: VERDICTS })
  if (!v) log(`verifier for ${g.name} returned nothing — findings unverified`)
  return { group: g.name, items, verdicts: v ? v.verdicts : null, coverage }
}))

const rows = []
const coverage = []
out.filter(Boolean).forEach(g => {
  coverage.push(...g.coverage)
  const vmap = {}
  ;(g.verdicts || []).forEach(v => { vmap[v.id] = v })
  g.items.forEach(it => rows.push(Object.assign({}, it, { verify: vmap[it.id] || null })))
})
const sevRank = { critical: 0, high: 1, medium: 2, low: 3 }
const kept = rows.filter(r => !r.verify || r.verify.verdict === 'CONFIRMED' || r.verify.verdict === 'PLAUSIBLE')
kept.sort((a, b) => sevRank[(a.verify && a.verify.severity) || a.severity] - sevRank[(b.verify && b.verify.severity) || b.severity])
const dropped = rows.filter(r => r.verify && (r.verify.verdict === 'REFUTED' || r.verify.verdict === 'DUPLICATE'))
  .map(r => ({ id: r.id, title: r.title, verdict: r.verify.verdict, duplicate_of: r.verify.duplicate_of || '', why: r.verify.reasoning }))
log(`total ${rows.length}; kept ${kept.length}; dropped ${dropped.length}`)
return { kept, dropped, coverage }
