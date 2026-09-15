# Secrets and production hardening

## LLM API keys

**Do not** put provider keys in `docker-compose.yml` `environment:` — they appear in `docker inspect` and process listings.

| Method | Use when |
|--------|----------|
| **`.env`** (chmod `600`) | Local dev; loaded via `env_file` on the `app` service only |
| **`data/secrets/llm/<name>_api_key`** | Bind-mounted files read by `entrypoint.sh` when env is unset |
| **`docker-compose.secrets.yml`** | Production: Docker secrets → `/run/secrets/*` (not in container env at create time) |

Example file layout:

```bash
mkdir -p data/secrets/llm
printf '%s' 'sk-…' > data/secrets/llm/deepseek_api_key
chmod 600 data/secrets/llm/deepseek_api_key
docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d
```

`./run-compose.sh` auto-includes the secrets overlay when `data/secrets/llm/*_api_key` files exist.

## JWT

- **Docker:** `entrypoint.sh` creates `data/secrets/jwt_secret.key` (≥32 chars) and exports `JWT_SECRET_KEY`. Compose must **not** set `JWT_SECRET_KEY=` (empty).
- **Bare metal:** `JWT_SECRET_KEY` in env **or** the same file path via `JWT_SECRET_FILE`.

## Admin password

No repo default. First empty volume: TTY prompt or `data/secrets/bootstrap_admin.txt`. Dev only: `AIFACTORY_DEV_BOOTSTRAP_PASSWORD`.

## Grafana

`GRAFANA_ADMIN_PASSWORD` is **required** in `.env` (no `admin` fallback). `./scripts/fill_production_env.py` generates one when missing.

## Sandbox demo login

`AIFACTORY_SANDBOX_DEMO_PASSWORD` in `.env` **or** auto-generated `data/secrets/sandbox_demo_password` on first container start. Never use legacy `SandboxDemo!2026` on reachable hosts.

## Fernet key (`AIFACTORY_FIREWALL_RULES_FERNET_KEY`)

Encrypts `data/config/firewall_rules.json`. Rotation procedure:

1. Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Decrypt rules with old key, re-encrypt with new key (maintenance script or admin export/import).
3. Update env and restart `app`.
4. Keep old key in a secure vault for 30 days for rollback.

## Rate limiting

Guest landing and some public routes use IP-based windows. Multi-instance deploys should use a shared store (Redis) for limits — not implemented in single-container dev.
