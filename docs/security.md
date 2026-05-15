# Security — first-run admin, HTTP hardening, sandbox

> Operational security for AI-Factory v2.1. Complements **[admin-panel-rbac.md](./admin-panel-rbac.md)** (roles) and **[configuration.md](./configuration.md)** (env vars).

---

## First admin account (no default `admin123`)

The container **does not** ship a known password. On an **empty** data volume (`admin.json` / `admin_users.json` missing), `entrypoint.sh` runs `python3 -m security.bootstrap_admin`.

| Situation | What happens |
|-----------|----------------|
| **Interactive TTY** (`./run.sh`, `docker compose run --rm -it app`) | Console prompts for **Admin password** + confirmation (min 8 chars, hidden input). User: `admin`. |
| **Non-interactive** (`docker compose up -d`) | Random password written to **`data/secrets/bootstrap_admin.txt`** (mode `0600`). Read once, then delete or rotate. |
| **Dev / demos only** | Set `AIFACTORY_DEV_BOOTSTRAP_PASSWORD=…` in `.env` (skips prompt; never in production). |
| **CLI** | `python cli/ai_company_cli.py init` — interactive bcrypt password (≥12 chars), separate from Docker entrypoint. |

After first login, change the password via **Admin → Users** (super_admin) or your operator process.

**Existing installs** with `data/config/admin.json` already present are **not** reset on upgrade.

---

## HTTP security middleware

| Control | Env / behavior |
|---------|----------------|
| **CSRF** (cookie sessions) | Default **on** (`AIFACTORY_CSRF_PROTECT=1`). Login sets `csrf_token` cookie; mutating `/api/admin/*` requests with `access_token` cookie must send header **`X-CSRF-Token`**. Bearer-only API clients (no session cookie) are unaffected. Admin UI sends the header automatically. |
| **FirewallManager** | Wired on every request: rate limits + explicit IP deny rules. Full default-deny ACL only when **`AIFACTORY_FIREWALL_ENFORCE=1`** (otherwise localhost + whitelist rules from `data/config/firewall_rules.json`). Optional encryption: `AIFACTORY_FIREWALL_RULES_FERNET_KEY`. |
| **Security headers** | `X-Content-Type-Options`, `X-Frame-Options`, **`Referrer-Policy`**, CSP, optional HSTS. With **`AIFACTORY_ENABLE_DEFAULT_CSP=1`** (compose default): API gets a strict CSP (`default-src 'none'`) via `main.py`; Next.js UI gets a UI-safe CSP via `web/frontend/middleware.ts`. Override API with **`AIFACTORY_CSP`**, UI with **`AIFACTORY_FRONTEND_CSP`**. |
| **Grafana** | Set **`GRAFANA_ADMIN_PASSWORD`** in `.env` (`fill_production_env.py` / `deploy.sh` generate a random value when missing). No well-known default in compose. |
| **LLM caps (multi-worker)** | **`LLMUsageGuard`** uses a file lock + shared `llm_usage_guard.json` so RPM and USD caps apply across all Uvicorn workers. |
| **Sandbox require container** | **`AIFACTORY_SANDBOX_REQUIRE_CONTAINER=1`** (compose default) — `SandboxIsolation` fails instead of subprocess fallback when Docker is unavailable. |
| **Secrets vault** | `AIFACTORY_SECRETS_VAULT_FILE` and `AIFACTORY_SECRETS_MASTER_KEY_FILE` can point to separate paths. |
| **JWT** | Persistent `data/secrets/jwt_secret.key` or `JWT_SECRET_KEY` (≥32 chars). |
| **LLM provider ids** | On startup, `auto_migrate_provider_ids()` renames legacy keys in `model_providers.yaml` and `llm_calls.jsonl` (`AIFACTORY_AUTO_MIGRATE_PROVIDER_IDS=1`, default). |
| **WebAuthn 2FA** | Passkeys as alternative to TOTP (`mfa_method`: `webauthn` \| `totp`). Env: `AIFACTORY_WEBAUTHN_RP_ID`, `AIFACTORY_WEBAUTHN_ORIGIN`, `AIFACTORY_WEBAUTHN_RP_NAME`. |
| **CI security benchmark** | `scripts/run_security_benchmark.sh` — pytest subset for CSRF, firewall, audit, sandbox, usage guard, WebAuthn helpers. |

