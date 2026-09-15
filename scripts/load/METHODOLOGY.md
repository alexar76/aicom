# Методика нагрузочных тестов экосистемы

Харнесс: [`locust_ecosystem.py`](locust_ecosystem.py) + [`run_load_smoke.sh`](run_load_smoke.sh).
Отдельные контуры: Factory soak [`scripts/load_test_factory.sh`](../load_test_factory.sh) (KI-3),
Mesh [`ai-service-mesh/backend/load/`](../../ai-service-mesh/backend/load/), Metis k6
[`metis/deploy/loadtest.k6.js`](../../metis/deploy/loadtest.k6.js).

venv для Locust лежит в `scripts/load/.venv*` и **не коммитится**.

---

## 1. Зачем

Доказать, что **read-path** флота живёт под нагрузкой: health, каталог, поиск, статистика,
шеллы. Не сжечь LLM-бюджет и не открыть платный Hub invoke.

Это **не** закрывает KI-3 (uvicorn crash-loop при `UVICORN_WORKERS=4+` на pipeline). KI-3 —
отдельный soak Factory API с профайлером.

## 2. Что входит в смесь Locust

Смесь — несколько классов `HttpUser` с **весом** (доля виртуальных пользователей) и
`wait_time` между задачами. Каждая задача — один HTTP-вызов. Тяжёлые POST выключены, пока
их явно не включат.

| Пользователь | weight | wait_time | Задача (weight внутри класса) | Метод | Путь | Зачем |
|---|---|---|---|---|---|---|
| FactoryUser | 2 | 1.0–3.0 с | health **6** | GET | `/api/health` | liveness API |
| | | | trust_metrics **3** | GET | `/api/marketing/trust-metrics` | публичные метрики |
| | | | products **1** | GET | `/api/products` | тяжёлый каталог (timeout 120 с) |
| FrontendUser | 2 | 0.5–2.0 с | home **1** | GET | `/` | HTML шелл Factory |
| HubUser | 5 | 0.3–1.2 с | stats_live **5** | GET | `/ai-market/v2/stats/live?limit=10` | живая статистика |
| | | | search **4** | GET | `/ai-market/v2/search?intent=translate&budget=2&limit=5` | поиск (без invoke) |
| | | | well_known **3** | GET | `/.well-known/ai-market.json` | federation seed |
| | | | capital_pricing **2** | GET | `/api/v2/capital/pricing?limit=5` | прайс капитала |
| | | | health **1** | GET | `/ai-market/v2/health` | liveness Hub |
| MeshUser | 3 | 0.8–2.5 с | stats **5** | GET | `/v1/stats` | дашборд; **429 = успех** |
| | | | activity **3** | GET | `/v1/activity?limit=30` | лента; 429 = успех |
| | | | agents **2** | GET | `/v1/agents?verified_only=true` | ростер; 429 = успех |
| | | | health **1** | GET | `/health` | liveness Mesh |
| | | | create_task **1** | POST | `/v1/tasks` | **выкл.** без `LOAD_MESH_TASKS=1` |
| ArgusUser | 3 | 0.5–2.0 с | health **6** | GET | `/health` локально; публично `/arena` | лендинг/health ARGUS |
| | | | arena_stats **2** | GET | `/arena/stats` | LIVE-арена JSON |
| | | | ask_ping **1** | POST | `/ask` | **выкл.** без `ARGUS_LOAD_ASK=1` |
| MonitorUser | 3 | 0.5–2.5 с | api_health **4** | GET | `/api/health` | liveness Monitor |
| | | | prefixed_health **3** | GET | `/monitor/api/health` | тот же API за префиксом nginx |
| | | | state **2** | GET | `/monitor/api/state` | граф; без токена 401 — ожидаемо |
| PulseUser | 2 | 0.6–2.0 с | pulse_shell **3** | GET | `/pulse/` | Pulse Terminal |
| | | | root **1** | GET | `/` | корень Pulse-хоста |

