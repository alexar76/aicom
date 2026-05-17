# FAQ — AI-Factory (подробный)

> Краткое руководство со скриншотами: [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) · English: [FAQ.md](./FAQ.md)

---

## Общие вопросы

### Что такое AI-Factory одной фразой?

Система, которая по текстовой идее прогоняет **цепочку AI-агентов** (исследование → ТЗ → код → QA → …) и сохраняет артефакты на диске, с админкой и опциональной публичной витриной.

### Чем отличается витрина от админки?

| | Витрина `/` | Админка `/admin` |
|---|------------|------------------|
| Вход | Обычно не нужен | JWT, логин `admin` |
| Цель | Показать готовые продукты, лид-формы | Управлять пайплайном |
| Источник правды | Отфильтрованный каталог API | **Pipeline** — полный список `prod-…` |

### Где «настоящие» данные по продукту?

**Admin → Pipeline** — полный каталог с задачами и ошибками. Dashboard — только снимок при загрузке. Live Monitor — поток метрик.

### Нужен ли git-клон для оператора?

Нет. Достаточно URL развёрнутого инстанса и пароля админа. Документация также на `/docs`.

---

## Установка и доступ

### Какой пароль у admin по умолчанию?

**Нет фиксированного пароля.** При первом пустом `data/` пароль задаётся в консоли entrypoint или пишется в `data/secrets/bootstrap_admin.txt`. Подробно: [security.md](./security.md).

### Не получается войти — что проверить?

1. Логин именно **`admin`** (если не создавали других пользователей).
2. Файл bootstrap / пароль, заданный при первом `up`.
3. Часы сервера (JWT).
4. HTTPS vs HTTP и cookie `Secure`.
5. Не путать порт: UI часто **9080**, API **9081** при Compose по умолчанию.

### Что такое роли viewer / operator / admin / super_admin?

См. [admin-panel-rbac.md](./admin-panel-rbac.md). **Operator** может гонять пайплайн, но не всегда менять Settings и провайдеров.

---

## New product и очередь

### Сколько времени занимает полный прогон?

От **нескольких минут** до **часов** — зависит от `full_software`, нагрузки LLM, QA с Playwright и числа repair-циклов. Лендинг обычно быстрее.

### Продукт в HUMAN_REVIEW_PENDING, задач нет?

