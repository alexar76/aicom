# Security

> Full doc: [`docs/security.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/security.md) · RBAC: [`docs/admin-panel-rbac.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/admin-panel-rbac.md)

## Public demo disclaimer

**[magic-ai-factory.com](https://magic-ai-factory.com)** uses shared credentials `admin` / `demo123` and **`AIFACTORY_DEMO_READONLY=1`** in `.env`.

Visitors **cannot** change the demo password, save Settings, run factory backup/restore, or manage admin users. See [[Public-Demo]].

---

## First admin password

| Situation | Behavior |
|-----------|----------|
| Empty `data/` volume | `entrypoint.sh` runs bootstrap |
| TTY / `run.sh` | Interactive password prompt (min 8 chars) |
| `docker compose up -d` | Random password → `data/secrets/bootstrap_admin.txt` |
| **Never in prod** | `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` |
| **Public demo only** | `demo123` on magic-ai-factory.com — not for self-hosted |

Rotate after first login on **your** instance: **Admin → Users** (super_admin). **Disabled on public demo.**

## HTTP hardening

| Control | Default |
|---------|---------|
| CSRF on cookie sessions | `AIFACTORY_CSRF_PROTECT=1` |
| Firewall manager | Rate limits; full deny when `AIFACTORY_FIREWALL_ENFORCE=1` |
| CSP | `AIFACTORY_ENABLE_DEFAULT_CSP=1` |
| Sandbox | `AIFACTORY_SANDBOX_REQUIRE_CONTAINER=1` |
| JWT | Persistent `data/secrets/jwt_secret.key` |
| Public demo | `AIFACTORY_DEMO_READONLY=1` on shared demo host |

## LLM keys

Not in compose `environment:` — use `.env`, `data/secrets/llm/*`, or `docker-compose.secrets.yml`.

[`docs/security-secrets.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/security-secrets.md)

## Factory backup / restore

Self-hosted **admin+** only. Full snapshot replace — see [[Owner-Guide]] and Settings. **Blocked when `AIFACTORY_DEMO_READONLY=1`.**

## Audit chain

Tamper-evident logs: `data/logs/audit/audit-*.jsonl` (hash chain per line).

## Sandbox

Preview runs in isolated Docker network when enabled. **Sandbox start blocked on public demo.**

## CI security tests

```bash
scripts/run_security_benchmark.sh
```
