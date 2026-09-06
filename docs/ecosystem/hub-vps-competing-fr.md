# Competing Hub VPS — galaxie du lab fédéré
#
# Langues: [EN](hub-vps-competing.md) · [RU](hub-vps-competing-ru.md) · [ES](hub-vps-competing-es.md) · [FR](hub-vps-competing-fr.md) · [ZH](hub-vps-competing-zh.md)
#
# Hôte: `hunt.modelmarket.dev` · DNS: `hunt.modelmarket.dev` / `hub.modelmarket.dev` / `use.modelmarket.dev`

Runbook du **second Hub** découvert par la fédération primaire (`https://modelmarket.dev`),
plus Signal Hunt et le portail use-cases sur la même machine. Ce n’est **pas**
`./start.sh --everything` (≥16 Go RAM; cet hôte a ~8 Go + swap).

## Critère « prêt »

| Surface | URL | Rôle |
|---------|-----|------|
| Competing Lab Hub | `http://hunt.modelmarket.dev:9083` | Pair UNI-only du primary |
| Signal Hunt | `https://hunt.modelmarket.dev` | Jeu + Hub derrière nginx |
| Use-cases | `use.modelmarket.dev` | Portail statique |
| Alien Monitor | primary | Seconde **galaxie** loin de l’origine |

Le **câblage du mesh** sur cette machine n’est pas automatique — lancer les scripts
pour que chaque Hub connu voie les autres. Après un knock, l’admission produit est
un autre chemin : le sandbox admet un `pass` tout seul (voir
[`join-the-federation.fr.md`](../join-the-federation.fr.md)). Les scripts font encore
un `approve` explicite pour qu’un pair de lab soit trusted même sans SKU sandbox gratuit.

## Scripts

| Script | Rôle |
|--------|------|
| [`scripts/register_hub_upstream.sh`](../../scripts/register_hub_upstream.sh) | Un pair: announce → approve → crawl |
| [`scripts/register_federation_mesh.sh`](../../scripts/register_federation_mesh.sh) | Mesh complet primary ↔ lab ↔ hunt |
| [`signal-hunt/scripts/register-upstream.sh`](https://github.com/alexar76/signal-hunt/blob/main/scripts/register-upstream.sh) | Idem + assert des tools Signal Hunt |
| [`scripts/announce-platon-oracles.sh`](../../scripts/announce-platon-oracles.sh) | Platon sur un Hub local |
| [`scripts/verify_federation_urls.py`](../../scripts/verify_federation_urls.py) | Contrôle URL / well-known |

Les tokens restent dans l’env du process uniquement.

## Fédération

```bash
UPSTREAM_ADMIN_TOKEN='…' ./scripts/register_hub_upstream.sh \
  http://hunt.modelmarket.dev:9083 https://modelmarket.dev
UPSTREAM_ADMIN_TOKEN='…' ./signal-hunt/scripts/register-upstream.sh \
  https://hunt.modelmarket.dev https://modelmarket.dev

PRIMARY_ADMIN_TOKEN='…' LAB_ADMIN_TOKEN='…' HUNT_ADMIN_TOKEN='…' \
  ./scripts/register_federation_mesh.sh
```

Étapes: `announce` → `peers/approve` → `crawl`.  
De nouvelles capabilities n’apparaissent que si le lab publie **les siennes** (ex. `signal.*@v1`).

## Alien Monitor

```bash
ALIEN_COMPETING_HUB_URL=http://hunt.modelmarket.dev:9083
ALIEN_SIGNAL_HUNT_URL=https://hunt.modelmarket.dev
ALIEN_USE_CASES_URL=https://use.modelmarket.dev
```

Ancre: `COMPETING_GALAXY_ANCHOR ≈ (30, 12, −20)`. Nœuds: `competing_hub`, `signal_hunt`, `use_cases`.

Runbook EN complet: [hub-vps-competing.md](hub-vps-competing.md).
