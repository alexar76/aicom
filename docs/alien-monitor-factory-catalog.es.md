# Alien Monitor — clústeres de productos Factory

> **English:** [alien-monitor-factory-catalog.md](./alien-monitor-factory-catalog.md) · **Русский:** [alien-monitor-factory-catalog.ru.md](./alien-monitor-factory-catalog.ru.md)

Cómo los productos reales de AI-Factory aparecen como **clústeres estelares naranjas** cerca del nodo Factory en modos UNI / LIVE.

---

## ¿Deben verse productos en UNI?

**Sí.** `ALIEN_MODE=universe` no es simulación TEST:

| Modo | Productos en mapa 3D |
|------|------------------------|
| **TEST** | No — solo contador simulado en Factory |
| **UNIVERSE (UNI)** | **Sí** — sync desde `GET /api/products` |
| **LIVE (real)** | **Sí** — mismo catálogo + RPC prod |

UNI levanta Anvil local **y** consulta Factory / Hub / Mesh / Prometheus en vivo. Sync en bootstrap y cada ~60 s (`ALIEN_FACTORY_SYNC_TICKS`, default 40 ticks).

Solo productos **listados en storefront**, no todos los estados del pipeline.

---

## Configuración

| Variable | Default (prod) | Rol |
|----------|----------------|-----|
| `AICOM_API_URL` | `http://127.0.0.1:9081` | Base API Factory (host network) |
| `ALIEN_FACTORY_API_TIMEOUT` | `30` | Timeout HTTP — `/api/products` 12–30 s |
| `ALIEN_MODE` | `universe` | Un valor en `.env` — sin líneas duplicadas |

Prod: `alien-monitor/docker-compose.prod.yml`, **`network_mode: host`** → `127.0.0.1:9081` es correcto.

---

## Por qué desaparecen los clústeres

1. **Timeout API (frecuente)** — antes 8 s; Factory `/api/products` más lento → catálogo vacío → borrado de clústeres. **Corregido:** fallo → `None` → **se conservan clústeres**; timeout 25–30 s.
2. **Modo TEST** — sin sync de catálogo.
3. **Catálogo vacío legítimo** — QA estricto oculta todos los productos (`200` + `[]`). Borrado esperado.

---

## Verificar

```bash
curl -s --max-time 45 http://127.0.0.1:9081/api/products | jq '.products | length'
curl -s http://127.0.0.1:9100/api/state | jq '[.nodes[] | select(.group=="cluster")] | length'
docker logs alien-monitor 2>&1 | grep -i 'factory catalog' | tail -5
```

En bootstrap: `factory catalog: +N products`.

---

## Relacionado

- [alien-monitor/README.md](https://github.com/alexar76/alien-monitor/blob/main/README.md)
- [uni-troubleshooting.md](./uni-troubleshooting.md) §16
- [funnel-growth.es.md](./funnel-growth.es.md)
