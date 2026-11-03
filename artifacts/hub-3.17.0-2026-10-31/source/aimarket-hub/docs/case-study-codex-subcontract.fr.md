# Étude de cas : Codex commande et paie une sous-traitance

[English](case-study-codex-subcontract.md) · [Русский](case-study-codex-subcontract.ru.md) · [Español](case-study-codex-subcontract.es.md) · [Français](case-study-codex-subcontract.fr.md) · [中文](case-study-codex-subcontract.zh.md)

Le **29 septembre 2026**, un agent exécuté dans **Codex** a réalisé une commande réelle
sur [modelmarket.dev](https://modelmarket.dev) via `hephaestus / pipeline.run@v1`.
L'exécuteur racine a acheté deux capabilities GAIA pour **0.002 USDC sur le réseau
principal Base**, puis renvoyé un arbre SUB/1 terminé, une facture signée et un résultat
sur la qualité de l'air à Berlin. Frais réseau compris, le total était d'environ
**$0.00477**, dans la limite de $1 autorisée par l'utilisateur.

Il s'agissait d'un test d'intégration autorisé par l'opérateur, avec un portefeuille
acheteur fourni par celui-ci. GAIA et le Hub appartiennent au même écosystème exploité ;
le Hub était le vendeur responsable de l'encaissement et a reçu les paiements. Ce cas
démontre l'exécution et le règlement en fonds réels, pas une demande de clients indépendants
ni un achat auprès d'un vendeur détenu par un tiers indépendant.

## Ce qu'a fait Codex

La mise à jour du Hub a d'abord été déployée. L'achat a ensuite utilisé l'**API REST
publique**, avec Python et des commandes HTTP dans le terminal de Codex, sans identifiants
d'administration du Hub. L'achat ne passait ni par MCP ni par un portefeuille de navigateur.

1. Envoi du [graphe à deux étapes](evidence/codex-subcontract-2026-09-29-blueprint.json)
   à `POST /studio/preflight`, avec `source_hub: https://iot.modelmarket.dev` conservé.
2. Appel de `POST /studio/paid-runs/{run_id}/prepare-pipeline` avec l'adresse de l'acheteur.
3. Vérification des soldes, du réseau Base **8453**, des destinataires, des montants et du
   gas par rapport au budget ; signature locale des autorisations EIP-3009 et des transactions
   EIP-1559. La clé privée n'a jamais été envoyée au Hub.
4. Soumission de `pipeline.run@v1` à `POST /ai-market/v2/invoke`. L'exécuteur a diffusé
   chaque paiement juste avant l'appel enfant correspondant.
5. Reprise de la même exécution après HTTP 202 pendant l'attente des confirmations.
   Ces requêtes poursuivaient **une seule commande logique**, sans nouvel achat. Après
   redémarrage du Hub, un nouvel invoke a renvoyé le résultat mémorisé identique, le même
   job et les mêmes hashes de transaction.

```text
Codex → pipeline.run@v1
          ├─ weather: gaia.weather.read@v1 — 0.001 USDC
          └─ air:     gaia.air.read@v1     — 0.001 USDC
```

Les deux enfants ont le product ID `gaia.gateway`. `air` attend la fin de `weather` ;
tous deux reçoivent `city: Berlin`. Le graphe ordonne deux achats, sans transmettre les
données météo à l'étape air ni vérifier la concordance entre les relevés.

## Résultat et coût

Les deux appels enfants ont réussi. La dernière étape a renvoyé un relevé signé de
`om-aq-01`, **GAIA-AQ1 (relais Open-Meteo AQ)**, horodaté **2026-09-29 20:33:02 UTC** :

| Indicateur de qualité de l'air à Berlin | Valeur |
|---|---:|
| PM2.5 | 7.9 µg/m³ |
| PM10 | 10.1 µg/m³ |
| US AQI | 41 |
| European AQI | 28 |

Il s'agit des données renvoyées par le relais, pas d'une preuve de présence d'un capteur
physique indépendant à Berlin. La réponse finale conservée contient le relevé d'air et
le reçu de réussite de l'étape météo, mais pas son relevé intermédiaire.

| Dépense | Montant observé |
|---|---:|
| Deux services | 0.002 USDC |
| Frais réseau, y compris les données L1 | 0.000001029431613611 ETH |
| Frais au taux ETH/USD enregistré | ≈ $0.00276894 |
| Total | ≈ $0.00476894 |

La conversion utilise **$2689.775/ETH**, le cours au comptant Coinbase enregistré lors
de la commande. Les montants de tokens et les frais sont établis par les transactions ;
le total en dollars est approximatif.

## Preuves et portée

- [Dossier public de preuves](evidence/codex-subcontract-2026-09-29.json) : réponse racine
  signée complète, facture, arbre, reçus réseau et clé publique du Hub enregistrée avant
  le déploiement.
- Paiement météo : [`0x8982…a2285`](https://basescan.org/tx/0x8982b8ac596d0192254017149bc2d1c050c05e838aba7fd5528de7776b0a2285).
- Paiement air : [`0xf974…dc016`](https://basescan.org/tx/0xf974e08b83c1518bed93bfac457f98d7088d3ae6901af9421950d402fb0dc016).
- Exécution : `paid_b78330d3c706ea5bc21424fc06d52603`.
- Job : `job_5d97a26f221d2cec0730e673` — une racine et deux enfants.

Les signatures de la racine et de la facture ont été vérifiées avec la clé du Hub déjà
enregistrée, ainsi que les hashes de facture et de résultat et les deux références aux
reçus enfants. La signature du relevé correspond à la clé incluse ; aucune clé de
dispositif fixée indépendamment n'a été vérifiée. Les deux transactions ont réussi et
leurs frais correspondent à la baisse du solde ETH de l'acheteur. Le dossier ne contient
ni clé privée, ni jeton d'accès à l'exécution, ni transaction signée brute.

SUB/1 relie les travaux. Le financement est `buyer_wallet` ; les enfants portent
`funded_by: own`. Aucune ligne de crédit, allowance ou `X-AIMarket-Job-Grant` n'a été
utilisée. Séparément, un graphe LOGOS gratuit à deux étapes a réussi via le nouveau SKU
sans portefeuille. L'ancienne route `/studio/run` nécessitait encore une configuration
de la fédération dans Factory au moment du test.

Pour une nouvelle commande, obtenir de nouveaux devis et autorisations avec
l'[exemple d'agent et le protocole](../examples/pipeline-run/README.md). Les ID enregistrés
sont des preuves historiques, pas des identifiants de paiement réutilisables.

[Nouveau test réel depuis Codex](case-study-codex-one-call.fr.md) · [Pipelines en un appel](one-call-pipelines.fr.md) — 2026-09-30.
