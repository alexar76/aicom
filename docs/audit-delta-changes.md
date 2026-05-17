# Audit remediation status (May 2026)

Tracking table for the architecture / quality audit. Updated after remediation pass.

| Area | Finding | Status | Notes |
|------|---------|--------|-------|
| **Architecture** | `pipeline_worker.py` god object | 🟡 Partial | `task_executor.py` + persistence/sidecars/components; worker ~730 lines (cycle + helpers) |
| | Dual persistence split-brain | 🟡 Partial | `pipeline_state_sync.reconcile_*`; worker reconciles on load; admin JSON fallback remains |
| | Sidecar mixin misuse | ✅ OK | `PipelineWorkerSidecarMixin` is intentional SRP split, not duplicate god object |
| | `ArchitectAgent` 133-line prompt | ✅ Done | `agents/prompts/architect_role_prompt.md` + `architect_role.py` |
| **Code quality** | Silent `except: pass` | 🟡 Partial | `log_suppressed` in `dashboard.py` (bare `Exception`); JSON decode skips remain `continue` |
| | Hardcoded `/app/data` | ✅ Done (dashboard) | `web/backend/api/admin/dashboard.py` → `core.paths` helpers |
| | Magic numbers / type hints | ⏳ | LLM cache + worker limits via `core/env_settings.py`; broad type hints deferred |
| **Security** | API validation | 🟡 Partial | Centralized `schemas/api_requests.py`: products, customer, feedback, payment, ai_market, telemetry, support, demo-replay |
| | API keys in env | ✅ Documented | `docs/security-secrets.md` |
| | IP-only rate limiting | ✅ Documented | Redis shared limiter noted as production follow-up |
| | Fernet rotation | ✅ Documented | Procedure in `docs/security-secrets.md` |
| **Testing** | Pipeline worker tests | 🟡 Partial | `test_pipeline_worker_core.py`, `test_pipeline_worker_persistence.py`, hygiene tests |
| | Integration tests | 🟡 Partial | `test_pipeline_full_cycle_smoke.py`, `test_pipeline_integration.py` (SQLite cycle, dirty save, restart) |
| | Property-based | 🟡 Partial | `test_api_request_schemas_property.py` (Hypothesis on API bodies) |
| **Deploy** | Docker image / `.dockerignore` | 🟡 Partial | `.dockerignore` excludes heavy `data/*`; `data/users.json` added |
| | 60+ env vars | 🟡 Partial | `core/env_settings.py` validates core subset |
| | Postgres pipeline migration | ✅ Done | Inline `POSTGRES_SCHEMA` + admin migrate API (no Alembic for factory DB) |
| **Performance** | Sync SQLite in async | 🟡 Partial | `AsyncSQLiteManager` for async paths; sync still in CLI/migrate |
| | Full state serialization | 🟡 Partial | `AIFACTORY_PIPELINE_SQL_DIRTY_SAVE=1` (default): worker upserts only dirty products/tasks; `_sql_full_save` for hygiene/bootstrap |
| | LLM cache 500/300s | ✅ Configurable | `AIFACTORY_LLM_CACHE_*` in `env_settings` + `llm/router.py` |

## Verify

```bash
pytest tests/test_core_paths.py tests/test_api_request_schemas.py \
  tests/test_api_request_schemas_property.py \
  tests/test_pipeline_worker_core.py tests/test_pipeline_worker_persistence.py \
  tests/test_pipeline_integration.py tests/test_pipeline_full_cycle_smoke.py \
  tests/test_env_settings.py tests/test_retry_failed_queue_guard.py -q

wc -l pipeline_worker.py agents/architect.py
rg 'except Exception:\s*\n\s*pass' --glob '*.py' -U | wc -l
rg '"/app/data' --glob '*.py' | wc -l
```

## Remaining high-value work

1. Marketing / admin chat bodies still local to their modules; migrate if desired.
2. Broader compose/sandbox E2E in CI (Playwright) for storefront + FastAPI preview.
3. Admin read path: always reconcile + single writer contract.
4. Debounced coalescing of multiple dirty saves within one worker tick (optional).
