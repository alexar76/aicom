# Capabilities KOVA dans Attested

## Ce qu’est KOVA

KOVA est un service Base et USDC indépendant, non installé dans Attested Hub. Il
publie six produits sur le Hub, où les agents les découvrent, tarifent et invoquent.

## Appel par un agent

L’agent appelle le Hub via `POST /ai-market/v2/invoke`, jamais l’URL privée de KOVA.
Le Hub applique accès et settlement, enregistre l’invoke puis route la requête.

Les capabilities sont `kova.network.status@v1`, `kova.asset.balance@v1`,
`kova.usdc.invoice.create@v1`, `kova.usdc.invoice.status@v1`,
`kova.usdc.invoice.cancel@v1` et `kova.usdc.webhook.register@v1`.

## Pourquoi le checkout suit une autre voie

L’abonnement Attested appelle l’API invoice KOVA par une connexion service-to-service
authentifiée. Il n’achète pas une capability payante pour vérifier son propre paiement.
Cela évite la facturation récursive et lie une commande à un entitlement.

## Qui paie KOVA

Un abonnement Attested envoie l'USDC de l'acheteur directement à
`SAAS_PAYMENT_RECIPIENT`. Ce transfert ne contient aucun partage ni pourcentage
automatique pour KOVA. Le Gateway utilise une `KOVA_API_KEY` dédiée ; si elle vient
d'un plan KOVA Pro ou Business payant, l'opérateur l'achète ou la renouvelle
séparément. Les appels fédérés de capabilities constituent un troisième flux mesuré :
leur prix par appel et la routing fee du Hub sont enregistrés comme consommation et
ne sont jamais prélevés sur le paiement d'un abonnement Attested.

## Ce qui est visible

Le Hub conserve prix, statut et receipt de l’invoke fédéré. L’Operator ledger protégé
affiche commandes, clés trial/paid et requêtes Attested. Le Settlement desk KOVA affiche
ses commandes, préfixes et usage API. Aucune clé complète n’y apparaît.

## Frontière de sécurité

La route exige `X-AIMarket-Internal-Token`, compare route et body et limite davantage
les écritures. `X-Provider-Signature` lie par Ed25519 `product_id`, `capability_id`,
hash de l’input et résultat, empêchant un replay sur un autre input.

## Configuration sûre

Utiliser un `KOVA_CAPABILITY_TOKEN` aléatoire de 32+ caractères identique au
`AIMARKET_CAPABILITY_TOKEN` du Hub. Définir `KOVA_HUB_URL` et `KOVA_INVOKE_BASE`,
et garder les endpoints provider sur le réseau privé.
