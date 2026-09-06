# UNI et LIVE — deux royaumes

> **English:** [uni-and-live.md](./uni-and-live.md) · **Русский:** [uni-and-live.ru.md](./uni-and-live.ru.md) · **Español:** [uni-and-live.es.md](./uni-and-live.es.md) · **Français** · **中文:** [uni-and-live.zh.md](./uni-and-live.zh.md)

Deux processus, deux hubs, deux catalogues. Les mélanger, c’est lire des dollars de bulle
comme du chiffre d’affaires.

Cette page est **UNI contre LIVE**. TEST est une troisième couche sur le même processus du
moniteur, pas une troisième économie. Interrupteur on-chain : [crypto-switch.fr.md](./crypto-switch.fr.md).
Sceau UNI : [uni-realm.md](./uni-realm.md).

## En un coup d’œil

| | **LIVE** | **UNI** |
|---|---|---|
| Hub | [modelmarket.dev](https://modelmarket.dev) | [uni.modelmarket.dev](https://uni.modelmarket.dev) |
| Alien Monitor | [`monitor.modelmarket.dev`](https://monitor.modelmarket.dev/) · `:9101` · `ALIEN_MODE=real` | [monitor-uni.modelmarket.dev](https://monitor-uni.modelmarket.dev/) · `:9100` · `ALIEN_MODE=universe` |
| Argent | Base, quand le crypto est **ON** | Anvil privé, chain id `31337` — simulé |
| Catalogue | fédération live (Platon, ATLAS, GAIA, oracles, …) | six laboratoires de bulle ci-dessous |
| Ces six laboratoires | **pas** des pairs de la fédération LIVE | KHRONOS · STOICHEION · HORIZON · PSEPHOS · KYMA · DIKTYON |
| Déployer le hub | `./scripts/deploy_hub.sh` | `bash deploy/uni-hub.sh …` |
| Déployer les capacités | satellites live | `bash deploy/uni-satellites.sh` |
| Déployer le moniteur | `ALIEN_MODE=real ./scripts/deploy_alien_monitor.sh --live` | `./scripts/deploy_alien_monitor.sh` (universe) |

Un badge LIVE sur la carte univers n’est pas de l’argent réel. Les boutons **naviguent**
entre les cartes ; ils ne repeignent pas un seul processus.

## LIVE

Ce que vous déployez : l’économie réelle.

- Le **hub** répond sur `https://modelmarket.dev`. Zéro capacité locale ; le catalogue est
  fédéré depuis les satellites live.
- Le **moniteur** est un second conteneur (`alien-monitor-live`). Le CTA de la carte et le
  sondage des stats vont vers ce hub. Le bouton LIVE reste. Le bouton UNI va vers
  `/monitor/`.
- **Sphères :** satellites live et étrangers. Jamais les six laboratoires UNI comme pairs
  de catalogue.
- Le **crypto** est un interrupteur à part. LIVE avec crypto **OFF** parle toujours au hub
  live ; il n’allume pas les nœuds de chaîne. Voir [crypto-switch.fr.md](./crypto-switch.fr.md).

## UNI

Ce que vous déployez : une économie parallèle scellée. De l’intérieur les API ressemblent
à LIVE. Le nom est le sceau : un sous-domaine distinct, jamais un chemin sous l’hôte live.

- Le **hub** répond sur `https://uni.modelmarket.dev` (loopback `:9183` derrière nginx).
- Le **moniteur** est le processus univers par défaut. CTA et sondage :
  `ALIEN_UNI_HUB_URL` / `https://uni.modelmarket.dev` — **pas** le hub live. Le bouton UNI
  reste. Le bouton LIVE va vers `/monitor-live/`.
- Les **pairs du catalogue** sont six laboratoires réservés à la bulle : un processus
  (`uni/satellite.py`) × six catalogues, levés par `deploy/uni-satellites.sh`. Chemins sous
  le nom du hub UNI pour que le garde SSRF du crawler les accepte. Les clés dans
  `/var/lib/uni-satellites` doivent survivre : le hub épingle la clé d’un pair au premier
  contact.

| satellite | produit | caps | vend |
|---|---|---|---|
| KHRONOS Time Series | `khronos` | 20 | statistiques, lissage, décomposition, prévision |
| STOICHEION Data Hygiene | `stoicheion` | 17 | schémas, diffs, profils, texte, unités |
| HORIZON Geo & Telemetry | `horizon` | 17 | géodésie, requêtes spatiales, télémétrie |
| PSEPHOS Draws & Ballots | `psephos` | 13 | tirages avec commitment, probabilité discrète, bulletins |
| KYMA Signal Lab | `kyma` | 12 | spectres, filtres, ondes |
| DIKTYON Graph Metrics | `diktyon` | 12 | centralité, connectivité, ordre |

Chaque capacité est une fonction pure de son entrée, calculée avec la bibliothèque
standard. Seul l’argent est simulé. Détail : [uni/README.md](../uni/README.md).

**Pont d’observation.** Platon, ATLAS et les autres satellites live peuvent apparaître sur
la carte UNI comme superposition d’état de services **live**. Ce ne sont pas des pairs du
catalogue UNI. Les pairs du catalogue sont les six laboratoires.

## Ne pas mélanger

| Fuite | Ce qui se passe |
|---|---|
| Le moniteur UNI sonde le hub live | les deux cartes montrent les mêmes invokes / dollars |
| Le CTA de la carte UNI est `modelmarket.dev` | un opérateur dans la bulle reçoit une porte de sortie |
| Liste seed LIVE dans le hub UNI | la bulle publie des adresses réelles et peut router de l’argent réel |
| Peindre `mode=real` sur le processus UNI | les chiffres à l’écran restent ceux de la bulle |

Le sceau du hub (`aimarket_hub/realm.py`) refuse un seed live dans UNI et un seed privé
dans LIVE. Le moniteur (`session_tick_mode`) refuse de faire tic-tac les nombres de
l’autre royaume sur ce processus.

## Voir aussi

- [uni-realm.md](./uni-realm.md) — sceau de chaîne, Anvil, pourquoi la bulle tourne en production
- [crypto-switch.fr.md](./crypto-switch.fr.md) — économie on-chain on/off (ce n’est pas UNI)
- [alien-monitor-factory-catalog.fr.md](./alien-monitor-factory-catalog.fr.md) — grappes Factory sur les deux cartes
- [quickstart-ecosystem-deploy.fr.md](./quickstart-ecosystem-deploy.fr.md) — flotte live
