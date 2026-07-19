# Agent brief — publish trimmed factory to GitHub (`alexar76/aicom`)

**Audience:** Cursor / CI agent that runs `scripts/publish_aicom_factory.sh` and maintains the public factory mirror.  
**Source of truth:** full monorepo at `Superowner/aicom` / local checkout — **not** the trimmed GitHub tree alone.

---

## What the trimmed repo is

`publish_aicom_factory.sh` rsyncs the monorepo **minus satellites** (`acex/`, `aimarket-hub/`, `plugins/`, `ai-service-mesh/`, etc.) to `alexar76/aicom`.  
Ecosystem deploy on a VPS needs those folders — they are separate GitHub repos.

| Need | Script / action |
|------|-----------------|
| CI pytest (factory + hub imports) | `./scripts/ci_fetch_factory_test_deps.sh` |
| VPS full ecosystem deploy | `./scripts/ensure_deploy_satellites.sh` then `./scripts/deploy_ecosystem.sh` |
| Single satellite publish | `./scripts/mirror_satellites.sh <id>` per `scripts/satellite-map.yaml` |

**Never** commit `.env`, `data/secrets/`, or tokens to the public mirror (rsync excludes enforce this).

---

## Publish workflow (happy path)

```bash
# 1. From full monorepo — implement + test here first
git pull origin main

# 2. Optional: export-only sanity check
./scripts/publish_aicom_factory.sh --dry-run

# 3. Push trimmed tree to GitHub
AICOM_FACTORY_REMOTE=https://github.com/alexar76/aicom.git \
  ./scripts/publish_aicom_factory.sh --message "sync factory from monorepo"

# 4. Satellites that changed in the same session (examples)
./scripts/mirror_satellites.sh aimarket-hub
./scripts/mirror_satellites.sh alien-monitor
```

Auth: `GH_PAT` or `GITHUB_TOKEN` with `repo` scope.

**Do not publish:** `docs/gitea-publishing.md` (internal Gitea hosts) — excluded in `scripts/aicom_publish_config.py`.

**Do publish:** this file, `docs/deploy-vps-trimmed.md`, `docs/deploy-ecosystem-runbook.md`, `docs/agent-github-sdk-publish.md`, `.env.vps.example`.

---

## P1 backlog — who fixes what

| ID | Topic | Monorepo status | GitHub agent action |
|----|--------|-----------------|---------------------|
| **P1-6** | BuildKit `image already exists` | **Fixed:** `scripts/docker_image_tag.sh`, `AICOM_IMAGE_TAG` on compose services, `build --pull` in deploy scripts | Ensure factory CI sets `AICOM_IMAGE_TAG=$(./scripts/docker_image_tag.sh)` before `docker compose build`. Do not rely on bare `:latest` for rebuild loops. |
| **P1-8** | `ALIEN_HOST=0.0.0.0` | **Documented:** default `127.0.0.1` + nginx; `.env.example` + runbook | No code change on mirror unless docs drift — copy latest runbook on publish. |
| **P1-9** | Hub `invoke_url` → `127.0.0.1` | **Fixed in `aimarket-hub`:** `AIMARKET_INVOKE_HOST_GATEWAY`, `hello-capability/publish.sh` | **Mirror `aimarket-hub`** after monorepo hub changes. VPS: `deploy_hub.sh` sets gateway + `host.docker.internal:host-gateway`. |
| **P1-10** | `install_nginx_proxy.sh` | **Added:** `scripts/install_nginx_proxy.sh` + snippets under `deploy/nginx/snippets/` | Included in factory publish. On VPS: `sudo ./scripts/install_nginx_proxy.sh` after nginx vhost exists. |
| **P1-11** | `.env.example` trimmed | **Added:** `scripts/generate_trimmed_env_example.sh` → `.env.vps.example` | Run `--write` in monorepo before publish; commit `.env.vps.example` to factory repo. |
| **P1-13** | Prometheus degrade | **Fixed:** Monitor UI banner when `layer_errors` contains prometheus | Mirror **`alien-monitor`** satellite for frontend change. Prometheus itself remains optional on VPS. |
| **P1-14** | Factory admin bootstrap | **Documented:** `docs/deploy-vps-trimmed.md` § Admin | No mirror code — operator creates `data/secrets/bootstrap_admin.txt` or uses TTY on first `up`. |

---

## VPS deploy checklist (after GitHub sync)

```bash
cp .env.vps.example .env   # fill secrets
chmod 600 .env

./scripts/ensure_deploy_satellites.sh
./scripts/deploy_ecosystem.sh --public-url https://your-domain.example.com
sudo ./scripts/install_nginx_proxy.sh   # if not already wired
./scripts/verify_ecosystem_full.sh
```

Generate tokens if missing:

```bash
openssl rand -hex 32   # ALIEN_API_TOKEN, AIMARKET_ADMIN_TOKEN
```

Factory admin first login: see `docs/security.md` — password from bootstrap file or interactive Docker entrypoint, not from the repo.

---

## CI on trimmed factory (GitHub Actions)

Minimum before `docker compose build` or pytest:

```yaml
- run: ./scripts/ci_fetch_factory_test_deps.sh
- run: export AICOM_IMAGE_TAG="$(./scripts/docker_image_tag.sh)"
- run: docker compose build --pull app
```

Hub/Mesh/Monitor images on VPS use **deploy scripts** in the full checkout (`deploy_hub.sh`, `deploy_mesh.sh`, `deploy_alien_monitor.sh`), not only root `docker-compose.yml`.

---

## When monorepo and mirror diverge

Symptoms: missing base-path routes (`/monitor/api/*`), verify script failures, old Hub invoke behavior.

1. Pull latest monorepo on the build host.
2. Re-run `publish_aicom_factory.sh` + mirror affected satellites.
3. Redeploy on VPS from **full** tree (or clone satellites next to trimmed factory).

Base-path fixes live in `alien-monitor/`, `apps/pulse-terminal/`, `platon/` — mirror those repos, not only factory.

---

## Related docs

- [`green-badges-runbook.md`](./green-badges-runbook.md) — keep CI / Security / Pages badges green after publish  
- [`deploy-vps-trimmed.md`](./deploy-vps-trimmed.md) — operator-facing VPS guide  
- [`deploy-ecosystem-runbook.md`](./deploy-ecosystem-runbook.md) — prod redeploy + auth tiers  
- [`security.md`](./security.md) — admin bootstrap, JWT, tokens  
- `scripts/satellite-map.yaml` — which folders are satellites vs factory
