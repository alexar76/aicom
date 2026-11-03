# Un appel client pour un pipeline payé depuis un portefeuille

[English](one-call-pipelines.md) · [Русский](one-call-pipelines.ru.md) · [Español](one-call-pipelines.es.md) · [Français](one-call-pipelines.fr.md) · [中文](one-call-pipelines.zh.md)

`await run_pipeline(...)` réunit préparation, signature locale, exécution racine et attente automatique en une opération. Le parcours normal comporte **deux requêtes principales au Hub** : préparer le graphe, puis invoquer la racine. Les appels RPC blockchain sont supplémentaires. HTTP 202, pertes de transport et erreurs temporaires peuvent nécessiter davantage de requêtes vers la même commande ; deux échanges HTTP ne garantissent pas la fin du travail.

## Vendeurs indépendants et reprise : 3.10.1

Un graphe payant peut désormais utiliser un pair de confiance annonçant **`SELLER-OP/1`**, sans `SELLS_FOR`, compte de revente ni clé de crédit du pair. L’acheteur règle la facture du vendeur avec ses fonds réels. Conservez `source_hub` : `run_pipeline(...)`, HTTP et MCP choisissent automatiquement l’adaptateur. Les chaînes gratuites restent utilisables sans source de paiement.

La préparation vérifie le manifeste signé et demande une offre au même pair. Il doit être actif, approuvé et avoir des clés épinglées ; une clé PQ épinglée impose également sa vérification. SKU, acheteur, prix du catalogue, destinataire déclaré, réseau, jeton, répartition des montants et échéance sont contrôlés. Aucune URL arbitraire de l’offre n’est suivie. Un pair incompatible échoue avant signature et paiement avec `settlement_route_unsupported`. La préparation peut laisser une facture inutilisée, sans travail ni transfert de fonds.

Le vendeur persiste `operation_id` et délivre un `operation_token` limité à l’opération. Son offre signée contient conditions, nonce/échéance et schéma d’entrée. Le token reste dans l’état privé du Hub acheteur et n’apparaît pas sur la facture publique. L’entrée peut dépendre d’étapes précédentes ; entrée résolue, acheteur et hash de paiement deviennent immuables au premier invoke. Une modification renvoie HTTP 409. Le secret de facture reste chez le vendeur ; aucune facture concurrente, clé de crédit ou autorisation SUB/1 n’est transmise. La clé privée du portefeuille reste chez le client.

Routes : `POST /ai-market/v2/operations/prepare`, `POST /ai-market/v2/operations/{operation_id}/invoke`, `GET /ai-market/v2/operations/{operation_id}`. Invoke et status exigent `X-Operation-Token` ; un token absent ou invalide donne 404. Prepare reçoit `product_id`, `capability_id`, `wallet`, `max_price_usd` ; invoke reçoit `input`, `wallet`, `tx_hash`, omis pour une opération gratuite. Un invoke en cours renvoie 202, un résultat terminal réussi ou échoué 200 : lire `status` et `success`. Status signe l’état sans exécuter ni payer. Le client habituel conserve ses deux requêtes principales au Hub.

Le Hub acheteur diffuse la transaction signée initiale, vérifie le règlement, puis lit l’opération distante avant de l’invoquer. Le vendeur vérifie aussi le paiement, persiste le verrou avant l’appel au fournisseur et conserve le résultat signé. La signature lie opération, empreintes de l’offre et de l’entrée, portefeuille et transaction. Une réponse perdue se récupère par lecture de la même opération ; le résultat conservé survit au redémarrage. La facture racine inclut `payment_rail: independent_seller`, l’offre et le statut/reçu signés. Un enfant SUB/1 local relie le résultat à l’arbre avec financement `own`, sans crédit transféré entre hubs.

Le worker acheteur renouvelle son bail toutes les 30 secondes. Après 180 secondes sans renouvellement, le même invoke racine peut reprendre un enfant `SELLER-OP/1` en cours dont l’étape et le job sont persistés. Le serveur transfère atomiquement la propriété et refuse les écritures de l’ancien worker. Status annonce `resume_same_run` ; le SDK conserve le paquet signé initial. Les fournisseurs historiques ne sont pas débloqués arbitrairement ; les autres états incertains exigent une réconciliation par l’opérateur.

La garantie est **au plus un envoi au fournisseur avec résultat durable**, pas une exécution exactement une fois pour tout fournisseur. Le fournisseur final reçoit des `Idempotency-Key` et `X-AIMarket-Operation-Id` stables ; il doit assurer une idempotence durable pour fermer sa propre fenêtre entre exécution et réponse. Si le vendeur s’arrête à cette frontière ou ignore l’issue, il indique `reconciliation_required` sans réexpédier. Un verrou périmé est signalé après 180 secondes, sans être libéré. `recovery.action: contact_operator` exige de réconcilier la même opération ; `replacement_payment_allowed` reste false. Seuls les listings locaux sont enveloppés, hors `pipeline.run@v1` récursif. Un endpoint x402 quelconque n’implémente pas automatiquement ce protocole.

