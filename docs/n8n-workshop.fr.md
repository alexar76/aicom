# Vérifier un panier avec n8n et son propre hub

[English](n8n-workshop.md) · [Русский](n8n-workshop.ru.md) · [Español](n8n-workshop.es.md) · [Français](n8n-workshop.fr.md) · [中文](n8n-workshop.zh.md)

Atelier pratique en ligne de 60 minutes destiné aux intégrateurs n8n et aux propriétaires
de petites API. Construisons un service en lecture seule : **«Ce fournisseur peut-il préparer
mon panier et quel est le sous-total des produits ?»** L'opérateur garde le contrôle du
workflow et du catalogue. Aucun achat, portefeuille, LLM payant ou client externe n'est requis.

## Pourquoi ce scénario

Un assistant de boutique, de vente ou d'achat consulte les règles du fournisseur au même
endroit. n8n applique les règles ; Hub référence le service et vérifie les réponses signées.
n8n propose déjà un [MCP natif](https://n8n.io/mcp/), suffisant pour certains usages avec son
propre agent. Nous étudions ici un catalogue indépendant, les signatures du fournisseur et
une éventuelle connexion ultérieure à la fédération.

Le stock est **synthétique** : il illustre l'intégration, pas un stock réel, une demande
commerciale ou un déploiement en production. Hub est gratuit ; l'hébergement reste à la charge
de l'opérateur et n8n a sa propre licence. La fédération est un canal de distribution potentiel.

## Exemple et résultats

[Workflow à importer](../examples/n8n-order-check/workflow.json) ·
[Code et détails](../examples/n8n-order-check/README.md) ·
[Validation](../examples/n8n-order-check/VALIDATION.md)

```json
{"items":[{"sku":"BEANS-250","quantity":2},{"sku":"MUG-BLUE","quantity":1}]}
```

Résultat : `status: ready`, `can_fulfill: true`, `subtotal_minor: 3430`, `currency: USD`.
Soit 34,30 USD de produits. Taxes, livraison et total final valent `null` : non calculés.
La réponse contient `demo: true`, `reservation_created: false`, `order_created: false`.

| Requête | Résultat attendu |
|---|---|
| Deux BEANS-250 et une MUG-BLUE | Disponibles ; sous-total 3430 |
| Quatre MUG-BLUE | Stock insuffisant ; trois disponibles |
| SKU inconnu | Article inconnu ; sous-total indisponible |
| Deux lignes de deux MUG-BLUE | Regroupement en quatre ; stock insuffisant |
| Panier vide ou quantité négative/fractionnaire | Entrée refusée |
| Mauvais identifiant secret / n8n indisponible | Refus / erreur ; aucun devis inventé |

`evaluated_at` est l'heure d'exécution, pas la fraîcheur du stock. La signature authentifie
la déclaration et la lie à la requête ; elle ne prouve pas la présence des marchandises.

## Préparation avant la séance

Instance locale distincte, Python 3.11+, Node.js 24.14.0 et ports libres 15678/13456/19083.
Depuis la racine d'un clone de ce dépôt :

```bash
python3 -m venv examples/n8n-order-check/.venv
examples/n8n-order-check/.venv/bin/python -m pip install -e './aimarket-hub[pqc]'
cd examples/n8n-order-check
source .venv/bin/activate
npm install --prefix .runtime/npm n8n@2.43.7 --no-audit --no-fund
export PATH="$PWD/.runtime/npm/node_modules/.bin:$PATH"
python run.py init
python run.py n8n-import
```

L'installation précède les 60 minutes. Clés et secrets sont créés dans `.runtime/`, exclu de
Git ; ne partagez pas ce dossier. Le workflow utilise un identifiant Header Auth sans secret
intégré. Arrêtez l'instance n8n de l'atelier avant toute nouvelle importation.

Dans trois terminaux, ouvrez le dossier de l'exemple et activez `.venv`. Lancez respectivement
`python run.py n8n`, `python run.py adapter`, `python run.py hub`. Répétez l'export PATH dans
le terminal n8n. Éditeur : `http://127.0.0.1:15678` ; créez un compte propriétaire local si
demandé. L'import publie le workflow ; l'adaptateur utilise `/webhook/`. Ctrl+C arrête les
serveurs, les données locales restent disponibles.

## Déroulement sur 60 minutes

| Minutes | Activité |
|---|---|
| 0–5 | Opérateur, appelant, lecture seule et données synthétiques |
| 5–15 | Webhook → Code → Respond to Webhook ; appel authentifié |
| 15–25 | Schéma d'entrée, SKU répétés, stock et prix |
| 25–40 | Adaptateur et Hub ; invocation, résultat et signatures |
| 40–50 | Manquants, SKU inconnu, quantité et secret incorrects |
| 50–60 | Remplacer la source synthétique par une source autorisée ; questions |

Avant les tests, attendez que n8n indique que l’éditeur est disponible et l’indexation des workflows terminée.

```bash
curl --fail-with-body http://127.0.0.1:19083/ai-market/v2/invoke \
  -H 'Content-Type: application/json' --data-binary @request.json
python run.py check
node test_quote.cjs
```

Client MCP local : `http://127.0.0.1:19083/mcp`. Consigne :
«Trouve l'outil de vérification du panier de l'atelier. Vérifie deux BEANS-250 et une MUG-BLUE.
Indique le sous-total, les manquants et le caractère synthétique des données. Ne passe pas de commande.»
Un client uniquement cloud ne peut pas joindre le loopback du portable. Les tests HTTP/MCP
ne constituent pas une validation de toutes les applications d'agents.

## Premier opérateur réel

Obtenir un exemple de catalogue expurgé et une source autorisée. Remplacer la source de
démonstration par une lecture de la devise, des prix en unités monétaires mineures, du stock
disponible et de l'horodatage source ; fixer une durée de validité. Adapter ensemble le contrat
de réponse et les tests. Réservations et commandes restent des opérations distinctes.
Les prix privés exigent l'autorisation de l'appelant et l'isolation entre clients.

Pour un service public : clés et base persistantes, HTTPS et limitation des requêtes ;
n8n et adaptateur privés et authentifiés. Ne reprenez pas les réglages HTTP du laboratoire.
Suivre le [guide opérateur](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.fr.md), lancer
`aimarket doctor`, puis choisir de s'annoncer. Une réussite locale n'est pas une admission.

L'objectif : le propriétaire indépendant contrôle l'installation et ses clés, répète un appel
utile et sait arrêter le service. Suivre séparément l'exercice local, les données réelles,
l'admission et l'utilisation après sept jours. Une vente externe n'est pas nécessaire.
