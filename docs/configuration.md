# Platform configuration (layered YAML)

## Layers

1. **Fragments** — sorted `*.yaml` under the **fragments directory** (default: `config/fragments/` next to the primary file’s parent, e.g. `/app/config/fragments/` in Docker). When the primary overlay is stored on a volume (e.g. `AIFACTORY_CONFIG_YAML=/app/data/config/…`), set **`AIFACTORY_CONFIG_FRAGMENTS_DIR=/app/config/fragments`** so bundled defaults still load. Fragments ship with the image/repo and define safe defaults (agents, storefront themes, feature toggles, and so on).
2. **Primary overlay** — resolved path to the editable YAML file (see **Environment**). Application code should use **`core.paths.config_path()`** so `AIFACTORY_CONFIG_PATH` is honored; `load_merged_config` and `config_yaml_path()` implement the YAML-specific precedence (`AIFACTORY_CONFIG_YAML` → `AIFACTORY_CONFIG` → default). Values in the overlay **win** over fragments via deep merge.

Merge order: fragments in lexicographic filename order, then the primary file. Nested dicts are merged recursively; scalars and lists from the overlay replace the fragment value.

Implementation: `core/config_merge.py` (`load_merged_config`, `config_yaml_path`, `config_fragments_dir`, `deep_merge`) and `core/paths.py` (`config_path`).

## Environment

**`core.paths.config_path()`** is the preferred entry point for “which primary YAML file does this process use?” (FastAPI `AppConfig`, payment helpers, scripts such as `set_auto_pipeline`, and so on). It applies `AIFACTORY_CONFIG_PATH` first, then delegates to **`config_yaml_path()`** in `core/config_merge.py` for the YAML env pair below.

| Variable | Role |
|----------|------|
| `AIFACTORY_CONFIG_PATH` | Optional explicit path (highest precedence). Used by `config_path()`; not read inside `config_yaml_path()`. |
| `AIFACTORY_CONFIG_YAML` | Preferred path to the primary overlay when `AIFACTORY_CONFIG_PATH` is unset (optional; default `/app/config.yaml`). **Docker Compose / `./run.sh`** set this to `/app/data/config/admin_config_overlay.yaml` so Admin → Settings survive container rebuilds (bind-mounted `./data`). |
| `AIFACTORY_CONFIG_FRAGMENTS_DIR` | Optional absolute path to bundled `config/fragments` (e.g. `/app/config/fragments`). Required when `AIFACTORY_CONFIG_YAML` lives under `/app/data/…` so defaults are not resolved as `/app/data/config/fragments` (which does not exist). |
| `AIFACTORY_CONFIG` | Legacy alias; used only if `AIFACTORY_CONFIG_YAML` is unset. |

Precedence for the on-disk primary file: **`AIFACTORY_CONFIG_PATH`** → **`AIFACTORY_CONFIG_YAML`** → **`AIFACTORY_CONFIG`** → **`/app/config.yaml`**.

**Docker / Compose:** the writable overlay should live under the **`./data` → `/app/data`** bind mount (see `docker-compose.yml` / `run.sh`). Otherwise edits are written to `/app/config.yaml` inside the container filesystem and **disappear** when the container is recreated.

`load_merged_config(primary)` merges `primary` as the overlay; pass `config_path()` (or `None` to use `config_yaml_path()` defaults inside `load_merged_config`).

## Admin → Settings

The admin API loads the **merged** view into memory (`web/backend/core/config.py` → `AppConfig._load_config`). Saving (including POST `/api/admin/settings`) writes the **full in-memory dict** back to the primary path via `yaml.dump`.

That matches the previous single-file behavior: operators still edit one persisted file; the merge layer only affects **read** defaults and repo-bundled structure. If the overlay grows large after many saves, that is expected (it now carries the effective config snapshot).

**Scripts that must not inflate the overlay** (for example toggling a single flag) should read and write **only** the primary YAML file with normal `yaml.safe_load` / `yaml.dump`, as `scripts/set_auto_pipeline.py` does.

## Code paths that read platform config

