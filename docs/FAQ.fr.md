# FAQ — AI-Factory (détaillée)

> Guide illustré : [USER_GUIDE.fr.md](./USER_GUIDE.fr.md) · English: [FAQ.md](./FAQ.md) · Español: [FAQ.es.md](./FAQ.es.md) · Русский: [FAQ.ru.md](./FAQ.ru.md) · **Français** · 中文: [FAQ.zh.md](./FAQ.zh.md)

---

## Généralités

### Qu'est-ce qu'AI-Factory en une phrase ?

Un système qui prend une idée en texte brut, la fait passer par une **chaîne d'agents IA** (recherche → spécification → code → QA → …) et enregistre les artefacts sur disque, avec un panneau d'administration et une vitrine publique optionnelle.

### Quelle est la différence entre la vitrine et le panneau d'administration ?

| | Vitrine `/` | Admin `/admin` |
|---|------------|------------------|
| Connexion | Généralement pas requise | JWT, identifiant `admin` |
| Objectif | Montrer les produits finis, formulaires de leads | Gérer le pipeline |
| Source de vérité | Catalogue API filtré | **Pipeline** — liste complète `prod-…` |

### Où sont les « vraies » données produit ?

**Admin → Pipeline** — le catalogue complet avec les tâches et les erreurs. Le Dashboard n'est qu'un instantané au moment du chargement. Live Monitor est un flux de métriques.

### L'opérateur a-t-il besoin d'un clone git ?

Non. L'URL de l'instance déployée et le mot de passe admin suffisent. La documentation est aussi servie sur `/docs`.

---

## Accès et installation

### Quel est le mot de passe admin par défaut ?

**Il n'y a pas de mot de passe fixe.** Sur un premier `data/` vide, le mot de passe est affiché dans la console de l'entrypoint ou écrit dans `data/secrets/bootstrap_admin.txt`. Détails : [security.md](./security.md).

### Démo publique (magic-ai-factory.com) ?

**Sans mot de passe :** identifiant `admin`, cliquez sur **Enter admin demo** (le champ mot de passe est masqué). `AIFACTORY_DEMO_READONLY=1` bloque les opérations destructives dans le panneau d'administration. Voir [security.md § Public demo](./security.md#public-demo-mode-aifactory_demo_readonly1).

### Impossible de se connecter — que vérifier ?

1. L'identifiant est exactement **`admin`** (si vous n'avez pas créé d'autres utilisateurs).
2. Le fichier bootstrap / le mot de passe défini au premier `up`.
3. L'horloge du serveur (JWT).
4. HTTPS vs HTTP et le cookie `Secure`.
5. Ne pas confondre les ports : l'UI est souvent sur **9080**, l'API sur **9081** avec la configuration Compose par défaut.

### Que sont les rôles viewer / operator / admin / super_admin ?

Voir [admin-panel-rbac.md](./admin-panel-rbac.md). **Operator** peut exécuter le pipeline, mais ne peut pas toujours modifier Settings ni les fournisseurs.

---

## New product et file d'attente

### Combien de temps prend un cycle complet ?

De **quelques minutes** à **plusieurs heures** — cela dépend de `full_software`, de la charge LLM, du QA avec Playwright et du nombre de cycles de réparation. Un landing est généralement plus rapide.

### Produit en HUMAN_REVIEW_PENDING, sans tâches ?