Сумма весов классов = 20. Ожидаемая доля VU: Hub 25%, Mesh/ARGUS/Monitor по 15%, Factory/Frontend/Pulse по 10%.

**Не в этой смеси:** lottery, Platon, oracle-family, GAIA, ATLAS, MOMUS, SKOPOS,
pipeline create, sandbox, paid invoke.

Публичные URL (`LOAD_TARGET=public`) бьют **разные серверы**. Карта: [`topology.py`](topology.py)
(тот же четырёххостовый флот, что [`scripts/llm_fleet.yaml`](../llm_fleet.yaml)).

| Сервер | SSH | Модули в смеси |
|---|---|---|
| **Factory** | `my-vps` | Factory, Hub, Mesh, ARGUS, Monitor, Pulse, ATLAS, THEMIS, verify, forge |
| **Oracles** | `admin-vps` | GAIA (`iot`), oracles/Platon, lottery, MOMUS, LOGOS |
| **Metis + SKOPOS** | `skopos.modelmarket.dev` | Metis `/health` + `/v1/verify`, SKOPOS |
| Hub lab (не в смеси) | `competing-lab` | hunt / lab hub |

Тяжёлые POST идут **на тот же хост, что и read того модуля** (Mesh/ARGUS/Hub invoke → factory; Metis verify → Metis). Падение Pulse не говорит ничего про Metis.

## 3. Три режима нагрузки

Задаются `LOAD_MODE`. Числа — **дефолты**; их можно перекрыть `LOAD_USERS` /
`LOAD_SPAWN_RATE` / `LOAD_DURATION`.

### 3.1 `smoke` — короткая нагрузка

**Вопрос:** смесь жива? Нет ли 5xx на health за полторы минуты.

| Параметр | Значение |
|---|---|
| Виртуальные пользователи | 8 |
| Нарастание | 4 VU/с (полный комплект за ~2 с) |
| Длительность | 90 с |
| Форма | ступенька: быстро выйти на полку и держать |
| Оценка запросов | ≈ 200–400 (зависит от wait_time и ошибок) |
| Pass | fail-ratio **< 5%** после вычета Mesh 429 и Monitor 401 без токена; p95 health **< 2 с** |

```bash
LOAD_TARGET=public LOAD_MODE=smoke ./scripts/load/run_load_smoke.sh
```

### 3.2 `constant` — постоянная нагрузка (soak)

**Вопрос:** держит ли полку без деградации и рестартов.

| Параметр | Значение |
|---|---|
| VU | 20 |
| Нарастание | 2 VU/с (~10 с до полки) |
| Длительность | 10 мин |
| Форма | константа после короткого ramp-up |
| Оценка запросов | ≈ 3–6 тыс. |
| Pass | fail-ratio **< 5%**; p95 health не хуже smoke больше чем в 2 раза; нет restart в логах Factory, если смотрим KI-3 soak рядом |

```bash
LOAD_TARGET=public LOAD_MODE=constant ./scripts/load/run_load_smoke.sh
```

Factory-only KI-3 (другой скрипт, не Locust):

```bash
./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 600 --concurrency 10
```

Там 10 воркеров, каждый ~2 req/s на `/api/health` и каждый третий на `/api/pipeline/list`,
10 минут, **0** ошибок, плюс хвост `uvicorn-last-crash.log`. Час (`--duration 3600`) —
операторский прогон на закрытие KI-3.

### 3.3 `ramp` — линейное нарастание, пока не крякнется

**Вопрос:** где ёмкость read-path. Не «уронить прод», а найти излом: fail-ratio, таймауты, 5xx.