Anything that needs “what the factory would see in production” should use **`load_merged_config(config_path())`** (or **`AppConfig`**, which uses the same path) instead of reading a hard-coded file alone. Examples: throughput presets, Telegram toggles, payment crypto block, site badge/head snippets, Director worker intervals.

**Admin → Settings** includes an expandable **Pipeline & product quality** section; values persist under the top-level YAML key **`quality`** (see `config/fragments/25-quality.yaml`). Matching `AIFACTORY_*` environment variables still override when set.

Secrets that must never live in the main overlay (Telegram tokens) use `data/secrets/telegram.yaml` and env vars; stripping legacy keys from the overlay still edits **only** the primary file (`telegram_credentials._strip_legacy_telegram_keys_in_config_yaml`).

### Host disk Telegram alerts

Defaults ship in `config/fragments/10-general.yaml` under `general.disk_*` and `general.telegram_notify_host_disk`. Operators can edit them in **Admin → Settings → Host disk alerts** (autosave with the rest of platform settings).

| `general.*` key | Default | Meaning |
|-----------------|---------|---------|
| `disk_warn_used_pct` | `90` | Warning when used % on a monitored path is ≥ this |
| `disk_crit_used_pct` | `96` | Critical when used % ≥ this |
| `disk_warn_free_gb` | `4` | Warning when free space &lt; this (GB) |
| `disk_crit_free_gb` | `1` | Critical when free space &lt; this (GB) |
| `disk_alert_cooldown_hours` | `8` | Minimum hours before repeating the same alert level |
| `disk_monitor_interval_minutes` | `15` | Background check interval |
| `telegram_notify_host_disk` | `true` | Send Telegram when thresholds are breached |

Runtime env overrides (until process restart) take precedence over saved settings — see `.env.example` (`AIFACTORY_DISK_WARN_USED_PCT`, `AIFACTORY_DISK_CRIT_USED_PCT`, `AIFACTORY_DISK_WARN_FREE_GB`, `AIFACTORY_DISK_CRIT_FREE_GB`, `AIFACTORY_DISK_ALERT_COOLDOWN_SEC`, `AIFACTORY_DISK_MONITOR_INTERVAL_SEC`, `AIFACTORY_DISK_MONITOR_PATHS`, `AIFACTORY_TELEGRAM_NOTIFY_HOST_DISK`). Implementation: `web/backend/services/host_disk_monitor.py`.

## Director / benchmark league (optional)

Autonomous benchmark runs (`scripts/benchmark_pass_rate.py`, triggered by Director on SLO breach or periodic autorun) call **admin** HTTP endpoints. Without credentials they would return **401** and overload the API.

| Variable | Role |
|----------|------|
| `AIFACTORY_BENCHMARK_ADMIN_TOKEN` | Admin JWT (same as browser `admin_token`) passed only to the benchmark subprocess via environment — **never** logged. |
| `AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE` | Alternative: path to a one-line file with the JWT (e.g. under `data/secrets/`, `chmod 600`). |

If **neither** is set, Director **skips** emitting `benchmark_now` on SLO auto-action and **skips** league runs (writes `data/state/benchmark_status.json` with `skipped_no_token`). Set one of the variables if you want autonomous benchmarks in production.

**Production (Docker Compose) — file on the bind-mounted data volume**

1. Sign in to **Admin** (`/admin/login`) with an account whose role is **admin** or **super_admin** (the JWT in browser devtools → Application → Local Storage → `admin_token` is the same string the API expects).
2. On the **host** next to your compose project (where `./data` is mounted to `/app/data`):

   ```bash
   install -d -m 700 ./data/secrets
   printf '%s' 'PASTE_JWT_HERE' > ./data/secrets/benchmark_admin_jwt.txt
   chmod 600 ./data/secrets/benchmark_admin_jwt.txt
   ```

3. In **`docker-compose.yml`** (or an override) under the `app` service `environment`, add:

   ```yaml
   AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE: /app/data/secrets/benchmark_admin_jwt.txt
   ```

   Prefer the **file** form in production so the token is not duplicated in shell history; avoid committing the file (it lives under `data/secrets/`, typically gitignored).

4. **Rebuild / restart** the `app` container so `director.worker` and benchmark subprocesses see the variable.

