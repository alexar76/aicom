# Capa de crecimiento del embudo (Funnel growth)

> **English:** [funnel-growth.md](./funnel-growth.md) · **Русский:** [funnel-growth.ru.md](./funnel-growth.ru.md) · **Español** · **Français:** [funnel-growth.fr.md](./funnel-growth.fr.md) · **中文:** [funnel-growth.zh.md](./funnel-growth.zh.md)

Captura pública de leads, auto-inicio del pipeline, página de estado, analítica y distribución tras COMPLETED. Código: `web/backend/services/funnel_*`, `web/backend/api/marketing.py`.

---

## Resumen

| Superficie | Ruta / API | Propósito |
|------------|------------|-----------|
| Formulario lead | `/lead` | Brief → pipeline opcional |
| Estado | `/status/{token}` | Polling del producto (15 s) |
| Métricas de confianza | `TrustMetricsStrip` en home | Shipped / en pipeline / leads |
| Widget admin | Dashboard → Funnel | `GET /api/admin/funnel/dashboard` |
| Waitlist embed | `GET /api/marketing/waitlist.js` | Formularios en landings generados |

En **COMPLETED**, `orchestrator/task_executor_agent.py` llama `funnel_distribute` (hub + blog) y `notify_lead_product_completed` (email).

---

## APIs públicas

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

Respuesta: `status_token`, `status_url`, `product_id`, `pipeline_started`.

### `GET /api/marketing/lead/status/{token}`

Sin autenticación. Email enmascarado, `product_state`, `storefront_url`, `sandbox_ready`.

### `POST /api/marketing/waitlist`

Para landings. Cuerpo: `{ "product_id", "email", "name?", "meta?" }`.

### Incrustar en landing

```html
<script src="/api/marketing/waitlist.js" data-product-id="prod-xxx"></script>
<form data-aifactory-waitlist>
  <input type="email" name="email" required />
  <button type="submit">Join waitlist</button>
</form>
```

O inyecta el script vía **Admin → Settings → published site head HTML**.

---

## Variables de entorno

| Variable | Por defecto | Rol |
|----------|---------|-----|
| `AIFACTORY_LEAD_AUTO_PIPELINE` | `1` | Encolar `marketing_landing` al enviar lead |
| `AIFACTORY_FUNNEL_AUTO_HUB_LIST` | `1` | Listar en hub al COMPLETED |
| `AIFACTORY_FUNNEL_NOTIFY_DISABLE` | — | `1` = no enviar email de finalización |
| `AIFACTORY_FUNNEL_DIR` | `data/funnel/` | Persistencia leads/waitlist |
| `OUTREACH_SMTP_*` / `AIFACTORY_FUNNEL_SMTP_*` | — | Email (mismo SMTP que outreach) |

Docker `data-init` y `entrypoint.sh` crean `data/funnel/` y `data/logs/marketing/` con UID `10001`.

---

## Persistencia

| Archivo | Contenido |
|---------|-----------|
| `data/funnel/leads.json` | Leads, tokens, enlace product_id |
| `data/funnel/waitlist.jsonl` | Waitlist append-only |
| `data/logs/marketing/events.jsonl` | Eventos de analítica |

---

## Admin

- **`GET /api/admin/funnel/dashboard?window_hours=168`** — etapas, leads 7d, pedidos, leads recientes.
- Requiere RBAC admin.

---

## Tests

`tests/test_funnel_growth.py` — auto-pipeline, estado público, analítica.

---

## Fuera de scope (futuro)

- Stripe one-shot en landings
- Recuperación de carrito abandonado
- Email en hero (hero sigue con `/api/public/generate-landing`)

Ver también: [marketing.md](./marketing.md), [pipeline-operations.md](./pipeline-operations.md).