Déployer Hub **3.10.1** avec migrations **44** (opérations) et **45** (baux). Aucun redéploiement des contrats de paiement n’est nécessaire. Les pairs indépendants doivent aussi être mis à jour pour publier ce contrat. Un graphe payant garde un réseau/jeton ; le client fourni accepte Base USDC et exige du gas natif. Parrainage du gas, autres réseaux, coordination des nonces entre machines et remboursements automatiques ne font pas partie de cette version.

Les tests couvrent clés et bases séparées, requêtes immuables, offres falsifiées, concurrence, réponses perdues, protection contre l’ancien worker, entrées dynamiques, chaînes gratuites et règlements Anvil via le vrai code de paiement du Hub. Deux scénarios Anvil utilisent un jeton et des comptes jetables, dont la perte de réponse ; ils prouvent l’intégration, pas la mise à jour de tous les vendeurs. Les vérifications de production sont consignées séparément. Aucun nouveau débit mainnet n’est requis pour ces tests.

## 1. Préparer le graphe

Appeler `POST /studio/prepare-pipeline` avec `nodes`, un `wallet` facultatif et `max_budget_usd`. Cette route réunit les anciens `/studio/preflight` et `/studio/paid-runs/{run_id}/prepare-pipeline`. Elle renvoie `ready`, `blockers`, les identités et conditions des étapes, `total_units`, `run_id`, `access_token`, `graph_digest`, `wallet`, `expires_at` et `offers` avec nonces de facture et autorisations EIP-712. La préparation ne crée aucun job racine et ne paie rien. Un graphe gratuit ne nécessite pas de portefeuille et renvoie `offers` vide ; un graphe payant sans portefeuille est refusé. Les anciennes routes restent disponibles. Le manifeste annonce la nouvelle sous `pipeline_execution.prepare_graph`.

`max_budget_usd` dans la requête au Hub limite uniquement le coût des services. Le paramètre `max_total_usd` du SDK vérifie également la provision pour les frais réseau décrite ci-dessous.

```json
{
  "nodes": [
    {"id": "weather", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1", "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}},
    {"id": "air", "product_id": "gaia.gateway", "capability_id": "gaia.air.read@v1", "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}, "depends_on": ["weather"]}
  ],
  "wallet": "<buyer-address>",
  "max_budget_usd": 1
}
```

## 2. Signer localement et exécuter

Le client vérifie la correspondance avec le graphe et le portefeuille demandés, les offres, autorisations, soldes, réseau, nonces en attente et estimation du gas. Il signe localement les autorisations EIP-3009 et transactions EIP-1559, attribue des nonces consécutifs et sauvegarde tout le lot avant envoi. Le Hub reçoit les transactions signées, jamais la clé privée. Une commande racine `pipeline.run@v1` est envoyée ; chaque paiement est diffusé juste avant son étape. Une réponse réussie contient résultat final, facture signée, reçu racine et arbre SUB/1. Vérifier `status` et `success` : un échec du fournisseur est aussi terminal, sans remboursement automatique du paiement externe.

```json
{
  "product_id": "hephaestus",
  "capability_id": "pipeline.run@v1",
  "source_hub": "local",
  "input": {
    "run_id": "<prepared-run-id>",
    "access_token": "<scoped-run-token>",
    "transactions": {"weather": "0x<signed-transaction>", "air": "0x<signed-transaction>"}
  }
}
```

## Python et ligne de commande

Installer le wheel distribué avec l’extra `client` (commande ci-dessous). Le client paie en **USDC natif sur Base (8453) ou Ethereum (1)** (voir les profils de paiement supplémentaires plus bas) et est testé sur macOS/Linux. Tout autre réseau ou token est refusé, sauf si votre propre politique `accepted_assets` le liste. Un graphe gratuit ne nécessite ni signataire, ni RPC, ni plafond de change. Le signataire est un objet local exposant `address`, `sign_message` et `sign_transaction`.

```python
import json, os
from eth_account import Account
from aimarket_hub.pipeline_client import run_pipeline

result = await run_pipeline(
    json.load(open("blueprint.json")),
    hub="https://modelmarket.dev",
    signer=Account.from_key(os.environ["PIPELINE_WALLET_KEY"]),
    rpc_url="https://mainnet.base.org",
    max_total_usd="1",
    state_path="order.private.json",
    wait=True,
)
print(result["status"], result["final_result"], result["bill_of_materials"])
```

```bash
python examples/pipeline-run/run.py blueprint.json \
  --hub https://modelmarket.dev --rpc https://mainnet.base.org \
  --max-total-usd 1 \
  --execute --prompt-key --state order.private.json
```

`--prompt-key` lit la clé localement sans écho ; sinon fournir `PIPELINE_WALLET_KEY` de façon sûre dans l’environnement. Aucun besoin de clé pour un graphe gratuit ou une reprise après signature. Une nouvelle commande CLI exige `--execute`. L’ancien exemple `client.py --budget` conserve son budget limité aux services. La version 3.10.1 exige le déploiement du Hub et les migrations 44–45, sans redéploiement des contrats de paiement.

