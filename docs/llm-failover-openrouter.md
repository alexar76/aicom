# LLM emergency failover — DeepSeek outage → OpenRouter (MiniMax + Kimi K3)

When **DeepSeek** is down, billing fails, or API keys stop working, the ecosystem can be switched to **OpenRouter** in minutes without redeploying every satellite by hand.

## When to use this

- DeepSeek returns payment / quota / outage errors across Factory, Metis, ATLAS, MOMUS, etc.
- You need a **known-good** cloud path while DeepSeek billing is fixed.
- You want the **factory on soft hold** so no autonomous pipeline work compounds bad LLM state.

## What the script does

`./scripts/failover_openrouter_minimax.sh` (or `python3 scripts/llm_failover_openrouter.py apply`):

| Target | Action |
|--------|--------|
| **Factory** | `general.factory_on_hold: true`; `openrouter_api` default in `data/config/model_providers.yaml`; key in `data/secrets/llm/openrouter_api_key` |
| **Alien Monitor** | Same `model_providers.yaml` bind-mount |
| **ATLAS** | `.env` overrides: `ATLAS_LLM_*` → OpenRouter + `minimax/minimax-m3` |
| **Metis** | `/opt/metis/deploy/prod.yaml`: base → MiniMax; all DeepSeek seats → OpenRouter; **`intent_parser_c` → `moonshotai/kimi-k3`** |
| **SKOPOS** | Already defaults to OpenRouter in `agent.example.yaml` — ensure `OPENROUTER_API_KEY` is set |

Models:

- **MiniMax-M3** — `minimax/minimax-m3` (Factory default heavy/light, Metis base + most council seats)
- **Kimi K3** — `moonshotai/kimi-k3` (Metis `intent_parser_c` diversifier via OpenRouter)

## Prerequisites

1. A working **`OPENROUTER_API_KEY`** (billing active on [openrouter.ai](https://openrouter.ai)).
2. SSH to the factory host (`FACTORY_SSH`, default `my-vps`) and Metis host (`METIS_SSH`, default `root@skopos.modelmarket.dev`).
3. Optional: key already in `/opt/metis/.env` — then use `--from-metis-env`.

## Quick run

```bash
# Read OpenRouter key from Metis .env, patch Metis + factory host, hold factory
./scripts/failover_openrouter_minimax.sh --from-metis-env

# Local / CI only (no SSH)
OPENROUTER_API_KEY=sk-or-... python3 scripts/llm_failover_openrouter.py apply --no-restart

# Metis only
./scripts/failover_openrouter_minimax.sh --metis-only --from-metis-env
```

After apply on the factory host the script restarts **`aicom-app-1`**, **`atlas-atlas-1`**, and **`alien-monitor`** so new env + YAML are picked up. Metis: `docker restart metis`.

## Verify

```bash
# Factory hold
python3 scripts/pipeline_focus_status.py

# Provider default (inside app container)
docker exec aicom-app-1 python3 -c "
import yaml; from pathlib import Path
p=Path('/app/data/config/model_providers.yaml')
d=yaml.safe_load(p.read_text())
print(d.get('default_provider'), d['providers']['openrouter_api']['models'])
"

# Metis base model
ssh root@skopos.modelmarket.dev "grep -E '^(base_model|api_key_env):' /opt/metis/deploy/prod.yaml"
```

Send a smoke prompt through Factory admin LLM test or `POST https://metis.modelmarket.dev/v1/chat/completions`.

## Restore DeepSeek

1. Admin → Settings → **resume factory** (`factory_on_hold: false`) when DeepSeek is healthy again.
2. Restore backups created by the script:
   - `/opt/metis/deploy/prod.yaml.bak-*`
   - `data/config/model_providers.yaml` from your volume backup or git-less `.bak-*`
3. Remove or comment the `# llm_failover_openrouter` block in factory `.env` if you added ATLAS overrides.
4. `docker restart metis aicom-app-1 atlas-atlas-1 alien-monitor`

```bash
python3 scripts/llm_failover_openrouter.py restore-deepseek
```

## Files

| Path | Role |
|------|------|
| `scripts/failover_openrouter_minimax.sh` | Operator entrypoint (SSH + docker) |
| `scripts/llm_failover_openrouter.py` | Patch logic (Factory hold, Metis YAML, env) |
| `llm/persist_openrouter.py` | Factory `model_providers.yaml` + secret sync |
| `data/config/model_providers.example.yaml` | Documents `openrouter_api` provider block |

## Related

- Factory hold semantics: [pipeline-operations.md](pipeline-operations.md#factory-hold-pause--resume)
- Metis benchmark seats: [metis/docs/en/BENCHMARKS.md](https://github.com/alexar76/metis/blob/main/docs/en/BENCHMARKS.md)
- SKOPOS default provider: [skopos/agent.example.yaml](https://github.com/alexar76/skopos/blob/main/agent.example.yaml)
