# Guide de l'utilisateur AI-Factory (détaillé)

> **Public visé :** opérateurs, responsables produit et support utilisant la **vitrine** et le **panneau d'administration**.  
> **Langues :** [English](./USER_GUIDE.md) · [Русский](./USER_GUIDE.ru.md) · [Español](./USER_GUIDE.es.md) · **Français** · [中文](./USER_GUIDE.zh.md) · **FAQ :** [FAQ.md](./FAQ.md) · [FAQ.ru.md](./FAQ.ru.md) · [FAQ.es.md](./FAQ.es.md)

> **Les captures d'écran** se trouvent dans [`docs/assets/screenshots/`](./assets/screenshots/). Si des PNG manquent dans votre clone, démarrez la stack et exécutez :
>
> ```bash
> cd web/frontend
> DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='votre-mot-de-passe' npm run capture-docs-screenshots
> ```

---

## Table des matières

1. [Ce que vous avez sous les yeux](#ce-que-vous-avez-sous-les-yeux)
2. [Où regarder — aide-mémoire par situation](#où-regarder--aide-mémoire-par-situation)
3. [Cinq idées avant de cliquer où que ce soit](#cinq-idées-avant-de-cliquer-où-que-ce-soit)
4. [Vos 15 premières minutes](#vos-15-premières-minutes)
5. [Vitrine publique (sans connexion)](#vitrine-publique-sans-connexion)
6. [Documentation publique `/docs`](#documentation-publique-docs)
7. [Connexion admin et sécurité](#connexion-admin-et-sécurité)
8. [Carte de navigation de l'admin](#carte-de-navigation-de-ladmin)
9. [Dashboard](#dashboard)
10. [Live Monitor](#live-monitor)
11. [New Product — assistant et modèles](#new-product--assistant-et-modèles)
12. [Pipeline Monitor — source de vérité](#pipeline-monitor--source-de-vérité)
13. [Workshop](#workshop)
14. [Discovery](#discovery)
15. [LLM Providers & LLM Logs](#llm-providers--llm-logs)
16. [Settings](#settings)
17. [Guides par scénario](#guides-par-scénario)
18. [Erreurs actionnables dans l'UI](#erreurs-actionnables-dans-lui)
19. [Index des captures d'écran](#index-des-captures-décran)
20. [Manuels connexes](#manuels-connexes)

---

## Ce que vous avez sous les yeux

**AI-Factory** accepte une **idée en langage courant** et exécute un **pipeline multi-agents fixe** avec des contrôles qualité, en enregistrant les artefacts sous `/app/data` (spécification, architecture, code, marketing).

| Surface | URL | Rôle |
|---------|-----|------|
| Vitrine | `/` | Acheteurs, démos |
| Page produit | `/product/{id}` | Statut public d'une exécution |
| Admin | `/admin` | Opérateurs |
| Docs dans l'app | `/docs` | Mêmes guides, images intégrées |

---

## Où regarder — aide-mémoire par situation

| Situation | Où aller d'abord | Quoi inspecter | Capture |
|-----------|------------------|----------------|---------|
| Le site ne se charge pas | État de l'hôte, `docker compose ps`, `:9081/api/health` | Conteneur `app` sain | — |
| Impossible de se connecter | `/admin/login`, [security.md](./security.md) | Mot de passe bootstrap, pas `admin123` | ![Login](./assets/screenshots/admin-login.png) |
| Produit créé — où est-il ? | **Pipeline** | Cherchez `prod-…`, triez *shipped first* | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| Pipeline affiche « try N of 8 » | **Pipeline** (patientez ; jusqu'à 5 min par tentative) | *Connection phase* = nouvelles tentatives HTTP ; puis *X / total* | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| Produit bloqué sur une étape | **Pipeline** → cliquez sur la tuile d'étape | Tâche `running` / `failed`, erreurs | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| Erreurs LLM / modèle | **LLM Providers** → **LLM Logs** | Clés, routage, délais | ![Providers](./assets/screenshots/admin-providers.png) |
| COMPLETED mais absent de la vitrine | Carte **Pipeline** | `storefront_gate_reasons` | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| Landing rapide uniquement | **New product** → landing-only | `marketing_landing` | ![New product](./assets/screenshots/admin-new-product.png) |
| Comparer deux spécifications | Diff **Workshop** | Deux ids de produit | ![Workshop](./assets/screenshots/admin-workshop.png) |
| Idées autonomes | **Discovery** | File classée, auto-enqueue dans Settings | ![Discovery](./assets/screenshots/admin-discovery.png) |
| Aperçu rapide de l'état | **Dashboard** | KPI, nombre de tâches | ![Dashboard](./assets/screenshots/admin-dashboard.png) |
| Configuration initiale / URL publique | **Setup wizard** | Checklist de l'instance | ![Setup](./assets/screenshots/admin-setup.png) |
| Métriques en direct / vidéo de démo | **Live Monitor** | SSE, demo replay | ![Live Monitor](./assets/screenshots/admin-live-monitor.png) |
| Session expirée | **/admin/login** | 401 | ![Login](./assets/screenshots/admin-login.png) |
| Permission refusée | [admin-panel-rbac.md](./admin-panel-rbac.md) | Votre rôle | — |

Plus de questions-réponses : **[FAQ.md](./FAQ.md)** · **[FAQ.ru.md](./FAQ.ru.md)**

---

## Cinq idées avant de cliquer où que ce soit

1. **Product** = une ligne du pipeline (`prod-xxxxxxxx`).
2. **State** = étape du pipeline — différent de la visibilité en vitrine.
3. **Delivery profile** = `full_software` | `marketing_landing` | `infer`.
4. **Sandbox** = aperçu sous `/api/sandbox/…`.
5. **LLM Providers** doit fonctionner, sinon les agents échouent — l'UI vous y renvoie depuis les cartes d'erreur.

---

## Vos 15 premières minutes

1. Ouvrez `/` et `/docs`.
2. Connectez-vous sur `/admin/login` (voir [security.md](./security.md) pour le mot de passe).
3. Fermez la carte bleue **Get oriented** après l'avoir lue.
4. **New product** → modèle ou idée personnalisée → envoyez.
5. **Pipeline** → trouvez votre id → observez la bande d'étapes.

---

## Vitrine publique (sans connexion)

**Cas — un invité soumet une idée**

1. Formulaire hero sur `/` (si activé).
2. Reçoit `prod-…` et `/product/{id}`.
3. L'opérateur retrouve le même id dans **Pipeline**.

![Storefront home](./assets/screenshots/public-home.png)

**Cas — un acheteur parcourt le catalogue**

Seuls apparaissent les produits qui passent les **marketplace gates** (leur nombre peut être inférieur à **Completed** du Dashboard).

Le bloc **Products** de la page d'accueil comporte deux grilles :

| Section | Ce qui apparaît |
|---------|-----------------|
| **Marketing landing pages** | `delivery_profile = marketing_landing` |
| **Full products** | `full_software` et autres profils non-landing |

**Chargement du catalogue :** le navigateur affiche d'abord depuis **`localStorage`** (`aicom_storefront_catalog_v1_all` ou `_<category>`), puis se rafraîchit depuis l'API en arrière-plan (*« Showing cached catalog — updating… »*). Ce **n'est pas** le même cache que celui du Pipeline Monitor de l'admin (`aicom_pipeline_catalog_v2_*`).

---

## Documentation publique `/docs`

Partagez `/docs` avec les parties prenantes — il inclut le guide de démarrage rapide et le même jeu de captures que ce fichier.

![Public docs](./assets/screenshots/public-docs.png)

---

## Connexion admin et sécurité

1. URL : **`/admin/login`**, utilisateur **`admin`**.
2. **Il n'y a pas de `admin123` par défaut.** À la première installation :
   - interactif : `docker compose run -it app` — le mot de passe est demandé dans la console ;
   - sans interface (headless) : le fichier **`data/secrets/bootstrap_admin.txt`** (lisez-le une fois, puis supprimez-le ou changez-le).
3. En production, utilisez uniquement **HTTPS** et changez le mot de passe dès le premier jour.
4. Le JWT réside dans `localStorage` — ne laissez jamais une session ouverte sur une machine partagée.
5. Activez la **2FA** lorsque c'est disponible.

![Admin login](./assets/screenshots/admin-login.png)

---

## Carte de navigation de l'admin

Le menu de gauche est une SPA unique sur `/admin` ; les onglets changent via `?tab=…`.

![Sidebar](./assets/screenshots/admin-sidebar.png)

| Onglet | Usage opérateur |
|--------|-----------------|
| **Dashboard** | KPI instantanés à l'ouverture |
| **Setup wizard** | Configuration initiale de l'URL et du LLM |
| **Live Monitor** | Métriques en streaming, Director, vidéo de démo |
| **Pipeline** | Tous les `prod-…`, étapes, vitrine, erreurs |
| **New product** | Mettre en file un nouveau travail |
| **Workshop** | Diffs spec/arch, canvas, patterns |
| **LLM Providers** | Clés de modèles et routage |
| **LLM Logs** | Débogage des échecs d'appels LLM |
| **Discovery** | Signaux externes → idées |
| **Settings** | Autopilot, CORS, demo replay, Railway … |
| **Corporate Chat / Brainstorming** | Discussions, hors pipeline | ![Chat](./assets/screenshots/admin-corporate-chat.png) · ![Brainstorming](./assets/screenshots/admin-brainstorming.png) |

Référence complète des onglets : [admin-guide.md](./admin-guide.md).

---

## Dashboard

**Quand :** vérification rapide du matin, après un déploiement.

| Bloc | Signification |
|------|---------------|
| Total / Active / Completed / Failed | Ampleur de la file |
| Pending / Running tasks | Backlog des workers |
| CPU / Memory / Disk | Ressources de l'hôte |
| Revenue | Si le commerce est activé |

**Note :** **Completed** du Dashboard ≠ nombre d'articles listés en vitrine.

![Dashboard](./assets/screenshots/admin-dashboard.png)

---

## Live Monitor

**Quand :** démos, Director autonome, escalades en direct.

![Live Monitor](./assets/screenshots/admin-live-monitor.png)

- Indicateur **Connected** (SSE).
- **Demo replay** — une vidéo intégrée d'une exécution du pipeline (configurée dans Settings).
- Les escalades et le flux des agents.

Détails : [pipeline-operations.md](./pipeline-operations.md) (section demo replay du Live Monitor).

### Setup wizard (première visite)

![Setup wizard](./assets/screenshots/admin-setup.png)

L'onglet **Setup wizard** couvre l'URL publique, la clé LLM et les vérifications requises avant le mode autonome. Voir aussi la carte bleue d'accueil sur le Dashboard.

---

## New Product — assistant et modèles

Chemin : `/admin?tab=new-product`

![New product](./assets/screenshots/admin-new-product.png)

### Cas : SaaS avec un dashboard (full_software)

| Étape | Action |
|-------|--------|
| Idée | « SaaS pour les standups d'équipes distantes avec auth et API » |
| Options | **Full product** ; langue des textes **Auto** ou **English** |
| Vérification | **Start building** → notez l'id `prod-…` |

### Cas : landing seule (rapide)

| Étape | Action |
|-------|--------|
| Options | **Marketing landing page only** |
| Vérification | Attendez-vous à moins d'étapes et un `COMPLETED` plus rapide |

### Cas : enregistrer un préréglage pour l'équipe

- **Save current to cloud** — le modèle est stocké sur le serveur (visible depuis un autre navigateur après connexion).
- Modèles locaux — conservés uniquement dans ce navigateur.

### Cas : préremplissage par IA

- Cochez la **case de consentement** — sans elle, le LLM n'est pas appelé.
- En cas d'échec — un panneau rouge **Actionable failure** avec **Retry** et des liens vers Providers.

---

## Pipeline Monitor — source de vérité

Chemin : `/admin?tab=pipeline`

![Pipeline](./assets/screenshots/admin-pipeline.png)

### Chargement du catalogue (important)

1. **Cold start** (pas d'instantané `localStorage` pour ce tri) : vous pouvez voir *Fetching first catalog page…* et *Server request N / M*.
2. Chaque **N** est une vraie **tentative HTTP** (jusqu'à 8 sur la première page). Les tentatives précédentes ont échoué ou expiré — le client réessaie avec un backoff.
3. **Délai par tentative :** jusqu'à **5 minutes** (`300_000` ms).
4. La barre de progression **Connection phase** ≈ index de tentative ; le **% du catalogue** apparaît dans l'en-tête sous la forme **X / total** une fois les lignes reçues.
5. **Cache :** après succès, un catalogue allégé est stocké dans **localStorage** (`aicom_pipeline_catalog_v2_*`) — la visite suivante s'affiche immédiatement, puis se rafraîchit en arrière-plan.

### Anatomie d'une carte

| UI | Rôle |
|----|------|
| Bande d'étapes (Anl, Pm, Dev, Qa…) | Statut de tâche par agent ; **cliquez** pour la fenêtre de tâche |
| **Spec** | Spécification du PM |
| **Dev handoff** | Transmission au développeur |
| Badges state / category | Filtrage et recherche |
| Storefront / follow-up | Étiquettes manuelles et gates de vitrine |

### Filtres à connaître

- **Sort: shipped first** — le travail terminé en haut.
- **Search** — id, titre, description, texte de suivi.

---

## Workshop

![Workshop](./assets/screenshots/admin-workshop.png)

Board, diff de matériaux (spec/arch), canvas d'itération, bibliothèque de patterns, labo Web Push — voir [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) pour le détail des scénarios.

---

## Discovery

![Discovery](./assets/screenshots/admin-discovery.png)

Idées externes classées, digest et état des sources. L'auto-enqueue ne s'exécute que lorsqu'il est explicitement activé dans **Settings** / env (`AIFACTORY_DISCOVERY_AUTO_ENQUEUE`) — voir [configuration.md](./configuration.md).

---

## LLM Providers & LLM Logs

![Providers](./assets/screenshots/admin-providers.png)

![LLM Logs](./assets/screenshots/admin-llm-logs.png)

Premier arrêt pour tout échec d'agent mentionnant des modèles, des tokens ou des délais.

| Symptôme | Action |
|----------|--------|
| Tous les agents échouent avec une erreur d'auth | Vérifiez la clé dans Providers |
| Un seul agent échoue | Règles de routage, id de modèle |
| Timeout / limite de débit | Logs + augmentez le délai dans le yaml du provider |
| Après avoir changé une clé | Enregistrez, puis **Retry** la tâche ou attendez le retraitement |

---

## Settings

![Settings](./assets/screenshots/admin-settings.png)

Mode autonome, demo replay, auto-publication, Railway, CORS — voir [configuration.md](./configuration.md).

---

## Guides par scénario

### 1 — Premier produit de bout en bout

Providers (clés) → New product → Pipeline pour observer les étapes → URL du sandbox → vérifiez les gates de vitrine si le listing compte.

### 2 — Catalogue Pipeline lent ou en cours de nouvelle tentative

Vérifiez `/api/health` → attendez la tentative en cours (jusqu'à 5 min) → onglet Network des DevTools sur `pipeline/products?light=1` → augmentez le délai du proxy en cas de 502 → voir [FAQ.md](./FAQ.md).

### 3 — Retirer de la vitrine sans supprimer

Pipeline → produit → contrôles de vitrine / marquez le suivi **not pursuing** (voir admin-guide) → vérifiez la vitrine publique dans une fenêtre de navigation privée.

### 4 — Démo investisseurs en cinq minutes

Préparez à l'avance une carte **Pipeline** verte + un sandbox ; activez le **demo replay** sur le Live Monitor ; les KPI du Dashboard.

### 5 — Produit ayant échoué au QA

Pipeline → tuile **Qa** en échec → erreur de tâche → rapport QA sous `data/bugs/{id}/` sur le serveur.

### 6 — L'audit de politique a rouvert d'anciens produits

Les produits peuvent afficher des états de réparation tout en restant listés — [pipeline-operations.md](./pipeline-operations.md).

---

## Erreurs actionnables dans l'UI

| Symptôme | Actions UI | À vérifier aussi |
|----------|------------|------------------|
| Réseau / timeout | Retry, Settings | Compose, proxy |
| 401 | Reconnectez-vous | Expiration du JWT |
| 403 | — | RBAC |
| Erreurs LLM | Providers, LLM Logs | Clés |
| Catalogue partiel | Retry du catalogue | FAQ « try N of 8 » |
| Préremplissage bloqué | Case de consentement | New product |

---

## Index des captures d'écran

| Fichier | Contenu |
|---------|---------|
| `public-home.png` | Vitrine `/` |
| `public-docs.png` | `/docs` |
| `admin-login.png` | Connexion |
| `admin-dashboard.png` | Dashboard |
| `admin-sidebar.png` | Barre latérale complète |
| `admin-setup.png` | Setup wizard |
| `admin-live-monitor.png` | Live Monitor |
| `admin-pipeline.png` | Pipeline Monitor |
| `admin-new-product.png` | Assistant New product |
| `admin-workshop.png` | Workshop |
| `admin-providers.png` | LLM Providers |
| `admin-llm-logs.png` | LLM Logs |
| `admin-discovery.png` | Discovery |
| `admin-settings.png` | Settings |
| `admin-corporate-chat.png` | Corporate Chat |
| `admin-brainstorming.png` | Brainstorming |

Rafraîchir : `cd web/frontend && npm run capture-docs-screenshots` — détails dans [assets/screenshots/README.md](./assets/screenshots/README.md).

---

## Manuels connexes

| Document | Quand |
|----------|-------|
| [FAQ.md](./FAQ.md) / [FAQ.ru.md](./FAQ.ru.md) / [FAQ.es.md](./FAQ.es.md) | Questions fréquentes |
| [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) | Guide en russe |
| [USER_GUIDE.es.md](./USER_GUIDE.es.md) | Guide en espagnol |
| [owner-guide.md](./owner-guide.md) | Propriétaire en production |
| [admin-guide.md](./admin-guide.md) | Chaque onglet admin |
| [admin-panel-rbac.md](./admin-panel-rbac.md) | Rôles |
| [pipeline-operations.md](./pipeline-operations.md) | Comportement des workers |
| [configuration.md](./configuration.md) | Variables d'environnement |

---

*AI-Factory v2.1 — guide utilisateur détaillé avec index situationnel et liens FAQ. Régénérez les captures après des changements majeurs de l'UI.*