## Budget, état et reprise

`max_total_usd` inclut les services et une réserve prudente pour le gas. Avant signature et avant chaque envoi ou nouvelle tentative de l’appel racine, le client lit le contrat ETH/USD Chainlink fixé sur Base via deux RPC de noms d’hôte différents. Le second est `https://base-rpc.publicnode.com`, ou `https://mainnet.base.org` si PublicNode est le principal ; utiliser `price_rpc_url` / `--price-rpc` pour un autre fournisseur de confiance. Les deux lectures doivent valider Base, 8 décimales, un tour complet et positif de moins de 1500 secondes, un bloc de moins de 120 secondes et un séquenceur actif après une heure de reprise. Les contrats sont lus au numéro du bloc observé. Un écart supérieur à 2% bloque l’envoi. La valorisation est le cours le plus élevé **majoré de 25%**. L’ancien `native_usd_ceiling`, facultatif, peut seulement augmenter cette valorisation ; il ne la réduit pas et ne remplace pas un oracle indisponible. À $20 000 par ETH, le calcul utilise au moins $25 000, même si un ancien fichier contient 6000.

Chaque paiement réserve 300 000 gas au double du prix observé et 100 fois la borne L1 de Base GasPriceOracle pour 2048 octets, plus $0.05 par commande. Dépasser le budget enregistré suspend l’envoi en conservant la commande et les signatures. Des données absentes, périmées ou contradictoires bloquent aussi les nouveaux envois, sans prix fixe de secours. Les graphes gratuits et les résultats terminés conservés localement n’ont pas besoin d’oracle. Après interruption d’une commande envoyée, le statut est lu avant toute réévaluation. Le fichier de reprise conserve les deux cours, les tours, les dates et la valorisation retenue. Ne pas remplacer une commande incertaine par un nouvel achat.

Le contrôle précède l’envoi du client ; il n’est pas continu pendant l’exécution d’un long graphe. Les RPC restent une dépendance de confiance : des noms distincts ne prouvent pas une infrastructure indépendante. Le change USD et les frais L1 peuvent évoluer après l’envoi et ne sont pas plafonnés par EIP-1559. Il s’agit d’une protection prudente, pas d’un séquestre garantissant une limite absolue en dollars.

