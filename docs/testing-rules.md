# Testing rules — read before you say "tests are green"

Hard-won rules for this codebase. Green pytest is necessary, not sufficient.
See the [2026-10-23 quality audit](quality-audit-2026-10-23.md) for the latest checked scope,
results, and remaining gaps.
For payment lifecycle, transaction reconciliation and the SQLite/PostgreSQL recovery matrix,
see [payment tests and transactions](payment-tests-and-transactions.md)
([RU](payment-tests-and-transactions.ru.md) · [ES](payment-tests-and-transactions.es.md) · [FR](payment-tests-and-transactions.fr.md) · [ZH](payment-tests-and-transactions.zh.md)).

---

## R1 — A new product-dict field must survive the SQLite round-trip

**The trap:** most tests use the JSON state backend, which round-trips *any* field. Production runs
`USE_SQLITE=true`, which persists only the keys allow-listed in
[`orchestrator/product_extras.py`](../orchestrator/product_extras.py) (`PRODUCT_EXTRA_KEYS`). A
field you add to a product dict — read at a later stage — is **silently dropped on reload** under
SQLite. Tests stay green; the feature does nothing in prod.

**Rule:** when you add a product field that is read after the stage that sets it (anything that must
survive a pipeline cycle), add it to `PRODUCT_EXTRA_KEYS` **and** write a round-trip test:

```python
from orchestrator.product_extras import extract_product_extras, merge_product_extras
extras = extract_product_extras({"id": "p1", "your_field": value})
assert merge_product_extras({"id": "p1"}, extras)["your_field"] == value
```

Real cases this caught: `config_arm`, `max_quality_loops_override` (L4 bandit never learned),
`surrogate_decisions` (AI-gate audit lost). See [[product-extras-sqlite-allowlist]].

## R2 — Run the suite under SQLite, not just the default

`USE_SQLITE=true pytest …` for anything touching pipeline state. If a test only ever exercises the
JSON backend, it cannot catch R1-class bugs. CI runs SQLite — match it locally before pushing.

**Local setup:** host Python often lacks `aiosqlite`. Use the project venv helper:

```bash
chmod +x scripts/run_tests_sqlite.sh
./scripts/run_tests_sqlite.sh tests/test_learning_loop_extras.py -q
```

Or manually: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then
`USE_SQLITE=true .venv/bin/python -m pytest …`.

## R3 — "Wired" ≠ "works". Trace the loop end-to-end with the real functions.

A module existing and being imported at a call site does **not** mean the loop closes. The L4 bandit
was fully "wired" (assign → apply → reward) and learned nothing because of R1. Before claiming a
feedback loop works, run a script that calls the **real production functions** end-to-end (not
reimplementations) and assert the *output artifact* changed — e.g. feed builds through
`record_terminal_outcome`, then assert `playbook.jsonl` gained an active rule and
`bandit.jsonl`/`outcomes.jsonl` got the row. See the demonstration pattern in this session's history.

## R4 — A field with no reader is not "done" — it's dead code

Before adding a field to the allow-list or calling a feature complete, grep for a **consumer**:

```bash
grep -rn "your_field" orchestrator core agents web --include=*.py | grep -v "test"
```

If it is only ever assigned, it is write-only and the feature is half-wired (e.g.
`surrogate_repair_hint` is generated but never fed to the dev agent). Don't persist dead fields;
don't claim the capability ships.

## R5 — The ruff gate is part of "passing"

CI fails on the lint gate, not only pytest. Reproduce it before reporting a clean result:

```bash
ruff check core/ llm/ orchestrator/ security/ agents/ --ignore E402
```

Enforced rule sets: `E,F,I,N,UP,B,C4,SIM,TCH,PIE,RUF100` (see `pyproject.toml`). Most are
auto-fixable (`--fix`); `TCH`/`SIM` may need `--unsafe-fixes` — but after a TYPE_CHECKING move,
re-run an **import smoke** (`python -c "import the.module"`) because moving a runtime import into
`if TYPE_CHECKING` breaks anything constructed at runtime.

## R6 — Self-learning claims need the frozen-control, not a vibe

Don't assert "the factory got smarter" from a synthetic run where you handed the live cohort better
numbers. The real verdict is the **live-vs-frozen-control gap** (`AIFACTORY_LEARNING_FROZEN=1` on a
cohort; `factory_ev_per_build{cohort}` / `/api/analytics/factory-iq`). A unit test proves the
*mechanism*; only the production A/B proves the *uplift*. State which one your evidence is. See
[`docs/effective-self-learning.md`](effective-self-learning.md) §4.

## R7 — Public/boundary surfaces need a leak test, not just a happy-path test

Anything served unauthenticated (`/api/public/*`, build replay, `/api/public/factory-iq`) must have a
test asserting it emits **only** whitelisted scalars — no prompts, raw outputs, paths, keys, or
per-product internals. Mirror the boundary discipline in
[`web/backend/services/build_replay.py`](../web/backend/services/build_replay.py).

## R8 — Cold-start / empty-data must be neutral and safe

Learning and analytics functions are called before any data exists. Assert the empty case explicitly:
neutral priors (not noise), no division by zero, no `KeyError`. The discovery scorer once raised
`KeyError: 'outcome_fit'` when called without `data_root` — only an empty-input test would have caught
it. Add a `test_*_empty`/`test_*_cold_start` for every new aggregator.

## R9 — Respect the concurrent writers and workspace publication policy

The working tree has other writers (factory/Cursor). Preserve their changes. If staging is
requested, stage **only your own files** (`git add <paths>`, never `git add -A`). Keep audit
changes local. The workspace [AGENTS.md](../AGENTS.md) prohibits GitHub publication.

## R10 — A coverage file does not prove tests passed

