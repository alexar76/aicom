# Contributing to AI-Factory

Thanks for helping improve AI-Factory v2.1. This document is the entry point for contributors; deeper operator and security detail lives under [`docs/`](docs/README.md).

## What you are working on

- **Backend:** FastAPI (`web/backend/`), pipeline worker (`pipeline_worker.py`), agents (`agents/`), orchestrator (`orchestrator/`).
- **Frontend:** Next.js admin + storefront (`web/frontend/`).
- **Config:** Layered YAML in `config/fragments/` with an optional overlay in [`config.yaml`](config.yaml) (intentionally empty in git — Admin → Settings persists overrides there).
- **Data:** Runtime state under `data/` (bind-mounted in Docker). **Do not commit** `data/users.json`, secrets, orders, or local methodology case dumps.

## Prerequisites

- **Python 3.12+**
- **Node.js 20+** (frontend)
- **Docker Compose V2** (recommended for full-stack dev and sandbox previews)
- At least one **LLM API key** (e.g. `DEEPSEEK_API_KEY` in `.env`)

## Local setup

```bash
git clone <your-fork-url>
cd aicom
cp -n .env.example .env    # add API keys; never commit .env

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # E2E / visual tests

cd web/frontend && npm ci && cd ../..
```

**Docker (closest to production):**

```bash
./scripts/deploy.sh --public-url http://localhost:9080
# Frontend http://localhost:9080  ·  API http://localhost:9081/api/health
```

First admin password: interactive TTY (`docker compose run --rm -it app`) or one-time file `data/secrets/bootstrap_admin.txt` on headless `up -d`. See [`docs/security.md`](docs/security.md).

## Development workflow

1. Fork the repo and branch from `main` (`feat/…`, `fix/…`).
2. Keep pull requests **focused** — one behavioral change per PR when possible.
3. Change **code, tests, and docs** together when behavior or env vars change.
4. Run the relevant checks locally (below) before opening a PR.
5. Do **not** commit secrets, wallet keys, or production hostnames unless they are public examples.

## Local checks

Run what your change touches; CI will run the rest on `main` / PRs.

| Check | Command |
|--------|---------|
| **Full backend tests** | `USE_SQLITE=true .venv/bin/pytest -q` |
| **Security benchmark** | `bash scripts/run_security_benchmark.sh` |
| **Single test file** | `.venv/bin/pytest tests/test_<name>.py -q` |
| **Python syntax (touched files)** | `python3 -m py_compile path/to/file.py` |
| **Frontend build** | `cd web/frontend && npm run build` |
| **OpenAPI schema** | `.venv/bin/python -c "from web.backend.main import app; app.openapi()"` |

**Playwright:** required for browser/E2E jobs (`python -m playwright install chromium --with-deps` on Linux CI).

**Pipeline worker locally:** `USE_SQLITE=true .venv/bin/python pipeline_worker.py` (needs configured providers and `data/state/`). The worker uses **event-driven wake** (`signal_new_work()`) with adaptive idle polling — see `AIFACTORY_PIPELINE_*_POLL_SEC` in [`docs/configuration.md`](docs/configuration.md).

## Continuous integration

GitHub Actions workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

| Job | Purpose |
|-----|---------|
| `backend-tests` | Full `pytest -q` with SQLite |
| `security-benchmark` | CSRF, firewall, audit chain, sandbox hardening, LLM usage guard, admin auth, WebAuthn helpers |
| `visual-standards-e2e` | Playwright visual standards |
| `browser-login-e2e` | FastAPI preview + declarative login crawl |
| `customer-api-smoke` | Uvicorn + `scripts/customer_journey_e2e.py` |
| `frontend-build` | `npm ci` + `npm run build` |

## Security-related contributions

Read [`docs/security.md`](docs/security.md) before changing auth, sandbox, firewall, or audit code.