---

## Audit log hash chain

Tamper-evident audit entries live under **`data/logs/audit/audit-*.jsonl`**. Each line chains `previous_hash` → `hash`. The logger updates the in-memory chain tip **before** durable append and syncs from disk on each write (crash-safe).

`SecurityManager` writes login/security events to the **hash-chain only** when `AuditLogger` is available (`get_audit_logs` reads from the chain). Legacy flat `data/logs/audit.jsonl` is a fallback if the chain cannot be initialized.

## Automated tests

| Module | Covers |
|--------|--------|
| `tests/test_csrf_middleware.py` | CSRF block/allow, login exempt, Bearer-only |
| `tests/test_firewall_middleware.py` | HTTP rate limit, `AIFACTORY_FIREWALL_ENFORCE` ACL |
| `tests/test_sandbox_isolation_hardening.py` | Container mode `docker run` hardening flags |
| `tests/test_security_hardening.py` | Bootstrap password, firewall permissive mode, audit chain |
| `tests/test_security.py` | FirewallManager unit, AuditLogger, SecurityManager |
| `tests/test_agent_handoff_audit.py` | Pipeline `agent_handoff` hash-chain events |

## Agent-to-agent handoff audit

Each time the pipeline **queues the next agent** (normal flow, peer-review block, QA/security gate, runtime test, monitoring refresh), an **`agent_handoff`** entry is appended to the same tamper-evident chain as admin security logs (`data/logs/audit/audit-*.jsonl`).

| Field | Meaning |
|-------|---------|
| `actor` | `agent:{from_agent}` (who finished or triggered the transition) |
| `resource` | `pipeline/{product_id}` |
| `details.from_agent` / `details.to_agent` | Handoff endpoints |
| `details.reason` | e.g. `sequential`, `peer_review_block`, `qa_gate`, `security_gate` |
| `details.output_fingerprint` | Key names + digest only — **not** LLM body text |

**Admin API:** `GET /api/admin/agent/handoffs?limit=200&product_id=…`  
**Security tab:** search `agent_handoff` in the audit log viewer (same chain as login events).

---

## Sandbox and Docker

| Topic | Guidance |
|-------|----------|
| **Static preview containers** | `network=none`, `cap-drop ALL`, `no-new-privileges`, non-root user, read-only root + tmpfs. |
| **Compose previews** | Optional internal bridge (`AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION=1`, default) — no outbound internet from generated stacks. |
| **Host access from factory container** | **`host.docker.internal:host-gateway` is not enabled by default** (reduces escape surface). For Ollama/LLM on the host: `docker compose -f docker-compose.yml -f docker-compose.host-gateway.yml up -d`. |
| **Trust model** | Factory container with Docker socket can start sibling containers — treat the host as a high-trust boundary. |

---

## Landing / UI copy language

Pipeline agents follow **`LANGUAGE_SYSTEM`** (see `llm/content_languages.py`):

- **Admin → New product → Landing & UI copy language** — `auto` or a fixed locale (`ru`, `en`, `es`, `de`, …).
- **`interface_locale`** — sidebar language (`en` / `ru` / `es`) passed at product create as default when the brief is silent.
- **Architect** emits `content_language`; **Developer** sets `<html lang="…">` and all visible strings accordingly.
- Mixed / unclear brief → **English**; clear Russian/English brief → matching language.

Supported codes include: `en`, `ru`, `es`, `de`, `fr`, `pt`, `it`, `pl`, `uk`, `tr`, `zh`, `ja`, `ko`, `ar`, `hi`, `id`, `vi`.

---

## Production checklist (security)

1. Do **not** set `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` in production.
2. Rotate admin password after bootstrap; restrict `data/secrets/` permissions.
3. Set **`JWT_SECRET_KEY`** and **`AIFACTORY_CORS_ORIGINS`** to your public origin only.
4. Enable **HTTPS** + `AIFACTORY_ENABLE_HSTS=1` behind a reverse proxy.
5. Consider **`AIFACTORY_FIREWALL_ENFORCE=1`** only after whitelisting operator IPs in firewall rules.
6. Use **`docker-compose.host-gateway.yml`** only when the factory must reach services on the host.
