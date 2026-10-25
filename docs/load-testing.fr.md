# Tests de charge : résultats du 2026-10-23, avant et après

**Langues :** [English](load-testing.md) · [Русский](load-testing.ru.md) · [Español](load-testing.es.md) · Français · [中文](load-testing.zh.md)

Ce que fait la flotte publique sous charge, ce que fait le chemin de l'argent en concurrence, ce qui
était lent et pourquoi, et ce qui a changé. Tous les chiffres ont été mesurés le 2026-10-23 ; les
commandes pour les refaire sont à la fin.

## Ce qui a tourné

| Test | Outil | Cible | Charge |
|---|---|---|---|
| Smoke public | Locust 2.46.5, `scripts/load/run_load_smoke.sh` | flotte en production (lecture seule) | 8 utilisateurs, 90 s |
| Constant public | idem | flotte en production (lecture seule) | 20 utilisateurs, 10 min |
| Chemin de l'argent | `aimarket-hub/scripts/load_money_path.py` | hub local, SQLite et PostgreSQL | 2 300 requêtes, 64 à la fois |
| Soak de l'usine (KI-3) | `scripts/load_test_factory.sh` | backend local de l'usine, 4 workers uvicorn | 10 fils, 15 min |

Le mélange public ne fait que lire : santé de l'usine, catalogue et bandeau de confiance, vitrine,
recherche, statistiques et discovery du hub, mesh, ARGUS, monitor et pulse. Il n'ouvre jamais
d'appel payant ; le chemin de l'argent est testé sur un hub local.

## Flotte publique, 20 utilisateurs pendant 10 minutes

| | Avant | Après |
|---|---|---|
| Requêtes | 7 538 | 7 626 |
| Échecs | **0 (0,00 %)** | **0 (0,00 %)** |
| Médiane, toutes requêtes | 170 ms | 180 ms |
| p95, toutes requêtes | 530 ms | 610 ms |

| Requête | Avant : médiane / p95 | Après : médiane / p95 | Changement |
|---|---|---|---|
| Usine `GET /api/products` (vitrine) | 7,3 s / 12 s | **0,22 s / 2,0 s** | médiane 33× plus rapide |
| Usine `GET /api/marketing/trust-metrics` | 4,7 s / 7,8 s | **0,18 s / 0,75 s** | médiane 26× plus rapide |
| Usine `GET /api/health` | 0,18 s / 3,8 s | **0,17 s / 0,43 s** | p95 9× plus bas |
| Vitrine `/` | 0,35 s / 0,38 s | 0,36 s / 0,60 s | — |
| Recherche du hub | 0,34 s / 0,56 s | 0,33 s / 0,65 s | — |
| Statistiques du hub | 0,17 s / 0,36 s | 0,18 s / 0,45 s | — |
| Hub well-known | 0,33 s / 0,49 s | 0,34 s / 0,67 s | — |
| Prix du capital du hub | 0,19 s / 0,39 s | 0,19 s / 0,46 s | — |
| Mesh, ARGUS, Pulse | 0,16–0,17 s / ≤ 0,18 s | 0,17 s / 0,24–0,40 s | — |
| Monitor `/api/health` | 0,16 s / 4,3 s | 0,17 s / 1,8 s | **déployé le 2026-10-23** (ci-dessous) |
| État du Monitor | 0,17 s / 3,0 s | 0,19 s / 2,4 s, max 62 s | **déployé le 2026-10-23** (ci-dessous) |

« Avant » a tourné juste après la mise en production des corrections de l'audit, « après » après les
optimisations ci-dessous. Les lignes marquées « — » n'ont pas changé ; l'écart vient du réseau du
portable entre les deux passages.

### Le smoke à 8 utilisateurs

| | Avant | Après |
|---|---|---|
| Requêtes / échecs | 477 / 0 | 477 / 0 |
| Réponse moyenne | 306 ms | 253 ms |
| Vitrine de l'usine, médiane | 5,1 s | 0,19 s |
| Bandeau de confiance, médiane | 4,6 s | 0,18 s |
| Requête la plus lente | 5,1 s | 2,4 s (monitor) |

### Le serveur pendant le passage à 20 utilisateurs

| | Avant | Après |
|---|---|---|
| CPU du worker du pipeline (file vide) | ~89 % d'un cœur | **16 %** |
| CPU de l'API de l'usine | 85–196 % | — |
| CPU / mémoire du hub | 0–55 % / 0,1 Go | — |
| Load average (factory-vps) | 2,1–3,6 | — |
| Redémarrages, blocages du limiteur, traces de l'usine | 0 / 0 / 0 | 0 / 0 / 0 |

### Le Monitor avant et après son déploiement

