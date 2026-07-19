# HELIOS — integración en el ecosistema

Cómo **HELIOS** encaja en el stack AICOM con PromoMaterials, DIOSCURI y Alien Monitor.

**English:** [helios-integration.md](./helios-integration.md) · **Русский:** [helios-integration-ru.md](./helios-integration-ru.md)

## Planos

| Plano | Rol |
|-------|-----|
| **Monorepo** `helios/` | Fuente de verdad |
| **GitHub** `alexar76/helios` | Espejo público |
| **Alien Monitor** | Nodo del grafo — poll `GET /health` |

```bash
./scripts/publish_all_repos.sh --satellite helios
```

## Nodo Alien Monitor

```bash
ALIEN_HELIOS_URL=http://helios:8791
ALIEN_HELIOS_YOUTUBE_URL=https://www.youtube.com/@My-AI-Factory
```

## DIOSCURI → HELIOS

```bash
HELIOS_SYNDICATION=1
HELIOS_QUEUE_PATH=/data/helios-queue.jsonl
```

## PromoMaterials

```bash
helios backfill-enqueue -n 10
helios worker
```

## Documentos relacionados

- [HELIOS README (ES)](../../helios/README-es.md)
- [Base de conocimiento (ES)](./knowledge-base-es.md)
