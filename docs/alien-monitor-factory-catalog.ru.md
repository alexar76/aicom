# Alien Monitor — кластеры продуктов Factory

> **English:** [alien-monitor-factory-catalog.md](./alien-monitor-factory-catalog.md) · **Русский** · **Español:** [alien-monitor-factory-catalog.es.md](./alien-monitor-factory-catalog.es.md) · **Français:** [alien-monitor-factory-catalog.fr.md](./alien-monitor-factory-catalog.fr.md) · **中文:** [alien-monitor-factory-catalog.zh.md](./alien-monitor-factory-catalog.zh.md)

Как реальные продукты AI-Factory появляются как **оранжевые звёздные скопления** возле узла Factory в режимах UNI / LIVE.

---

## Должны ли продукты быть в UNI?

**Да.** `ALIEN_MODE=universe` — это не TEST-симуляция:

| Режим | Продукты на 3D-карте |
|-------|----------------------|
| **TEST** | Нет — только симулированный счётчик на Factory |
| **UNIVERSE (UNI)** | **Да** — синхронизация из `GET /api/products` |
| **LIVE (real)** | **Да** — тот же каталог + prod RPC |

UNI поднимает локальный Anvil **и** опрашивает live Factory / Hub / Mesh / Prometheus. Синхронизация при старте (bootstrap) и каждые ~60 с (`ALIEN_FACTORY_SYNC_TICKS`, по умолчанию 40 тиков).

На карте только продукты **из публичной витрины**, не все состояния пайплайна.

---

## Конфигурация

| Переменная | По умолчанию (prod) | Роль |
|------------|----------------|------|
| `AICOM_API_URL` | `http://127.0.0.1:9081` | База Factory API (host network) |
| `ALIEN_FACTORY_API_TIMEOUT` | `30` | Таймаут HTTP — `/api/products` 12–30 с |
| `ALIEN_MODE` | `universe` | Одна строка в `.env` — без дублей |

Prod: `alien-monitor/docker-compose.prod.yml`, **`network_mode: host`** → `127.0.0.1:9081` корректен.

---

## Почему кластеры пропадают

1. **Таймаут API (часто)** — был 8 с, Factory `/api/products` медленнее → пустой каталог → удаление всех кластеров. **Исправлено:** ошибка → `None` → **кластеры сохраняются**; таймаут 25–30 с.
2. **Режим TEST** — синхронизации каталога нет.
3. **Пустой каталог по делу** — строгий QA скрывает все продукты (`200` + `[]`). Удаление ожидаемо.

---

## Проверка

```bash
curl -s --max-time 45 http://127.0.0.1:9081/api/products | jq '.products | length'
curl -s http://127.0.0.1:9100/api/state | jq '[.nodes[] | select(.group=="cluster")] | length'
docker logs alien-monitor 2>&1 | grep -i 'factory catalog' | tail -5
```

На bootstrap: `factory catalog: +N products`.

---

## См. также

- [alien-monitor/README.md](https://github.com/alexar76/alien-monitor/blob/main/README.md) — деплой
- [uni-troubleshooting.md](./uni-troubleshooting.md) §16 — расширенная диагностика
- [funnel-growth.ru.md](./funnel-growth.ru.md) — публичный лид → пайплайн (сторона Factory)
