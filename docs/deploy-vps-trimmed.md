# VPS deploy — trimmed factory checkout

Guide for `alexar76/aicom` on a single host **without** the full monorepo satellites in git.

For the agent that pushes to GitHub, see [`agent-github-factory-publish.md`](./agent-github-factory-publish.md).

---

```bash
./scripts/bootstrap-vps.sh --write-env
```

Host `python3-pip` / `nodejs` are **optional** — SDK tests run inside Hub/ARGUS containers. See [`agent-github-sdk-publish.md`](./agent-github-sdk-publish.md).

## 1. Bootstrap `.env`

```bash
cp .env.vps.example .env
chmod 600 .env
```

Regenerate from monorepo when vars change:

```bash
./scripts/generate_trimmed_env_example.sh --write
```

| Variable | Required | Notes |
|----------|----------|--------|
| `DEEPSEEK_API_KEY` (or other LLM) | yes | Pipeline + Monitor AI |
| `JWT_SECRET_KEY` | prod | Or let Docker create `data/secrets/jwt_secret.key` |
| `ALIEN_API_TOKEN` | yes for verify | `openssl rand -hex 32` |
| `AIMARKET_ADMIN_TOKEN` | yes for Hub | `deploy_hub.sh` can generate |
| `MESH_API_TOKEN`, `MESH_ADMIN_TOKEN` | yes for Mesh | `deploy_mesh.sh` can append |
| `NEXT_PUBLIC_SITE_URL` | yes | Public HTTPS origin |

---

## 2. Satellites (not in trimmed git)

```bash
./scripts/ensure_deploy_satellites.sh
# or CI: ./scripts/ci_fetch_factory_test_deps.sh
```

Clones `acex`, `aimarket-hub`, `plugins/*` from `github.com/alexar76/*`.

---

## 3. Deploy

```bash
./scripts/quickstart_ecosystem.sh --public-url https://your-domain.example.com
# or: ./scripts/deploy_ecosystem.sh --public-url https://your-domain.example.com
```

Unique Docker tags (avoids BuildKit stale image errors):

```bash
export AICOM_IMAGE_TAG="$(./scripts/docker_image_tag.sh)"
```

---

## 4. Nginx

Default: services bind **127.0.0.1**; nginx terminates TLS and proxies paths.

```bash
sudo ./scripts/install_nginx_proxy.sh
```

Snippets: `/monitor/` → `:9100`, `/pulse/` → `:5199`. Factory app still needs its own `server` routes for `:9080` / `:9081`.

### `ALIEN_HOST`

| Value | When |
|-------|------|
| `127.0.0.1` (default) | nginx in front — recommended |
| `0.0.0.0` | Direct access to `:9100` without proxy (debug only) |

---

## 5. Factory Admin — first login (P1-14)

Symptom: Admin UI stuck on «Проверка сессии…» / cannot sign in.

**Cause:** empty `data/` volume — no admin user / JWT yet.

**Fix (pick one):**

1. **Headless VPS** — create bootstrap password file before first start:
   ```bash
   mkdir -p data/secrets
   echo 'your-strong-password-here' > data/secrets/bootstrap_admin.txt
   chmod 600 data/secrets/bootstrap_admin.txt
   docker compose up -d app
   ```
   Login: user `admin`, password from file.

2. **Interactive first start** — `docker compose up app` (TTY) and follow entrypoint prompt.

3. **JWT** — ensure `JWT_SECRET_KEY` is set (≥32 chars) or `data/secrets/jwt_secret.key` exists after first boot.

Details: [`security.md`](./security.md), root `README.md` § Admin.

---

## 6. Prometheus optional (P1-13)

Monitor runs without Prometheus. If `:9090` is down, universe mode shows a **degraded metrics** banner; graph and UNI sim still work.

To enable: start Prometheus from root `docker-compose.yml` profile or point `PROMETHEUS_URL` at an existing instance.

---

## 7. Hub hello-capability (P1-9)

Hub in Docker cannot call `127.0.0.1` inside its network namespace.

On host:

```bash
cd aimarket-hub/examples/hello-capability
python3 server.py   # prints invoke_url
```

Hub container (via `deploy_hub.sh`):

- `AIMARKET_INVOKE_HOST_GATEWAY=host.docker.internal`
- `--add-host=host.docker.internal:host-gateway`

Publish:

```bash
AIMARKET_ADMIN_TOKEN=... ./publish.sh
```

---

## 8. SDK smoke (optional)

```bash
./scripts/sdk_e2e_hello.sh
```

Uses Hub container Python if host has no `pip`. Set `CAPABILITY_HOST` to your public IP when Hub runs in Docker.

## 9. ARGUS economy

| Symptom | Fix |
|---------|-----|
| `argus economy discover` → OFF | `ARGUS_WALLET_KEY` in `.env` or `argus keystore create` |
| HTTP `/ask` won't buy capabilities | `hub_invoke` needs approval — use `argus economy invoke` |

See [`argus/docs/developer-guide/en.md`](https://github.com/alexar76/argus/blob/main/docs/developer-guide/en.md).

## 10. Verify

```bash
./scripts/verify_ecosystem_full.sh
```

Expect all checks PASS after tokens and nginx are wired.
