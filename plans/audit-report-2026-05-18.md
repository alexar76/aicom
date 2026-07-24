# AI-Factory v2.1 — Полный аудит: баги, безопасность, killer-фича

**Дата:** 2026-05-18
**Ветка:** main
**Коммит:** f09dfd03

---

## Часть 1. Безопасность

### 🔴 Критические

| # | Проблема | Файл | Строка |
|---|----------|------|--------|
| 1 | **Монтирование Docker-сокета внутрь контейнера** — `/var/run/docker.sock:/var/run/docker.sock`. Это классический вектор побега из контейнера. Любой скомпрометированный код внутри контейнера получает root-доступ к хосту. | `docker-compose.yml` | 18 |

### 🟠 Высокие

| # | Проблема | Файл |
|---|----------|------|
| 2 | **Hardcoded секреты в `.env`** — Fernet-ключ шифрования (`AIFACTORY_FIREWALL_RULES_FERNET_KEY`), пароль Grafana, пароль sandbox лежат открытым текстом. Хотя `.env` в `.gitignore`, на проде файл доступен любому с доступом к ФС. | `.env` |
| 3 | **Admin WebSocket без аутентификации** — `/api/admin/ws/metrics` отдаёт полную админ-метрику любому подключившемуся клиенту без проверки токена. | `web/backend/main.py:300-315` |
| 4 | **Sandbox API без аутентификации** — Все эндпоинты sandbox (start, stop, git/init, git/push, active list) открыты для неаутентифицированных запросов. | `web/backend/api/sandbox.py` |
| 5 | **SSRF через Git Remote URL** — `git/init` принимает `remote_url` без валидации, позволяя злоумышленнику указать свой URL. При `git push` сервер попытается соединиться с атакующим хостом — зондирование внутренней сети. | `web/backend/api/sandbox.py:776-822` |
| 6 | **Проброс чувствительных заголовков в sandbox-прокси** — Reverse-прокси для sandbox (`/api/sandbox/backend/...`) форвардит `Authorization`, `Cookie`, `X-CSRF-Token` в сгенерированный LLM'ом контейнер. | `web/backend/api/sandbox.py:635-652` |

### 🟡 Средние

| # | Проблема | Файл |
|---|----------|------|
| 7 | **Спуфинг IP через X-Forwarded-For** — Фаервол доверяет заголовку `X-Forwarded-For` без проверки источника, позволяя обойти IP-based рейт-лимиты и ACL. | `web/backend/middleware/firewall_http.py:15-21` |
| 8 | **Утечка деталей исключений** — Глобальный exception handler возвращает `str(exc)` в теле ответа. Утекают детали внутренних ошибок, включая ошибки LLM-провайдеров. | `web/backend/main.py:280-286` |
| 9 | **CSRF-защита только для /api/admin** — Пользовательские mutation-эндпоинты (регистрация, чат) не защищены от CSRF. | `web/backend/middleware/csrf.py:49-50` |
| 10 | **Нет рейт-лимита на регистрацию** — Можно создать неограниченное количество аккаунтов. | `web/backend/api/customer.py:67-73` |
| 11 | **CSP для sandbox iframe** — HTML из sandbox-контейнера сервится с того же origin, что и API. XSS-пейлоад в сгенерированном коде может быть исполнен. | `web/backend/api/sandbox.py:569-593` |

### 🟢 Чисто

- SQL-инъекции — **нет** (везде параметризованные запросы)
- `eval`/`exec` — **нет**
- `subprocess shell=True` — **нет**
- `pickle` / небезопасная десериализация — **нет**
- Path traversal — защита через `resolve()` + `relative_to()`
- RBAC на админских роутах — реализован
- Stripe webhook — верификация HMAC-SHA256
- Пароли — pbkdf2_sha256 через passlib
- Security-заголовки (CSP, HSTS, X-Frame-Options) — настроены

### 🔧 Рекомендации по безопасности (топ-3)

1. **Убрать Docker socket mount.** Перейти на Docker API через TCP с TLS, либо запускать sandbox-контейнеры через отдельный Docker-in-Docker (dind) контейнер с ограниченными привилегиями.
2. **Добавить аутентификацию на sandbox API.** Все мутирующие эндпоинты (`/api/sandbox/*`) должны требовать JWT-токен с RBAC, как это уже сделано для `/api/admin`.
3. **Валидировать `remote_url` в git/init.** Разрешить только HTTPS-URL к GitHub/GitLab/Bitbucket, блокировать внутренние IP-диапазоны (10.x, 172.16+, 192.168.x, 127.x).

---

## Часть 2. Баги

### 🔴 Критические

