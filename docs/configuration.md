# Platform configuration (layered YAML)

## Layers

1. **Fragments** — sorted `*.yaml` under `config/fragments/` next to the primary file’s parent (typically `/app/config/fragments/` in Docker). They ship with the repo and define safe defaults (agents, storefront themes, feature toggles, and so on).
2. **Primary overlay** — resolved path to the editable YAML file (see **Environment**). Application code should use **`core.paths.config_path()`** so `AIFACTORY_CONFIG_PATH` is honored; `load_merged_config` and `config_yaml_path()` implement the YAML-specific precedence (`AIFACTORY_CONFIG_YAML` → `AIFACTORY_CONFIG` → default). Values in the overlay **win** over fragments via deep merge.

Merge order: fragments in lexicographic filename order, then the primary file. Nested dicts are merged recursively; scalars and lists from the overlay replace the fragment value.

Implementation: `core/config_merge.py` (`load_merged_config`, `config_yaml_path`, `deep_merge`) and `core/paths.py` (`config_path`).

## Environment

**`core.paths.config_path()`** is the preferred entry point for “which primary YAML file does this process use?” (FastAPI `AppConfig`, payment helpers, scripts such as `set_auto_pipeline`, and so on). It applies `AIFACTORY_CONFIG_PATH` first, then delegates to **`config_yaml_path()`** in `core/config_merge.py` for the YAML env pair below.

| Variable | Role |
|----------|------|
| `AIFACTORY_CONFIG_PATH` | Optional explicit path (highest precedence). Used by `config_path()`; not read inside `config_yaml_path()`. |
| `AIFACTORY_CONFIG_YAML` | Preferred path to the primary overlay when `AIFACTORY_CONFIG_PATH` is unset (optional; default `/app/config.yaml`). |
| `AIFACTORY_CONFIG` | Legacy alias; used only if `AIFACTORY_CONFIG_YAML` is unset. |

Precedence for the on-disk primary file: **`AIFACTORY_CONFIG_PATH`** → **`AIFACTORY_CONFIG_YAML`** → **`AIFACTORY_CONFIG`** → **`/app/config.yaml`**.

`load_merged_config(primary)` merges `primary` as the overlay; pass `config_path()` (or `None` to use `config_yaml_path()` defaults inside `load_merged_config`).

## Admin → Settings

The admin API loads the **merged** view into memory (`web/backend/core/config.py` → `AppConfig._load_config`). Saving (including POST `/api/admin/settings`) writes the **full in-memory dict** back to the primary path via `yaml.dump`.

That matches the previous single-file behavior: operators still edit one persisted file; the merge layer only affects **read** defaults and repo-bundled structure. If the overlay grows large after many saves, that is expected (it now carries the effective config snapshot).

**Scripts that must not inflate the overlay** (for example toggling a single flag) should read and write **only** the primary YAML file with normal `yaml.safe_load` / `yaml.dump`, as `scripts/set_auto_pipeline.py` does.

## Code paths that read platform config

Anything that needs “what the factory would see in production” should use **`load_merged_config(config_path())`** (or **`AppConfig`**, which uses the same path) instead of reading a hard-coded file alone. Examples: throughput presets, Telegram toggles, payment crypto block, site badge/head snippets, Director worker intervals.

**Admin → Settings** includes an expandable **Pipeline & product quality** section; values persist under the top-level YAML key **`quality`** (see `config/fragments/25-quality.yaml`). Matching `AIFACTORY_*` environment variables still override when set.

Secrets that must never live in the main overlay (Telegram tokens) use `data/secrets/telegram.yaml` and env vars; stripping legacy keys from the overlay still edits **only** the primary file (`telegram_credentials._strip_legacy_telegram_keys_in_config_yaml`).

## Other YAML files

Not every YAML file participates in this merge:

- `data/config/model_providers.yaml` — LLM router / admin providers UI.
- `data/config/director_rules.yaml` — Director decision rules.
- `llm_pricing.yaml` (path from code) — pricing overrides.

Provider ids in `model_providers.yaml` (`default_provider`, `providers` keys, routing `preferred_provider` / `fallback_provider`) should match `providers` keys in `llm_pricing.yaml` (canonical DeepSeek cloud id: **`deepseek_api`**, aligned with `config/fragments/50-llm.yaml`).

Treat those as separate documents unless explicitly wired to `load_merged_config`.
