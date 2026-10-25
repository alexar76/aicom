# Factory quality audit — 2026-10-23

**The tested gates are recorded below. Unqualified “maximum industry-standard compliance” is not confirmed.**
The latest verification removes `braces` from the frontend tree and passes the full npm development-dependency gate.
This is a local engineering assessment, not an independent certification. Changes and reports stay local;
this audit performed no GitHub publication.

**Latest corrective verification:** see [skip reconciliation, production and UNI settlement](#skip-resolution). The earlier sections preserve historical results.

## Baseline scope and results

The scope is the Factory's Python suite, critical Python lint/type gates, main `web/frontend`,
and the component boundaries described below. Satellite checks are named individually; their results
do not certify every project in this monorepo.

| Gate | Result |
| --- | --- |
| Factory Python suite with coverage | **Passed: 5,828 tests, 84 subtests; 60 skipped, one deselected; exit 0 in 206.99 seconds.** |
| Factory line coverage | **60.5%** of 59,394 statements (35,915 covered). No branch-coverage claim or global threshold. |
| Main frontend production build | Passed on Next.js **16.4.2**, with TypeScript checking and 36 generated pages. Used the supported `--webpack` option because Turbopack's IPC port was denied by the local execution environment. |
| Main frontend unit tests | **63 passed**, 12 files, Vitest **4.1.12**. |
| Main frontend ESLint | Passed with `--max-warnings=0`. |
| Main frontend browser E2E | **9 passed** against the final production build: languages, hydration, chart mounting, motion and browser errors. |
| Python browser checks | Real FastAPI login scenario, visual-standards fixture, diagram golden PNG and full-software mobile viewport check passed. |
| Critical-path Ruff | Passed for `core`, `llm`, `orchestrator`, `security`, `agents`; new regression tests checked explicitly too. |
| Backend/director/scripts syntax and undefined-name checks | Passed for E9/F821/F822/F823. |
| Curated strict mypy | Passed for eight files, matching the existing CI selection. |
| Docstring import guard | Passed over the repository. |
| Root `requirements.txt` pip-audit | Passed: no known vulnerabilities in the resolved requirements at audit time. |
| Main frontend production npm dependencies | Passed: zero reported vulnerabilities. |
| Main frontend npm including development dependencies | **Blocked: 7 High package-chain entries**, all rooted in `braces`; zero Moderate/Critical after the fixes. No advisory suppression was added. |
| First-party Bandit High gate | Passed for `web/backend`, `security`, `llm`, `aimarket-hub`, `orchestrator`, `agents`, `core`, excluding tests and dependency environments. |
| Secret scan | Gitleaks: **1,964 current Factory source/test/script files**, zero findings, redacted output. This is not a scan of all history or every satellite. |
| PostgreSQL payment recovery | **50 passed** across SQLite and a real temporary PostgreSQL **18.3** cluster; includes crash/restart and concurrent refund recovery. Cluster stopped afterward. |
| TypeScript SDK | **73 passed**, TypeScript build passed; npm including development dependencies reports zero vulnerabilities after the Vitest patch. |

Evidence for local source revision `52cd5f361a43a62f84ed38e5215a750543a45580` is saved in the
[verification manifest](../artifacts/quality-audit-2026-10-23/verification.json),
[backend JUnit report](../artifacts/quality-audit-2026-10-23/factory-tests.xml) and
[coverage summary](../artifacts/quality-audit-2026-10-23/coverage-summary.json).
At baseline validation, executable source matched that revision. The follow-up below tests additional local changes.

The old lint/import and targeted-test counts in earlier conversation messages are overlapping selections,
not a total to add to the full-suite count. A coverage file is never considered proof of test success.

## Corrected defects

- **False-green quality gates.** The pytest wrapper now requires a completed zero exit status,
  preserves failures, returns 124 on deadline, removes stale reports and kills the subprocess group.
  The dependency-audit script propagates scanner/network/tool errors, runs all its declared checks,
  and does not install or rewrite dependencies during an audit. Real shell/child-process tests
  exercise those behaviors.
- **Spending protections.** Corrupt/unreadable LLM ledgers fail closed instead of resetting spend to
  zero. Dates, amounts and timestamps are validated; writes are private and atomic. Real router →
  provider → pricing → ledger integration exposed and fixed CostGuard reading the wrong cap keys.
- **Error disclosure.** API error handlers use the same production-mode aliases as the startup guard.
  HTTP regression tests verify safe public errors and explicitly enabled development details.
- **Watchdog correctness.** Monotonic deadlines, safe callback rearming, deadline rechecks, awaited
  callback results and idempotent monitoring prevent lost registrations and stale timeout actions.
- **Snapshot restoration.** Archives reject absolute/parent paths, links, special files and excluded
  dependency trees before changing live code. Restore destinations cannot traverse existing symlinks.
  Extraction uses Python's data filter; failed snapshot creation preserves the previous archive and
  removes its partial file. Adversarial archive and copy-failure tests exercise the filesystem.
- **Vault boundary.** The Vault reader validates HTTP(S) origins and refuses redirects changing
  scheme, host or effective port, preventing `X-Vault-Token` forwarding to another authority.
  Malformed, non-object, invalid-UTF-8 and oversized responses fail closed. Two real local HTTP servers
  verify that a rejected destination receives neither a request nor a token.
- **Merchant isolation.** Hub card top-ups prefer `AIMARKET_STRIPE_*[_FILE]`. The service filter
  rejects shared unscoped Factory Stripe credentials. Explicitly empty/unreadable scoped secrets
  cannot fall back to a different merchant. Standalone legacy configuration remains supported.
  Tests connect the actual environment filter to the real secret reader; the hub's 44 card tests pass.
- **Atomic file permissions.** Sensitive JSON temporary files receive their permissions before content
  is written; the existing bind-mount fallback applies permissions as well.
- **Test reliability.** SQLite rate-limit/nonces are isolated per test. Unit environment-construction
  tests no longer install packages from PyPI. Checked-in browser fixtures use the installed test
  runtime while retaining real uvicorn, browser, cookies and scenario execution. Version-drift tests
  use controlled versions; reservation-settlement checks verify the actual ledger entry and held sum.
- **Checking performance.** Source scans prune dependencies/virtualenvs before descending; root
  classification reads its YAML map once. Service-environment checks parse Compose configuration once
  per comparison instead of once per variable. The deployment-address guard keeps its original scope.
- **Dependency fixes.** OpenTelemetry API/SDK/exporter move together to **1.45.1**. Next.js and its
  ESLint config move to **16.4.2**, Vitest to **4.1.12**. A selector-parser override selects **7.1.7**;
  the resulting CSS build and browser suite pass. Vitest uses an explicit ESM config without the
  previous loader warning.
- **Documentation and frontend.** Corrected Next.js version, payment-network wording, test verdicts,
  ledger recovery instructions and coverage scope. Repaired local report/document links, preserved
  documented full-page authentication reloads and used client navigation for ordinary internal links.
  The roster age clock no longer reads the clock during render.
- **Vendored module parity.** Refreshed the monitor's copy of canonical `chain_net.py`; **63** monitor
  chain tests pass. No deployment or on-chain operation was performed.

## Component integration

The `component_integration` marker identifies deterministic integration tests with real local components:

- `test_llm_accounting_integration.py`: 11 cases joining router, provider adapter, pricing, persistent
  usage ledger and circuit breaker. Only external provider HTTP is simulated. Covers streaming,
  failover/recovery, daily/monthly tiers, hard limits and corrupt state.
- `test_pipeline_recovery_integration.py`: three cases joining watchdog, real state machine, SQLite,
  reopen/reclaim, event bus and the replay API, including terminal failures and damaged database recovery.
- `test_hub_card_secret_scope.py`: ten cases joining the service environment filter and hub secret
  reader, including legacy operation and a configured secret that must fail closed.
- `test_vault_http_boundary.py`: 13 cases covering real redirect handling and invalid response/origin
  boundaries. Network servers exist only for the redirect cases; other cases inject serialized responses.

The final marker selection completed with **37 passed**. These cases complement existing customer/payment/pipeline tests; they do not mock the state
machine, ledger or production request handlers they are intended to verify.

## Baseline limits and acceptance criteria

1. **Development dependency gate remains red.** `braces <=3.0.3` has
   [CVE-2026-93687 / GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
   with no patched release listed at audit time. npm reports its dependants too: Tailwind, chokidar,
   micromatch, fast-glob and Next's lint packages. The production dependency graph is clean, but that
   does not make the development/build graph clean. Do not replace this result with an audit exception
   or a forced major migration without compatibility validation.
2. **Static analysis is bounded.** A zero High gate is not a zero-findings claim. The initial broader
   scan also reported Medium hints (URL opening, constructed SQL, bind addresses and temporary paths); the final expanded scan reports 98 Medium and 318 Low hints across 159,572 lines.
   Some are constant placeholders or service configuration; this assessment does not claim every
   remaining hint was independently eliminated. Type checking is limited to the curated eight files.
3. **Skipped and excluded tests are explicit.** The Factory wrapper excludes legacy live marketplace/
   visual suites and separately exercised browser scenarios. Legacy optional UI tests include outdated
   selectors and a vacuous count assertion; they are not accepted as browser validation. Live fleet
   probes require their explicit environment flag, and case-sensitive filesystem fixtures cannot run
   on this volume. Of the 60 main-run skips, 25 PostgreSQL cases were covered in the separate
   50-case SQLite/PostgreSQL run, and the optional email-validator case was covered after installing
   that extra (12 identity tests passed). Remaining skips include 23 live probes, five filesystem
   cases, three missing deployment-environment cases and three non-applicable content/badge checks.
   A skip is not a pass.
4. **Deployment assurance remains separate.** No production soak, external penetration test,
   independent contract review, full satellite-suite campaign or regulatory certification occurred.
   Other tasks edited this shared working tree concurrently. The final source revision and gate results are recorded in the local verification artifact; a later source change needs its own validation.
5. **Coverage has no global enforcement threshold.** Coverage now includes `core`, `llm` and `security`
   alongside backend/agents/orchestration. Compare the new scope to a new baseline, not the previous
   narrower percentage. Selected modules reached: atomic JSON **100%**, snapshot guard **96.4%**,
   cost guard **96.1%**, usage guard **92.9%**, watchdog **91.7%**, secret resolver **66.7%**.
   These are line-coverage figures, not proof that all error/concurrency paths were exercised.
   Provider charges remain estimates; in-flight concurrency is not a provider-side
   hard billing limit. Single-file bind mounts retain a documented non-atomic fallback.

<a id="follow-up"></a>
## Earlier follow-up: payment error handling and enforced coverage

**The final corrected working tree passed 6,025 tests and 84 subtests; 34 tests skipped, one deselected;
exit 0 in 176.17 seconds.** This run included a disposable PostgreSQL 18.3 cluster and enforced payment
coverage thresholds after successful test completion. The cluster and temporary frontend server were stopped.
No deployment, GitHub write or real-money transfer was performed by this audit.

| Follow-up check | Result |
| --- | --- |
| Payment/UNI selection inside the full run | **348 passed, zero skipped**; includes financial regression tests, deterministic canary checks and the coverage-gate tests |
| Added regression cases | **170** in five new files; included in the full count, not additional to it |
| SQLite/PostgreSQL recovery | Both fixture variants executed, including hard process exits, refunds and HTTP/store recovery. PostgreSQL is the UNI backend; Factory commerce and KOVA/SaaS retain their own SQLite stores. |
| Global coverage | **60.7% lines** (36,096/59,427 statements), **49.8% branches** (10,227/20,548). Combined coverage.py score: 57.9%; do not compare it to the old line-only score. |
| Main frontend | ESLint zero warnings; **63 unit tests**, production build with 36 pages, **9 browser E2E tests** passed |
| TypeScript SDK | Build and **73 tests** passed |
| Hub card top-ups | **44 tests** passed; Stripe HTTP is simulated |
| eSIM recovery | **5 store + 10 rails tests** passed; supplier/chain outcomes are simulated |
| Python lint/type/import guards | Critical Ruff plus new tests/scripts; broad backend/director/scripts syntax/name gate; curated mypy eight files; docstring import guard passed |
| Python dependencies / SDK npm / frontend production npm | No reported vulnerabilities at this verification |
| Frontend npm including development dependencies | **Still fails: 7 High dependency-chain entries rooted in unpatched `braces`** |
| First-party Bandit | **0 High**, no scanner errors; 98 Medium / 318 Low hints. Eight payment SQL hints reviewed as constant SQL structure plus bound values, with no suppression. |

Five functions reached 100% of their measured lines and branches (the completion helper has no static
branches; its exception cleanup is exercised explicitly). Confirmation reached 94.2% lines / 91.7% branches:

| Critical function | Line coverage | Branch coverage | Required lines / branches |
| --- | --- | --- | --- |
| `seal_quote` | 100.0% | 100.0% | 100% / 100% |
| `verify_claim` | 100.0% | 100.0% | 100% / 100% |
| `_complete_checkout` | 100.0% | — (0 static branches) | 100% / 100% |
| `_confirm_payment` | 94.2% | 91.7% | 90% / 85% |
| `CommerceService.create_order_and_license` | 100.0% | 100.0% | 95% / 90% |
| `UniWalletService.refund_withdrawal` | 100.0% | 100.0% | 100% / 100% |

The [coverage gate](../scripts/check_payment_coverage.py) now runs after the full suite in both
[CI](../scripts/run_factory_pytest_ci.py) and [local](../scripts/run_factory_pytest.sh) entrypoints.
It fails for missing/malformed reports, missing functions, absent branch measurement, invalid counters
and results below either unrounded threshold. Its negative tests also verify that runner/export failures
cannot become success. This is enforcement for six named functions, not a global coverage threshold.

Corrected failure paths:

- **Commit and fulfilment.** A `confirmed` flag without a committed order cannot return success.
  Operational/integrity errors roll back both order and license. An error after commit retains the
  transfer claim, so the original checkout can recover and another door cannot spend it.
- **Persistence and recovery.** A failed checkpoint/cleanup returns a safe 503 and retains a retry path.
  Corrupt pending-payment history is preserved until restored. Empty/non-object legacy claim history
  and unavailable legacy UNI history block settlement instead of being treated as unused money.
- **Quote-key preservation.** Confirmation never silently creates a replacement key. New quotes also
  cannot replace a lost key while signed quotes exist. Parallel initial publication uses one complete
  private key; partial files are removed on failure. Invalid legacy prices are rejected safely.
- **RPC and proof validation.** Outages/malformed responses return 503 without declaring a payment
  failed or delivering value. RPC credentials are absent from tested public errors and checkout logs.
  SPL balances reject non-finite/negative data and validate raw u64 amounts/decimals. Real Ed25519 tests
  reject small-order keys, malformed encodings and proofs moved across customers/sites/transfers.
  A full Solana HTTP → RPC verifier → signature → claim → order/license case complements EVM cases.
- **Refund eligibility.** Unknown/ineligible/already-broadcast withdrawals, invalid gross/fee values and
  unavailable refund ledger claims cannot mint a refund. Both real UNI backends exercise these guards.
- **Audit output.** Dependency reports default to the excluded `.internal/audit/` directory; an explicit
  `AIFACTORY_AUDIT_REPORT_DIR` selects the evidence directory. The audit no longer creates an
  unclassified root file that breaks the repository-root guard.

Evidence: [final manifest](../artifacts/quality-audit-2026-10-23/followup/verification.json),
[JUnit](../artifacts/quality-audit-2026-10-23/followup/factory-tests.xml),
[coverage](../artifacts/quality-audit-2026-10-23/followup/factory-coverage.json),
[test/gate log](../artifacts/quality-audit-2026-10-23/followup/factory-tests.log),
[dependency log](../artifacts/quality-audit-2026-10-23/followup/dependency-audit.log),
[payment SQL review](../artifacts/quality-audit-2026-10-23/followup/payment-sast-review.json).
The manifest ties results to hashes of the changed executable/test/config files; source hashes were
checked again after the run. Documentation explains the payment lifecycle, scenarios and commands in
[EN](payment-tests-and-transactions.md), [RU](payment-tests-and-transactions.ru.md),
[ES](payment-tests-and-transactions.es.md), [FR](payment-tests-and-transactions.fr.md), [ZH](payment-tests-and-transactions.zh.md).

**Limits recorded at that earlier follow-up (dependency finding superseded below).** The [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
still lists no patched version, and the npm registry still serves 3.0.3. No advisory was hidden,
no unsupported override was introduced and no forced major migration was presented as a fix.
The 34 skips are 23 explicitly enabled live-fleet probes, five case-sensitive-filesystem cases,
three missing deployment-environment cases, two non-applicable CSS-import checks and one badge placeholder.
Global line/branch coverage remains limited, 90 other Medium SAST hints are not individually cleared,
and type checking remains scoped. No real-money positive settlement/refund, production soak,
external penetration test or independent certification was performed. These limits prevent an
unqualified claim of full compliance with every possible industry standard.

<a id="braces-resolution"></a>
## Earlier verification: braces removed and critical payment coverage at 100%

**The local Factory run passed 6,039 tests and 84 subtests, with 34 skipped and one deselected;
exit 0 in 186.76 seconds.** The six-function coverage gate also exited 0. The temporary PostgreSQL
18.3 cluster was stopped after the run. Of the total, **362 payment/UNI cases passed with zero skips**.
The 34 skips retain the categories recorded in the earlier follow-up.

| Critical function | Covered / measured lines | Covered / measured branches | Required lines / branches |
| --- | --- | --- | --- |
| `seal_quote` | 27 / 27 | 10 / 10 | 100% / 100% |
| `verify_claim` | 21 / 21 | 8 / 8 | 100% / 100% |
| `_complete_checkout` | 8 / 8 | 0 / 0 (no static branches) | 100% / 100% |
| `_confirm_payment` | 137 / 137 | 60 / 60 | 100% / 100% |
| `CommerceService.create_order_and_license` | 29 / 29 | 10 / 10 | 100% / 100% |
| `UniWalletService.refund_withdrawal` | 25 / 25 | 12 / 12 | 100% / 100% |

These are **247 statements and 100 measured branches** across the six functions. Completion-helper
exception cleanup is covered explicitly even though coverage.py reports no static branches there.
The [coverage gate](../scripts/check_payment_coverage.py) requires 100% for every function and rejects
incomplete reports. Both Factory runners and the [main CI workflow](../.github/workflows/ci.yml) invoke
it after successful tests. Global coverage is **60.8% lines** (36,111/59,427) and **49.8% branches**
(10,233/20,548), reported separately; six-function coverage does not establish coverage of every
payment integration or production failure mode.

The [new confirmation tests](../tests/test_payment_confirmation_boundaries.py) contribute **14 cases**
(seven scenarios × SQLite/PostgreSQL fixtures), already included in the totals. They exercise blank
and wrong-network hashes, real async-lock contention while a quote is consumed, legacy server-price
fallback, retry of a pinned transfer, unsupported persisted chain and order insertion conflict after
initial reads. The last case uses a real committed competing order: HTTP returns 409, retains retryable
state, creates no additional license and does not expose the existing license key. Existing crash,
rollback, corrupt-store, RPC outage, cryptographic proof and refund scenarios remain in the full run.
PostgreSQL applies to UNI; checkout commerce and the KOVA/SaaS stores retain their SQLite databases.
External chain/provider responses are simulated, while local persistence, signatures and locks are real.

### Dependency resolution and compatibility

The old [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) still has no upstream patched
release at verification time. The affected dependency tree is instead removed from this frontend:

- Tailwind CSS and its PostCSS plugin move together to **4.3.3**, with `tailwind-merge` **3.7.0**.
  The obsolete v3 build/watch dependency chain and separate autoprefixer are removed. Classes are
  migrated for renamed scales and removed flex utilities; base layers and form defaults preserve
  utility precedence and existing behavior. Production testing caught and fixed an optimizer issue
  dropping unprefixed backdrop blur declarations.
- The pinned **16.4.2** Next ESLint plugin receives a scoped npm alias from its `fast-glob` dependency
  to **tinyglobby 0.2.17**. This covers the plugin's actual `globSync` directory lookup, not every
  possible fast-glob API. Nine integration tests load the real plugin and include actual navigation-rule
  diagnostics for literal, glob, brace and array roots. Relative/trailing-slash results resolve to the
  same directories in this consumer. Future Next upgrades must revalidate this contract.
- A clean **`npm ci --ignore-scripts`** succeeds from the regenerated lockfile. `npm ls braces --all`
  prints an empty tree (npm uses exit 1 for that empty selection). The lockfile contains no braces entry.
  The fresh full npm audit reports **0 total vulnerabilities**, including development dependencies;
  the production-only audit also reports 0. There is no advisory exception or vulnerability suppression.

The [dependency compatibility notes](../web/frontend/DEPENDENCIES.md) explain the override, source
scan scope and reproducible checks. Tailwind's [official upgrade guide](https://tailwindcss.com/docs/upgrade-guide)
requires Safari 16.4+, Chrome 111+ and Firefox 128+. Browser verification here uses Chromium;
other engines/older versions are not certified by these results.

| Repeated check | Final result |
| --- | --- |
| Full dependency-audit script | **Exit 0:** Bandit High gate, root pip-audit, frontend npm including dev, SDK npm |
| Main frontend clean installation | Passed; installed braces tree empty |
| Frontend lint / unit | Zero ESLint warnings; **74 tests in 13 files** passed |
| Frontend production build | Passed with **36 pages** and TypeScript checking via `npm run build -- --webpack` |
| Frontend browser | **12 passed** against the final production build: original nine plus two v3-style contracts at 375/1280px and form/layout defaults |
| CSS comparison | Twelve selected computed-style cases match pre-upgrade production values; only invisible zero-size shadow layers are normalized. Fixture screenshots were also inspected. This is not a pixel-equivalence claim for every route. |
| TypeScript SDK | **73 tests** and build passed |
| Python lint/type/import gates | Critical Ruff; new test/gate Ruff; backend/director/scripts syntax and name checks; curated mypy eight files; docstring import guard passed |

The default Turbopack build could not bind its required local IPC port in this execution environment,
including the escalated retry. Its failed log is preserved separately. The successful build and browser
results above use Next's supported webpack path; they do not certify Turbopack.

Evidence: [verification manifest](../artifacts/quality-audit-2026-10-23/braces-resolution/verification.json),
[JUnit](../artifacts/quality-audit-2026-10-23/braces-resolution/factory-tests.xml),
[coverage](../artifacts/quality-audit-2026-10-23/braces-resolution/factory-coverage.json),
[test and coverage-gate log](../artifacts/quality-audit-2026-10-23/braces-resolution/factory-tests.log),
[full npm audit](../artifacts/quality-audit-2026-10-23/braces-resolution/frontend-all-dependencies-audit.json),
[dependency checks](../artifacts/quality-audit-2026-10-23/braces-resolution/dependency-audit.log),
[browser tests](../artifacts/quality-audit-2026-10-23/braces-resolution/frontend-browser.log).
Payment documentation and runnable commands are updated in EN, RU, ES, FR and ZH.

These results close the frontend braces finding and the remaining measured coverage gaps in the six
critical functions. The broader limits recorded above still apply: global coverage, separately reviewed
SAST hints, scoped typing, other browsers/satellites and independent production/security assurance.
All changes remain local; no GitHub write, deployment or transfer of real funds was performed.

<a id="skip-resolution"></a>
## Latest verification: original skips exercised, atomic UNI settlement and production contracts

**6,139 Factory tests and 84 subtests passed; 24 intentional live probes skipped, one test
deselected; exit 0 in 190.53 seconds.** The live probes ran separately against production:
**32 passed, zero skipped**, comprising the **23 original live cases**, one new unpaid-invoke guard
and eight offline contracts. The 24 default-suite live skips are exactly the cases that passed
in that production run. Selections overlap; their numbers are not additive.

**All 34 originally skipped cases were exercised.** The [case-by-case reconciliation](../artifacts/quality-audit-2026-10-23/skip-resolution/original-skips.json)
maps each original ID to a completed passing testcase, with the source report and reason for the fix.

| Original cause | Cases | Resolution and evidence |
| --- | --- | --- |
| Live fleet opt-in | 23 | Production run through temporary loopback SSH forwards; original authenticated SKOPOS fleet-status test retained. The new unpaid request returns 402. |
| Case-insensitive development filesystem | 5 | Real temporary case-sensitive HFS+ volume, selected through `AIFACTORY_CASE_SENSITIVE_TMPDIR`. The first fixture now contains files in both spellings; an empty directory correctly remains exempt. |
| Missing deployment environment for Compose rendering | 3 | Actual Compose merge with `--env-file /dev/null`, synthetic interpolation-only values and `--no-env-resolution`. No deployment secrets or Docker daemon are needed to render; tool/configuration errors fail the tests. |
| No applicable stylesheet import | 2 | Both CSS import syntaxes are parsed; tests check the current self-hosted font stylesheet linked by the layout, its woff2 files and CSP permissions. A parser regression case also runs. |
| KOVA placeholder test badge | 1 | KOVA's dedicated suite passed **59 tests** with no skips; generated SVG/JSON now state that count. The consistency guard rejects placeholders. |

Two environment assumptions surfaced when the full suite was first placed on the small HFS+ volume.
The pipeline recovery test relied on a 20 ms sleep despite coarse filesystem timestamps; it now sets
explicit older/newer/equal mtimes. Sandbox scheduling tests relied on real disk capacity and an
external default data directory; their fixtures now specify resources, isolate registry/data state,
and retain the separate low-resource guard tests. The final full run uses the ordinary temp filesystem
and sends only collision fixtures to the case-sensitive volume. Failed and interrupted attempt logs
are retained; their coverage is not presented as a passing run.

### Additional critical financial coverage

**450 payment/UNI cases passed without skips** inside the full run. The same selection also
passed on an isolated PostgreSQL 16 container (**450 passed**), matching the new service configured in
both CI variants. The full run uses PostgreSQL **18.3**. These backend variants concern UNI, while
checkout commerce/KOVA/SaaS retain SQLite.

The two new settlement modules add **88 parametrized cases**, included in those totals. They use real
stores and signatures, database triggers rejecting receipt inserts, eight `os._exit(9)` child-process
crashes after receipt insertion, concurrent retries and controlled competing operations.

| Critical function | Covered / measured statements | Covered / measured branches | Required statements / branches |
| --- | --- | --- | --- |
| `seal_quote` | 27 / 27 | 10 / 10 | 100% / 100% |
| `verify_claim` | 21 / 21 | 8 / 8 | 100% / 100% |
| `_complete_checkout` | 8 / 8 | 0 / 0 | 100% / 100% |
| `_confirm_payment` | 137 / 137 | 60 / 60 | 100% / 100% |
| `CommerceService.create_order_and_license` | 29 / 29 | 10 / 10 | 100% / 100% |
| `UniWalletService.refund_withdrawal` | 25 / 25 | 12 / 12 | 100% / 100% |
| `UniWalletService.charge` | 25 / 25 | 10 / 10 | 100% / 100% |
| `UniWalletService.withdraw_to_chain` | 22 / 22 | 10 / 10 | 100% / 100% |
| `UniWalletService.hold` | 26 / 26 | 12 / 12 | 100% / 100% |
| `UniWalletService.spend_hold` | 49 / 49 | 20 / 20 | 100% / 100% |
| `UniWalletService.release_hold` | 20 / 20 | 10 / 10 | 100% / 100% |
| `UniWalletService._credit` | 18 / 18 | 6 / 6 | 100% / 100% |
| `issue_receipt` | 34 / 34 | 12 / 12 | 100% / 100% |

All **13 targets** require 100% of measured statements and branches. `_complete_checkout` has zero
static branches; its exception cleanup remains covered explicitly. Missing reports or branch counters
fail the gate. Global coverage is **60.8% statements** (36,134/59,446) and **50.0% branches**
(10,280/20,562), a separate measure. This is not coverage of every possible production
failure or every satellite.

The new tests reproduced and corrected these issues locally:

- **Receipt and money could commit separately.** Charge, credit/grant/top-up, reserve spending and
  withdrawal creation now pass the active database connection to receipt issuance. Balance, ledger,
  reserve/withdrawal state and signed receipt commit together. Signing/insert failure or process death
  rolls the complete transaction back. A retry returns the persisted receipt instead of a newly signed
  payload that was never stored.
- **Long idempotency keys collided.** Receipt keys are no longer truncated to 128 characters; the
  schemas already use unrestricted TEXT. Two grants sharing a long prefix now retain distinct
  receipts and recover correctly on retry.
- **Retry/recovery state was ambiguous.** A fully depleted reserve can return its original receipt on
  retry. A committed legacy claim without a receipt, or a hold claim without a reserve record, fails
  closed without credit/debit changes and requires operator reconciliation.
- **Corrupt receipt JSON was accepted as a different type.** Receipt readers now reject arrays,
  null/scalars and damaged JSON. A damaged top-up receipt still pins the transfer as already claimed;
  it is not treated as unused money. An unknown wallet amount raises an explicit wallet error.

Strict mypy now passes for **10 files**, including both changed financial modules, and the main CI
type selection includes them. No type-ignore exception was introduced. Critical Ruff, all touched
Python tests/scripts, backend syntax/name checks and the docstring import guard also pass.
The dependency-audit script passes with no reported pip/npm vulnerabilities. The final broad Bandit
report has **0 High, 97 Medium and 318 Low** hints and no scanner errors. Seven financial SQL hints are
reviewed as constant column/predicate/placeholder structure plus bound values; the other 90 Medium
hints remain outside that individual review.

### Production meaning and reproduction

Production checks verify real Factory, Hub, Mesh, ARGUS/UNI, Monitor, Lottery, Pulse and SKOPOS
responses. SKOPOS public health must omit private fleet metrics. Its operator-key `fleet.status`
capability reads status without a funded hub channel, transfers or LLM calls; an unauthenticated
request must receive 402. The [live runner](../scripts/run_ecosystem_live_tests.py) reads only the required
credentials, holds them in memory, uses loopback-only SSH forwards and closes the tunnels. Their
values are absent from saved reports.

**The new UNI code fixes remain local; this verification did not deploy them.** Production success
validates the active release's tested contracts, not the presence of the new local fixes. No GitHub
write, deployment, transfer, license issuance or provider/LLM spend was performed by this audit.

```bash
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-live-contracts \
  .venv-quality/bin/python scripts/run_ecosystem_live_tests.py \
  --ssh-host factory-vps --skopos-ssh-host skopos-vps

# Requires a disposable local PostgreSQL test cluster; never use a production URL.
PAYMENT_FIX_TEST_PG_URL=postgresql://aicom_test@127.0.0.1:55487/postgres \
  AIFACTORY_CASE_SENSITIVE_TMPDIR=/path/to/case-sensitive/test-volume \
  USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-quality \
  AIFACTORY_PYTEST_HARD_CAP_SEC=1800 \
  .venv-quality/bin/python scripts/run_factory_pytest_ci.py --timeout-method=signal
```

On Linux, the normal temporary filesystem generally preserves case and no volume override is needed.
For macOS the verified temporary-volume setup is below. Run test commands inside the subshell before
it exits; the trap detaches the volume. Only collision fixtures use this volume.

```bash
(
  set -eu
  case_volume_root=$(mktemp -d /tmp/aicom-case-volume.XXXXXX)
  hdiutil create -size 2g -type SPARSE -fs 'Case-sensitive HFS+' \
    -volname AicomAudit "$case_volume_root/cases.sparseimage"
  mkdir "$case_volume_root/mount"
  hdiutil attach "$case_volume_root/cases.sparseimage" \
    -mountpoint "$case_volume_root/mount" -nobrowse
  trap 'hdiutil detach "$case_volume_root/mount"' EXIT
  export AIFACTORY_CASE_SENSITIVE_TMPDIR="$case_volume_root/mount"
  USE_SQLITE=true .venv-quality/bin/python -m pytest -q tests/test_case_collisions.py
)
```

Evidence: [final manifest](../artifacts/quality-audit-2026-10-23/skip-resolution/verification.json),
[full JUnit](../artifacts/quality-audit-2026-10-23/skip-resolution/factory-tests.xml),
[coverage](../artifacts/quality-audit-2026-10-23/skip-resolution/factory-coverage.json),
[full test/gate log](../artifacts/quality-audit-2026-10-23/skip-resolution/factory-tests.log),
[production JUnit](../artifacts/quality-audit-2026-10-23/skip-resolution/production-tests.xml),
[production log](../artifacts/quality-audit-2026-10-23/skip-resolution/production-tests.log),
[PostgreSQL 16 JUnit](../artifacts/quality-audit-2026-10-23/skip-resolution/ci-postgres-tests.xml),
[financial mypy](../artifacts/quality-audit-2026-10-23/skip-resolution/financial-mypy.log),
[SQL review](../artifacts/quality-audit-2026-10-23/skip-resolution/payment-sast-review.json).

## Reproduction

Use a dedicated Python 3.12 environment; the shared `.venv` was incomplete and differed from the
requirements. The audited environment installs root requirements plus pytest-mock, Ruff 0.15.15,
mypy 1.19.1, types-PyYAML, Bandit 1.9.4 and pip-audit 2.9.0. Cross-package tests additionally need
jsonschema, email-validator and the local source packages `aimarket-hub`, `aimarket-bridges` and `awr/reference/python`.
The local editable packages were installed with `--no-deps` to retain the root Factory dependency
versions for this test run; this is not a claim that all satellite distribution metadata agrees with
root dependency pins.

```bash
PAYMENT_FIX_TEST_PG_URL="${PAYMENT_FIX_TEST_PG_URL:?use a disposable PostgreSQL test cluster}" \
  USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-quality \
  AIFACTORY_PYTEST_HARD_CAP_SEC=1800 \
  .venv-quality/bin/python scripts/run_factory_pytest_ci.py --timeout-method=signal

.venv-quality/bin/python -m pytest -q -m component_integration
.venv-quality/bin/python -m pip_audit -r requirements.txt
AIFACTORY_AUDIT_PYTHON=.venv-quality/bin/python bash scripts/run_dependency_audit.sh
# The dependency gate now passes, including frontend development dependencies.

cd web/frontend
npm ci --ignore-scripts
npm run lint -- --max-warnings=0
npm run test:unit
npm run build -- --webpack
# Start production with isolated data, then run the existing Playwright suite against it.
```

Assessment references include [OWASP error handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)
and the [pytest exit-code contract](https://www.pytest.org/en/latest/reference/exit-codes.html).
They are assessment references, not certifications.