| # | Баг | Файл | Строка |
|---|-----|------|--------|
| 1 | **`asyncio.gather` без `return_exceptions=True`** — в Phase 3 пайплайна. Если один агент бросает исключение, `gather` немедленно отменяет **все** остальные задачи. Одна ошибка рушит весь параллельный прогон, теряя in-progress LLM-вызовы. | `pipeline_worker.py` | 528 |
| 2 | **`CancelledError` ломает shutdown директора** — в `main()` воркера `CancelledError` перехватывается без вызова `worker.stop()`. Три фоновые задачи (`_signal_check_task`, `_auto_pipeline_task`, `_benchmark_league_task`) никогда не отменяются — утекают корутины в event loop. | `director/worker.py` | 800-801 |
| 3 | **Fire-and-forget метрики без try/except** — `asyncio.create_task(self._periodic_metrics_update(30))` создаёт фоновую задачу обновления Prometheus-метрик. Если `_update_pipeline_metrics()` упадёт один раз, метрики замирают навсегда до перезапуска процесса. | `main.py` | 280 |

### 🟠 Высокие

| # | Баг | Файл | Строка |
|---|-----|------|--------|
| 4 | **DELETE + INSERT в одной транзакции теряет данные** — `_save_decisions()` делает `DELETE FROM director_decisions` затем `INSERT OR REPLACE` в одной транзакции. Если INSERT упадёт на середине, DELETE откатится вместе с транзакцией, но catch на строке 252 молча глотает ошибку — оператор не узнает о потере. | `orchestrator/director_integration.py` | 243-252 |
| 5 | **SQLite-соединения без close()** — `DirectorIntegration.conn` и `CommerceService._conn` открываются и никогда не закрываются. Файловые дескрипторы утекают на весь lifetime процесса. | `orchestrator/director_integration.py:58-65`, `web/backend/services/commerce.py:53-60` |
| 6 | **Гистерезис авто-пайплайна может заблокировать создание навсегда** — Если `pause_thr=1, resume_thr=1`, то `resume_thr` становится `max(0, 1-1) = 0`. Бэклог должен упасть до нуля, чтобы пайплайн возобновился. Одна pending-идея = вечный блок. | `director/worker.py` | 161-164 |

### 🟡 Средние

| # | Баг | Файл | Строка |
|---|-----|------|--------|
| 7 | **`assert` для control flow — исчезает с `-O`** — `async_sqlite_manager.py` (4 шт.), `async_postgres_manager.py` (4 шт.), `postgres_manager.py`, `agents/dev.py:312`, `llm/pricing_estimate.py:287`, `security/docker_sandbox.py:87`, `browser_preview_e2e.py:472`. В production с `python -O` валидация молча пропадает. | различные |
| 8 | **`datetime.utcnow()` — deprecated с Python 3.12** — 4 файла используют устаревший метод. Заменить на `datetime.now(timezone.utc)`. | `llm/openai_compatible.py:313`, `orchestrator/pipeline_worker_persistence.py:57`, `web/backend/api/admin/chat.py:180`, `web/backend/services/corporate_standup.py:71` |
| 9 | **Наивные datetime без timezone** — `DirectorReportGenerator` создаёт `datetime.fromtimestamp()` без `tz=`, что даёт разные результаты на машинах с не-UTC таймзоной. | `director/report_generator.py:78,97,103` |
| 10 | **`except Exception` ловит `CancelledError`** — В Python 3.8+ `CancelledError` наследует `Exception`. Ловля `Exception` в асинхронных методах не даёт корректно завершить graceful shutdown. | `pipeline_worker.py:493`, `director_integration.py:112,173,227,252` |

### 🔧 Рекомендации по багам (топ-3)

1. **Добавить `return_exceptions=True` в `asyncio.gather`** на строке 528 `pipeline_worker.py`. Собирать ошибки и рейзить агрегированное исключение после завершения всех задач.
2. **Обернуть `_update_pipeline_metrics()` в try/except** внутри `_periodic_metrics_update`, чтобы один сбой не убивал все метрики навсегда.
3. **Заменить все `assert` на `if ... raise`** в production-критичных местах (особенно в менеджерах БД и валидации Docker-контейнеров).

---

## Часть 3. Архитектура и killer-фича

### Текущий стек

```
User Idea → Pipeline (13 agents) → Shippable Product
              │
              ├── Discovery → PM → Architect → Developer → QA (Playwright)
              ├── DevOps → Security Scan → Hardening
              └── Marketing → Sales → Landing Page / Full-Stack App
```

- **Бэкенд:** Python 3.12, FastAPI, SQLite/PostgreSQL, LangGraph
- **LLM:** OpenAI, Anthropic, Ollama, DeepSeek, Groq, Together AI
- **Инфра:** Docker Compose, Prometheus + Grafana
- **Фронтенд:** Next.js + Tailwind CSS

### Ключевые разрывы архитектуры

