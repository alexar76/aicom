# Runbook — деплой экосистемы после security/audit fixes

**Для кого:** тот, кто выкатывает prod (`magic-ai-factory.com`, `modelmarket.dev`, monitor на `/monitor/`).  
**Когда читать:** перед любым полным redeploy после merge security-фиксов (Monitor auth, Hub sync, Mesh, channels, ARGUS mesh URL).

Связанные документы: [`deploy-ecosystem.md`](./deploy-ecosystem.md) (краткая шпаргалка), [`ecosystem-audit-report.md`](./ecosystem-audit-report.md) (что закрыто и что ещё открыто), [`production-metrics.md`](./production-metrics.md).

---

## Pre-flight — обязательно до `deploy_ecosystem.sh`

### 1. Секреты в `.env` (или `data/secrets/`)

| Переменная | Где | Зачем |
|------------|-----|--------|
| `ALIEN_API_TOKEN` | `.env` | Monitor: mutating API + `/api/state` в prod. Без токена → 503 на write, 401 на state |
| `AIMARKET_ADMIN_TOKEN` | `.env` или `data/secrets/aimarket_admin_token.txt` | Hub admin; `deploy_hub.sh` сгенерирует, если пусто |
| `MESH_API_TOKEN`, `MESH_ADMIN_TOKEN` | `.env` | Mesh; `deploy_mesh.sh` допишет, если пусто |
| `AIFACTORY_CRYPTO_ENABLED` | `.env` | `1` — платные invoke требуют payment channel (и на Hub, и на Factory) |

`deploy_hub.sh` / `deploy_mesh.sh` **не перезаписывают** уже заданные ключи — только дополняют отсутствующие.

### 2. Monitor — публичный UI vs закрытый API

В `alien-monitor/docker-compose.prod.yml` по умолчанию:

```env
ALIEN_ENV=production
ALIEN_PUBLIC_READ=1
```

| Endpoint | Поведение в prod |
|----------|------------------|
| `GET /api/summary`, `GET /api/topology` | Публично (демо `/monitor/`) |
| `GET /api/state` | **Только с** `Authorization: Bearer $ALIEN_API_TOKEN` |
| `WebSocket /ws` стрим | Публично |
| `set_mode` по WS | Нужен `token` в JSON-сообщении (= `ALIEN_API_TOKEN`) |
| Universe / AI / argus-run POST | Bearer token |

Чтобы закрыть и summary/topology: `ALIEN_PUBLIC_READ=0` в `.env` перед `deploy_alien_monitor.sh`.

### 3. Mesh — read API закрыт в prod

`deploy_mesh.sh` дописывает `MESH_PUBLIC_READ=0`.  
`docker-compose.prod.yml` mesh: `${MESH_PUBLIC_READ:-0}`.

Проверка после deploy:

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8090/v1/agents
# ожидается 401 без Bearer MESH_API_TOKEN
```

### 4. ARGUS → Mesh (co-located)

На одном хосте mesh слушает `127.0.0.1:8090`.  
`deploy_argus.sh` дописывает в `argus/.env`, если ключа нет:

```env
ARGUS_MESH_URL=http://127.0.0.1:8090
```

Путь регистрации агента: `/v1/agents` (не `/ai-service-mesh/api/agents`).

---

## Что изменилось в коде (кратко для деплоя)

| Область | Было | Стало |
|---------|------|--------|
| **Hub catalog** | `hub.db` в docker volume ≠ sync на хосте | `deploy_hub.sh`: mount `data/` → `/factory_data`, mirror + `import_factory_products` после health |
| **Hub paid invoke** | Канал только при `AIFACTORY_PROD=1` | Канал при `AIFACTORY_CRYPTO_ENABLED=1` |
| **Factory channels** | Debit по `channel_id` | + `channel_secret` при open, header `X-Payment-Channel-Secret` при invoke/pipeline |
| **Hub federated fetch** | httpx с redirect | `outbound_http.safe_*`, `follow_redirects=False`, `_url_is_safe` |
| **Monitor read** | Всё без auth | Tiered auth (см. таблицу выше) |
| **Mesh stats** | Public read по умолчанию | `MESH_PUBLIC_READ=0` в prod |
| **Docs hub port** | «9083→9080 в контейнере» | Контейнер слушает **9083** |

Полный список: [`ecosystem-audit-report.md`](./ecosystem-audit-report.md) §4–5.

---

## Деплой (рекомендуемый путь)

Из корня репо на сервере:

```bash
cd /path/to/aicom
git pull origin main

# убедиться что ALIEN_API_TOKEN и прочие ключи в .env
grep -E '^(ALIEN_API_TOKEN|AIFACTORY_CRYPTO_ENABLED|MESH_PUBLIC_READ)=' .env

