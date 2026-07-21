# Intégration HELIOS — satellite du monorepo

🌐 **[English](./helios-integration.md)** · **[Русский](./helios-integration-ru.md)** · **[Español](./helios-integration-es.md)** · **Français** · **[中文](./helios-integration-zh.md)**

HELIOS vit dans `helios/` au sein du monorepo AICOM et est mis en miroir vers [github.com/alexar76/helios](https://github.com/alexar76/helios).

## Plans

| Plan | Rôle |
|------|------|
| **Monorepo** `helios/` | Source de vérité |
| **GitHub** `alexar76/helios` | Miroir public — docs, CI, self-host |
| **Hôte opérateur** | ffmpeg + YouTube OAuth + worker cron |
| **Alien Monitor** | Nœud du graphe — sonde `GET /health`, stats YouTube |

```bash
./scripts/publish_all_repos.sh --satellite helios
```

## Secrets — jamais dans git

| Fichier | Objet |
|---------|-------|
| `.env` | `YOUTUBE_*`, clés LLM, webhook |
| `helios.config.yaml` | Réglages non secrets (limites, racines d'assets) |

Les deux sont exclus du rsync des satellites (`satellite-map.yaml` → `exclude_paths`).

## Nœud Alien Monitor

| Env | Objet |
|-----|-------|
| `ALIEN_HELIOS_URL` | Sonder `GET /health` (par défaut `http://127.0.0.1:8791`) |
| `ALIEN_PUBLIC_HELIOS_URL` | Lien de détail du nœud (dépôt GitHub) |
| `ALIEN_HELIOS_YOUTUBE_URL` | Lien de la chaîne YouTube dans le panneau |

**Réponse health :**

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

**Position :** étagère nord-ouest (`helios` @ `-8.5, 7.5, -5.0`).  
**Arêtes :** `factory → helios`, `dioscuri → helios` (file de releases).

Cliquez sur le nœud → stats YouTube en cache (aucun appel API en direct depuis Monitor).

## Hook DIOSCURI

```bash
# dioscuri .env
HELIOS_SYNDICATION=1
HELIOS_QUEUE_PATH=/data/helios-queue.jsonl
```

Le worker HELIOS ingère le jsonl à chaque exécution de `helios worker`.

**Docker (volume partagé) :**

```bash
docker volume create aicom-ecosystem-data
docker compose -f dioscuri/docker-compose.yml -f helios/docker-compose.yml \
  -f docs/ecosystem/docker-compose.cognition.yml up -d --build
```

## PromoMaterials

Le contenu reste dans PromoMaterials ; HELIOS est le moteur :

```bash
helios backfill-scan
helios backfill-enqueue -n 10
helios worker
```

## Documents connexes

- [HELIOS landing](https://alexar76.github.io/helios/) — galerie vidéo + [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory)
- [HELIOS README](../../helios/README.md) · [RU](../../helios/README-ru.md) · [ES](../../helios/README-es.md)
- [Architecture](../../helios/docs/architecture.md)
- [Audit de sécurité](../../helios/docs/SECURITY-AUDIT.md)
- [Base de connaissances](./knowledge-base.md)