Déployé sur monitor.modelmarket.dev à 09:21 UTC (image `alien-monitor:overlaythread-20261023-alien-monitor-live` :
l'image en service plus le nouveau `main.py`). La même sonde avant et après : 20 clients, chacun environ un
`GET /api/health` par seconde pendant 90 secondes, depuis le même portable. La médiane est surtout une nouvelle
connexion TLS par requête.

| | Avant | Après |
|---|---|---|
| Requêtes / échecs | 960 / 0 | 1 060 / 0 |
| Médiane | 685 ms | 666 ms |
| p95 | 1 844 ms | **1 147 ms** |
| p99 | 4 185 ms | **1 272 ms** |
| La plus lente | 4 330 ms | **1 369 ms** |

## Chemin de l'argent sur un hub local

Des appels payants depuis de nombreux comptes, chaque appel payant répété trois fois en même temps
sous un même `Idempotency-Key`, et des inscriptions en course pour un budget de crédits offerts de
0,25 $ ; puis un audit du grand livre.

| Base | Requêtes | Simultanées | Débit | p95 | Grand livre après le passage |
|---|---|---|---|---|---|
| SQLite | 2 300 | 64 | 80 req/s | 2,3 s | tous les invariants tiennent ; 100 groupes à clé débités une fois chacun ; les crédits offerts s'arrêtent à 0,25 $ |
| PostgreSQL 18 | 2 299 | 64 | 41 req/s | 4,3 s | idem ; une connexion coupée, non débitée d'après l'audit |

Les invariants : le montant réservé d'un compte égale la somme de ses réservations actives (et vaut
zéro à la fin), aucun argent n'est créé ni perdu, chaque groupe à clé est débité exactement une fois.

## Backend de l'usine avec 4 workers (KI-3)

| | Avant le correctif | Après le correctif |
|---|---|---|
| Requêtes en 15 min | 25 577 | 33 710 |
| `/api/health` refusé par le propre limiteur de l'application | **13 779 sur 17 907** | **0 sur 23 542** |
| Échecs (pas de réponse ou 5xx) | 0 | 0 |
| Redémarrages de workers | 0 | 0 |
| Mémoire des 4 workers | — | 480 → 435 Mo, stable |

Le superviseur tue le backend après cinq sondes de santé ratées d'affilée. Le limiteur comptait la
sonde et la refusait sous charge : un backend occupé était tué parce qu'il était occupé.

## Ce qui était lent, et ce qui a changé

| Où | Cause, mesurée | Changement |
|---|---|---|
| Worker du pipeline | 92 % de son CPU dans `yaml.safe_load` : la configuration était relue pour chaque produit à chaque cycle (py-spy, processus en production) | l'analyse est réutilisée tant qu'aucun fichier de configuration ne change (mtime, taille, inode) |
| Vitrine `/api/products` | 57 évaluations de démo pour 19 produits, chacune parcourant l'arbre du produit, `node_modules` compris : 5,1 s sur 5,4 s | le parcours élague les arbres tiers ; une évaluation par produit et par requête ; la vitrine construite sert 30 s et se reconstruit dès que le pipeline écrit |
| Bandeau de confiance | 4 s à charger les 3 510 tâches que l'usine a exécutées, pour compter des états de produits | lecture des seuls produits (0,4 ms) ; cache d'une minute ; construit hors de la boucle d'événements |
| `/api/health` de l'usine | boucle d'événements bloquée derrière le bandeau | le travail est passé dans un fil |
| Superviseur KI-3 | le limiteur par adresse comptait et refusait la sonde | sonde non comptée ; 403/429 lu comme vivant |
| Monitor | 17 interrogations de satellites avec des clients HTTP bloquants dans la boucle d'événements | un fil de travail ; **déployé le 2026-10-23** |
| Journaux du hub | 311 traces par jour venant des grands livres ACEX, éteints par configuration | un avertissement par grand livre ; mêmes réponses 503 |
| Director | une réponse vide du modèle jetait tout un cycle de découverte | un enrichissement qui échoue reste vide |

## Le refaire

```bash
LOAD_TARGET=public LOAD_MODE=smoke ./scripts/load/run_load_smoke.sh
LOAD_TARGET=public LOAD_MODE=constant ./scripts/load/run_load_smoke.sh
python aimarket-hub/scripts/load_money_path.py --invokes 2000 --concurrency 64
python aimarket-hub/scripts/load_money_path.py --invokes 2000 --concurrency 64 --database-url postgresql:///scratch_db
./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 900 --concurrency 10
```

Le passage PostgreSQL efface le schéma de la base qu'on lui donne. Méthode, modes et critères :
[`scripts/load/METHODOLOGY.md`](../scripts/load/METHODOLOGY.md). Passages précédents :
[`scripts/load/RESULTS-2026-09-14.md`](../scripts/load/RESULTS-2026-09-14.md).