5. **Rotate** the file when the JWT expires (admin sessions are finite) or after password rotation — otherwise benchmarks stop until you refresh the token.

Optional: set `AIFACTORY_BENCHMARK_ADMIN_TOKEN` instead of `_FILE` if your orchestrator injects secrets only as env vars (same semantics).

## Other YAML files

Not every YAML file participates in this merge:

- `data/config/model_providers.yaml` — LLM router / admin providers UI.
- `data/config/director_rules.yaml` — Director decision rules.
- `llm_pricing.yaml` (path from code) — pricing overrides.

Provider ids in `model_providers.yaml` (`default_provider`, `providers` keys, routing `preferred_provider` / `fallback_provider`) should match `providers` keys in `llm_pricing.yaml` (canonical DeepSeek cloud id: **`deepseek_api`**, aligned with `config/fragments/50-llm.yaml`).

Treat those as separate documents unless explicitly wired to `load_merged_config`.

## LLM routing & critical-task escalation

The router (`llm/router.py`) always tries `default_provider` first when it is set
and healthy. Per-rule `preferred_provider` only applies when **no** default is
configured; `fallback_provider` only applies on **failover** (after the current
provider errors or its circuit is open) and only to *enabled* providers. So with
a default provider configured, normal routing switches only between that
provider's **heavy** (strong) and **light** models — never across providers.

The "strong model" for any task is therefore `model_role: heavy` **of the
default provider** — the one provider a user is guaranteed to have a key for.
Do **not** hardcode specific providers (e.g. `anthropic_cloud`) in routing rules
as a quality lever; a user may have no key for them.

### `llm.critical_escalation_enabled` (opt-in, default `false`)

Set in `config/fragments/50-llm.yaml` (Admin → Settings), or override with the
env var `AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED=1`. Reader:
`core.throughput_limits.effective_llm_critical_escalation_enabled()` (env wins
over config; surfaced in `throughput_snapshot()`).

When **enabled**, a **critical** task may fail over **across providers** — not
just between strong/weak models of the default. Escalation fires only when all
of the following hold:

1. **A stronger provider has a key.** The escalation target must have
   credentials wired — a literal `api_key`, a populated `api_key_env`, or be a
   local provider (Ollama, which needs none). Keyless cloud providers are never
   targeted.
2. **The default could not cope.** Escalation happens on the failover path only
   — after the default provider errored or its circuit breaker is open. The
   default is always tried first, so cost stays low in the happy path.
3. **The task is critical.** `security_scan`, `code_generation`,
   `architecture_design`, `qa_testing`, `hardening` — single source of truth is
   `llm.cost_guard._CRITICAL_TASK_TYPES` (`is_critical_task()`).
4. **Opt-in & documented.** Off by default. Enabling it intentionally widens
   routing from "model tier within one provider" to "between providers", which
   is why it is a distinct, clearly-labelled setting.

**Target selection:** among untried providers that are available *and*
credentialed, the router picks the highest `priority` (operator-declared
ranking in `model_providers.yaml`). On a cross-provider failover the model id is
**re-bound** to the new provider's role-appropriate model — a model id is
provider-specific, so the default's model is never carried onto another
provider. A caller-pinned `model_override` (e.g. the gate-failing repair model)
is always honored as-is.

When **disabled** (default), critical tasks behave exactly as before: default
provider first, then only a rule's explicit `fallback_provider` (if any).

## Security-related environment variables

See **[security.md](./security.md)** for narrative and production checklist. Quick reference:

