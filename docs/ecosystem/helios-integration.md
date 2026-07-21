# HELIOS integration — monorepo satellite

🌐 **English** · **[Русский](./helios-integration-ru.md)** · **[Español](./helios-integration-es.md)** · **[Français](./helios-integration-fr.md)** · **[中文](./helios-integration-zh.md)**

HELIOS lives at `helios/` in the AICOM monorepo and mirrors to [github.com/alexar76/helios](https://github.com/alexar76/helios).

## Planes

| Plane | Role |
|-------|------|
| **Monorepo** `helios/` | Source of truth |
| **GitHub** `alexar76/helios` | Public mirror — docs, CI, self-host |
| **Operator host** | ffmpeg + YouTube OAuth + cron worker |
| **Alien Monitor** | Graph node — polls `GET /health`, YouTube stats |

```bash
./scripts/publish_all_repos.sh --satellite helios
```

## Secrets — never in git

| File | Purpose |
|------|---------|
| `.env` | `YOUTUBE_*`, LLM keys, webhook |
| `helios.config.yaml` | Non-secret tuning (limits, asset roots) |

Both excluded from satellite rsync (`satellite-map.yaml` → `exclude_paths`).

## Alien Monitor node

| Env | Purpose |
|-----|---------|
| `ALIEN_HELIOS_URL` | Poll `GET /health` (default `http://127.0.0.1:8791`) |
| `ALIEN_PUBLIC_HELIOS_URL` | Node detail link (GitHub repo) |
| `ALIEN_HELIOS_YOUTUBE_URL` | YouTube channel link in panel |

**Health response:**

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

**Position:** northwest shelf (`helios` @ `-8.5, 7.5, -5.0`).  
**Edges:** `factory → helios`, `dioscuri → helios` (release queue).

Click the node → cached YouTube stats (no live API call from Monitor).

## DIOSCURI hook

```bash
# dioscuri .env
HELIOS_SYNDICATION=1
HELIOS_QUEUE_PATH=/data/helios-queue.jsonl
```

HELIOS worker ingests jsonl on each `helios worker` run.

**Docker (shared volume):**

```bash
docker volume create aicom-ecosystem-data
docker compose -f dioscuri/docker-compose.yml -f helios/docker-compose.yml \
  -f docs/ecosystem/docker-compose.cognition.yml up -d --build
```

## PromoMaterials

Content stays in PromoMaterials; HELIOS is the engine:

```bash
helios backfill-scan
helios backfill-enqueue -n 10
helios worker
```

## Related docs

- [HELIOS landing](https://alexar76.github.io/helios/) — video gallery + [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory)
- [HELIOS README](../../helios/README.md) · [RU](../../helios/README-ru.md) · [ES](../../helios/README-es.md)
- [Architecture](../../helios/docs/architecture.md)
- [Security audit](../../helios/docs/SECURITY-AUDIT.md)
- [Knowledge base](./knowledge-base.md)
