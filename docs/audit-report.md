# AI-Factory v2.1 — Uncompromising Audit Report

**Date:** 2026-05-17  
**Scope:** Full codebase audit — architecture, code quality, security, testing, deployment, performance  
**Tone:** Critical / "biased" — this report identifies problems, not accomplishments  

---

## 1. Architecture

### 1.1 Monolithic Pipeline Worker — `pipeline_worker.py` (1903 lines)

The central [`PipelineWorker`](pipeline_worker.py:86) class is a textbook god object. It handles:

- State loading & recovery (JSON corruption → SQLite snapshot)
- Task creation, execution, retry, timeout
- Agent initialization and lifecycle
- Health check HTTP server
- Quality gates, security gates, release critic
- Watermark policy, lesson recording, artifact persistence
- Content hash computation, poll interval tuning

**Problems:**

| Issue | Location | Severity |
|-------|----------|----------|
| Single class violates SRP — 7+ responsibilities | [`pipeline_worker.py:86-1889`](pipeline_worker.py:86) | 🔴 Critical |
| `_process_task()` spans 847 lines (704–1551) — impossible to reason about | [`pipeline_worker.py:704-1551`](pipeline_worker.py:704) | 🔴 Critical |
| `run()` loop is 83 lines with nested try/except blocks 6 levels deep | [`pipeline_worker.py:425-508`](pipeline_worker.py:425) | 🟠 High |
| State recovery logic duplicates state machine's own persistence | [`pipeline_worker.py:288-325`](pipeline_worker.py:288) | 🟠 High |
| Mixed sync/async: SQLite snapshot read is synchronous behind async method | [`pipeline_worker.py:246-286`](pipeline_worker.py:246) | 🟠 High |

### 1.2 Dual Persistence Layer (JSON + SQLite) — Split Brain Risk

The [`PipelineStateMachine`](orchestrator/state_machine.py:198) supports **three backends** (JSON, SQLite, PostgreSQL) but the worker's recovery logic only checks SQLite snapshots. If both diverge, there is no reconciliation strategy — the last snapshot wins.

| Problem | Location |
|---------|----------|
| No source-of-truth protocol when both backends are active | [`pipeline_worker.py:246-325`](pipeline_worker.py:246) |
| `_load_state_with_recovery()` only attempts SQLite, never PostgreSQL | [`pipeline_worker.py:288-325`](pipeline_worker.py:288) |
| `_save_state_async()` writes to one backend at a time — concurrent access risk | [`pipeline_worker.py:354-377`](pipeline_worker.py:354) |
| Migration from JSON to SQLite is one-shot, no rollback | [`orchestrator/state_machine.py:649-696`](orchestrator/state_machine.py:649) |

### 1.3 PipelineWorker Inheritance — Sidecar Mixin Misuse

[`PipelineWorker`](pipeline_worker.py:86) inherits [`PipelineWorkerSidecarMixin`](orchestrator/pipeline_worker_sidecars.py) — but the mixin contains core lifecycle methods (`signal_new_work`, `close`). This is an inversion: mixins should **add** optional behavior, not be required for the parent class to function.

### 1.4 Agent Architecture — Base Class Leaks Responsibilities

[`BaseAgent`](agents/base_agent.py:83-780) is 697 lines and contains:

- LLM generation with fallback logic (355-line `_fallback_generate`)
- JSON extraction with **7 fallback strategies** (`_extract_json`, 138 lines)
- Context augmentation with domain guides, lessons, code style
- Artifact persistence (save/load/list)
- Directory initialization
- Logging

**Problem:** Agents should receive prepared context, not self-augment. The base class knows too much about the file system, LLM routing, and data formats.

### 1.5 Architect Agent — 1210 Lines of Prompt Engineering

[`ArchitectAgent`](agents/architect.py:941-1209) has a **133-line system prompt** embedded as a string. It also contains:

- Visual design preset rotation (8 presets, SHA-256 hash selection)
- Novelty scoring against last 20 outputs (Jaccard similarity)
- Generic UI brief detection
- Design pipeline (moodboard → layout → final UI)
- Implementation contract validation (docker-compose, testing, etc.)

**Issues:**