| Variable | Role |
|----------|------|
| `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` | Dev only: known password on first empty install (skips console prompt). |
| `AIFACTORY_DEMO_READONLY` | `1` on public demo hosts (e.g. magic-ai-factory.com): blocks factory backup/restore, settings save, admin password change, user CRUD. Sandbox preview stays enabled. Persist in `.env` across rebuilds. See [security.md](./security.md#public-demo-mode-aifactory_demo_readonly1). |
| `AIFACTORY_FACTORY_RESTORE_MAX_MB` | Max upload size for factory restore ZIP from Admin (default `2048`). |
| `AIFACTORY_CSRF_PROTECT` | `1` (default): CSRF double-submit for admin cookie sessions. |
| `AIFACTORY_FIREWALL_ENFORCE` | `1`: enforce full firewall ACL on HTTP; unset = rate limit + deny list only. |
| `AIFACTORY_FIREWALL_RULES_FERNET_KEY` | Fernet key for encrypted `data/config/firewall_rules.json`. |
| `AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION` | `1` (default): internal Docker network for compose previews (no egress). |
| `AIFACTORY_ENABLE_DEFAULT_CSP` / `AIFACTORY_CSP` | API/HTML Content-Security-Policy headers. |
| `AIFACTORY_ENABLE_HSTS` | Emit Strict-Transport-Security behind HTTPS. |
| `JWT_SECRET_KEY` | HS256 signing key (≥32 chars) or use `data/secrets/jwt_secret.key` from entrypoint. |
| `AIFACTORY_SECRETS_VAULT_FILE` | Encrypted secrets vault path (default `data/secrets/encrypted_vault.json`). |
| `AIFACTORY_SECRETS_MASTER_KEY_FILE` | Fernet master key path (default `data/secrets/master.key`) — keep separate from vault file. |
| `GRAFANA_ADMIN_PASSWORD` | Grafana UI password — `fill_production_env.py` generates when missing. |
| `AIFACTORY_SANDBOX_REQUIRE_CONTAINER` | `1` = pipeline sandbox fails if Docker cannot start; also defaults execution mode to **container**. |
| `AIFACTORY_SANDBOX_EXECUTION_MODE` | `container` or `process` (overrides default). |
| `AIFACTORY_PIPELINE_IDLE_POLL_SEC` | Worker sleep when queue idle (default `2.0`; overridden immediately on wake). |
| `AIFACTORY_PIPELINE_ACTIVE_POLL_SEC` | Worker poll when tasks pending/running (default `0.25`). |
| `AIFACTORY_PIPELINE_WORKER_WAKE` | `1` (default): after API/CLI pipeline writes, POST `http://127.0.0.1:8091/wake` so the worker skips idle poll. |
| `AIFACTORY_WORKER_HEALTH_PORT` | Worker health + wake HTTP port (default `8091`; `0` disables). |
| *(dependency)* `watchfiles` | Installed with the app image (`requirements.txt`). Watches `pipeline.json` and `pipeline.db` parent dirs; wakes worker without waiting for idle poll. |
| `AIFACTORY_LLM_CIRCUIT_STATE_FILE` | Optional override for shared circuit-breaker JSON (default `data/state/llm_circuit_breakers.json`). |
| `AIFACTORY_POST_DEVOPS_HUMAN_GATE` | `1`/`0` explicit override for post-DevOps operator approve before Sales (full software). |
| `AIFACTORY_HUMAN_REVIEW_REQUIRED` | Default `1`: apply human gate when `delivery_profile` is `full_software`; set `0` to disable unless gate forced on. |
| `AIFACTORY_HUMAN_REVIEW_MODE` | `optional` (default) / `required` / `off` — release-cockpit integration with human review decisions in feedback stream. |

### Pipeline and storefront policy

**Delivery profile** (product create / spec): `marketing_landing` | `full_software` | `infer`. Normalized aliases include `landing`, `marketing`, `brochure` → `marketing_landing` (`core/delivery_profile.py`).

**Post-DevOps human gate:** after Security → DevOps, **`full_software`** products enter **`HUMAN_REVIEW_PENDING`** until Admin **Approve** (→ `SALES_ACTIVE` + sales task) or **Reject** (→ developer rework). **`marketing_landing`** skips the gate. APIs: `POST /api/admin/pipeline/products/{id}/human-review/approve|reject`.

**Authoritative pipeline state:** with `USE_SQLITE=true`, **`data/state/pipeline.db`** is source of truth; `pipeline.json` may be stale or partial — use Admin Pipeline or SQLite for ops.

**Host LLM on bare metal:** use compose overlay `docker-compose.host-gateway.yml` (not enabled in base `docker-compose.yml`).

**Product content language** at create time: request fields `interface_locale` and `content_locale` (`auto` or `en`/`ru`/…); stored on pipeline products for Architect/Developer agents.