| Параметр | Значение |
|---|---|
| Старт | 4 VU |
| Шаг | +4 VU каждые 20 с |
| Потолок | 80 VU |
| Spawn rate внутри шага | 2 VU/с |
| Стоп | fail-ratio **≥ 8%** после минимум 80 запросов, **или** потолок + 60 с полки, **или** 20 мин |
| Форма | пила-лестница (step ramp) |
| Оценка запросов | зависит от того, где сломается; полный прогон до потолка ≈ 15–20 мин |
| Как читать «кряк» | первая ступень, где p95 health > 2 с **или** fail-ratio ≥ 8% **или** массовые 5xx/timeout. Это ёмкость, не баг-репорт само по себе |

Из смеси **исключаются известные дефекты**, иначе «кряк» наступает на первом запросе:

- Pulse `/pulse/` отдавал **502** (2026-09-14) — для ramp выставляется `LOAD_SKIP_PULSE=1`
- Monitor `/monitor/api/state` без токена — **401**, это контракт; в отчёте не failure

```bash
LOAD_TARGET=public LOAD_MODE=ramp ./scripts/load/run_load_smoke.sh
```

На **production** ramp — только с низким шагом и с наблюдением. Это не DoS и не pentest.
`ARGUS_LOAD_ASK` и `LOAD_MESH_TASKS` в ramp **запрещены** (скрипт их сбрасывает).

## 4. Порядок прогона

0. **Preflight** — по одному GET на health каждого блока. Фиксируем код и время.
1. **smoke** — короткая ступенька.
2. **constant** — полка, если smoke зелёный.
3. **ramp** — только после того, как известные 5xx убраны или явно skip.
4. Тяжёлые POST (`ARGUS_LOAD_ASK`, `LOAD_MESH_TASKS`) — отдельным прогоном, 2–4 VU, не на публичном флоте без нужды.

Отчёты: `scripts/load/reports/` (gitignored) — HTML + CSV Locust.

## 5. Что уже измерено (2026-09-14, один GET, публичный флот)

Локальный compose на этой машине был выключен. Preflight против live:

| Блок | URL | HTTP | Время |
|---|---|---|---|
| Factory health | `magic-ai-factory.com/api/health` | 200 | 0.38 с |
| Factory frontend | `magic-ai-factory.com/` | 200 | 0.36 с |
| Hub health | `modelmarket.dev/ai-market/v2/health` | 200 | 0.82 с |
| Hub well-known | `modelmarket.dev/.well-known/ai-market.json` | 200 | 0.28 с |
| Mesh health | `service-mesh.modelmarket.dev/health` | 200 | 0.38 с |
| Mesh stats | `service-mesh.modelmarket.dev/v1/stats` | 200 | 0.28 с |
| ARGUS arena | `magic-ai-factory.com/arena/stats` | 200 | 0.37 с |
| ARGUS `/health` на том же хосте | `magic-ai-factory.com/health` | **404** | 0.30 с — nginx не отдаёт ARGUS `/health` с корня; публичный health = `/arena` |
| Monitor health | `monitor.modelmarket.dev/api/health` | 200 | 0.51 с |
| Monitor state | `monitor.modelmarket.dev/monitor/api/state` | **401** | 0.26 с — нужен `ALIEN_API_TOKEN` |
| Pulse | `magic-ai-factory.com/pulse/` | **502** | 0.35 с — живой дефект, не «ёмкость» |
| Metis health | `metis.modelmarket.dev/health` | 200 | 0.73 с (k6, не Locust) |
| Oracles health | `oracles.modelmarket.dev/health` | 200 | 0.73 с |
| GAIA | `iot.modelmarket.dev/` | 200 | 0.73 с |
| ATLAS | `atlas.modelmarket.dev/` | 200 | 0.69 с |

Locust-прогон (`smoke`/`constant`/`ramp`) на этом шаге ещё не закрыт: установка venv на
системном Python 3.9 собирала gevent из исходников. Венв должен быть Python **3.11+**
(`scripts/load/.venv`, gitignored).

## 6. Чего прогон **не** доказывает

- Стабильность uvicorn-воркеров под pipeline (KI-3).
- Ёмкость LLM, debit Hub, escrow.
- Что 502 на Pulse «нормален» — это баг, его чинят, а не разгоняют.