Для **`full_software`** после DevOps включён **ручной gate**: нужно **Approve** или **Reject** на карточке Pipeline (`HumanReviewGatePanel`). Лендинги (`marketing_landing`) этот шаг не проходят. См. [admin-guide.md](./admin-guide.md#post-devops-human-review) (EN).

### Чем отличается full_software от marketing_landing?

| | full_software | marketing_landing |
|---|---------------|-------------------|
| Результат | API, БД, много страниц | Статический/простой сайт |
| Стадии | Полная цепочка | Укороченный путь |
| Деплой | Railway / compose | Vercel/Netlify static |

### Где взять id продукта после создания?

Экран успеха в мастере, **Pipeline** (поиск по имени), URL `/product/{id}` если уже опубликован.

### Можно ли отменить продукт в очереди?

Зависит от state и политики воркера. См. admin-guide и API. Часто проще оставить `FAILED` / not pursuing, чем физически удалять.

---

## Pipeline Monitor

### Почему пишет «try 4 of 8» / «Server request 4 / 8»?

Это **четвёртая попытка того же HTTP-запроса** к `/api/admin/pipeline/products`. Предыдущие завершились ошибкой, таймаутом или 502. Клиент **намеренно** повторяет с backoff (см. `pipelineCatalogFetch.ts`). Это не означает, что «браузер не доходит до API».

### Сколько ждать одну попытку?

До **5 минут** (`clientTimeoutMs` 300 000 ms) на попытку. Между попытками — пауза до ~8 с на первой странице.

### Почему полоса прогресса «не двигается»?

- Во время **Connection phase** полоса показывает **номер попытки HTTP**, а не % каталога.
- После появления строк смотрите шапку: **X / total** и зелёную полосу — это **реальный** прогресс подгрузки страниц.

### Где кеш каталога?

**Pipeline Monitor:** в **localStorage** — `aicom_pipeline_catalog_v2_{sort}` и peek на 2 строки. Первый визит / другая сортировка / очистка — «холодный» старт с ретраями.

**Публичная витрина (`/`):** `aicom_storefront_catalog_v1_{category}` — сначала кеш, потом фоновый `GET /api/products`. См. [marketing.md](./marketing.md).

### Почему «All Categories (0)», а потом появляются цифры?

Категории считаются по **уже загруженным** строкам; пока каталог догружается, счётчики могут быть неполными (суффикс `+` в опциях).

### Продукт COMPLETED, но не на витрине — почему?

Типичные причины в `storefront_gate_reasons`:

- нет кода на диске;
- не прошёл **marketplace quality**;
- скрыт вручную (**hidden from storefront**);
- state ещё не shipped-family.

Смотрите карточку в **Pipeline** и [pipeline-operations.md](./pipeline-operations.md).

### Как найти «зависший» продукт?

1. Pipeline → фильтр state **running** / смотреть оранжевые стадии.
2. Клик по стадии → задача `running` давно без `ended_at`.
3. Live Monitor / LLM Logs.
4. Логи воркера: `data/logs/`.

### Что значит «Updating from server… 2 / 10»?

Загружено 2 строки каталога из 10 на сервере; остальные подтянутся фоном чанками по 12.

---

## LLM и провайдеры

### Агенты молчат / все FAILED с LLM

1. **LLM Providers** — ключи, enabled, model id.
2. **LLM Logs** — последние ошибки.
3. `data/config/model_providers.yaml` на volume (не в git).
4. Лимиты rate limit провайдера.

### Нужен ли интернет из контейнера?

Да, для облачных API. Ollama на хосте — overlay `docker-compose.host-gateway.yml`.

### Что такое heavy / light модель?

Маршрутизация в Providers: тяжёлые задачи (архитектор) vs лёгкие. См. admin-guide.

---

## Витрина и покупатели

### Почему на главной меньше продуктов, чем Completed в Dashboard?

Витрина применяет **дополнительные фильтры** (качество, код, скрытие). Dashboard считает все `COMPLETED` в пайплайне.

### Support / Lumen — это агент пайплайна?

**Нет.** Это помощник для покупателей маркетплейса, отдельный от ростера **AI Agents**.

---

## Discovery и Director

### Идеи появились сами — это нормально?

Если включены **autonomous pipeline** и **discovery auto-enqueue**. Иначе идеи только вручную или через API Discovery.

### Как отключить автопостановку идей?

`AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0`, `general.auto_pipeline: false` в Settings — см. [configuration.md](./configuration.md).

---

## Sandbox и превью

### Sandbox не открывается в iframe

1. `AIFACTORY_SANDBOX_PREVIEW_API`, compose preview.
2. Docker socket в контейнере app.
3. CSP / mixed content — HTTPS.
4. Логи sandbox в API.

### Чем sandbox отличается от auto-publish?

**Sandbox** — превью на фабрике. **Auto-publish** — выгрузка статики на Vercel/Netlify после DevOps.

---

## Данные и бэкапы

### Где лежат продукты?

Bind mount **`./data`** (или `~/aicom-data`) — `data/code/`, `data/specs/`, `data/state/pipeline.db`, конфиги.

### Потерялись данные после docker run

Частая ошибка: **named volume** вместо bind mount. См. README — раздел про миграцию с named volume.

### Можно ли удалить все demo-продукты?

`./scripts/run_factory_demo_reset.sh` или `wipe_pipeline_products.py` — осторожно, необратимо.

---

## Производительность и CI

### API каталога медленный

После оптимизаций light-режим должен отвечать за **секунды** на малый `limit`. Если снова минуты — проверьте размер `pipeline.db`, прокси timeout, не грузите `light=0` без нужды.

### GitHub Actions падает на тестах

См. `.github/workflows/ci.yml` — pytest + Playwright jobs. Локально: `pytest -q` в venv.

---

## Безопасность

### Можно ли показывать git remote на стриме?

**Нет**, если в URL есть токен. См. README — Screen recordings & Git remotes.

### Где хранится JWT?

`localStorage` браузера + httpOnly cookie (см. security.md). Не на публичных машинах.

---

## Документация и скриншоты

### Как обновить скриншоты в гайде?

```bash
cd web/frontend
DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='…' npm run capture-docs-screenshots
```

Список файлов: [assets/screenshots/README.md](./assets/screenshots/README.md).

### Картинки в markdown битые в git clone

PNG не коммитятся или ещё не сняты — запустите скрипт выше на работающем инстансе.

---

## Куда эскалировать

| Уровень | Документ |
|---------|----------|
| Оператор UI | [USER_GUIDE.ru.md](./USER_GUIDE.ru.md), этот FAQ |
| Владелец инстанса | [owner-guide.md](./owner-guide.md) |
| DevOps / env | [configuration.md](./configuration.md), [production-domain.md](./production-domain.md) |
| API интеграция | [api-integration-guide.md](./api-integration-guide.md) |
| Уязвимости | [SECURITY.md](../SECURITY.md) |

---

*Дополняйте FAQ при повторяющихся вопросах в поддержке.*
