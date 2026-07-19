# Слой роста воронки (Funnel growth)

> **English:** [funnel-growth.md](./funnel-growth.md) · **Español:** [funnel-growth.es.md](./funnel-growth.es.md)

Публичный захват лидов, автозапуск пайплайна, страница статуса, аналитика и дистрибуция после COMPLETED. Код: `web/backend/services/funnel_*`, `web/backend/api/marketing.py`.

---

## Обзор

| Поверхность | Путь / API | Назначение |
|-------------|------------|------------|
| Форма лида | `/lead` | Бриф → опционально старт пайплайна |
| Статус | `/status/{token}` | Polling состояния продукта (15 с) |
| Trust metrics | `TrustMetricsStrip` на главной | Shipped / in pipeline / leads |
| Виджет админки | Dashboard → Funnel | `GET /api/admin/funnel/dashboard` |
| Waitlist embed | `GET /api/marketing/waitlist.js` | Формы на сгенерированных лендингах |

При **COMPLETED** `orchestrator/task_executor_agent.py` вызывает `funnel_distribute` (hub + blog) и `notify_lead_product_completed` (email).

---

## Публичные API

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

В ответе: `status_token`, `status_url`, `product_id`, `pipeline_started`.

### `GET /api/marketing/lead/status/{token}`

Без авторизации. Маскированный email, `product_state`, `storefront_url`, `sandbox_ready`.

### `POST /api/marketing/waitlist`

Для лендингов. Тело: `{ "product_id", "email", "name?", "meta?" }`.

### Встраивание на лендинг

```html
<script src="/api/marketing/waitlist.js" data-product-id="prod-xxx"></script>
<form data-aifactory-waitlist>
  <input type="email" name="email" required />
  <button type="submit">Join waitlist</button>
</form>
```

Или скрипт через **Admin → Settings → Head snippet on generated sites**.

---

## Переменные окружения

| Переменная | По умолчанию | Роль |
|------------|--------------|------|
| `AIFACTORY_LEAD_AUTO_PIPELINE` | `1` | Создать продукт `marketing_landing` при лиде |
| `AIFACTORY_FUNNEL_AUTO_HUB_LIST` | `1` | Листинг на hub при COMPLETED |
| `AIFACTORY_FUNNEL_NOTIFY_DISABLE` | — | `1` — не слать email о готовности |
| `AIFACTORY_FUNNEL_DIR` | `data/funnel/` | Хранение лидов и waitlist |
| `OUTREACH_SMTP_*` / `AIFACTORY_FUNNEL_SMTP_*` | — | Email (те же SMTP, что outreach) |

Docker `data-init` и `entrypoint.sh` создают `data/funnel/` и `data/logs/marketing/` с UID `10001`.

---

## Хранение данных

| Файл | Содержимое |
|------|------------|
| `data/funnel/leads.json` | Лиды, токены статуса, связь с product_id |
| `data/funnel/waitlist.jsonl` | Waitlist (append-only) |
| `data/logs/marketing/events.jsonl` | События аналитики |

---

## Админка

- **`GET /api/admin/funnel/dashboard?window_hours=168`** — стадии воронки, лиды за 7 д, заказы, последние лиды.
- Требуется admin RBAC.

---

## Тесты

`tests/test_funnel_growth.py` — auto-pipeline, public status, analytics.

---

## Вне scope (позже)

- Stripe one-shot на лендингах
- Abandoned cart
- Email на hero (hero по-прежнему через `/api/public/generate-landing`)

См. также: [marketing.md](./marketing.md), [pipeline-operations.md](./pipeline-operations.md).
