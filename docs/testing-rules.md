# Testing rules — read before you say "tests are green"

Hard-won rules for this codebase. Every one of these comes from a real bug that **passed unit
tests and still broke production**. Green pytest is necessary, not sufficient.

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

CI fails on the lint gate, not only pytest. Reproduce it exactly before pushing:

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

## R9 — Respect the concurrent writers

The working tree has other writers (factory/Cursor) that can revert edits. Stage **only your own
files** (`git add <paths>`, never `git add -A`), and on push to Gitea fetch+merge+retry on a race.
See [[repo-concurrent-writers-gitea]].

---

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
