# HELIOS — integración en el ecosistema (satélite del monorepo)

🌐 **[English](./helios-integration.md)** · **[Русский](./helios-integration-ru.md)** · **Español** · **[Français](./helios-integration-fr.md)** · **[中文](./helios-integration-zh.md)**

HELIOS vive en `helios/` en el monorepo de AICOM y se replica en [github.com/alexar76/helios](https://github.com/alexar76/helios).

## Planos

| Plano | Rol |
|-------|-----|
| **Monorepo** `helios/` | Fuente de verdad |
| **GitHub** `alexar76/helios` | Espejo público — docs, CI, autoalojamiento |
| **Host del operador** | ffmpeg + YouTube OAuth + worker cron |
| **Alien Monitor** | Nodo del grafo — sondea `GET /health`, estadísticas de YouTube |

```bash
./scripts/publish_all_repos.sh --satellite helios
```

## Secretos — nunca en git

| Archivo | Propósito |
|---------|-----------|
| `.env` | `YOUTUBE_*`, claves LLM, webhook |
| `helios.config.yaml` | Ajustes no secretos (límites, raíces de assets) |

Ambos excluidos del rsync del satélite (`satellite-map.yaml` → `exclude_paths`).

## Nodo Alien Monitor

| Env | Propósito |
|-----|-----------|
| `ALIEN_HELIOS_URL` | Sondear `GET /health` (por defecto `http://127.0.0.1:8791`) |
| `ALIEN_PUBLIC_HELIOS_URL` | Enlace al detalle del nodo (repositorio GitHub) |
| `ALIEN_HELIOS_YOUTUBE_URL` | Enlace al canal de YouTube en el panel |

**Respuesta de health:**

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

**Posición:** repisa noroeste (`helios` @ `-8.5, 7.5, -5.0`).  
**Aristas:** `factory → helios`, `dioscuri → helios` (cola de lanzamientos).

Haz clic en el nodo → estadísticas de YouTube en caché (sin llamada en vivo a la API desde Monitor).

## Hook de DIOSCURI

```bash
# dioscuri .env
HELIOS_SYNDICATION=1
HELIOS_QUEUE_PATH=/data/helios-queue.jsonl
```

El worker de HELIOS ingiere el jsonl en cada ejecución de `helios worker`.

**Docker (volumen compartido):**

```bash
docker volume create aicom-ecosystem-data
docker compose -f dioscuri/docker-compose.yml -f helios/docker-compose.yml \
  -f docs/ecosystem/docker-compose.cognition.yml up -d --build
```

## PromoMaterials

El contenido permanece en PromoMaterials; HELIOS es el motor:

```bash
helios backfill-scan
helios backfill-enqueue -n 10
helios worker
```

## Documentos relacionados

- [HELIOS landing](https://alexar76.github.io/helios/) — galería de vídeos + [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory)
- [HELIOS README](../../helios/README.md) · [RU](../../helios/README-ru.md) · [ES](../../helios/README-es.md)
- [Arquitectura](../../helios/docs/architecture.md)
- [Auditoría de seguridad](../../helios/docs/SECURITY-AUDIT.md)
- [Base de conocimiento](./knowledge-base.md)
