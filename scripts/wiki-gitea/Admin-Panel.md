# Admin panel

> Full tab reference: [`docs/admin-guide.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/admin-guide.md)

## URL

`/admin/login` → JWT session (cookie + optional Bearer for API scripts).

## Roles (RBAC)

| Role | Typical access |
|------|----------------|
| `viewer` | Read-mostly dashboards, pipeline view |
| `operator` | Mutations except destructive/super settings |
| `admin` | Full factory ops |
| `super_admin` | Users, security-sensitive settings |

Details: [`docs/admin-panel-rbac.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/admin-panel-rbac.md)

## Core tabs (operator)

| Tab | Purpose |
|-----|---------|
| **New product** | Submit idea + product type |
| **Pipeline** | Stage machine per `prod-*` id |
| **Dashboard** | Aggregate KPIs |
| **LLM Providers** | Provider keys, model routing |
| **LLM Logs** | Historical calls (filter by product/provider) |
| **Live Monitor** | Real-time pipeline + optional demo video |
| **Time Travel** | Replay / inspect past pipeline states |
| **Settings** | Persisted YAML overlay (quality, discovery, site) |
| **Storefront / Marketing** | Themes, vitrine policy |
| **Users** | Admin accounts, MFA |

## Auth tips

- Stale `admin_token` cookie → empty tabs; re-login clears state
- CSRF: mutating requests need `X-CSRF-Token` when using cookie session (UI sends automatically)
- Demo vitrine may open admin with limited viewer role — some write APIs blocked by design

## In-app documentation page

Next.js `/docs` renders curated guides + screenshots from `web/frontend/public/docs-screenshots/`.

## Demo replay

Pipeline walkthrough video:

- Admin **Live Monitor** / **Settings** when published
- `GET /api/public/pipeline-demo-replay`
- Regenerate: `python scripts/record_pipeline_demo_video.py` → `sync_demo_replay_from_recording.py`

Skill: `.cursor/skills/pipeline-demo-video/SKILL.md` in repo.
