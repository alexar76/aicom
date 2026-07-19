# HELIOS — интеграция в экосистему

Как **HELIOS** (broadcast-пайплайн) вписывается в стек AICOM вместе с PromoMaterials, DIOSCURI и Alien Monitor.

**English:** [helios-integration.md](./helios-integration.md) · **Español:** [helios-integration-es.md](./helios-integration-es.md)

## Плоскости

| Плоскость | Роль |
|-----------|------|
| **Monorepo** `helios/` | Источник правды |
| **GitHub** `alexar76/helios` | Публичное зеркало |
| **VPS / macOS** | ffmpeg + OAuth + worker |
| **Alien Monitor** | Узел графа — poll `GET /health`, YouTube stats |

```bash
./scripts/publish_all_repos.sh --satellite helios
```

## Секреты — никогда в git

| Файл | Назначение |
|------|------------|
| `.env` | YouTube OAuth, LLM keys |
| `helios.config.yaml` | Несекретные настройки |

Исключены из rsync в `satellite-map.yaml`.

## Узел Alien Monitor

Позиция: `-8.5, 7.5, -5.0` (северо-запад, над DIOSCURI).

```bash
ALIEN_HELIOS_URL=http://helios:8791
ALIEN_PUBLIC_HELIOS_URL=https://github.com/alexar76/helios
ALIEN_HELIOS_YOUTUBE_URL=https://www.youtube.com/@My-AI-Factory
```

Клик по узлу → subscribers, views, videos (из кеша HELIOS).

## DIOSCURI → HELIOS

```bash
# dioscuri .env
HELIOS_SYNDICATION=1
HELIOS_QUEUE_PATH=/data/helios-queue.jsonl
```

При новом релизе DIOSCURI append-ит job `release-short` (fail-soft).

## PromoMaterials

Контент остаётся в PromoMaterials; HELIOS — движок:

```bash
helios backfill-scan
helios backfill-enqueue -n 10
helios worker
```

## Связанные документы

- [HELIOS README (RU)](../../helios/README-ru.md)
- [База знаний (RU)](./knowledge-base-ru.md)
- [Runbook](../../helios/docs/runbook-ru.md)
