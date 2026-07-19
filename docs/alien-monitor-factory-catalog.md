# Alien Monitor — Factory product clusters

> **Русский:** [alien-monitor-factory-catalog.ru.md](./alien-monitor-factory-catalog.ru.md) · **Español:** [alien-monitor-factory-catalog.es.md](./alien-monitor-factory-catalog.es.md)

How real AI-Factory products appear as **orange star clusters** near the Factory node in UNI / LIVE modes.

---

## Should products show in UNI mode?

**Yes.** `ALIEN_MODE=universe` is not TEST simulation:

| Mode | Factory products on 3D map |
|------|----------------------------|
| **TEST** | No — only a simulated counter on Factory |
| **UNIVERSE (UNI)** | **Yes** — sync from `GET /api/products` |
| **LIVE (real)** | **Yes** — same catalog + production RPC |

UNI runs local Anvil **and** polls live Factory / Hub / Mesh / Prometheus. Catalog sync runs on bootstrap and every ~60 s (`ALIEN_FACTORY_SYNC_TICKS`, default 40 ticks).

Only **storefront-listed** products appear (same gate as the public shop), not every pipeline state.

---

## Configuration

| Variable | Default (prod) | Role |
|----------|----------------|------|
| `AICOM_API_URL` | `http://127.0.0.1:9081` | Factory API base (host network on prod) |
| `ALIEN_FACTORY_API_TIMEOUT` | `30` | HTTP timeout — `/api/products` can take 12–30 s |
| `ALIEN_MODE` | `universe` | One value in `.env` — avoid duplicate lines |

Prod compose: `alien-monitor/docker-compose.prod.yml` uses **`network_mode: host`**, so `127.0.0.1:9081` is correct.

---

## Why clusters disappear

1. **API timeout (most common)** — Monitor used 8 s timeout; Factory `/api/products` often slower → empty catalog → all clusters removed. **Fixed:** fetch failure returns `None` → **keep existing clusters**; default timeout 25–30 s.
2. **Mode switched to TEST** — no catalog sync.
3. **Legitimate empty catalog** — strict QA hides all products from storefront (`200` + `[]`). Clusters removed by design.

---

## Verify

```bash
curl -s --max-time 45 http://127.0.0.1:9081/api/products | jq '.products | length'
curl -s http://127.0.0.1:9100/api/state | jq '[.nodes[] | select(.group=="cluster")] | length'
docker logs alien-monitor 2>&1 | grep -i 'factory catalog' | tail -5
```

Expect bootstrap note: `factory catalog: +N products`.

---

## Related

- [alien-monitor/README.md](https://github.com/alexar76/alien-monitor/blob/main/README.md) — deploy
- [uni-troubleshooting.md](./uni-troubleshooting.md) §16 — extended troubleshooting
- [docs/funnel-growth.md](./funnel-growth.md) — public lead → pipeline (Factory side)
