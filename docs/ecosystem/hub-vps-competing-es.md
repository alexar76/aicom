# Competing Hub VPS — galaxia del laboratorio federado
#
# Idiomas: [EN](hub-vps-competing.md) · [RU](hub-vps-competing-ru.md) · [ES](hub-vps-competing-es.md) · [FR](hub-vps-competing-fr.md) · [ZH](hub-vps-competing-zh.md)
#
# Host: `hunt.modelmarket.dev` · DNS: `hunt.modelmarket.dev` / `hub.modelmarket.dev` / `use.modelmarket.dev`

Runbook del **segundo Hub** que la federación primaria (`https://modelmarket.dev`) descubre,
más Signal Hunt y el portal use-cases en la misma máquina. No es `./start.sh --everything`
(requiere ≥16 GB RAM; este host tiene ~8 GB + swap).

## Criterio de listo

| Superficie | URL | Rol |
|------------|-----|-----|
| Competing Lab Hub | `http://hunt.modelmarket.dev:9083` | Peer UNI-only del primary |
| Signal Hunt | `https://hunt.modelmarket.dev` | Juego + Hub propio detrás de nginx |
| Use-cases | `use.modelmarket.dev` | Portal estático |
| Alien Monitor | primary | Segunda **galaxia** lejos del origin |

La federación **no** es automática: hay que ejecutar los scripts.

## Scripts

| Script | Propósito |
|--------|-----------|
| [`scripts/register_hub_upstream.sh`](../../scripts/register_hub_upstream.sh) | Un peer: announce → approve → crawl |
| [`scripts/register_federation_mesh.sh`](../../scripts/register_federation_mesh.sh) | Mesh completo primary ↔ lab ↔ hunt |
| [`signal-hunt/scripts/register-upstream.sh`](https://github.com/alexar76/signal-hunt/blob/main/scripts/register-upstream.sh) | Igual + aserta tools de Signal Hunt |
| [`scripts/announce-platon-oracles.sh`](../../scripts/announce-platon-oracles.sh) | Platon en un Hub local |
| [`scripts/verify_federation_urls.py`](../../scripts/verify_federation_urls.py) | Comprobación de URL / well-known |

Los tokens solo viven en el env del proceso.

## Federación

```bash
UPSTREAM_ADMIN_TOKEN='…' ./scripts/register_hub_upstream.sh \
  http://hunt.modelmarket.dev:9083 https://modelmarket.dev
UPSTREAM_ADMIN_TOKEN='…' ./signal-hunt/scripts/register-upstream.sh \
  https://hunt.modelmarket.dev https://modelmarket.dev

PRIMARY_ADMIN_TOKEN='…' LAB_ADMIN_TOKEN='…' HUNT_ADMIN_TOKEN='…' \
  ./scripts/register_federation_mesh.sh
```

Pasos: `announce` → `peers/approve` → `crawl`.  
Nuevas capabilities solo si el lab publica **las suyas** (p. ej. `signal.*@v1`).

## Alien Monitor

```bash
ALIEN_COMPETING_HUB_URL=http://hunt.modelmarket.dev:9083
ALIEN_SIGNAL_HUNT_URL=https://hunt.modelmarket.dev
ALIEN_USE_CASES_URL=https://use.modelmarket.dev
```

Ancla: `COMPETING_GALAXY_ANCHOR ≈ (30, 12, −20)`. Nodos: `competing_hub`, `signal_hunt`, `use_cases`.

Runbook EN completo: [hub-vps-competing.md](hub-vps-competing.md).
