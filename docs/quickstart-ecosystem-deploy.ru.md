# Развёртывание всей экосистемы — быстрый старт с нуля

Поэтапный runbook для поднятия полной публичной экосистемы на чистом Ubuntu VPS. Он
оборачивает уже существующие скрипты развёртывания и **не** вводит нового движка деплоя.
Начинайте с нужного вам уровня и останавливайтесь на нём; каждый уровень опирается на предыдущий.

Для справочника операционного уровня (частичные передеплои, опасность передеплоя Hub, точный
порядок ручных шагов) см. **[`deploy-ecosystem.md`](./deploy-ecosystem.md)**.

---

## 1. Что такое «экосистема»

| Компонент | Что делает | Контейнер / процесс |
|-----------|------------|---------------------|
| **Factory** | Собирает и поставляет AI-продукты (стек Compose `aicom-app`) | `aicom-app-1` |
| **Hub** | Федеративный hub AIMarket Protocol v2 — discovery, channels, invoke, settle | `modelmarket-hub` |
| **Mesh** | API service-mesh, связывающий продукты между собой | `aicom-mesh-api` |
| **ARGUS-3** | Персональный агент + WARDEN MCP firewall (reference client) | `argus` / `:8787` |
| **Alien Monitor** | 3D-визуализатор экосистемы (режимы UNIVERSE / TEST / REAL) + терминал **Pulse** | `alien-monitor`, Pulse |
| **Lottery relayer** | UNI relayer для LIVE Monitor (опционально; шаг может WARN) | `:9195` |
| **Ecosystem landing** | Публичная карта [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) | nginx / шаг 7 |
| **Oracles** | Семнадцать оракулов на [oracles.modelmarket.dev](https://oracles.modelmarket.dev) (+ UMBRAL) | **отдельный хост (L4)** |
| **On-chain** (опционально) | Контракты Base-mainnet: Escrow, capability NFT, Agent Lottery | деплой через Foundry |

**Не входит в `deploy_ecosystem.sh`:** Metis, DIOSCURI, HELIOS — отдельно; см. [§Чего нет на одном VPS](#9-чего-нет-на-одном-vps).

Четыре уровня онбординга:

| Уровень | Цель | Одна команда |
|---------|------|--------------|
| **L1** | Попробовать локально (только Factory) | `./scripts/quickstart.sh` |
| **L2** | Self-host **core fleet** на одном VPS | `./scripts/quickstart_ecosystem.sh` или `./scripts/deploy_ecosystem.sh` |
| **L3** | Публичный продакшен (DNS + TLS + verify) | `./scripts/quickstart_ecosystem.sh --public-url https://…` |
| **L4** | Хост оракулов (**отдельная машина** по умолчанию) | `./scripts/setup-oracles-platon-on-host.sh` |

Модель аутентификации для *потребления* Hub — это **Ed25519** (SDK подписывает каждый invoke;
ключ кошелька — это 32-байтовый seed Ed25519, а не Ethereum-ключ). secp256k1/EIP-712 опционален
и используется только для on-chain-списаний по каналам. Со стороны потребителя см.
[документацию AIMarket SDK](https://github.com/alexar76/aimarket-sdks/blob/main/docs/en.md) и
[Python-агент](https://github.com/alexar76/aimarket-agent/blob/main/docs/en.md) (без состояния, без кошелька).

---

## 2. Предварительные требования

На целевом Ubuntu VPS, прежде чем переходить к любому уровню:

- **Docker Engine + Compose v2** (`docker compose`, а не устаревший `docker-compose`).
- **nginx** — терминация TLS и обратное проксирование (уровни 3–4).
- **DNS-записи A/AAAA**, указывающие на хост, на котором вы запускаетесь (уровень 3+):
  - `magic-ai-factory.com`, `www.magic-ai-factory.com` → хост Factory
  - `modelmarket.dev`, `www.modelmarket.dev` → хост Factory
  - `oracles.modelmarket.dev` → **хост оракулов** (`78.17.126.214`), напрямую (без проксирования через factory)
- **Заполненный `.env`** в корне репозитория. Скопируйте `.env.example` и задайте хотя бы один LLM-ключ:

```bash
cp .env.example .env
# then set, e.g.:
#   DEEPSEEK_API_KEY=...
#   ANTHROPIC_API_KEY=...
# optional port overrides:
#   AICOM_PORT_FRONTEND=9080
#   AICOM_PORT_API=9081
```

Для LLM-ключей предпочитайте файловые секреты (`data/secrets/llm/<provider>_api_key` +
оверлей `docker-compose.secrets.yml`), а не inline-записи `environment:` — см. комментарии
в `.env.example`.

---

## 3. Уровень 1 — Попробовать локально

Только Factory. Собирает образ, поднимает стек и сквозным образом ставит в очередь демо-продукт:

```bash
./scripts/quickstart.sh                      # build + run + landing demo
./scripts/quickstart.sh --no-build           # reuse the existing image
./scripts/quickstart.sh "Your product idea"  # full_software profile from your idea
```

Что происходит: `./run.sh` (сборка) → запуск → `./demo.sh --no-open` (постановка демо-продукта в
очередь). Следите за прогрессом в **Admin → Pipeline** по адресу `http://localhost:9080`. Запись
повтора сборки без Docker лежит в `docs/sample-output/build-replay-spliteasy.json`.

---

## 4. Уровень 2 — Core fleet на одном VPS

**Рекомендуемая обёртка** (preflight Docker + `.env` + deploy + next steps):

```bash
./scripts/quickstart_ecosystem.sh
./scripts/quickstart_ecosystem.sh --skip-verify
./scripts/quickstart_ecosystem.sh --public-url https://…
```

Обёртка вызывает **`scripts/deploy_ecosystem.sh`**. Можно напрямую:

```bash
./scripts/deploy_ecosystem.sh
```

Порядок шагов:

1. **Factory** — `./scripts/deploy.sh`
2. **Hub** — `./scripts/deploy_hub.sh` (**не** Compose из подпапки)
3. **Mesh** — `./scripts/deploy_mesh.sh`
4. **ARGUS-3** — `./scripts/deploy_argus.sh` (`:8787`)
5. **Alien Monitor + Pulse** — `./scripts/deploy_alien_monitor.sh`
6. **UNI lottery relayer** — `./scripts/deploy_lottery_uni.sh` (не фатально)
7. **Ecosystem landing** — `./scripts/deploy_ecosystem_landing.sh` (не фатально)

Затем прогрев Factory API и `./scripts/verify_ecosystem_full.sh` (**17+ проверок**), если не `--skip-verify`.

### Порты (хост)

| Сервис | Порт хоста | Health / вход |
|--------|------------|---------------|
| Factory API | `:9081` | `GET /api/health` |
| Factory UI (frontend) | `:9080` | `GET /` |
| Hub | `:9083` | `GET /.well-known/ai-market.json` |
| Mesh | `:8090` | `GET /v1/stats` |
| ARGUS | `:8787` | `GET /health` |
| Alien Monitor | `:9100` | `GET /api/health` |
| Терминал Pulse | `:5199` | `GET /` |
| Relayer лотереи UNI | `:9195` | `GET /healthz` |
| Ecosystem landing | nginx | `https://modeldev.modelmarket.dev/` (после L3 TLS) |

> **Публичный порт UI — это `:9080`, а не старый `:8080`.** nginx проксирует публичный домен на
> `127.0.0.1:9080`.

Флаги:

```bash
./scripts/deploy_ecosystem.sh --skip-verify   # faster; skips the smoke suite (not for prod)
```

---

## 5. Уровень 3 — Публичный продакшен

### 5.1 Направьте DNS

Записи A/AAAA для `magic-ai-factory.com`, `www.magic-ai-factory.com`, `modelmarket.dev` и
`www.modelmarket.dev` должны резолвиться на этот хост **до** выпуска сертификатов.

### 5.2 Деплой с зашитым публичным URL

```bash
./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
```

`--public-url` передаётся в `deploy.sh`, чтобы `NEXT_PUBLIC_SITE_URL` был задан для сборки
Next.js (Open Graph, sitemap, серверные метаданные). Если TLS ещё не поднят, можно сначала
использовать `http://magic-ai-factory.com`, а затем пересобрать образ приложения, когда заработает HTTPS.

### 5.3 Однократные команды TLS (запускать от root)

**Vhost Hub + AIMarket Hub + Let's Encrypt** для `modelmarket.dev`:

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-modelmarket-ssl.sh
```

Это устанавливает `deploy/nginx/modelmarket.dev.conf`, собирает `modelmarket-hub:latest` из
контекста **корня репозитория**, запускает hub на `127.0.0.1:9083`, включает `certbot.timer` и
выпускает сертификат для `modelmarket.dev` + `www.modelmarket.dev`.

**Vhost Factory** для `magic-ai-factory.com` (см. [`production-domain.md`](./production-domain.md)):

```bash
sudo cp deploy/nginx/magic-ai-factory.com.conf /etc/nginx/sites-available/magic-ai-factory.com
sudo ln -sf /etc/nginx/sites-available/magic-ai-factory.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx \
  -d magic-ai-factory.com -d www.magic-ai-factory.com \
  --non-interactive --agree-tos --redirect \
  -m YOUR_EMAIL@example.com
```

После того как HTTPS поднят, задайте `NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com` в `.env` и
пересоберите, чтобы бандл подхватил это значение:

```bash
docker compose build app --no-cache
docker compose up -d
```

Публичный Alien Monitor отдаётся по адресу `https://magic-ai-factory.com/monitor/` (nginx проксирует
`/monitor/` → `127.0.0.1:9100`; `deploy_alien_monitor.sh` патчит активный vhost Certbot, если этот
блок отсутствует).

### 5.4 Проверка

```bash
./scripts/verify_ecosystem_full.sh
```

Ожидайте **`17/17 PASS`**.

---

## 6. Уровень 4 — Хост оракулов

Оракулы работают на **отдельной машине** (`78.17.126.214`). **`deploy_ecosystem.sh` НЕ
разворачивает оракулы или Platon** — `oracles/` и `platon/` в этом монорепозитории являются
архивными зеркалами внешнего стека. Настройте их на хосте Platon, затем выполните федерацию с
хоста Factory.

### 6.1 На хосте Platon (`78.17.126.214`, от root)

Приложение Platon уже должно слушать на `127.0.0.1:8080` с
`PUBLIC_URL=https://oracles.modelmarket.dev`. Затем:

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-oracles-platon-on-host.sh
```

Это устанавливает `deploy/nginx/oracles.modelmarket.dev.conf`, проверяет Platon на
`127.0.0.1:8080/api/health` и выпускает сертификат для `oracles.modelmarket.dev`.

### 6.2 С хоста Factory — федерация

```bash
./scripts/announce-platon-oracles.sh
```

Это считывает admin-токен (`data/secrets/aimarket_admin_token.txt`), отправляет POST на
`/ai-market/v2/federation/announce` локальному hub (`:9083`) с well-known URL Platon и публичным
ключом подписи, после чего запускает обход федерации.

Проверьте хост оракулов:

```bash
curl -s https://oracles.modelmarket.dev/.well-known/ai-market.json | jq '{hub_url, manifest_url, capabilities_count}'
curl -s https://oracles.modelmarket.dev/api/health | jq '{status, kappa, order_parameter}'
```

Семнадцать оракулов (Platon, Chronos, Lattice, Murmuration, Lumen, Colony, Turing, Percola, Fermat, Ablation, Landauer, Sortes, Gauss, Aestus, Betti, Kantor, Fourier) и экономический цикл
описаны в [`oracles/docs/en.md`](../oracles/docs/en.md).

---

## 7. Опционально — On-chain (Base, chain 8453)

Держится **отдельно** от оркестрации контейнеров. Эти команды деплоят Solidity-контракты в
Base mainnet через Foundry. Обе по умолчанию выполняют сухой прогон без газа; передайте `broadcast`,
чтобы потратить реальный газ.

**Ядро экосистемы** — FakeUSDT + `AIMarketEscrow` + `AIMarketCapabilityNFT`
(ACEX намеренно исключён — аудит пометил AuditPool TWAP + PulseAMM как HIGH):

```bash
./scripts/deploy_ecosystem_base.sh            # dry-run (no gas)
./scripts/deploy_ecosystem_base.sh broadcast  # real deploy
```

**Agent Lottery** — `AIAgentLottery` (билеты на нативном ETH; admin/governance/treasury
устанавливаются в `OWNER` при деплое):

```bash
./scripts/deploy_lottery_base.sh              # dry-run (simulate, NO gas)
./scripts/deploy_lottery_base.sh broadcast    # real deploy
```

Обе читают burner-ключ из `$BURNER_KEYFILE` (по умолчанию `~/.aicom-base-deployer.json`) и используют `BASE_RPC` (по умолчанию `https://mainnet.base.org`). Скрипт ecosystem-core передаёт владение Escrow/NFT в `OWNER` двухшаговым transfer после broadcast (затем `OWNER` должен вызвать `acceptOwnership`); лотерея же задаёт admin/governance/treasury равными `OWNER` на деплое, без передачи после деплоя. Это реальные средства — держите ставки минимальными.

---

## 8. Топология с несколькими хостами

```
┌──────────────────────────────────────────────┐      ┌────────────────────────────────────┐
│  FACTORY FLEET — 5.129.212.122                │      │  ORACLE HOST — 78.17.126.214        │
│                                                │      │                                      │
│  Factory  aicom-app-1        :9081 API/:9080 UI│      │  Platon Shadow Oracle  127.0.0.1:8080│
│  Hub      modelmarket-hub    :9083             │ fed  │  Oracle family (17 oracles)          │
│  Mesh     aicom-mesh-api     :8090             │◄────►│                                      │
│  ARGUS    reference agent    :8787             │ announce-platon-oracles.sh (factory)      │
│  Monitor  alien-monitor      :9100             │      │  oracles.modelmarket.dev           │
│  Pulse    terminal           :5199             │      │  НЕ в deploy_ecosystem.sh (L4)     │
│  Lottery relayer (UNI)       :9195             │      │                                      │
│  Landing  modeldev…          nginx             │      └────────────────────────────────────┘
│  magic-ai-factory.com  /  modelmarket.dev      │
└──────────────────────────────────────────────┘
```

`deploy_ecosystem.sh` / `quickstart_ecosystem.sh` — **левый блок**, шаги 1–7. Оракулы — Level 4,
по умолчанию отдельная машина.

---

## 9. Чего нет на одном VPS

| Компонент | Почему | Как добавить |
|-----------|--------|--------------|
| **17 oracles** | Level 4 | `setup-oracles-platon-on-host.sh` + `announce-platon-oracles.sh` |
| **On-chain Base** | опционально | `deploy_ecosystem_base.sh broadcast` |
| **Metis** | не в fleet-скрипте | отдельный deploy |
| **DIOSCURI / HELIOS** | satellites | отдельные репо |
| **Prometheus** | опционально | `deploy_observability.sh` |

---

## 10. Проверка и эксплуатация

### Полный smoke (17+ проверок)

```bash
./scripts/verify_ecosystem_full.sh
```

Проверяет ядро Factory (`/api/health`, frontend `:9080`, `/api/products`, trust-metrics, security
store, funnel lead, admin dashboard, product P&L), Hub (`.well-known`, `stats/live`, capital
pricing), Mesh (`/v1/stats`), Pulse (`:5199`), Alien Monitor (health UNIVERSE + внутрипроцессные
пробы TEST/REAL/UNIVERSE) и лотерею UNI (развёрнутый `evm_lottery`, relayer `/healthz`, живые
метрики лотереи). Переопределить цели можно через `FACTORY_URL`, `HUB_URL`, `MESH_URL`,
`MONITOR_URL`, `PULSE_URL`, `LOTTERY_RELAYER_URL`.

### Частичные передеплои

| Цель | Команда |
|------|---------|
| Только Factory | `./scripts/deploy.sh` |
| Только Hub | `./scripts/deploy_hub.sh` |
| Mesh + Monitor (демо-стек) | `./scripts/deploy_demo_stack.sh` (предполагает, что Factory + Hub уже подняты) |
| Только проверка | `./scripts/verify_ecosystem_full.sh` |

### Опасность передеплоя Hub — прочитайте это

> **НЕ используйте Compose из подпапки для передеплоя Hub.** Всегда используйте `./scripts/deploy_hub.sh`.
>
> ```bash
> cd aimarket-hub && docker compose up -d --build   # WRONG — breaks image/context; Hub can disappear
> ```
>
> `deploy_hub.sh` собирает из **корня монорепозитория** (`modelmarket-hub:latest`, контейнер
> `modelmarket-hub`), соответствует настройке TLS в `setup-modelmarket-ssl.sh` и безопасно
> заменяет контейнер. Файл `aimarket-hub/docker-compose.yml` оставлен только для справки при
> локальной разработке. Никогда не останавливайте/не удаляйте `modelmarket-hub`, не запустив
> сразу же `deploy_hub.sh`.

---

## 11. Связанная документация

- [`deploy-ecosystem.md`](./deploy-ecosystem.md) — операционный справочник (ручной порядок, частичные передеплои)
- [`production-domain.md`](./production-domain.md) — `magic-ai-factory.com` nginx + TLS
- [`production-modelmarket-dev.md`](./production-modelmarket-dev.md) — домен hub, DNS, хост оракулов
- [`oracles/docs/en.md`](../oracles/docs/en.md) — семнадцать оракулов и экономический цикл
- [Документация AIMarket SDK](../aimarket-sdks/docs/en.md) · [Python-агент](../aimarket-agent/docs/en.md) — потребление Hub

---

🇬🇧 [English](./quickstart-ecosystem-deploy.md) · 🇷🇺 [Русский](./quickstart-ecosystem-deploy.ru.md) · 🇪🇸 [Español](./quickstart-ecosystem-deploy.es.md) · 🇫🇷 [Français](./quickstart-ecosystem-deploy.fr.md) · 🇨🇳 [中文](./quickstart-ecosystem-deploy.zh.md)