Only a completed pytest process with exit code 0 establishes a passing test run. Coverage can
be written after a failure or before interpreter teardown hangs. The CI runner
[`scripts/run_factory_pytest_ci.py`](../scripts/run_factory_pytest_ci.py) preserves pytest's exit
status, clears stale reports, and returns **124** when the run exceeds
`AIFACTORY_PYTEST_HARD_CAP_SEC` (default **600**, a positive integer). It terminates the test process
group so browser/server children do not survive a cancelled run. The former
`AIFACTORY_PYTEST_HANG_GRACE_SEC` shortcut is no longer used.

`scripts/run_factory_pytest.sh` uses `.venv/bin/python` in CI when available. Both runners use
[.coveragerc](../.coveragerc), including `core`, `llm`, and `security`. The regular factory runner
excludes the browser-heavy files listed in that script; those require their separate jobs.
Skipped, excluded, and deselected tests are not evidence of passing those scenarios.

## R11 — Corrupt budget state must block paid calls

The LLM usage guard starts at zero only when its state file is absent. Invalid JSON, unreadable
files, invalid dates, negative/non-finite counters, and invalid request timestamps raise
`LLMUsageStateError`. A rejected read leaves the original file unchanged. Writes use atomic
replacement and mode 0600; an I/O failure propagates to the caller.

Recovery: stop paid workers, preserve the damaged file for investigation, restore the last
valid ledger, and reconcile spend since that backup with provider billing before resuming.
Deleting the ledger resets recorded spend; do not use deletion as a recovery procedure.

## R12 — Test production error boundaries using every deployment alias

Public unexpected failures return a generic response while server logs retain diagnostics.
`AIFACTORY_EXPOSE_ERROR_DETAILS` is a development-only opt-in. The main API uses
`security.prod_startup_guard.is_production_mode()` to suppress details under `AIFACTORY_PROD`,
`AIFACTORY_PRODUCTION`, and production `AIFACTORY_ENV` values. Boundary regression tests must
assert that internal paths and exception text never appear in those production responses.

## R13 — Exercise contracts between real components

Mocks can reproduce the same incorrect assumptions on both sides of a boundary. The
`CostGuard` unit tests supplied `daily_cost_cap_usd`/`monthly_cost_cap_usd`, while the actual
`LLMUsageGuard` returns `daily_cap_usd`/`monthly_cap_usd`. As a result, unit tests passed while
real budget-aware model selection always saw the normal tier. Component integration tests
reproduced the mismatch before the consumer and its unit fixtures were corrected.

Run the deterministic component selection with:

```bash
USE_SQLITE=true .venv/bin/python -m pytest -q -m component_integration \
  tests/test_llm_accounting_integration.py tests/test_pipeline_recovery_integration.py
```

The LLM tests use the actual router, HTTP provider, pricing, file-backed ledger, and circuit
breaker. Only external HTTP is simulated using `httpx.MockTransport`; no paid provider calls
are made. They cover daily/monthly budget tiers, model selection, persisted spend, streaming,
failover/recovery, and corrupt-ledger rejection.

The pipeline tests connect the watchdog callback, state machine, real temporary SQLite,
event bus, and production build-replay router mounted in an in-process FastAPI app. They
check restart/retry ownership, terminal failure, next-agent handoff, response sanitization,
and database-corruption recovery. Managers, HTTP clients, and event-bus workers are closed
in fixture teardown.

`component_integration` is distinct from the existing `integration` marker for live fleet
probes. These new tests run in the normal local/CI suite and do not require an external stack.

---

## R14 — Financial coverage and recovery are explicit gates

The standard Factory runners measure branches and run
[`check_payment_coverage.py`](../scripts/check_payment_coverage.py) after a successful suite/export.
All 13 named financial functions require 100% measured lines and branches; missing data, an export failure or a rounded
percentage just below a floor must fail. The global percentage remains a separate, honest metric.
See the [latest audit](quality-audit-2026-10-23.md#skip-resolution) for floors, actual results and scope.

A failed/ambiguous order commit must retain the single-use transfer claim for the original checkout.
Test failure before and after commit, rollback between order/license inserts, persistence cleanup,
key backup restoration and retry with the same hash. A flag saying `confirmed` is not a committed order.
An unreadable financial history is unknown state: preserve it, refuse settlement and test recovery.
Never replace a missing quote key while signed quotes exist or put RPC credentials in error logs.
Balance/ledger/withdrawal changes and their signed receipt must share one transaction. Exercise signing
and SQL failures plus hard process exits after receipt insertion. A retry must return the persisted
receipt; missing legacy financial history requires reconciliation. The branch gate needs real SQLite
and disposable PostgreSQL tests. Live production probes run separately with explicit opt-in.

### Pre-merge checklist

- [ ] `USE_SQLITE=true pytest <touched slice>` green (R2)
- [ ] New product fields in `PRODUCT_EXTRA_KEYS` + round-trip test (R1)
- [ ] End-to-end trace through real functions asserts the artifact changed (R3)
- [ ] Every new field has a consumer (R4)
- [ ] `ruff check …` green + import smoke after any TYPE_CHECKING move (R5)
- [ ] Learning claims labelled mechanism-vs-uplift; frozen-control where it matters (R6)
- [ ] Public surfaces have a leak test (R7)
- [ ] Empty/cold-start test for new aggregators (R8)
- [ ] Staged only your files (R9)
- [ ] Completed test exit status checked; no success inferred from coverage (R10)
- [ ] Budget corruption and failed writes tested where spend tracking changes (R11)
- [ ] Production error responses tested for all deployment aliases (R12)
- [ ] Changed component contracts exercised with real producers and consumers (R13)
- [ ] Financial changes pass the full coverage gate and real-store failure/retry scenarios (R14)