./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
```

Скрипт по порядку:

1. `deploy.sh` — Factory  
2. `deploy_hub.sh` — Hub + **авто-sync каталога** (mirror + import в volume)  
3. `deploy_mesh.sh` — Mesh (`MESH_PUBLIC_READ=0`)  
4. `deploy_argus.sh` — ARGUS (`ARGUS_MESH_URL` при необходимости)  
5. `deploy_alien_monitor.sh` — Monitor + Pulse  
6. `deploy_lottery_uni.sh` (best-effort)  
7. `deploy_ecosystem_landing.sh` (best-effort)  
8. warm-up Factory API  
9. `verify_ecosystem_full.sh` — **ожидается PASS по всем проверкам**

Быстрый redeploy без verify (не на prod без причины):

```bash
./scripts/deploy_ecosystem.sh --skip-verify
```

### Частичный redeploy

| Цель | Команда | Примечание |
|------|---------|------------|
| Только Hub + sync каталога | `./scripts/deploy_hub.sh` | После ship новых продуктов на Factory |
| Только Mesh | `./scripts/deploy_mesh.sh` | |
| Только Monitor | `./scripts/deploy_alien_monitor.sh` | `ALIEN_MODE=real` для LIVE |
| Только Factory | `./scripts/deploy.sh` | После — желательно `deploy_hub.sh` для sync |
| Проверка без redeploy | `./scripts/verify_ecosystem_full.sh` | |

**Hub:** никогда `cd aimarket-hub && docker compose up` на prod — только `./scripts/deploy_hub.sh`.

---

## Post-deploy — чеклист

```bash
# 1. Ecosystem verify
./scripts/verify_ecosystem_full.sh

# 2. Hub manifest (порт 9083, не 9080)
curl -sf http://127.0.0.1:9083/.well-known/ai-market.json | head -c 200

# 3. Factory shipped products попали в hub (после sync)
curl -sf 'http://127.0.0.1:9083/ai-market/v2/capabilities?source=local&limit=5' | jq '.capabilities | length'

# 4. Monitor: summary публично, state закрыт
curl -sf http://127.0.0.1:9100/api/summary | jq .total_invocations_24h
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9100/api/state          # → 401
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $ALIEN_API_TOKEN" http://127.0.0.1:9100/api/state    # → 200

# 5. Mesh read закрыт
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8090/v1/stats           # → 401

# 6. ARGUS health + mesh URL в argus/.env
curl -sf http://127.0.0.1:8787/health
grep ARGUS_MESH_URL argus/.env

# 7. Публичные метрики (после redeploy Factory с новым endpoint)
curl -sf https://magic-ai-factory.com/api/public/ecosystem-status | jq .slo

# 8. Hub live stats (внешний URL)
curl -sf https://modelmarket.dev/ai-market/v2/stats/live | jq .summary
```

Логи hub sync (в выводе `deploy_hub.sh`):

```
--- Syncing factory catalog into hub volume ---
mirrored N products → .../pipeline.json
import_factory_products upserted M capability row(s)
```

Если `WARN: hub import failed` — проверить mount `/factory_data` и наличие `data/pipeline.json` на хосте.

---

## Breaking change — payment channels (Factory + клиенты)

После redeploy **новые** каналы (`POST /ai-market/channel/open`) возвращают:

```json
{
  "channel": { "channel_id": "ch_...", ... },
  "channel_secret": "<one-time secret>",
  "protocol_version": "v1"
}
```

При invoke и pipeline **обязательно** передавать:

```http
X-Payment-Channel: ch_...
X-Payment-Channel-Secret: <channel_secret из open>
```

Hub уже требовал secret; Factory теперь на parity.

**Старые каналы** без `secret_hash` в store продолжают работать без secret (back-compat). Новые — только с secret.

Pipeline body:

```json
{
  "channel_id": "ch_...",
  "channel_secret": "...",
  "nodes": [ ... ]
}
```

---

## Автономная эксплуатация (без ручного sync)

| Задача | Как |
|--------|-----|
| Каталог Factory → Hub | Автоматически при каждом `deploy_hub.sh` |
| Полный redeploy | Только при релизе образов, не для sync |
| Ежедневные метрики | cron: `python3 scripts/collect_production_metrics.py` |
| Smoke | cron: `./scripts/smoke_stack_test.sh` |

Пример crontab на хосте:

```cron
0 6 * * *  cd /path/to/aicom && python3 scripts/collect_production_metrics.py >> /var/log/aicom-metrics.log 2>&1
15 6 * * * cd /path/to/aicom && ./scripts/smoke_stack_test.sh >> /var/log/aicom-smoke.log 2>&1
```

`restart: unless-stopped` на контейнерах hub / mesh / factory / monitor — перезапуск после reboot хоста без ручного вмешательства.

---

## Troubleshooting

| Симптом | Вероятная причина | Действие |
|---------|-------------------|----------|
| Shipped products не в Hub | Не был `deploy_hub.sh` после ship | `./scripts/deploy_hub.sh` |
| Monitor `/api/state` 401 в браузере | Ожидаемо в prod | Токен только для ops/automation |
| Monitor mutating API 503 | Нет `ALIEN_API_TOKEN` | Задать в `.env`, redeploy monitor |
| Mesh 401 на `/v1/agents` | `MESH_PUBLIC_READ=0` | Норма; передать `Authorization: Bearer $MESH_API_TOKEN` |
| ARGUS не регистрируется в mesh | Старый `ARGUS_MESH_URL` | `ARGUS_MESH_URL=http://127.0.0.1:8090` в `argus/.env`, redeploy argus |
| Invoke 402 `invalid_channel_secret` | Нет `X-Payment-Channel-Secret` | Взять secret из ответа `channel/open` |
| Hub stats на :9080 | Старый runbook | Hub на **:9083** |
| `ecosystem-status` 404 снаружи | Factory не redeployed | `./scripts/deploy.sh` |

