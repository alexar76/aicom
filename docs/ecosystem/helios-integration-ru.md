# HELIOS — интеграция в экосистему (спутник монорепозитория)

🌐 **[English](./helios-integration.md)** · **Русский** · **[Español](./helios-integration-es.md)** · **[Français](./helios-integration-fr.md)** · **[中文](./helios-integration-zh.md)**

HELIOS живёт в `helios/` в монорепозитории AICOM и зеркалируется в [github.com/alexar76/helios](https://github.com/alexar76/helios).

## Плоскости

| Плоскость | Роль |
|-----------|------|
| **Monorepo** `helios/` | Источник правды |
| **GitHub** `alexar76/helios` | Публичное зеркало — docs, CI, self-host |
| **Хост оператора** | ffmpeg + YouTube OAuth + cron-worker |
| **Alien Monitor** | Узел графа — опрашивает `GET /health`, статистику YouTube |

```bash
./scripts/publish_all_repos.sh --satellite helios
```

## Секреты — никогда в git

| Файл | Назначение |
|------|------------|
| `.env` | `YOUTUBE_*`, ключи LLM, webhook |
| `helios.config.yaml` | Несекретная настройка (лимиты, корни ассетов) |

Оба исключены из rsync спутника (`satellite-map.yaml` → `exclude_paths`).

## Узел Alien Monitor

| Env | Назначение |
|-----|------------|
| `ALIEN_HELIOS_URL` | Опрос `GET /health` (по умолчанию `http://127.0.0.1:8791`) |
| `ALIEN_PUBLIC_HELIOS_URL` | Ссылка на детали узла (репозиторий GitHub) |
| `ALIEN_HELIOS_YOUTUBE_URL` | Ссылка на YouTube-канал в панели |

**Ответ health:**

```json
{
  "ok": true,
  "version": "0.1.0",
  "uptimeSec": 3600,
  "queue_pending": 3,
  "uploaded_today": 2,
  "max_uploads_per_day": 9,
  "dryRun": false,
  "youtube": {
    "subscribers": 1200,
    "views": 45000,
    "videos": 12,
    "cached_at": "2026-07-07T10:00:00Z",
    "stale": false
  }
}
```

**Позиция:** северо-западная полка (`helios` @ `-8.5, 7.5, -5.0`).  
**Рёбра:** `factory → helios`, `dioscuri → helios` (очередь релизов).

Клик по узлу → закешированная статистика YouTube (без живого вызова API из Monitor).

## Хук DIOSCURI

```bash
# dioscuri .env
HELIOS_SYNDICATION=1
HELIOS_QUEUE_PATH=/data/helios-queue.jsonl
```

Worker HELIOS считывает jsonl при каждом запуске `helios worker`.

**Docker (общий том):**

```bash
docker volume create aicom-ecosystem-data
docker compose -f dioscuri/docker-compose.yml -f helios/docker-compose.yml \
  -f docs/ecosystem/docker-compose.cognition.yml up -d --build
```

## PromoMaterials

Контент остаётся в PromoMaterials; HELIOS — движок:

```bash
helios backfill-scan
helios backfill-enqueue -n 10
helios worker
```

## Связанные документы

- [HELIOS landing](https://alexar76.github.io/helios/) — видеогалерея + [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory)
- [HELIOS README](../../helios/README.md) · [RU](../../helios/README-ru.md) · [ES](../../helios/README-es.md)
- [Архитектура](../../helios/docs/architecture.md)
- [Аудит безопасности](../../helios/docs/SECURITY-AUDIT.md)
- [База знаний](./knowledge-base.md)