[Chainlink ETH/USD — Base](https://data.chain.link/feeds/base/base/eth-usd) · [L2 sequencer](https://docs.chain.link/data-feeds/l2-sequencer-feeds).

Le fichier de reprise est remplacé atomiquement, avec permissions 0600 et fsync ; un verrou distinct interdit l’utilisation simultanée du même chemin. Il contient des identifiants limités à la commande et des transactions signées exécutables : il doit rester privé. Il ne contient aucune clé privée. Après sauvegarde du lot, la reprise ne nécessite pas de signataire et ne choisit aucun nouveau nonce ou paiement. Avant signature, le signataire initial reste nécessaire. Une réponse de préparation perdue peut laisser un devis inutilisé ; aucun paiement ni job racine n’existe encore. Ne pas effectuer d’autres transactions simultanées depuis ce portefeuille.

L’attente est activée par défaut. HTTP 202 poursuit la même commande ; après une erreur de transport, le statut est lu avant de renvoyer le payload initial. `PipelinePending` conserve le chemin du fichier en cas de délai dépassé ou de rapprochement nécessaire. Un état serveur occupé est interrogé en lecture seule, sans déverrouillage. `wait=False` renvoie un résultat en attente à reprendre. Un fichier local terminé renvoie son résultat mémorisé sans réseau. Un enfant en échec n’est ni racheté ni réexécuté automatiquement. Pour reprendre, omettre graphe et nouveaux paramètres de budget/RPC : la politique et le graphe sauvegardés restent immuables.

```python
result = await run_pipeline(resume=True, state_path="order.private.json")
```

```bash
python examples/pipeline-run/run.py --resume --state order.private.json
```

[Codex : une opération client, deux sous-traitants payés](case-study-codex-one-call.fr.md) — 2026-09-30.

## Accès des agents : mise à jour 3.9.0

Le client s’installe depuis un wheel versionné sans cloner le dépôt. Le manifeste signé publie `pipeline_execution.client.distribution`, son URL et son SHA-256. Le Hub distribue le paquet ; cela ne signifie pas que PyPI propose déjà cette version.

```bash
pip install "aimarket-hub[client] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
aimarket-pipeline --help
```

`aimarket-pipeline` accepte les mêmes arguments que `examples/pipeline-run/run.py`. L’extra `client` inclut la signature des paiements et la vérification ML-DSA. Python 3.11+ est requis. Linux/macOS sont testés ; le verrou Windows est implémenté mais non testé dans cette version. HTTP/MCP est accessible depuis tout langage avec un signataire local.

MCP expose `pipeline_prepare`, `pipeline_invoke`, `pipeline_status`. La préparation reçoit le graphe, le plafond des services et le portefeuille facultatif ; l’exécution reçoit `run_id`, `access_token` et le paquet signé localement ; le statut reçoit l’ID et le jeton. Un graphe gratuit ne nécessite ni signataire ni fonds. Le serveur MCP distant ne peut pas signer pour un portefeuille tiers : connecter un signataire local ou utiliser Python. Ne jamais transmettre de clé privée comme argument. Les signatures et offres sont renvoyées intégralement.

Le SDK vérifie la préparation signée, la facture et le reçu racine, leurs liens au graphe/à la commande/au portefeuille et les empreintes du résultat et de la facture, même en cache. Les clés du Hub sont épinglées lors de la première préparation HTTPS. Pour une confiance indépendante, fournir `trusted_hub_key` et `trusted_hub_pq_key` (CLI : `--trusted-hub-key`, `--trusted-hub-pq-key`). Une fois la clé PQ épinglée, supprimer sa signature provoque un refus. Cette vérification porte sur le compte rendu signé du Hub, pas sur l’identité indépendante de chaque appareil.

`GET /studio/paid-runs/{run_id}/pipeline` avec `X-Studio-Run-Token` lit sans payer ni appeler d’enfant. Après une réponse perdue ou une reprise, le SDK lit ce statut avant RPC/gas. Il récupère donc une commande terminée malgré un RPC indisponible ou des frais plus élevés. Un travail occupé est interrogé en lecture seule. Les reprises 429/5xx espacent les essais et respectent `Retry-After` numérique dans le délai restant. `PipelineHTTPError` conserve `status_code`, `detail` et `state_path`.

Une réservation persistante du portefeuille empêche des plages de nonce communes entre plusieurs fichiers d’état sur le même hôte. Elle réside dans `~/.aimarket/wallets` ; `AIMARKET_WALLET_STATE_DIR` choisit un répertoire commun. Tous les clients participants doivent le partager. Le succès libère la réservation ; un échec attend que les nonces soient consommés ou que les autorisations expirent sans transaction en attente. Conserver le fichier original. Entre hôtes ou logiciels différents, employer un signataire/coordinateur commun ou des portefeuilles dédiés ; des fichiers locaux ne coordonnent pas des signataires externes arbitraires.

Preflight renvoie `blockers[].code` : `settlement_route_unsupported`, `route_unavailable`, `mixed_assets_unsupported`, `service_budget_exceeded`. Les routes externes passent par un vendeur de référence, une revente configurée ou un pair indépendant compatible SELLER-OP/1. Le manifeste expose cette limite. Un graphe payant utilise une chaîne/un jeton ; Python accepte Base USDC. Une présence au catalogue ne garantit pas la compatibilité du paiement.

Si le fournisseur a exécuté mais que sa réponse est perdue, aucun nouvel achat automatique n’est autorisé. `recovery.action` indique `wait`, `resume_same_run` ou `contact_operator`, sans paiement de remplacement. La réconciliation exige un reçu ou une preuve du fournisseur. Les enfants non envoyés ne sont pas payés ; les paiements externes confirmés ne sont pas remboursés automatiquement. Cette incertitude est signalée sans rejouer silencieusement le travail.


Vérification supplémentaire en production, 2026-09-30 : le Hub vendeur distinct `https://independentai.network/hub` a exécuté `kova.network.status@v1` pour 0.002 USDC sur Base. Le client a volontairement perdu la première réponse puis repris la même opération sans nouveau paiement. Les deux Hubs ont le même administrateur : le test prouve un déploiement et un destinataire distincts, pas des propriétaires commerciaux indépendants.

[Base transaction](https://basescan.org/tx/0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919) · [Evidence](evidence/independent-seller-mainnet-2026-09-30.json) · [Oracle RPC evidence — SDK 3.10.2](evidence/native-price-oracle-2026-09-30.json).


Test du fournisseur prépayé en production, 2026-09-30 : `weather.witness@v1` publie son véritable destinataire et fonctionne à prix fixe. Son compte distinct a démarré à zéro, sans dotation ni garantie. Un dépôt réel de 0.02 USDC via EIP-3009 l’a financé ; l’acheteur a ensuite payé 0.002 USDC pour le SKU racine. Le fournisseur a acheté météo et air GAIA à 0.001 chacun, laissant 0.018. C’est une comptabilité prépayée après dépôt réel, pas deux virements supplémentaires en chaîne ni une ligne de crédit. Le plafond quotidien est de 0.02, sans recharge automatique. Berlin a renvoyé agreement=true, 14.5°C, humidité 64%, PM2.5 9.9 µg/m³ et US AQI 33, relevés à 2026-09-30T07:01:32Z. L’exécution `paid_580f85c4a2f4deba7a83bc26140fc558` correspond au job `job_db9c841f8a360f04c891a68b` avec les deux reçus enfants. Un HTTP 429 du RPC après signature locale a suspendu l’envoi ; la reprise du paquet enregistré a terminé la même commande. Dépôt et achat ont utilisé l’oracle. Le coût cumulé comptabilisé prudemment est de $0.047149423922618862625 sur $1, dépôt entier compris et sans compter deux fois les débits enfants.

[Evidence](evidence/witness-prepaid-mainnet-2026-09-30.json) · [Deposit](https://basescan.org/tx/0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e) · [Root payment](https://basescan.org/tx/0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272).


Le SDK 3.10.3 tente la même requête RPC jusqu’à trois fois en cas de HTTP 429/5xx ou de panne de transport, avec des pauses limitées à cinq secondes. Après épuisement des tentatives, l’envoi s’arrête et la commande est conservée : aucun cours fixe de remplacement ni nouveau paiement.

## État de publication des paquets — vérifié le 2026-09-30

PyPI contient désormais le wheel et l’archive source de `aimarket-hub==3.10.3`. Ses 131 fichiers correspondent à la compilation de production. La version 3.11.0 ajoute la prise en charge du gas et nécessite une nouvelle publication, sans remplacer les fichiers 3.10.3. La publication distincte de `aimarket-agent==2.5.0` reste à vérifier. Publication et déploiement sont distincts. La récupération fournisseur, les remboursements et davantage de réseaux/jetons constituent les étapes suivantes.

## Prise en charge du gas — SDK 3.11.0

Le SDK choisit `gas_mode="auto"` par défaut. La préparation signée par le Hub indique si tout le graphe peut être sponsorisé. L’acheteur signe localement uniquement les autorisations EIP-3009 exactes en USDC ; un portefeuille distinct de l’opérateur signe les transactions et paie le gas. L’acheteur n’a besoin ni d’ETH, ni de signature de transactions, ni de configuration RPC. `gas_mode="required"` refuse un graphe payant dès la préparation si le sponsor est indisponible. `gas_mode="buyer"` conserve le gas payé par l’acheteur. HTTP et MCP gardent `buyer` par défaut pour compatibilité. CLI : `--gas-mode required`.

La préparation renvoie `gas_sponsorship` ; l’appel racine accepte `authorizations: {step_id: signature}` à la place de `transactions`. Les deux champs ensemble sont interdits. Le devis fixe le mode, l’acheteur, les destinataires, les montants, les nonces et les échéances ; une reprise ne peut remplacer les signatures. Le Hub ne reçoit jamais la clé privée de l’acheteur. La facture signée identifie le sponsor et le payeur du gas ; les frais de gas de l’acheteur sont nuls. Les graphes gratuits fonctionnent toujours sans signataire ni sponsor, même avec `required`.

Cette première version prend en charge les paiements directs USDC sur Base 8453, y compris aux vendeurs indépendants compatibles. Le MarketSplitter actuel lie le payeur à `msg.sender` : les paiements avec partage de commission sont donc explicitement exclus. La voie directe ne nécessite aucun redéploiement de contrat. `auto` peut revenir au gas payé par l’acheteur ; `required` ne le peut pas. Un solde insuffisant, un plafond journalier atteint, un oracle indisponible ou un nonce occupé laisse la même commande en attente, sans paiement de remplacement.

Avant chaque nouveau paiement, le Hub vérifie l’oracle ETH/USD, l’estimation prudente, le solde et les plafonds par paiement et par jour. Après résolution et validation de l’entrée de l’étape, il réserve un nonce et enregistre atomiquement les octets signés dans la base partagée. Une seule transaction est en attente par portefeuille. Les processus partagent les registres de nonces et de budget ; les reprises renvoient exactement les mêmes octets. Une panne après cet enregistrement reste récupérable après expiration du devis : le paiement peut déjà avoir eu lieu. Les résultats terminés en cache ne nécessitent aucun RPC. Des bases distinctes ne doivent pas partager un portefeuille de gas.

Configuration : `AIMARKET_PIPELINE_RELAY_ENABLED=1`, `AIMARKET_PIPELINE_RELAY_KEY_FILE` (fichier privé, sans lien symbolique), `AIMARKET_PIPELINE_RELAY_RPC`, éventuellement `AIMARKET_PIPELINE_RELAY_PRICE_RPC`, `AIMARKET_PIPELINE_RELAY_DAILY_WEI` (20000000000000 par défaut), `AIMARKET_PIPELINE_RELAY_MAX_GAS_USD` (0.10). Alimenter un portefeuille dédié ; ne jamais installer la clé de l’acheteur. Le compteur journalier réserve des bornes prudentes en ETH sans libérer l’écart après minage. L’estimation USD n’est pas un plafond USD immuable sur chaîne. Les transactions déjà enregistrées restent récupérables après désactivation des nouveaux paiements sponsorisés.

Tests : processus concurrents avec connexions distinctes, annulation de réservation, signatures invalides, reprise immuable, graphes gratuits et véritable transfert EIP-3009 sur Anvil avec zéro ETH pour l’acheteur. Ces tests ne certifient ni déploiement en production ni achèvement de la récupération fournisseur, des remboursements ou du support multiréseau.

Vérification en production le 2026-09-30 : une étape gratuite LOGOS puis `kova.network.status@v1` sur `https://independentai.network/hub`, avec signature de messages uniquement et sans RPC configuré dans le SDK. Coût acheteur : **0.002 USDC** de service et **0** de gas ; solde ETH et nonce inchangés. La perte volontaire de la première réponse invoke a récupéré la même commande. KOVA a renvoyé `pass`, score 100, bloc Base 51983924. Le sponsor a payé 516607663289 wei. Son financement complet de 0.00002 ETH était déjà comptabilisé, sans compter deux fois le gas. Dépense prudente cumulée : **$0.1163241752052936711504319125 sur $1**, essais antérieurs compris. Les preuves ci-dessous ne contiennent ni jetons d’accès ni clés privées.

`run_id: paid_38c0a7c6c2fe992186116a2822205d3d` · `job_id: job_dc0b37b785a7f358bfb30b23`

[Base transaction](https://basescan.org/tx/0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857) · [Evidence](evidence/gas-sponsorship-mainnet-2026-09-30.json)

## Récupération du résultat fournisseur — SDK/Hub 3.12.0

`PROVIDER-OP/1` couvre le fournisseur qui termine alors que le Hub vendeur perd sa réponse. Avant l’exécution, le fournisseur enregistre l’ID et l’empreinte du produit, de la capability et de l’entrée ; avant la réponse, il enregistre résultat et signature. Une reprise identique rend le résultat durable ; une entrée modifiée est refusée. Les appels concurrents ne doublent pas le travail. KOVA utilise sa base SQLite existante.

L’opérateur active explicitement les produits compatibles : `AIMARKET_PROVIDER_OPERATION_PRODUCTS=kova-network`. Les nouvelles offres signées `SELLER-OP/1` annoncent `provider_recovery: PROVIDER-OP/1` ; URL et clé publique initiales sont figées dans l’état privé. Après une réponse perdue ou une exécution devenue obsolète, le vendeur lit `GET <invoke_url>/operations/<operation_id>`. Il vérifie signature, ID, produit, capability, empreinte exacte de l’entrée et signature distincte du résultat. Le travail payant exige la vérification sauvegardée du paiement original. La réponse finale est immuable, même face à un ancien processus retardé. Aucun second POST fournisseur ni nouveau paiement.

Les routes invoke et status de KOVA exigent le jeton privé partagé : `AIMARKET_CAPABILITY_TOKEN` et `KOVA_CAPABILITY_TOKEN`. `AIMARKET_INVOKE_HOST_GATEWAY` n’autorise que l’hôte fournisseur de l’opérateur. Les preuves publiques ne contiennent ni clé ni jeton. L’acheteur passe toujours par les contrôles de paiement du Hub.

Il s’agit de récupération coopérative, pas d’une garantie universelle d’effets externes exécutés exactement une fois. Une panne entre l’effet et l’enregistrement laisse une issue inconnue, sans répétition automatique. Le fournisseur doit lier sa transaction métier à l’ID ou réconcilier l’effet. Les anciens fournisseurs restent en réconciliation manuelle ; KOVA bloque les entrées incertaines afin d’éviter les écritures doubles.

Une facture déjà payée peut être reprise après expiration si l’horodatage vérifié du bloc précède strictement l’échéance. Les paiements tardifs sont refusés et les nonces restent à usage unique. Les RPC explicites séparés par des virgules constituent une liste exclusive. La facture publique omet le champ interne de délégation du job. Tests : redémarrage, concurrence, entrée modifiée, authentification, signatures altérées, deux Hubs sans second paiement, effet incertain et échéance.

Vérification en production, 2026-09-30 : LOGOS → KOVA pour 0.002 USDC, sans gas acheteur. Après redémarrage de KOVA, le résultat signé a été récupéré par GET depuis son journal durable. La perte de réponse a été simulée sur une copie isolée de l’opération ; les registres de production sont restés inchangés. Aucun nouvel appel fournisseur ni paiement. Le bloc Base 51984647 a été conservé. Status sans jeton a répondu 401 ; la recherche autorisée d’une opération inconnue, 404. Dépense prudente cumulée : $0.1183241752052936711504319125 sur $1. Les remboursements et davantage de réseaux/jetons restent les étapes suivantes.

`run_id: paid_7f29b95f0ebf51092a52883053172f93` · `job_id: job_4ca838ba5866031111ed1778`

[Base transaction](https://basescan.org/tx/0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758) · [Evidence](evidence/provider-recovery-mainnet-2026-09-30.json)


## Remboursement approuvé par le vendeur — SDK/Hub 3.13.0

`SELLER-REFUND/1` rembourse un paiement direct confirmé en USDC sur Base. L’acheteur demande une offre pour une étape d’une chaîne terminée ; le vendeur initial signe localement une autorisation EIP-3009. Le sponsor paie le gaz. Aucune clé privée n’est transmise au Hub et ni l’acheteur ni le vendeur n’a besoin d’ETH pour cette voie. Préparer l’offre ne transfère rien et n’oblige pas le vendeur à accepter.

HTTP utilise le `X-Studio-Run-Token` initial : `POST /studio/paid-runs/{run_id}/refunds/{step_id}/prepare` crée ou retrouve l’offre signée ; `POST /studio/paid-runs/{run_id}/refunds/{step_id}` reçoit `{"authorization":"0x…"}` et poursuit le même remboursement ; `GET` lit son état. HTTP 202 signifie en attente. MCP expose `pipeline_refund_prepare`, `pipeline_refund`, `pipeline_refund_status`, avec run ID, jeton limité et step ID. Transmettez uniquement la signature du vendeur, jamais sa clé.

`refund_pipeline(state_path=..., step_id=...)` retourne l’offre sans paiement. Ne partagez que son objet `offer` avec le vendeur, jamais le fichier privé de reprise de l’acheteur. Le vendeur utilise `sign_refund_offer(offer, seller_signer=..., buyer_wallet=..., original_tx_hash=..., max_usdc=..., trusted_hub_key=..., trusted_hub_pq_key=...)` du module `aimarket_hub.refund_client`. Destinataire autorisé, paiement initial, plafond, jeton, réseau et signature du Hub sont vérifiés localement. Envoyez la signature via `refund_pipeline(..., authorization=signature)`. Répéter avec le même fichier reprend le même remboursement ; `RefundPending` en conserve l’identité. L’application du vendeur décide du droit au remboursement avant de signer.

Seuls le vendeur initial, l’acheteur initial et le montant total exact du paiement vérifié sont acceptés. La chaîne doit être completed ou failed : un résultat fournisseur inconnu exige d’abord une réconciliation. La signature soumise reste immuable. Les octets de transaction sont enregistrés avant diffusion et partagent le coordinateur de nonce et de budget du sponsor en base. Une réponse perdue ou un redémarrage réutilise la même transaction. Une autorisation expirée ne peut être renouvelée qu’avant signature d’une transaction par le Hub, en conservant refund ID et nonce d’autorisation pour empêcher deux transferts.

Facture et résultat initiaux restent immuables. Un avoir signé `pipeline.refund/1` relie les deux hashes, montant, jeton, réseau, parties et payeur du gaz. Lire l’état ne déplace aucun fonds. Cette version accepte un remboursement intégral par paiement direct Base USDC sans frais répartis, avec sponsor disponible. Remboursements partiels, frais MarketSplitter, débit forcé et jetons arbitraires ne sont pas implémentés. Le vendeur peut refuser ou manquer de fonds ; une capacité insuffisante du sponsor laisse le même remboursement en attente. Le gaz consommé n’est pas remboursé. Les chaînes gratuites fonctionnent toujours sans source de paiement.

Les tests couvrent mauvais signataire, montant modifié, concurrence, autorisations expirées, transactions persistées, réponses perdues, SDK/MCP et achat puis remboursement Anvil sans ETH chez les deux parties. La vérification mainnet est documentée séparément après exécution.


Vérification mainnet, 2026-09-30 : un SKU statique temporaire de l’opérateur a livré son résultat pour 0.001 USDC, puis son portefeuille vendeur distinct a approuvé le remboursement intégral. Ce dispositif vérifie un règlement et un remboursement réels, pas un vendeur commercial indépendant. Les soldes USDC des deux parties sont revenus à leur valeur initiale ; ETH et nonce de l’acheteur sont inchangés. Le sponsor a payé les deux transactions. La perte volontaire de la réponse a récupéré le même avoir ; après redémarrage du Hub, résultat et remboursement ont conservé exactement les mêmes valeurs JSON. Le listing temporaire a été supprimé. Dépense cumulée conservatrice : $0.1193241752052936711504319125 sur $1, financement intégral du sponsor et achat brut inclus malgré son remboursement. Aucun nouveau contrat déployé.

`run_id: paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc` · `refund_id: refund_95331477f4fb1e81b122b51b63857f0e`

[Purchase / Покупка / Compra / Achat / 购买](https://basescan.org/tx/0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58) · [Refund / Возврат / Reembolso / Remboursement / 退款](https://basescan.org/tx/0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf) · [Evidence](evidence/refund-mainnet-2026-09-30.json)


## Profils de paiement supplémentaires et plusieurs machines — SDK/Hub 3.14.0

Le SDK accepte USDC natif sur **Base 8453 et Ethereum 1**, avec adresses fixées, six décimales et domaine EIP-712 `USD Coin` / `2`. Un graphe payant conserve une seule chaîne et un seul actif ; séparez les graphes mixtes en commandes distinctes. Le Hub doit proposer cette voie : sa présence dans le SDK ne transfère pas les soldes entre chaînes et ne change pas la devise du vendeur. Les graphes gratuits restent inchangés. Sponsoring et remboursements restent limités aux paiements directs Base USDC ; sur Ethereum, l’acheteur paie le gaz. `gas_mode="required"` refuse une voie payante sans sponsor avant signature.

`accepted_assets=[...]` remplace la liste par défaut. Chaque entrée fixe `chain_id`, `token_contract`, `decimals`, `eip712_name`, `eip712_version`, `usd_pegged: true`, `authorization: "EIP-3009"`. Il s’agit de la politique de l’acheteur pour un jeton dollar audité, pas d’une garantie sur tout ERC-20. Le Hub ne peut pas l’élargir. Les montants utilisent une arithmétique décimale. Actifs non dollar, ERC-20 uniquement approve, autres réseaux et graphes atomiques multichaînes sont refusés. CLI : `--accepted-assets approved-assets.json`. La politique est conservée dans le fichier de reprise et ne change pas avec resume.

Un vendeur local Ethereum configure `AIMARKET_X402_CHAIN=ethereum`. Diffusion et vérification utilisent le chain ID signé ; `AIMARKET_SETTLE_RPC_1` et `AIMARKET_SETTLE_RPC_8453` sélectionnent les RPC par réseau. `AIMARKET_SETTLE_RPC_URL` reste une liste de repli exclusive : une liste Base seule ne convient pas à Ethereum. Chaque RPC doit annoncer le réseau de la facture avant vérification ou diffusion. Un actif personnalisé exige adresse, symbole, décimales, `AIMARKET_X402_EIP712_NAME` et `AIMARKET_X402_EIP712_VERSION` corrects, ainsi qu’une liste correspondante chez l’acheteur. Ne valorisez pas en dollars un jeton qui ne l’est pas.

Ethereum vérifie ETH/USD frais via deux hôtes RPC, avec marge de 25%, gaz borné et réserve de $0.05. Aucun supplément L1 Base n’est ajouté. Feed Chainlink fixé : `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`, huit décimales, heartbeat 3600 s, âge maximal 3900 s. Base conserve le contrôle du séquenceur et la réserve L1. Mauvais réseau, blocs ou prix périmés et divergence supérieure à 2% arrêtent le paiement. Le prix manuel ne peut qu’augmenter le plafond.

Pour plusieurs machines, installez l’extra `postgres` et configurez le même **PostgreSQL appartenant à l’acheteur** via `AIMARKET_WALLET_DATABASE_URL` avant toute nouvelle commande. Utilisez une connexion directe ou session pooling ; transaction pooling PgBouncer ne préserve pas les advisory locks de session. Le coordinateur sérialise chaque `(chain_id, wallet)` entre connexions et conserve l’état privé, le jeton limité du Hub et les octets signés avant envoi, jamais la clé privée. Réservez l’accès aux agents coopérants de l’acheteur. Le DSN n’est ni conservé dans la commande ni transmis au Hub.

Copiez sûrement le fichier privé vers la machine suivante et appelez `run_pipeline(resume=True, state_path=...)`. Une copie antérieure à la signature retrouve le paquet déjà enregistré ; une commande terminée est consultée avant toute nouvelle signature. Une autre commande ne récupère pas une réservation inachevée. Après échec terminal, libération seulement si tous les nonces signés sont consommés, ou si les autorisations ont expiré sans transaction en attente. Une panne de BD bloque tout nouvel envoi ; les résultats locaux terminés restent accessibles. Tous les clients doivent partager BD et schéma, sans coordinateur indépendant ni logiciel tiers utilisant le même portefeuille. Les fichiers locaux restent le défaut ; un acheteur sponsorisé n’a pas besoin de PostgreSQL.

Tests sur PostgreSQL réel : connexions indépendantes, panne du client, copies périmées et échec de sauvegarde. Une EVM locale de chain ID 1 a exécuté un vrai achat EIP-3009 via le SDK ; l’oracle est testé séparément. Sur Ethereum mainnet, lectures uniquement : les deux observations de prix concordaient et name/version/decimals USDC correspondaient au profil. Aucun achat mainnet Ethereum n’est revendiqué, aucune dépense supplémentaire.

[Contrats Circle](https://developers.circle.com/stablecoins/usdc-contract-addresses) · [Ethereum ETH/USD](https://data.chain.link/feeds/ethereum/mainnet/eth-usd) · [Vérification en lecture](evidence/ethereum-profile-2026-09-30.json)

Livraison : Hub et wheel téléchargeable 3.14.0. PyPI vérifié le 2026-09-30 affiche encore `aimarket-hub==3.10.3` et `aimarket-agent==2.4.0`. Nouveaux artefacts : `aimarket-hub==3.14.0` et SDK fournisseur distinct `aimarket-agent==2.5.0`. Les identifiants de publication sont absents de cet environnement ; l’envoi PyPI reste à réaliser par l’opérateur. Le wheel fixé du Hub est déjà installable. Aucun redéploiement de contrat nécessaire.

```bash
pip install "aimarket-hub[client,postgres] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
# Optional: buyer-owned PostgreSQL, same database/schema on every client host.
export AIMARKET_WALLET_DATABASE_URL='postgresql://<buyer-user>:<password>@<buyer-db>/<database>'
aimarket-pipeline --resume --state pipeline-run.private.json
```
