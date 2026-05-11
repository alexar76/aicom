# CLI reference (`cli/ai_company_cli.py`)

The Click-based CLI is invoked **inside the container** (or from a dev venv with `/app/data` mounted):

```bash
docker compose exec app python /app/cli/ai_company_cli.py --help
```

Some README examples use the shorthand **`ai-company`** — that binary is **not** guaranteed on `$PATH` in every image; prefer the explicit `python /app/cli/ai_company_cli.py` form unless your entrypoint wraps it.

---

## Command tree (implemented)

| Command | Purpose |
|---------|---------|
| `init` | Interactive bootstrap — bcrypt admin password (≥12 chars), `admin.json`, optional default `model_providers.yaml`, `director_rules.yaml`. |
| `start` | Writes PID file and spawns `python -m main` **inside the same environment** (legacy monolith helper — production stacks often use Compose/systemd instead). |
| `stop [--graceful]` | Stops PID from platform.pid. |
| `restart {orchestrator,web,director}` | **Stub** — prints success; real restarts go through process manager / Compose. |
| `create-idea "<text>"` | Enqueues one product idea into the pipeline data layer. |
| `create-ideas-batch` | Batch enqueue from `--ideas-file` and/or repeated `--idea`; `--mode`, concurrency guards. |
| `discover [--enqueue] [--top-k N]` | Runs discovery ranking; optional enqueue of top ideas. |
| `status [--watch]` | Shows pipeline / platform snapshot (see implementation for fields). |
| `models list` | Pretty table of providers from `model_providers.yaml`. |
| `models test <provider>` | HTTP probe (Ollama tags vs OpenAI-style `/models`). |
| `models switch <task_type> <provider>` | Rewrites routing rule `preferred_provider`. |
| `director run-now` | Runs collector → analyzer → decisions → report generator (real modules under `director/`). |
| `director config` | Prints `director_rules.yaml`. |
| `storefront list` | Reads `/app/config.yaml` storefront themes table. |
| `storefront apply <name>` | Sets active theme in `/app/config.yaml`. |
| **`director report`** | **Not implemented** — use Admin UI or read `/app/data/reports/director/*.md`. |
| **`storefront preview`** | **Not implemented** — use Next dev server or deployed URL. |
| `security scan` | **Demonstration** progress UI — not a full SAST suite. |
| `security report` | Prints a canned JSON-style panel. |
| `audit export [--from YYYY-MM-DD] [--format json|csv]` | Exports legacy `/app/data/logs/audit.jsonl`. |
| `wallet balance` | **Demo table** with placeholder addresses (not live chain balances). |
| `wallet withdraw …` | **Interactive demo** — confirms then prints fake initiation message. |
| `test-payment <product_id>` | **Smoke placeholder** for payment wiring. |

---

## Examples

```bash
# Initialize data directory (first boot)
docker compose exec -it app python /app/cli/ai_company_cli.py init

# Enqueue from operator terminal
docker compose exec app python /app/cli/ai_company_cli.py create-idea "Stripe-less invoice SaaS for freelancers"

# Discovery → optionally create products
docker compose exec app python /app/cli/ai_company_cli.py discover --top-k 5 --enqueue

# Routing experiment: send code_generation to a provider id defined in YAML
docker compose exec app python /app/cli/ai_company_cli.py models switch code_generation deepseek_api

# Director manual analysis
docker compose exec app python /app/cli/ai_company_cli.py director run-now
```

---

## When to prefer Admin UI or HTTP API

| Task | Recommended surface |
|------|---------------------|
| Provider secrets / keys | Admin **LLM Providers** (hot reload hooks) |
| Storefront hide / marketing copy | Admin **Pipeline** row panels → REST PATCH endpoints |
| Observability | Admin **Live Monitor**, Grafana/Prometheus stack |
| Bulk scripted intake | CLI batch / `POST /api/admin/products/create-batch` |

---

## Related docs

- [owner-guide.md](./owner-guide.md)  
- [api-integration-guide.md](./api-integration-guide.md)  
- [pipeline-operations.md](./pipeline-operations.md)  
