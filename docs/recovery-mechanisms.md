# Recovery mechanisms

Operator-facing guide to **pause, restore, and roll back** AI-Factory and satellite stacks without silent data loss.

> **Pre-mainnet:** On-chain recovery (multisig owner, incident runbooks) is tracked in
> [`known-issues.md`](known-issues.md) (KI-2…KI-5). This document covers what works **today** in self-hosted factory + hub.

---

## Quick reference

| Situation | Mechanism | Entry point |
|-----------|-----------|-------------|
| Stop LLM spend immediately | **Factory hard hold** (`AIFACTORY_FACTORY_ON_HOLD=1`) | Env / compose |
| Pause pipeline + discovery (UI) | **Factory soft hold** (Admin → Settings) | [`admin-guide.md`](admin-guide.md) |
| Restore factory data | **Backup ZIP** + optional host tarball | [`owner-guide.md`](owner-guide.md) §7 |
| Bad SQLite migration | **Auto `.bak` + `--rollback`** | `python -m orchestrator.migrate --rollback` |
| Corrupt `pipeline.json` | **Recover from SQLite** | `AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE=1` |
| Postgres cutover / rollback | **pg_dump / pg_restore** | [`postgres-production-runbook.md`](postgres-production-runbook.md) |
| Failed product in pipeline | **Reopen failed** + `suggested_recovery` | Admin → product → Reopen |
| Stuck agent task | **Escalation ladder** (retry → restart → bypass) | `orchestrator/escalation.py` |
| LLM provider outage | **Circuit breaker** (half-open recovery) | [`admin-guide.md`](admin-guide.md), Prometheus |
| Mesh task stuck in VERIFYING | **Dead-letter recovery** | `ai-service-mesh` DB maintenance |
| ZK artifacts missing | **PLONK re-setup** (no ceremony) | `contracts/zk/scripts/setup_plonk.sh` |
| Release deploy mistake | **`rollback_plan`** in release cockpit | DevOps agent output |
| Desktop user data | **Versioned JSON export** | Desktop app Settings → backup |

---

## 1. Factory hold (soft vs hard)

### Soft hold (config / Admin UI)

- **Flag:** `general.factory_on_hold` in Admin Settings (persisted in factory config).
- **Effect:** Pipeline worker skips agent/LLM phases; **Director Discovery** (`market_research` LLM) and auto-enqueue are skipped; queued ideas remain in the queue.
- **Resume:** Toggle off in Admin → Settings → Factory hold.

### Hard hold (emergency)

- **Flag:** `AIFACTORY_FACTORY_ON_HOLD=1` in environment.
- **Effect:** Same as soft hold; overrides config — useful when UI is unreachable.
- **Code:** `core/factory_hold.py`, `director/worker.py`.

See also: [`pipeline-operations.md`](pipeline-operations.md), factory hold banner in Admin UI.

---

## 2. Backup and restore (factory)

### Admin ZIP (application-level)

1. Admin → Settings → **Download backup** (full factory state snapshot).
2. **Restore:** upload ZIP via Admin (creates pre-restore snapshot automatically).
3. **Blocked** on public demo (`public_demo_guard`).

### Host tarball (operator)

```bash
./scripts/backup_factory_data.sh
# Restores data/state, sqlite, secrets layout — see script header
```

**Recovery order after restore:** start Factory → `./scripts/deploy_hub.sh` → mesh/monitor per [`deploy-ecosystem.md`](deploy-ecosystem.md).

---

## 3. Database migration rollback

```bash
python -m orchestrator.migrate --status
python -m orchestrator.migrate --rollback   # uses automatic .bak before migrate
```

Tests: `tests/test_migrate_rollback.py`.

---

## 4. Pipeline JSON ↔ SQLite recovery

When `pipeline.json` is corrupt or stale but SQLite is authoritative:

```bash
export AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE=1
# restart factory API — writer rebuilds JSON from DB when safe
```

Logic: `core/pipeline_state_writer.py`.

---

## 5. Failed product recovery

1. Product reaches `FAILED` with failure report.
2. Admin → **Reopen failed** (`POST /pipeline/products/{id}/reopen-failed`).
3. Optional `suggested_recovery` routes to the right agent (PM, Dev, QA).

Services: `web/backend/services/pipeline_reopen.py`, `pipeline_failure_report.py`.

---

## 6. Task escalation & LLM circuit breaker

- **Escalation:** automatic retry → restart task → escalate to human → bypass (`orchestrator/escalation.py`).
- **LLM circuit breaker:** opens on provider errors; half-open probes before full recovery; metric `llm_circuit_recovery_duration_seconds`.

---

## 7. AI Service Mesh recovery

Stuck tasks in `VERIFYING` can be moved to dead-letter for manual replay — see `ai-service-mesh/backend/ai_service_mesh/db.py` and mesh operator docs.

---

## 8. ZK artifact recovery

| Backend | Recovery |
|---------|----------|
| **PLONK** (default) | Re-run `contracts/zk/scripts/setup_plonk.sh` — public ptau, no ceremony |
| **Groth16** (optional) | Multi-party ceremony per [`contracts/zk/ZK_CEREMONY.md`](../contracts/zk/ZK_CEREMONY.md) |

Production guard: `security/zk_artifacts.py` + `prod_startup_guard` blocks `AIFACTORY_PROD=1` with simulated ZK.

---

## 9. On-chain / contract recovery (pre-mainnet)

| Control | Purpose |
|---------|-----------|
| `Ownable2Step` | Two-step ownership transfer on EVM contracts |
| `AcceptOwnership.s.sol` | Accept pending owner after deploy |
| Multisig owner (planned KI-2) | Not yet required on testnet |
| External audit (KI-2) | Track in `contracts/audits/audit-response.md` |

Contract usage & testnet drills: [`contracts/USAGE.md`](../contracts/USAGE.md).

---

## 10. Full fleet redeploy (disaster-ish)

Ordered redeploy from repo root:

```bash
./scripts/deploy_ecosystem.sh
# Factory → deploy_hub.sh → mesh → monitor → verify_ecosystem_full.sh
```

Details: [`deploy-ecosystem.md`](deploy-ecosystem.md). **Do not** redeploy Hub via `cd aimarket-hub && docker compose up` — wrong build context.

---

## Related

- [`owner-guide.md`](owner-guide.md) — backups, first-run secrets
- [`configuration.md`](configuration.md) — env overrides
- [`security.md`](security.md) — audit chain, CSRF
- [`known-issues.md`](known-issues.md) — KI tracker