| Problem | Location |
|---------|----------|
| System prompt embedded as raw string — no templating | [`agents/architect.py:961+`](agents/architect.py:961) |
| Visual design domain logic belongs in a separate module | [`agents/architect.py:168-423`](agents/architect.py:168) |
| `_needs_ui_experience()` heuristic is fragile keyword matching | [`agents/architect.py:136-150`](agents/architect.py:136) |
| 7+ helper functions at module level, not class methods | [`agents/architect.py:136-938`](agents/architect.py:136) |

---

## 2. Code Quality

### 2.1 Error Handling — Silent Failures Everywhere

The codebase has an epidemic of bare `except Exception: pass` or `except Exception: try...pass` patterns:

| Pattern | Count (approximate) | Impact |
|---------|---------------------|--------|
| `except Exception: ... pass` | 20+ occurrences | Bugs invisible in production |
| Bare `try:` without specifying exceptions | 30+ occurrences | KeyboardInterrupt swallowed |
| Nested try/except with no logging | 15+ occurrences | Silent data corruption possible |

Examples:

```python
# pipeline_worker.py:306
try:
    state = self._state_from_sqlite_snapshot()
except Exception:
    pass  # Corruption silently ignored, None returned
```

```python
# agents/base_agent.py:598
try:
    return json.loads(text)
except Exception:
    pass  # Falls through 6 more fallback strategies silently
```

### 2.2 Hardcoded Container Paths

At least **8 files** hardcode `/app/data/...` paths:

| File | Hardcoded Path |
|------|----------------|
| [`llm/router.py:46`](llm/router.py:46) | `config_path = "/app/data/config/model_providers.yaml"` |
| [`agents/base_agent.py`](agents/base_agent.py) | Artifact paths via `data_root / "artifacts"` |
| [`security/audit_logger.py`](security/audit_logger.py) | Log directory derived from `data_root` |
| [`web/backend/main.py:61`](web/backend/main.py:61) | `chat_path = Path("/app/data/state/chat_messages.json")` |
| [`llm/pricing_estimate.py:79`](llm/pricing_estimate.py:79) | `Path("/app/data") / "config" / "llm_pricing.yaml"` |

**Impact:** Running outside Docker (e.g., in tests) requires manual `AIFACTORY_DATA_ROOT` override — if forgotten, runtime failures or silent fallback to missing files.

### 2.3 Type Safety — Inconsistent

- [`pipeline_worker.py`](pipeline_worker.py) uses `dict` everywhere instead of typed dataclasses
- Worker methods receive/return `dict` for products, tasks, states — no type checking
- [`agents/base_agent.py`](agents/base_agent.py) uses `Optional[dict]` for structured data
- [`AgentInput`](agents/base_agent.py:27) / [`AgentOutput`](agents/base_agent.py:59) are dataclasses but agents return raw dicts through the pipeline
- `_process_task()` has no return type annotation

### 2.4 JSON Parsing — Over-Engineered Fallbacks

[`_extract_json()`](agents/base_agent.py:575-712) tries 7 strategies:

1. Direct `json.loads()`
2. Markdown code block extraction
3. Truncated JSON repair
4. Partial JSON recovery
5. Find first `{` / last `}`
6. Try with `strict=False`
7. Regex fallback

**Problem:** If the LLM consistently returns malformed JSON, the fix should be better prompting, not 7 parsing strategies. This masks prompt quality issues.

### 2.5 Magic Numbers and Strings

| Value | Location | Why Problematic |
|-------|----------|-----------------|
| `_METHODOLOGY_ISSUE_CAP = 22` | [`agents/pm.py:40`](agents/pm.py:40) | No explanation for 22 |
| `500` entries cache limit | [`llm/router.py`](llm/router.py) | Arbitrary — no memory sizing |
| `300` second TTL | [`llm/router.py`](llm/router.py) | No rationale |
| `0.18` novelty threshold | [`agents/architect.py`](agents/architect.py) | Magical similarity threshold |
| `60` second health check interval | [`llm/router.py:133`](llm/router.py:133) | Hardcoded |
| `15` min brute-force block | [`security/firewall.py`](security/firewall.py) | Not configurable |

---

## 3. Security

### 3.1 Firewall — Encryption Key in Environment Variable

[`FirewallManager`](security/firewall.py:73) reads `AIFACTORY_FIREWALL_RULES_FERNET_KEY` from the environment. While Fernet encryption at rest is good practice,:

- No key rotation mechanism
- Key derived directly from env var, not a secret store
- If the env var leaks (logs, error messages, `docker inspect`), all rules are decrypted
- `_resolved_fernet_key()` silently falls back to plaintext JSON if key is missing

### 3.2 Audit Logger — Crash-Safe but Not Race-Safe

[`AuditLogger.log()`](security/audit_logger.py:196-244) uses `fsync` for crash safety (good), but:

- File writes are not protected by a cross-process lock — two worker processes could corrupt the log
- File rotation is process-local — if two processes rotate simultaneously, data loss occurs
- `_audit_log_files_chrono()` sorts by filename but has no IPC mechanism

### 3.3 Agent Handoff Audit — Payload Fingerprinting Weakness

[`fingerprint_payload()`](security/agent_handoff_audit.py:43-50) only hashes the **first 40 keys** of the payload. This means:

- If the payload has 41+ keys, keys 41+ are **excluded from the audit trail**
- No error or warning when truncation occurs

### 3.4 Rate Limiting — IP-Only

[`FirewallManager.is_allowed()`](security/firewall.py:203-235) rate-limits by IP alone:

- NAT environments: all users behind one IP share the same limit
- No user-agent or session-based rate limiting
- No distributed rate limiting (Redis/centralized counter)
- Rate limit state is in-memory only — lost on restart

### 3.5 No Input Validation at API Layer

The [`web/backend/api/products.py`](web/backend/api/products.py) and similar modules accept user input, but:

- No structured input validation schemas (Pydantic models are absent in many routes)
- SQL injection possible in raw SQL queries in [`orchestrator/sqlite_manager.py`](orchestrator/sqlite_manager.py)
- No request size limiting at the application layer

### 3.6 API Keys in Environment — Docker Compose Leak

[`docker-compose.yml`](docker-compose.yml) passes **all** API keys as environment variables:

```
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
GROQ_API_KEY=gsk-...
TOGETHER_API_KEY=...
```

These are visible in `docker inspect`, `/proc` of any container process, and error logs.

---

## 4. Testing

### 4.1 Coverage Gaps

| Component | Estimated Coverage | Risk |
|-----------|-------------------|------|
| `pipeline_worker.py` (1903 lines) | Low — core orchestration untested | 🔴 Critical |
| Full pipeline end-to-end | Single smoke test | 🟠 High |
| Error recovery paths | Not tested | 🟠 High |
| `web/backend/main.py` (1225 lines) | Partial — route mocking | 🟠 High |
| Agent fallback generation | Not tested | 🟡 Medium |
| State machine edge cases | Partial | 🟡 Medium |

### 4.2 Test Quality Issues

- [`conftest.py`](tests/conftest.py) fixtures use `tempfile.TemporaryDirectory` but many tests don't clean up artifacts created inside
- `mock_llm_provider` fixture mocks the entire LLM layer — tests pass but don't validate real prompt→output integration
- Tests in [`test_pipeline_worker_core.py`](tests/test_pipeline_worker_core.py) use shallow mocks that don't exercise error paths
- No property-based testing for state machine transitions
- No load/stress tests for concurrent pipeline processing

### 4.3 Async Testing Inconsistency

Some tests use `@pytest.mark.asyncio` with `await`, others use synchronous wrappers. The `async_postgres_manager` and `async_sqlite_manager` have minimal async test coverage.

---

## 5. Deployment & DevOps

### 5.1 Docker Build — Bloated Image

[`Dockerfile`](Dockerfile):

- Single stage production image includes: Python, Node.js 20, Docker-in-Docker, Playwright browsers, build toolchain — **~2GB+ image size**
- `apt-get install` not combined with `rm -rf /var/lib/apt/lists/*` in one RUN layer
- No `.dockerignore` — potentially copies `node_modules`, `__pycache__`, test fixtures into the build context

### 5.2 Environment Variable Sprawl

**60+ environment variables** in [`docker-compose.yml`](docker-compose.yml) with no validation or defaults documentation:

- No single source of truth for what each variable does
- No type validation — `AIFACTORY_WORKER_POLL_INTERVAL_SEC_IDLE` could be "abc" and silently use default
- Variables spread across docker-compose, code defaults, and YAML config files

### 5.3 Database Migration — No Strategy

[`migrate_json_to_sqlite()`](orchestrator/state_machine.py:649-696) is the only migration path:

- No PostgreSQL migration support via this method
- No migration versioning
- No rollback on partial failure
- No zero-downtime migration

