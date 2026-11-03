# Codex : une opération client, deux sous-traitants payés

[English](case-study-codex-one-call.md) · [Русский](case-study-codex-one-call.ru.md) · [Español](case-study-codex-one-call.es.md) · [Français](case-study-codex-one-call.fr.md) · [中文](case-study-codex-one-call.zh.md)

Le **30 septembre 2026**, Codex a répété le test GAIA avec le nouveau `await run_pipeline(...)`, le même portefeuille fourni par l’opérateur et un **budget total de $1**. Le Hub exécutait `modelmarket-hub:prod-20260930-onecall`. Les deux enfants ont réussi, avec attente automatique des confirmations. Les services ont coûté **0.002 USDC**, pour une dépense totale mesurée avec gas de **≈ $0.00468270**.

## Procédure et requêtes observées

Le client a appelé `POST /studio/prepare-pipeline` avec graphe et portefeuille, vérifié graphe, conditions, soldes et marge réseau, signé localement, sauvegardé le lot en privé et invoqué `pipeline.run@v1`. Aucun identifiant administrateur ni clé privée n’a été envoyé au Hub. L’achat utilisait l’API REST publique depuis Python dans le terminal de Codex, pas MCP. L’appelant attendait une seule opération SDK, sans reprise manuelle.

| Ordre | Requête Hub | HTTP | État |
|---|---|---:|---|
| 1 | `POST /studio/prepare-pipeline` | 200 | `ready` |
| 2 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 3 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 4 | `POST /ai-market/v2/invoke` | 200 | `completed` |

Le test payant a effectué **quatre requêtes au Hub**, pas exactement deux. Les appels RPC et de cotation sont supplémentaires. La première réponse contenait devis et autorisations. Chaque 202 reprenait le même run avec le lot signé identique. Il y avait un job racine et deux enfants réussis. Ensuite, `run_pipeline(resume=True, ...)` a renvoyé le même résultat local avec **zéro requête Hub supplémentaire**. Le test et la vérification des preuves ont pris 11.872 secondes : une observation, pas une garantie de délai.

## Graphe et résultat

Le graphe a acheté `gaia.weather.read@v1`, puis `gaia.air.read@v1`, du produit `gaia.gateway`, avec `source_hub: https://iot.modelmarket.dev` et `city: Berlin`. `air` attendait la fin de `weather`, sans recevoir ses valeurs météo. Le résultat final était un relevé signé de **GAIA-AQ1 (relais Open-Meteo AQ)**, appareil `om-aq-01`, à **2026-09-30 04:24:34 UTC**. Le dossier atteste la réussite météo mais ne conserve pas son relevé intermédiaire. Ce sont des données du relais, pas une preuve de capteur physique distinct à Berlin.

| Indicateur | Valeur |
|---|---:|
| PM2.5 | 8.8 µg/m³ |
| PM10 | 11.1 µg/m³ |
| US AQI | 33 |
| European AQI | 24 |

## Budget et règlement

Le payeur était `0x6E94c380d908531f9822035d6cc4c8D2B0186C9c`, le destinataire USDC `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`. Le règlement utilisait l’USDC existant sur Base mainnet, chain ID 8453. L’acheteur a choisi un plafond ETH/USD de 6000 ; la dernière estimation conservatrice était $0.1195256567368, sous $1. La dépense en dollars utilise le cours Coinbase **$2673.555/ETH** observé pendant le test. Ni ce cours ni l’estimation ne constituent un plafond strict en dollars imposé sur chaîne.

| Dépense | Montant |
|---|---:|
| Services / USDC | 0.002 USDC |
| Gas (L2 + L1) | 0.000001003418744789 ETH |
| Gas / USD | ≈ $0.00268270 |
| Total / USD | ≈ $0.00468270 |

## Tests complémentaires et vérification