| Area | Notes |
|------|--------|
| **Admin auth** | JWT in `data/secrets/jwt_secret.key`; CSRF on cookie sessions; TOTP or **WebAuthn passkeys** (`mfa_method`). |
| **Sandbox** | Prefer **container** mode in production (`AIFACTORY_SANDBOX_REQUIRE_CONTAINER=1`). Process fallback is dev-only. |
| **Audit** | Tamper-evident hash chain under `data/logs/audit/`; pipeline **agent handoffs** use action `agent_handoff`. |
| **LLM caps** | `LLMUsageGuard` is cross-worker (file lock on `llm_usage_guard.json`). |

Add or extend tests under `tests/test_security*.py`, `tests/test_csrf_middleware.py`, `tests/test_firewall_*.py`, `tests/test_sandbox_*.py`, `tests/test_agent_handoff_audit.py`.

## Configuration and migrations

- **Env vars:** document new keys in [`.env.example`](.env.example) and [`docs/configuration.md`](docs/configuration.md).
- **LLM provider IDs:** canonical names live in [`llm/provider_ids.py`](llm/provider_ids.py). Legacy ids (`deep-seek` → `deepseek_api`) are auto-migrated on API startup when `AIFACTORY_AUTO_MIGRATE_PROVIDER_IDS=1` (default). Manual run: `python scripts/migrate_llm_calls_provider_ids.py`.
- **Deploy helper:** [`scripts/fill_production_env.py`](scripts/fill_production_env.py) appends **missing** production keys only (never overwrites your `.env`).

## API documentation

- Swagger UI: `/api/docs` (proxied via frontend at `http://localhost:9080/api/docs` in Compose).
- Hand-crafted OpenAPI metadata: [`web/backend/openapi_meta.py`](web/backend/openapi_meta.py). Prefer adding `summary` / `description` on new FastAPI routes.
- Integration guide: [`docs/api-integration-guide.md`](docs/api-integration-guide.md).

## Pull request checklist

- [ ] **Why** — problem and intended outcome in the PR description.
- [ ] **Test plan** — commands run and observed results (copy-paste friendly).
- [ ] **Config/env** — new variables listed in `.env.example` + `docs/configuration.md` if applicable.
- [ ] **Secrets** — none in diff; no accidental `data/` commits.
- [ ] **Compatibility** — note API, pipeline state, or admin UI breaking changes.
- [ ] **Security** — if touching auth/sandbox/audit, mention threat model and link tests added.

## Commit messages

- Imperative, concise subject (≤72 chars when possible).
- Body explains **why**, not only what.
- Examples:
  - `Harden sandbox Docker defaults when container mode is required`
  - `Validate store orders with Pydantic before revenue aggregation`

## Code style

- Match surrounding modules (naming, imports, logging).
- Prefer extending existing helpers over duplicating logic.
- New Python modules: add **type hints** on public functions; agents are being migrated incrementally — add hints when you touch a file.
- Keep diffs focused; avoid drive-by refactors unrelated to the PR.

## Reporting bugs and proposing features

Open an issue with:

1. **Expected** vs **actual** behavior  
2. **Reproduction steps** (commands, env, product id if pipeline-related)  
3. **Logs** or screenshots (redact secrets)  
4. **Version** — commit hash or image tag  

## Good first contributions

- Clarify docs ([`docs/README.md`](docs/README.md) index).
- Add focused tests for pipeline state transitions, quality gates, or finance aggregation.
- Improve admin UI filters, error messages, or observability panels.
- Per-route OpenAPI `summary` / `description` on heavily used admin endpoints.
- Type hints on a single agent module you are already modifying.

## Where to read more

| Topic | Doc |
|--------|-----|
| Security | [`docs/security.md`](docs/security.md) |
| Configuration | [`docs/configuration.md`](docs/configuration.md) |
| Pipeline ops | [`docs/pipeline-operations.md`](docs/pipeline-operations.md) |
| Admin UI | [`docs/admin-guide.md`](docs/admin-guide.md) |
| Agents | [`docs/agents.md`](docs/agents.md) |
| Architecture | [`docs/architecture-orchestrator.md`](docs/architecture-orchestrator.md) |

Questions about scope? Open an issue before a large refactor. For production deployments, see [`docs/production-domain.md`](docs/production-domain.md) and [`README.md`](README.md).