Ручной sync каталога (если hub уже up, без полного redeploy):

```bash
PYTHONPATH=.:aimarket-hub AIFACTORY_DATA_ROOT=./data \
  python3 scripts/sync_pipeline_mirror_and_hub.py --mirror-only

docker exec -e AIFACTORY_DATA_ROOT=/factory_data modelmarket-hub python3 -c "
from pathlib import Path
from aimarket_hub.database import HubDatabase
from aimarket_hub.factory_bridge import import_factory_products
db = HubDatabase('/app/data/hub.db')
p = Path('/factory_data/pipeline.json')
print(import_factory_products(db, pipeline_json_path=str(p)))
"
```

(Требует mount `/factory_data` из `deploy_hub.sh`.)

---

## Base path: `/monitor/`, `/pulse/`, `/platon/` (VPS trimmed deploy)

**Корневая проблема:** Vite `BASE_PATH=/monitor/` (и `/pulse/`, `/platon/`), а API/WS на бэкенде — `/api/*`, `/ws`. Без strip prefix UI на прямом порту зависает.

| Режим | Base path | Кто strip'ит prefix |
|--------|-----------|---------------------|
| **Behind nginx** (`magic-ai-factory.com`) | `/monitor/`, `/pulse/` | `deploy/nginx/snippets/*.conf` → `proxy_pass …/` |
| **Standalone ports** (`:9100`, `:5199`, `:8080`) | тот же | backend middleware / nginx **в контейнере** |

**В репо (после фикса):**

- **Monitor** — `MonitorBasePathMiddleware`: `/monitor/api/*` → `/api/*`, `/monitor/ws` → `/ws`
- **Pulse** — `apps/pulse-terminal/nginx.prod.conf`: `location ^~ /pulse/assets/`, `/pulse/api/`
- **Platon** — `platon/frontend/nginx.conf` + `platonUrl()` / `platonWsUrl()` в фронте

**Pre-flight trimmed monorepo:** `./scripts/ensure_deploy_satellites.sh` (вызывается из `deploy_ecosystem.sh`) — клонирует `acex/`, `aimarket-hub/`, `plugins/` если отсутствуют.

**Verify (path-prefix):** `verify_ecosystem_full.sh` проверяет `/monitor/api/health`, `/monitor/api/state`, `/pulse/pulse/`, опционально Platon.

**Чеклист VPS перед релизом:**

```bash
./scripts/verify_ecosystem_full.sh          # ожидается 0 failed
curl -sf http://127.0.0.1:9100/monitor/api/health
curl -sf http://127.0.0.1:5199/pulse/ | grep -q assets
# ALIEN_API_TOKEN в .env + redeploy monitor (иначе /api/state → 503)
grep -q '^ALIEN_API_TOKEN=' .env && ./scripts/deploy_alien_monitor.sh
```

**Секреты Monitor:** без `ALIEN_API_TOKEN` в prod `/api/state` возвращает 503 — relayer и verify падают. `deploy_alien_monitor.sh` подгружает `.env`, но **не перезаписывает** `ALIEN_MODE` из аргументов скрипта.

---

## Ещё не закрыто (не блокирует этот deploy)

- `/supply/stake` — on-chain verify (S-H4)
- Prometheus не в `deploy_ecosystem.sh` — LIVE monitor без prom metrics (C-M3)
- ACEX on-chain settlement wiring (P2)

Детали: [`ecosystem-audit-report.md`](./ecosystem-audit-report.md).

---

## Команда для агентов / CI

Полный redeploy экосистемы:

```bash
./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
```

Не останавливать `modelmarket-hub` без немедленного `./scripts/deploy_hub.sh`.

### Docker image tags (P1-6)

При ошибке BuildKit `image already exists` на rebuild:

```bash
export AICOM_IMAGE_TAG="$(./scripts/docker_image_tag.sh)"
./scripts/deploy_alien_monitor.sh   # или deploy_mesh.sh / deploy.sh
```

Compose-сервисы используют `image: <name>:${AICOM_IMAGE_TAG:-local}`; deploy-скрипты вызывают `build --pull`.

### Nginx snippets (P1-10)

```bash
sudo ./scripts/install_nginx_proxy.sh
```

### Trimmed factory / GitHub mirror

Агент, пушащий в `alexar76/aicom`: [`agent-github-factory-publish.md`](./agent-github-factory-publish.md).  
VPS без сателлитов в git: [`deploy-vps-trimmed.md`](./deploy-vps-trimmed.md), шаблон `.env.vps.example`.

### Monitor bind (P1-8)

По умолчанию `ALIEN_HOST=127.0.0.1` — доступ через nginx `/monitor/`.  
`ALIEN_HOST=0.0.0.0` только если нужен прямой `:9100` без proxy.
