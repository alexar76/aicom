# Funnel growth layer

> **English** · **Русский:** [funnel-growth.ru.md](./funnel-growth.ru.md) · **Español:** [funnel-growth.es.md](./funnel-growth.es.md) · **Français:** [funnel-growth.fr.md](./funnel-growth.fr.md) · **中文:** [funnel-growth.zh.md](./funnel-growth.zh.md)

Public lead capture, pipeline auto-start, status tracking, analytics, and post-ship distribution. Implemented under `web/backend/services/funnel_*` and `web/backend/api/marketing.py`.

---

## Overview

| Surface | Path / API | Purpose |
|---------|------------|---------|
| Lead form | `/lead` | Public brief → optional auto-pipeline |
| Status page | `/status/{token}` | Poll product state (15s) |
| Trust metrics | Homepage `TrustMetricsStrip` | Live shipped / in-pipeline / leads |
| Admin widget | Dashboard → Funnel card | `GET /api/admin/funnel/dashboard` |
| Waitlist embed | `GET /api/marketing/waitlist.js` | Forms on generated landings |

On pipeline **COMPLETED**, `orchestrator/task_executor_agent.py` calls `funnel_distribute` (hub auto-list + blog) and `notify_lead_product_completed` (email).

---

## Public APIs

### `POST /api/marketing/lead`

```json
{
  "email": "owner@example.com",
  "idea": "Marketing landing for AI scheduling assistant with waitlist",
  "name": "",
  "company": "",
  "source": "lead_page",
  "referral": null
}
```

Response includes `status_token`, `status_url`, `product_id`, `pipeline_started`.

### `GET /api/marketing/lead/status/{token}`

Public (no auth). Returns masked email, `product_state`, `storefront_url`, `sandbox_ready`.

### `POST /api/marketing/waitlist`

For generated landing pages. Body: `{ "product_id", "email", "name?", "meta?" }`.

### Embed on a generated landing

```html
<script src="/api/marketing/waitlist.js" data-product-id="prod-xxx"></script>
<form data-aifactory-waitlist>
  <input type="email" name="email" required />
  <button type="submit">Join waitlist</button>
</form>
```

Or inject the script via **Admin → Settings → published site head HTML**.

---

## Environment

| Variable | Default | Role |
|----------|---------|------|
| `AIFACTORY_LEAD_AUTO_PIPELINE` | `1` | Enqueue `marketing_landing` product on lead submit |
| `AIFACTORY_FUNNEL_AUTO_HUB_LIST` | `1` | List product on hub when COMPLETED |
| `AIFACTORY_FUNNEL_NOTIFY_DISABLE` | unset | Skip completion email when `1` |
| `AIFACTORY_FUNNEL_DIR` | `data/funnel/` | Leads + waitlist persistence |
| `OUTREACH_SMTP_*` / `AIFACTORY_FUNNEL_SMTP_*` | — | Completion email (reuse outreach SMTP) |

Docker `data-init` and `entrypoint.sh` create `data/funnel/` and `data/logs/marketing/` owned by UID `10001`.

---

## Persistence

| File | Content |
|------|---------|
| `data/funnel/leads.json` | Lead records, status tokens, product linkage |
| `data/funnel/waitlist.jsonl` | Append-only waitlist signups |
| `data/logs/marketing/events.jsonl` | Analytics events (also used by funnel metrics) |

---

## Admin

- **`GET /api/admin/funnel/dashboard?window_hours=168`** — funnel stages, leads 7d, paid orders, recent leads.
- Requires admin RBAC (`Depends(require_admin_with_rbac)`).

---

## Tests

`tests/test_funnel_growth.py` — lead auto-pipeline, public status, analytics stages.

---

## Not in scope (future)

- Stripe one-shot checkout for landing CTAs
- Abandoned cart recovery
- Hero email capture (hero still uses `/api/public/generate-landing`)

See also: [marketing.md](./marketing.md) (storefront analytics), [pipeline-operations.md](./pipeline-operations.md).
