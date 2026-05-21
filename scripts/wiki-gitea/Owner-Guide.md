# Platform owner handbook

> Full illustrated handbook: [`docs/owner-guide.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/owner-guide.md)  
> User walkthrough: [`docs/USER_GUIDE.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.md) · RU: [`docs/USER_GUIDE.ru.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.ru.md)

## What you operate

One **Compose stack** turns briefs into web artifacts with optional **crypto checkout**, **sandbox previews**, and a **public storefront**.

- **Public:** storefront + `/api/products`, `/api/sandbox`, `/api/support` (Lumen buyer help)
- **Admin:** JWT SPA + `/api/admin/*`
- **Worker:** pipeline + Director on same container
- **Data:** bind mount `~/aicom-data:/app/data` (or `./data`)

**Homepage vs pipeline:** the marketing site highlights **guest landing** (`marketing_landing`). Autonomous Director and many admin submits use **`full_software`** — same gates, longer runs.

## Day-one checklist

1. [[Quick-Start]] — stack up, bootstrap password saved
2. **Admin → LLM Providers** — enable at least one provider + test latency
3. **Admin → Settings** — review quality / discovery toggles
4. Submit test product (`marketing_landing` first)
5. **Pipeline** tab until **COMPLETED** or inspect `BUG_FOUND`
6. **Storefront** — list when ready; understand remediation may reopen pipeline

## Key admin tabs

| Tab | Use |
|-----|-----|
| Dashboard | KPI snapshot (not full truth) |
| Pipeline | Per-product stages, errors, storefront toggle |
| LLM Providers | Keys, routing, models |
| LLM Logs | Trace failures (~jsonl on disk) |
| Live Monitor | Streaming metrics + demo replay |
| Settings | Merged YAML overlay persist |
| Users | RBAC, password, 2FA |

Screenshot workflow: `cd web/frontend && npm run capture-docs-screenshots`

## Storefront vs Completed

**Completed** in dashboard ≠ always on public vitrine. Listing requires storefront readiness + operator policy. During remediation, cards may stay visible while pipeline repairs (see [[Pipeline]]).

## Support vs pipeline

**Lumen** (`/api/support/*`) = buyer marketplace chat.  
**AI Agents** admin roster = pipeline agents only — do not confuse.

## CLI

[`docs/cli-reference.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/cli-reference.md) — `cli/ai_company_cli.py`

## Metrics & alerts

[`docs/factory-metrics-reference.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/factory-metrics-reference.md)  
Grafana: compose profile + `GRAFANA_ADMIN_PASSWORD` in `.env`