### 5.4 Single Point of Failure

- SQLite database file is a SPOF — corruption means total pipeline state loss
- No read replicas for PostgreSQL mode
- Pipeline worker is a single process — if it crashes mid-task, tasks are stale until recovery cycle
- No horizontal scaling for pipeline processing

---

## 6. Performance

### 6.1 Synchronous SQLite in Async Workers

[`_load_state_from_sqlite()`](orchestrator/state_machine.py:578-604) and [`_save_state_to_sqlite()`](orchestrator/state_machine.py:630-647) use synchronous `sqlite3` module inside async methods. This blocks the event loop during I/O.

### 6.2 Full State Serialization on Every Change

Every task completion serializes the **entire pipeline state** (all products, all tasks) to disk:

```
complete_task() → _apply_task_completion() → _save_state() → JSON/SQLite
```

For a pipeline with 100+ completed tasks, this means re-writing everything each time.

### 6.3 LLM Cache — Small and Short-Lived

- 500 entries max — for 11 agents × multiple products, this fills quickly
- 300-second TTL — most cache entries expire before reuse
- Cache is process-local — not shared between worker instances

### 6.4 Polling Loop Instead of Events

[`run()`](pipeline_worker.py:425-508) uses `mtime` polling with `time.sleep()`:

- Idle poll: `AIFACTORY_WORKER_POLL_INTERVAL_SEC_IDLE` (default 5s)
- Active poll: `AIFACTORY_WORKER_POLL_INTERVAL_SEC_ACTIVE` (default 1s)

This wastes CPU on idle polling. A file watcher (`inotify` / `watchdog`) would be more efficient.

---

## 7. Maintainability

### 7.1 Cyclomatic Complexity

| Method | Lines | Complexity Estimate |
|--------|-------|-------------------|
| `_process_task()` | 847 | > 50 (unmaintainable) |
| `_fallback_generate()` | 355 | > 20 |
| `generate()` in LLM Router | 89 | > 15 |
| `_load_state_with_recovery()` | 37 | > 10 |

### 7.2 Duplicate Configuration Sources

Pipeline flow is defined in **three places**:

1. [`config/pipeline_flow.json`](config/pipeline_flow.json) — SSOT (single source of truth)
2. [`STATE_TRANSITIONS`](orchestrator/state_machine.py:162-195) — duplicates agent flow mapping
3. [`_create_next_task()`](orchestrator/state_machine.py:477-527) — has `EXTENDED_PIPELINE` logic that skips stages

If `pipeline_flow.json` changes, `STATE_TRANSITIONS` must also change or the state machine rejects valid transitions.

### 7.3 No API Versioning

All API routes are unversioned (`/api/products`, `/api/admin/...`). Breaking changes require simultaneous frontend+backend deployment.

### 7.4 Frontend-Backend Coupling

Frontend [`lib/`](frontend/lib/) modules have hardcoded knowledge of backend response shapes. No API client generation from OpenAPI spec.

---

## 8. Recommendations Summary

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 🔴 | Split `pipeline_worker.py` into domain services (orchestrator, task runner, health) | 2 weeks | Architecture sanity |
| 🔴 | Replace bare `except Exception: pass` with specific exception handling + logging | 3 days | Bug visibility |
| 🔴 | Add input validation schemas (Pydantic) to all API routes | 1 week | Security |
| 🟠 | Make all `/app/data/` paths configurable with runtime validation | 1 day | Portability |
| 🟠 | Add PostgreSQL migration support to `migrate_json_to_sqlite()` | 2 days | Production readiness |
| 🟠 | Replace polling with file watcher or event-driven wakeup | 3 days | Performance |
| 🟠 | Add integration tests for `pipeline_worker.py` with real SQLite/PostgreSQL | 1 week | Reliability |
| 🟠 | Implement distributed rate limiting (Redis) | 3 days | Security |
| 🟡 | Move API keys to Docker secrets or vault | 1 day | Security |
| 🟡 | Add API versioning prefix (`/api/v1/...`) | 1 day | API stability |
| 🟡 | Extract Architect prompts to template files | 1 day | Maintainability |
| 🟡 | Add `.dockerignore` and optimize Docker layers | 1 day | Build performance |
| 🟡 | Add async SQLite/PostgreSQL access with connection pooling | 3 days | Performance |
