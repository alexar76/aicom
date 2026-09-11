# SKOPOS — интеграция в экосистему

**SKOPOS** ([`skopos/`](https://github.com/alexar76/skopos)) — спутник **наблюдаемости флота** AICOM: аналитика nginx и Apache по SSH, Security Center, история сканирований и AI-аналитик. На своём сервере (self-hosted); для продакшена рекомендуется PostgreSQL.

> 🌐 Языки: [English](./skopos-integration.md) · **Русский** · [Español](./skopos-integration-es.md) · [Français](./skopos-integration-fr.md) · [中文](./skopos-integration-zh.md)

---

## Живые поверхности

| Поверхность | URL | Роль |
|-------------|-----|------|
| **Дашборд** | [skopos.modelmarket.dev](https://skopos.modelmarket.dev) | UI на Streamlit (в продакшене защищён паролем) |
| **Публичный статус** | `GET /healthz` | Несекретный JSON для Alien Monitor и проб |
| **Alien Monitor** | [monitor.modelmarket.dev/](https://monitor.modelmarket.dev/) | Узел 3D-графа — кликните по сфере **SKOPOS** |

---

## Узел Alien Monitor

| Env | Назначение |
|-----|------------|
| `ALIEN_SKOPOS_URL` | Опрос `GET /healthz` (по умолчанию `https://skopos.modelmarket.dev`) |
| `ALIEN_PUBLIC_SKOPOS_URL` | Ссылка в панели — URL дашборда |
| `ALIEN_SKOPOS_GITHUB_URL` | Ссылка на GitHub в панели (по умолчанию `https://github.com/alexar76/skopos`) |

**Ответ health (несекретный):**

```json
{
  "ok": true,
  "service": "skopos",
  "version": "0.1.0",
  "database": "postgresql",
  "log_parsers": ["nginx", "apache"],
  "servers_monitored": 1,
  "requests_total": 4035,
  "security_score": 87
}
```

**Позиция в графе:** западная полка рядом с Metis (`skopos` @ `-11.5, -3.5, 1.5`).  
**Рёбра:** `factory → skopos` (телеметрия трафика), `skopos → metis` (флот хостов), `skopos → hub` (состояние экосистемы).

Клик по сфере → **Open SKOPOS dashboard**, GitHub, docs, руководство по интеграции. Метрики показывают число отслеживаемых серверов, суммарное количество разобранных запросов и security score — без секретов.

---

## Развёртывание на узле Metis

Продакшен-стек для тестов: [`metis/deploy/skopos-test/`](https://github.com/alexar76/metis/tree/main/deploy/skopos-test/).

```bash
cd metis/deploy/skopos-test
./remote-sync.sh
```

Nginx-vhost `skopos.modelmarket.dev` находится в [`metis/deploy/nginx.conf`](https://github.com/alexar76/metis/blob/main/deploy/nginx.conf) — проксирует `:8501` (UI) и `:8502` (`/healthz`).

TLS (после того как DNS указывает на хост Metis):

```bash
docker run --rm -v /opt/metis/deploy/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot certbot/certbot certonly --webroot \
  -w /var/www/certbot -d skopos.modelmarket.dev --agree-tos -m you@example.com
docker restart metis-nginx
```

---

## Пути в монорепозитории

| Путь | Роль |
|------|------|
| `skopos/` | Исходный код приложения |
| `metis/deploy/skopos-test/` | Docker Compose + `servers.yaml` для хоста Metis |
| `alien-monitor/backend/skopos_*.py` | Узел графа + живой опрос |
| `docs/ecosystem/skopos-integration.md` | Этот файл |

Репозиторий спутника: [alexar76/skopos](https://github.com/alexar76/skopos) — публикация через `./scripts/publish_all_repos.sh --satellite skopos`.

**Лендинг:** [skopos.modelmarket.dev](https://skopos.modelmarket.dev) (live) · [alexar76.github.io/skopos](https://alexar76.github.io/skopos/) (GitHub Pages, EN/RU/ES). Источник: `skopos/docs/landing/index.html`. Workflow: `skopos/.github/workflows/pages.yml`.

---

## Независимость

SKOPOS не требует Factory, Hub или Metis во время работы. Alien Monitor деградирует мягко, когда `/healthz` недоступен (узел показывает `offline`).

---

## Экономика AIMarket (опциональная сторона предложения)

SKOPOS может **продавать аналитику о флоте** другим ИИ-агентам через [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol/blob/main/spec.md) — по той же схеме, что и Metis `/aimarket/invoke`.

**По умолчанию выключено.** Включайте только если хотите видеть SKOPOS в федеративной экономике агентов:

```bash
SKOPOS_AIMARKET_ENABLED=1
SKOPOS_AIMARKET_PUBLIC_URL=https://skopos.modelmarket.dev
# Optional: protect invoke with API key
SKOPOS_AIMARKET_API_KEY=your-secret
# Optional: auto-register capabilities on Hub at startup
SKOPOS_HUB_URL=https://modelmarket.dev
SKOPOS_AIMARKET_AUTO_REGISTER=1
SKOPOS_AIMARKET_PUBLISH_TOKEN=...
```

| Endpoint | Роль |
|----------|------|
| `GET /.well-known/ai-market.json` | Обнаружение |
| `GET /ai-market/v2/manifest` | Каталог возможностей |
| `POST /aimarket/invoke` | Контракт вызова Hub `{input, product_id, capability_id}` → `{result}` |

### Оплачиваемые возможности

| ID | Что продаётся | ~USD/вызов |
|----|----------------|-----------|
| `skopos.fleet.status@v1` | Heartbeat + security score | $0.01 |
| `skopos.security.posture@v1` | Оценка флота, алерты, замечания | $0.08 |
| `skopos.traffic.summary@v1` | Агрегаты трафика за 24 ч | $0.05 |
| `skopos.briefing@v1` | Человекочитаемый брифинг по флоту (правила / LLM) | $0.15 |

ARGUS, Factory или Alien Monitor могут **покупать** контекст о состоянии безопасности без SSH-доступа к вашему флоту.

### Режим потребителя (опционально)

Задайте `SKOPOS_HUB_URL`, чтобы SKOPOS мог **обнаруживать** возможности Hub (бесплатный поиск). Платные вызовы от SKOPOS к оракулам требуют интеграции кошелька (в будущем); в автономном режиме отсутствие Hub игнорируется.

Nginx на Metis должен проксировать порт **8502** для `/healthz`, `/.well-known/*`, `/ai-market/*` и `/aimarket/invoke` (см. `metis/deploy/nginx.conf`).