Un graphe LOGOS gratuit à deux étapes a réussi avec le même SDK sans portefeuille, RPC ou plafond de change, en deux requêtes Hub. Un graphe payant au budget total $0.003 a passé le devis des services mais a été refusé localement faute de marge réseau : une préparation, aucune invocation racine ni paiement. **84 tests locaux** et **4 tests de paiement Anvil** ont réussi. Ils couvrent perte de réponse, reprises identiques, reprise sans signataire après signature, budget gas insuffisant, mauvaise chaîne ou autorisation, verrouillage et échec terminal d’un enfant.

La CLI a également exécuté un graphe gratuit en production, puis renvoyé le même résultat enregistré lors de la reprise sans clé du portefeuille.

Les deux transactions ont réussi. Les montants USDC et frais correspondent aux variations de soldes. Les signatures racine et facture ont été vérifiées avec la clé du Hub enregistrée avant le test, ainsi que les hashes facture/résultat et deux références aux reçus enfants. La signature du relevé d’air a été contrôlée avec sa clé incluse, sans ancrage indépendant de l’identité du dispositif. Les preuves publiques contiennent résultats signés et reçus réseau, sans clé privée, jeton d’exécution ou transaction signée brute.

Cela reste un test autorisé par l’opérateur : GAIA et Hub appartiennent au même écosystème exploité, le Hub étant vendeur responsable de l’encaissement. Il démontre paiement et sous-traitance réels, pas demande indépendante. SUB/1 relie les travaux ; le financement est `buyer_wallet`, les enfants portent `funded_by: own`, sans allowance de crédit. Aucun contrat n’a été redéployé. Le test gratuit SDK ne certifie pas l’ancienne route `/studio/run`, configurée séparément.

## Preuves et reproduction

- [JSON](evidence/codex-one-call-2026-09-30.json) · [Blueprint](evidence/codex-one-call-2026-09-30-blueprint.json)
- [API / SDK](one-call-pipelines.fr.md)
- `run_id`: `paid_ce7dfb28ec21c0ffbc6f65884929aeec`
- `job_id`: `job_dd54651f9104c5c5ac31cc4e`
- `weather`: [0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e](https://basescan.org/tx/0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e)
- `air`: [0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1](https://basescan.org/tx/0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1)

---

Vérification complémentaire de l’accès des agents (3.9.0) : 175 tests ciblés et quatre tests de paiement locaux Anvil ont réussi. Une installation propre a exécuté un graphe gratuit via le SDK en deux requêtes Hub. MCP prepare/invoke/status a terminé un autre graphe gratuit. La commande payante originale a été récupérée par deux GET (manifeste et statut racine), sans clé de portefeuille ni RPC. Le SDK a vérifié les reçus du Hub. Aucun nouveau paiement mainnet n’a été effectué. Le wheel est distribué par le Hub, avec son SHA-256 dans le manifeste signé ; aucune publication PyPI n’a été effectuée.

[JSON](evidence/agent-rails-2026-09-30.json)

## Suite : vendeur indépendant, 3.10.1

Codex a ajouté SELLER-OP/1 et déployé Hub avec les migrations 44–45. Le guide détaille protocole et limites. **223 tests ciblés et 6 scénarios Anvil locaux** ont réussi, dont deux règlements entre hubs distincts avec un jeton jetable, l’un avec réponse perdue. Pour chaque scénario indépendant, l’acheteur a payé exactement 4 000 unités une seule fois ; le vendeur a créé et consommé sa facture. Ce sont des tests locaux d’intégration, pas de nouveaux achats mainnet.

En production : manifeste signé, wheel et cinq guides vérifiés, chaîne gratuite MCP, chaîne gratuite SDK avec deux requêtes principales, puis récupération de la commande payante initiale par GET uniquement. Aucun nouveau paiement mainnet depuis le portefeuille de test. Le listing local weather.witness n’a pas de route de paiement direct compatible : la préparation renvoie désormais 409/settlement_route_unsupported au lieu de 500, avant travail et paiement. Son contrat SUB/1 financé par crédit reste inchangé. Aucun pair indépendant de production n’a été mis à jour ni acheté ; cette route a été testée avec deux hubs contrôlés sur Anvil.

[Preuves expurgées](evidence/seller-operations-2026-09-30.json). Aucune clé privée, aucun token d’opération ni paquet de transactions signées n’est publié.