Pour **`full_software`**, il y a un **gate manuel** après DevOps : vous devez faire **Approve** ou **Reject** sur la carte Pipeline (`HumanReviewGatePanel`). Les landings (`marketing_landing`) sautent cette étape. Voir [admin-guide.md](./admin-guide.md#post-devops-human-review) (EN).

### Quelle est la différence entre full_software et marketing_landing ?

| | full_software | marketing_landing |
|---|---------------|-------------------|
| Résultat | API, BD, nombreuses pages | Site statique/simple |
| Étapes | Chaîne complète | Chemin raccourci |
| Déploiement | Railway / compose | Vercel/Netlify statique |

### Où trouver l'id du produit après l'avoir créé ?

L'écran de succès de l'assistant, **Pipeline** (recherche par nom), ou l'URL `/product/{id}` s'il est déjà publié.

### Puis-je annuler un produit dans la file d'attente ?

Cela dépend de l'état et de la politique du worker. Voir admin-guide et l'API. Souvent il est plus simple de le laisser `FAILED` / sans le poursuivre que de le supprimer physiquement.

---

## Pipeline Monitor

### Pourquoi affiche-t-il « try 4 of 8 » / « Server request 4 / 8 » ?

C'est la **quatrième tentative de la même requête HTTP** vers `/api/admin/pipeline/products`. Les précédentes se sont terminées par une erreur, un timeout ou un 502. Le client réessaie **délibérément** avec backoff (voir `pipelineCatalogFetch.ts`). Cela ne signifie **pas** que « le navigateur n'atteint pas l'API ».

### Combien de temps doit durer une tentative ?

Jusqu'à **5 minutes** (`clientTimeoutMs` 300 000 ms) par tentative. Entre les tentatives, une pause allant jusqu'à ~8 s sur la première page.

### Pourquoi la barre de progression « ne bouge pas » ?

- Pendant la **Connection phase**, la barre affiche le **numéro de la tentative HTTP**, pas le % du catalogue.
- Une fois les lignes apparues, regardez l'en-tête : **X / total** et la barre verte — c'est la progression **réelle** de l'hydratation des pages.

### Où est le cache du catalogue ?

**Pipeline Monitor :** dans le **localStorage** — `aicom_pipeline_catalog_v2_{sort}` plus un aperçu de 2 lignes. Première visite / tri différent / stockage effacé → un démarrage « à froid » avec des tentatives.

**Vitrine publique (`/`) :** `aicom_storefront_catalog_v1_{category}` — d'abord le cache, puis un `GET /api/products` en arrière-plan. Voir [marketing.md](./marketing.md).

### Pourquoi « All Categories (0) » d'abord, puis des chiffres apparaissent ?

Les catégories sont comptées à partir des lignes **déjà chargées** ; tant que le catalogue s'hydrate encore, les compteurs peuvent être incomplets (le suffixe `+` sur les options).

### Produit COMPLETED mais pas sur la vitrine — pourquoi ?

Raisons typiques dans `storefront_gate_reasons` :

- pas de code sur disque ;
- n'a pas passé le **marketplace quality** ;
- masqué manuellement (**hidden from storefront**) ;
- l'état n'est pas encore dans la famille shipped.

Vérifiez la carte dans **Pipeline** et [pipeline-operations.md](./pipeline-operations.md).

### Comment trouver un produit « bloqué » ?

1. Pipeline → filtre état **running** / surveillez les étapes oranges.
2. Cliquez sur une étape → une tâche `running` depuis longtemps sans `ended_at`.
3. Live Monitor / LLM Logs.
4. Logs du worker : `data/logs/`.

### Que signifie « Updating from server… 2 / 10 » ?

2 lignes du catalogue sur 10 côté serveur ont été chargées ; le reste est récupéré en arrière-plan par blocs de 12.

---

## LLM et fournisseurs

### Les agents sont silencieux / tout est FAILED avec le LLM

1. **LLM Providers** — clés, enabled, model id.
2. **LLM Logs** — les dernières erreurs.
3. `data/config/model_providers.yaml` sur le volume (pas dans git).
4. Les limites de débit (rate limits) du fournisseur.

### Le conteneur a-t-il besoin d'un accès internet ?

Oui, pour les API cloud. Ollama sur l'hôte — l'overlay `docker-compose.host-gateway.yml`.

### Qu'est-ce qu'un modèle heavy / light ?

Le routage dans Providers : les tâches lourdes (architect) vs les légères. Voir admin-guide.

---

## Vitrine et acheteurs

### Pourquoi y a-t-il moins de produits sur la page d'accueil que de Completed dans le Dashboard ?

La vitrine applique des **filtres supplémentaires** (qualité, code, masquage). Le Dashboard compte chaque `COMPLETED` du pipeline.

### Support / Lumen — est-ce un agent du pipeline ?

**Non.** C'est un assistant pour les acheteurs de la place de marché, distinct du roster **AI Agents**.

---

## Discovery et Director

### Des idées sont apparues d'elles-mêmes — est-ce normal ?

Oui, si **autonomous pipeline** et **discovery auto-enqueue** sont activés. Sinon, les idées n'arrivent que manuellement ou via l'API Discovery.

### Comment désactiver la mise en file automatique des idées ?

`AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0`, `general.auto_pipeline: false` dans Settings — voir [configuration.md](./configuration.md).

---

## Sandbox et prévisualisation

### La sandbox ne s'ouvre pas dans l'iframe

1. `AIFACTORY_SANDBOX_PREVIEW_API`, compose preview.
2. Le socket Docker dans le conteneur app.
3. CSP / mixed content — HTTPS.
4. Les logs de la sandbox dans l'API.

### En quoi la sandbox diffère-t-elle de l'auto-publish ?

**Sandbox** est une prévisualisation sur la factory. **Auto-publish** est l'export statique vers Vercel/Netlify après DevOps.

---

## Données et sauvegardes

### Où vivent les produits ?

Le bind mount **`./data`** (ou `~/aicom-data`) — `data/code/`, `data/specs/`, `data/state/pipeline.db`, et les configs.

### Les données ont disparu après docker run

Une erreur fréquente : un **named volume** au lieu d'un bind mount. Voir le README — la section sur la migration depuis un named volume.

### Puis-je supprimer tous les produits de démo ?

`./scripts/run_factory_demo_reset.sh` ou `wipe_pipeline_products.py` — attention, c'est irréversible.

---

## Performance et CI

### L'API du catalogue est lente

Après optimisations, le mode light devrait répondre en **secondes** pour un petit `limit`. Si ce sont de nouveau des minutes — vérifiez la taille de `pipeline.db`, le timeout du proxy, et ne chargez pas `light=0` sans nécessité.

### GitHub Actions échoue sur les tests

Voir `.github/workflows/ci.yml` — jobs pytest + Playwright. En local : `pytest -q` dans le venv.

---

## Sécurité

### Puis-je montrer le git remote sur un stream ?

**Non**, si l'URL contient un token. Voir le README — Screen recordings & Git remotes.

### Où est stocké le JWT ?

Le `localStorage` du navigateur + un cookie httpOnly (voir security.md). Pas sur des machines publiques.

---

## Documentation et captures d'écran

### Comment mettre à jour les captures d'écran du guide ?

```bash
cd web/frontend
DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='…' npm run capture-docs-screenshots
```

Liste des fichiers : [assets/screenshots/README.md](./assets/screenshots/README.md).

### Les images en markdown sont cassées dans un git clone

Les PNG ne sont pas commités ou n'ont pas encore été capturés — exécutez le script ci-dessus sur une instance en cours d'exécution.

---

## Escalade

| Niveau | Doc |
|---------|----------|
| Opérateur UI | [USER_GUIDE.fr.md](./USER_GUIDE.fr.md), cette FAQ · RU: [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) · ES: [USER_GUIDE.es.md](./USER_GUIDE.es.md) |
| Propriétaire de l'instance | [owner-guide.md](./owner-guide.md) |
| DevOps / env | [configuration.md](./configuration.md), [production-domain.md](./production-domain.md) |
| Intégration API | [api-integration-guide.md](./api-integration-guide.md) |
| Vulnérabilités | [SECURITY.md](../SECURITY.md) |

---

*Complétez cette FAQ lorsque des questions reviennent régulièrement au support.*