1. **Нет очереди задач** — пайплайн работает in-process через asyncio. Не масштабируется горизонтально. Нет retry-механики для упавших агентов (кроме ручного retry).
2. **Нет OpenTelemetry / distributed tracing** — Prometheus даёт метрики, но трассировка одного прогона пайплайна через 13 агентов невозможна.
3. **Нет Kubernetes/Helm-чарта** — деплой только на одной машине через Docker Compose.
4. **CI/CD для сгенерированных продуктов отсутствует** — после пайплайна продукт статичен. Нет авто-деплоя в облако (Vercel, Railway, Fly.io).

### 🔥 Killer-фича: **Self-Healing Product Evolution Loop**

**Идея:** Сейчас AI-Factory генерирует продукт один раз и заканчивает. Добавить **непрерывный цикл улучшения продукта** на основе реальных метрик использования и фидбека пользователей.

**Как это работает:**

```
Готовый продукт (live)
    │
    ├── Сбор RUM-метрик (Core Web Vitals, ошибки JS, bounce rate)
    ├── Скрипты heatmaps / session recordings
    ├── Форма обратной связи (лайк/дизлайк на фичи)
    └── Анализ конверсии (если магазин)
            │
            ▼
    Evolution Agent анализирует данные
            │
            ├── Находит: «страница /pricing отваливается с JS-ошибкой у 12% пользователей»
            ├── Находит: «bounce rate 80% на /features — возможно, плохой UX»
            └── Находит: «корзина бросается в 60% случаев — проверить flow оформления»
            │
            ▼
    Автоматический PR с фиксом
            │
            ├── QA agent перезапускает Playwright-тесты на новом коде
            ├── Security scan прогоняется заново
            └── Авто-деплой при прохождении quality gates
```

**Ключевые компоненты:**

1. **RUM SDK** — легковесный JS-скрипт, встраиваемый в сгенерированный продукт. Собирает: ошибки JS, Web Vitals (LCP, CLS, INP), время на странице, клики, конверсии.
2. **Feedback Widget** — встраиваемый виджет «👍/👎» для каждой секции лендинга. Пользователь продукта может дать обратную связь.
3. **Evolution Agent** — новый агент в пайплайне. Анализирует накопленные метрики, находит аномалии, генерирует конкретные задачи на исправление.
4. **Auto-PR Loop** — интеграция с GitHub. Evolution Agent создаёт issue → Developer Agent делает PR → QA проверяет → авто-мёрж при зелёных тестах.

**Почему это killer:**

- **Ни один конкурент такого не делает.** Bolt/Lovable/v0 — генераторы. Никто не замыкает цикл «сгенерировал → запустил → улучшил».
- **Сдвиг парадигмы.** Из «сгенерируй и забудь» в «живой продукт, который сам себя чинит».
- **Zero-ops для пользователя.** Продукт работает, сам находит проблемы, сам чинит, сам деплоит.
- **Монетизация.** Подписка на «живой» продукт с авто-эволюцией дороже, чем разовая генерация.

**Примерный объём реализации:** ~3-4 недели на MVP (RUM SDK + Feedback Widget + Evolution Agent + Auto-PR Loop).

---

## Часть 4. Сводная таблица приоритетов

| Приоритет | Категория | Проблема | Влияние |
|-----------|-----------|----------|---------|
| 🔴 P0 | Security | Docker socket mount | Побег из контейнера → компрометация хоста |
| 🔴 P0 | Bug | `gather` без `return_exceptions` | Потеря всех параллельных LLM-вызовов при одной ошибке |
| 🔴 P0 | Bug | Fire-and-forget метрики | Потеря observability навсегда |
| 🟠 P1 | Security | Sandbox API без auth | Неавторизованный запуск/остановка sandbox'ов |
| 🟠 P1 | Security | SSRF через git remote URL | Зондирование внутренней сети |
| 🟠 P1 | Security | Проброс заголовков в sandbox | Утечка JWT/сессий в LLM-контейнер |
| 🟠 P1 | Bug | DELETE+INSERT в одной транзакции | Беззвучная потеря данных |
| 🟠 P1 | Bug | Утечка SQLite-соединений | Истощение файловых дескрипторов |
| 🟡 P2 | Security | X-Forwarded-For спуфинг | Обход рейт-лимитов |
| 🟡 P2 | Security | Утечка исключений в ответ API | Information disclosure |
| 🟡 P2 | Bug | `assert` для control flow | Валидация исчезает с `python -O` |
| 🟡 P2 | Bug | `datetime.utcnow()` deprecated | Совместимость с Python 3.12+ |
| 🟢 P3 | Feature | Self-Healing Evolution Loop | Конкурентное преимущество, монетизация |

---

*Отчёт сгенерирован автоматически на основе статического анализа кодовой базы AI-Factory v2.1.*
