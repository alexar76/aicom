# Alien Monitor — clusters de produits Factory

> **English:** [alien-monitor-factory-catalog.md](./alien-monitor-factory-catalog.md) · **Русский:** [alien-monitor-factory-catalog.ru.md](./alien-monitor-factory-catalog.ru.md) · **Español:** [alien-monitor-factory-catalog.es.md](./alien-monitor-factory-catalog.es.md) · **Français** · **中文:** [alien-monitor-factory-catalog.zh.md](./alien-monitor-factory-catalog.zh.md)

Comment les produits réels d'AI-Factory apparaissent sous forme de **clusters d'étoiles orange** près du nœud Factory dans les modes UNI / LIVE.

---

## Les produits doivent-ils apparaître en mode UNI ?

**Oui.** `ALIEN_MODE=universe` n'est pas une simulation TEST :

| Mode | Produits Factory sur la carte 3D |
|------|----------------------------------|
| **TEST** | Non — seulement un compteur simulé sur Factory |
| **UNIVERSE (UNI)** | **Oui** — synchronisation depuis `GET /api/products` |
| **LIVE (real)** | **Oui** — même catalogue + RPC de production |

UNI lance un Anvil local **et** interroge en direct Factory / Hub / Mesh / Prometheus. La synchronisation du catalogue s'exécute au démarrage (bootstrap) et toutes les ~60 s (`ALIEN_FACTORY_SYNC_TICKS`, 40 ticks par défaut).

Seuls les produits **listés dans le storefront** apparaissent (même filtre que la boutique publique), pas tous les états du pipeline.

---

## Configuration

| Variable | Par défaut (prod) | Rôle |
|----------|-------------------|------|
| `AICOM_API_URL` | `http://127.0.0.1:9081` | Base de l'API Factory (réseau host en prod) |
| `ALIEN_FACTORY_API_TIMEOUT` | `30` | Timeout HTTP — `/api/products` peut prendre 12–30 s |
| `ALIEN_MODE` | `universe` | Une seule valeur dans `.env` — éviter les lignes en double |

Le compose de prod `alien-monitor/docker-compose.prod.yml` utilise **`network_mode: host`**, donc `127.0.0.1:9081` est correct.

---

## Pourquoi les clusters disparaissent

1. **Timeout API (le plus fréquent)** — le Monitor utilisait un timeout de 8 s ; `/api/products` de Factory est souvent plus lent → catalogue vide → tous les clusters supprimés. **Corrigé :** un échec de récupération renvoie `None` → **conservation des clusters existants** ; timeout par défaut 25–30 s.
2. **Passage en mode TEST** — pas de synchronisation du catalogue.
3. **Catalogue vide légitime** — une QA stricte masque tous les produits du storefront (`200` + `[]`). Suppression des clusters voulue.

---

## Vérification

```bash
curl -s --max-time 45 http://127.0.0.1:9081/api/products | jq '.products | length'
curl -s http://127.0.0.1:9100/api/state | jq '[.nodes[] | select(.group=="cluster")] | length'
docker logs alien-monitor 2>&1 | grep -i 'factory catalog' | tail -5
```

Note attendue au bootstrap : `factory catalog: +N products`.

---

## Voir aussi

- [alien-monitor/README.md](https://github.com/alexar76/alien-monitor/blob/main/README.md) — déploiement
- [uni-troubleshooting.md](./uni-troubleshooting.md) §16 — dépannage étendu
- [funnel-growth.fr.md](./funnel-growth.fr.md) — lead public → pipeline (côté Factory)
