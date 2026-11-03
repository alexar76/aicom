# Un appel client pour un pipeline payé depuis un portefeuille

[English](https://modelmarket.dev/clients/pipeline-guide/en) · [Русский](https://modelmarket.dev/clients/pipeline-guide/ru) · [Español](https://modelmarket.dev/clients/pipeline-guide/es) · [Français](https://modelmarket.dev/clients/pipeline-guide/fr) · [中文](https://modelmarket.dev/clients/pipeline-guide/zh)

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

[Codex : une opération client, deux sous-traitants payés](https://modelmarket.dev/clients/pipeline-guide/fr) — 2026-09-30.

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

[Base transaction](https://basescan.org/tx/0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919) · Evidence: `independent-seller-mainnet-2026-09-30.json` · Oracle RPC evidence — SDK 3.10.2: `native-price-oracle-2026-09-30.json`.


Test du fournisseur prépayé en production, 2026-09-30 : `weather.witness@v1` publie son véritable destinataire et fonctionne à prix fixe. Son compte distinct a démarré à zéro, sans dotation ni garantie. Un dépôt réel de 0.02 USDC via EIP-3009 l’a financé ; l’acheteur a ensuite payé 0.002 USDC pour le SKU racine. Le fournisseur a acheté météo et air GAIA à 0.001 chacun, laissant 0.018. C’est une comptabilité prépayée après dépôt réel, pas deux virements supplémentaires en chaîne ni une ligne de crédit. Le plafond quotidien est de 0.02, sans recharge automatique. Berlin a renvoyé agreement=true, 14.5°C, humidité 64%, PM2.5 9.9 µg/m³ et US AQI 33, relevés à 2026-09-30T07:01:32Z. L’exécution `paid_580f85c4a2f4deba7a83bc26140fc558` correspond au job `job_db9c841f8a360f04c891a68b` avec les deux reçus enfants. Un HTTP 429 du RPC après signature locale a suspendu l’envoi ; la reprise du paquet enregistré a terminé la même commande. Dépôt et achat ont utilisé l’oracle. Le coût cumulé comptabilisé prudemment est de $0.047149423922618862625 sur $1, dépôt entier compris et sans compter deux fois les débits enfants.

Evidence: `witness-prepaid-mainnet-2026-09-30.json` · [Deposit](https://basescan.org/tx/0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e) · [Root payment](https://basescan.org/tx/0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272).


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

[Base transaction](https://basescan.org/tx/0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857) · Evidence: `gas-sponsorship-mainnet-2026-09-30.json`

## Récupération du résultat fournisseur — SDK/Hub 3.12.0

`PROVIDER-OP/1` couvre le fournisseur qui termine alors que le Hub vendeur perd sa réponse. Avant l’exécution, le fournisseur enregistre l’ID et l’empreinte du produit, de la capability et de l’entrée ; avant la réponse, il enregistre résultat et signature. Une reprise identique rend le résultat durable ; une entrée modifiée est refusée. Les appels concurrents ne doublent pas le travail. KOVA utilise sa base SQLite existante.

L’opérateur active explicitement les produits compatibles : `AIMARKET_PROVIDER_OPERATION_PRODUCTS=kova-network`. Les nouvelles offres signées `SELLER-OP/1` annoncent `provider_recovery: PROVIDER-OP/1` ; URL et clé publique initiales sont figées dans l’état privé. Après une réponse perdue ou une exécution devenue obsolète, le vendeur lit `GET <invoke_url>/operations/<operation_id>`. Il vérifie signature, ID, produit, capability, empreinte exacte de l’entrée et signature distincte du résultat. Le travail payant exige la vérification sauvegardée du paiement original. La réponse finale est immuable, même face à un ancien processus retardé. Aucun second POST fournisseur ni nouveau paiement.

Les routes invoke et status de KOVA exigent le jeton privé partagé : `AIMARKET_CAPABILITY_TOKEN` et `KOVA_CAPABILITY_TOKEN`. `AIMARKET_INVOKE_HOST_GATEWAY` n’autorise que l’hôte fournisseur de l’opérateur. Les preuves publiques ne contiennent ni clé ni jeton. L’acheteur passe toujours par les contrôles de paiement du Hub.

Il s’agit de récupération coopérative, pas d’une garantie universelle d’effets externes exécutés exactement une fois. Une panne entre l’effet et l’enregistrement laisse une issue inconnue, sans répétition automatique. Le fournisseur doit lier sa transaction métier à l’ID ou réconcilier l’effet. Les anciens fournisseurs restent en réconciliation manuelle ; KOVA bloque les entrées incertaines afin d’éviter les écritures doubles.

Une facture déjà payée peut être reprise après expiration si l’horodatage vérifié du bloc précède strictement l’échéance. Les paiements tardifs sont refusés et les nonces restent à usage unique. Les RPC explicites séparés par des virgules constituent une liste exclusive. La facture publique omet le champ interne de délégation du job. Tests : redémarrage, concurrence, entrée modifiée, authentification, signatures altérées, deux Hubs sans second paiement, effet incertain et échéance.

Vérification en production, 2026-09-30 : LOGOS → KOVA pour 0.002 USDC, sans gas acheteur. Après redémarrage de KOVA, le résultat signé a été récupéré par GET depuis son journal durable. La perte de réponse a été simulée sur une copie isolée de l’opération ; les registres de production sont restés inchangés. Aucun nouvel appel fournisseur ni paiement. Le bloc Base 51984647 a été conservé. Status sans jeton a répondu 401 ; la recherche autorisée d’une opération inconnue, 404. Dépense prudente cumulée : $0.1183241752052936711504319125 sur $1. Les remboursements et davantage de réseaux/jetons restent les étapes suivantes.

`run_id: paid_7f29b95f0ebf51092a52883053172f93` · `job_id: job_4ca838ba5866031111ed1778`

[Base transaction](https://basescan.org/tx/0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758) · Evidence: `provider-recovery-mainnet-2026-09-30.json`


## Remboursement approuvé par le vendeur — SDK/Hub 3.13.0

`SELLER-REFUND/1` rembourse un paiement direct confirmé en USDC sur Base. L’acheteur demande une offre pour une étape d’une chaîne terminée ; le vendeur initial signe localement une autorisation EIP-3009. Le sponsor paie le gaz. Aucune clé privée n’est transmise au Hub et ni l’acheteur ni le vendeur n’a besoin d’ETH pour cette voie. Préparer l’offre ne transfère rien et n’oblige pas le vendeur à accepter.

HTTP utilise le `X-Studio-Run-Token` initial : `POST /studio/paid-runs/{run_id}/refunds/{step_id}/prepare` crée ou retrouve l’offre signée ; `POST /studio/paid-runs/{run_id}/refunds/{step_id}` reçoit `{"authorization":"0x…"}` et poursuit le même remboursement ; `GET` lit son état. HTTP 202 signifie en attente. MCP expose `pipeline_refund_prepare`, `pipeline_refund`, `pipeline_refund_status`, avec run ID, jeton limité et step ID. Transmettez uniquement la signature du vendeur, jamais sa clé.

`refund_pipeline(state_path=..., step_id=...)` retourne l’offre sans paiement. Ne partagez que son objet `offer` avec le vendeur, jamais le fichier privé de reprise de l’acheteur. Le vendeur utilise `sign_refund_offer(offer, seller_signer=..., buyer_wallet=..., original_tx_hash=..., max_usdc=..., trusted_hub_key=..., trusted_hub_pq_key=...)` du module `aimarket_hub.refund_client`. Destinataire autorisé, paiement initial, plafond, jeton, réseau et signature du Hub sont vérifiés localement. Envoyez la signature via `refund_pipeline(..., authorization=signature)`. Répéter avec le même fichier reprend le même remboursement ; `RefundPending` en conserve l’identité. L’application du vendeur décide du droit au remboursement avant de signer.

Seuls le vendeur initial, l’acheteur initial et le montant total exact du paiement vérifié sont acceptés. La chaîne doit être completed ou failed : un résultat fournisseur inconnu exige d’abord une réconciliation. La signature soumise reste immuable. Les octets de transaction sont enregistrés avant diffusion et partagent le coordinateur de nonce et de budget du sponsor en base. Une réponse perdue ou un redémarrage réutilise la même transaction. Une autorisation expirée ne peut être renouvelée qu’avant signature d’une transaction par le Hub, en conservant refund ID et nonce d’autorisation pour empêcher deux transferts.

Facture et résultat initiaux restent immuables. Un avoir signé `pipeline.refund/1` relie les deux hashes, montant, jeton, réseau, parties et payeur du gaz. Lire l’état ne déplace aucun fonds. Cette version accepte un remboursement intégral par paiement direct Base USDC sans frais répartis, avec sponsor disponible. Remboursements partiels, frais MarketSplitter, débit forcé et jetons arbitraires ne sont pas implémentés. Le vendeur peut refuser ou manquer de fonds ; une capacité insuffisante du sponsor laisse le même remboursement en attente. Le gaz consommé n’est pas remboursé. Les chaînes gratuites fonctionnent toujours sans source de paiement.

Les tests couvrent mauvais signataire, montant modifié, concurrence, autorisations expirées, transactions persistées, réponses perdues, SDK/MCP et achat puis remboursement Anvil sans ETH chez les deux parties. La vérification mainnet est documentée séparément après exécution.


Vérification mainnet, 2026-09-30 : un SKU statique temporaire de l’opérateur a livré son résultat pour 0.001 USDC, puis son portefeuille vendeur distinct a approuvé le remboursement intégral. Ce dispositif vérifie un règlement et un remboursement réels, pas un vendeur commercial indépendant. Les soldes USDC des deux parties sont revenus à leur valeur initiale ; ETH et nonce de l’acheteur sont inchangés. Le sponsor a payé les deux transactions. La perte volontaire de la réponse a récupéré le même avoir ; après redémarrage du Hub, résultat et remboursement ont conservé exactement les mêmes valeurs JSON. Le listing temporaire a été supprimé. Dépense cumulée conservatrice : $0.1193241752052936711504319125 sur $1, financement intégral du sponsor et achat brut inclus malgré son remboursement. Aucun nouveau contrat déployé.

`run_id: paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc` · `refund_id: refund_95331477f4fb1e81b122b51b63857f0e`

[Purchase / Покупка / Compra / Achat / 购买](https://basescan.org/tx/0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58) · [Refund / Возврат / Reembolso / Remboursement / 退款](https://basescan.org/tx/0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf) · Evidence: `refund-mainnet-2026-09-30.json`


## Profils de paiement supplémentaires et plusieurs machines — SDK/Hub 3.14.0

Le SDK accepte USDC natif sur **Base 8453 et Ethereum 1**, avec adresses fixées, six décimales et domaine EIP-712 `USD Coin` / `2`. Un graphe payant conserve une seule chaîne et un seul actif ; séparez les graphes mixtes en commandes distinctes. Le Hub doit proposer cette voie : sa présence dans le SDK ne transfère pas les soldes entre chaînes et ne change pas la devise du vendeur. Les graphes gratuits restent inchangés. Sponsoring et remboursements restent limités aux paiements directs Base USDC ; sur Ethereum, l’acheteur paie le gaz. `gas_mode="required"` refuse une voie payante sans sponsor avant signature.

`accepted_assets=[...]` remplace la liste par défaut. Chaque entrée fixe `chain_id`, `token_contract`, `decimals`, `eip712_name`, `eip712_version`, `usd_pegged: true`, `authorization: "EIP-3009"`. Il s’agit de la politique de l’acheteur pour un jeton dollar audité, pas d’une garantie sur tout ERC-20. Le Hub ne peut pas l’élargir. Les montants utilisent une arithmétique décimale. Actifs non dollar, ERC-20 uniquement approve, autres réseaux et graphes atomiques multichaînes sont refusés. CLI : `--accepted-assets approved-assets.json`. La politique est conservée dans le fichier de reprise et ne change pas avec resume.

Un vendeur local Ethereum configure `AIMARKET_X402_CHAIN=ethereum`. Diffusion et vérification utilisent le chain ID signé ; `AIMARKET_SETTLE_RPC_1` et `AIMARKET_SETTLE_RPC_8453` sélectionnent les RPC par réseau. `AIMARKET_SETTLE_RPC_URL` reste une liste de repli exclusive : une liste Base seule ne convient pas à Ethereum. Chaque RPC doit annoncer le réseau de la facture avant vérification ou diffusion. Un actif personnalisé exige adresse, symbole, décimales, `AIMARKET_X402_EIP712_NAME` et `AIMARKET_X402_EIP712_VERSION` corrects, ainsi qu’une liste correspondante chez l’acheteur. Ne valorisez pas en dollars un jeton qui ne l’est pas.

Ethereum vérifie ETH/USD frais via deux hôtes RPC, avec marge de 25%, gaz borné et réserve de $0.05. Aucun supplément L1 Base n’est ajouté. Feed Chainlink fixé : `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`, huit décimales, heartbeat 3600 s, âge maximal 3900 s. Base conserve le contrôle du séquenceur et la réserve L1. Mauvais réseau, blocs ou prix périmés et divergence supérieure à 2% arrêtent le paiement. Le prix manuel ne peut qu’augmenter le plafond.

Pour plusieurs machines, installez l’extra `postgres` et configurez le même **PostgreSQL appartenant à l’acheteur** via `AIMARKET_WALLET_DATABASE_URL` avant toute nouvelle commande. Utilisez une connexion directe ou session pooling ; transaction pooling PgBouncer ne préserve pas les advisory locks de session. Le coordinateur sérialise chaque `(chain_id, wallet)` entre connexions et conserve l’état privé, le jeton limité du Hub et les octets signés avant envoi, jamais la clé privée. Réservez l’accès aux agents coopérants de l’acheteur. Le DSN n’est ni conservé dans la commande ni transmis au Hub.

Copiez sûrement le fichier privé vers la machine suivante et appelez `run_pipeline(resume=True, state_path=...)`. Une copie antérieure à la signature retrouve le paquet déjà enregistré ; une commande terminée est consultée avant toute nouvelle signature. Une autre commande ne récupère pas une réservation inachevée. Après échec terminal, libération seulement si tous les nonces signés sont consommés, ou si les autorisations ont expiré sans transaction en attente. Une panne de BD bloque tout nouvel envoi ; les résultats locaux terminés restent accessibles. Tous les clients doivent partager BD et schéma, sans coordinateur indépendant ni logiciel tiers utilisant le même portefeuille. Les fichiers locaux restent le défaut ; un acheteur sponsorisé n’a pas besoin de PostgreSQL.

Tests sur PostgreSQL réel : connexions indépendantes, panne du client, copies périmées et échec de sauvegarde. Une EVM locale de chain ID 1 a exécuté un vrai achat EIP-3009 via le SDK ; l’oracle est testé séparément. Sur Ethereum mainnet, lectures uniquement : les deux observations de prix concordaient et name/version/decimals USDC correspondaient au profil. Aucun achat mainnet Ethereum n’est revendiqué, aucune dépense supplémentaire.

[Contrats Circle](https://developers.circle.com/stablecoins/usdc-contract-addresses) · [Ethereum ETH/USD](https://data.chain.link/feeds/ethereum/mainnet/eth-usd) · Vérification en lecture: `ethereum-profile-2026-09-30.json`

Livraison : Hub et wheel téléchargeable 3.14.0. PyPI vérifié le 2026-09-30 affiche encore `aimarket-hub==3.10.3` et `aimarket-agent==2.4.0`. Nouveaux artefacts : `aimarket-hub==3.14.0` et SDK fournisseur distinct `aimarket-agent==2.5.0`. Les identifiants de publication sont absents de cet environnement ; l’envoi PyPI reste à réaliser par l’opérateur. Le wheel fixé du Hub est déjà installable. Aucun redéploiement de contrat nécessaire.

```bash
pip install "aimarket-hub[client,postgres] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
# Optional: buyer-owned PostgreSQL, same database/schema on every client host.
export AIMARKET_WALLET_DATABASE_URL='postgresql://<buyer-user>:<password>@<buyer-db>/<database>'
aimarket-pipeline --resume --state pipeline-run.private.json
```

---

# Codex : une opération client, deux sous-traitants payés

[English](https://modelmarket.dev/clients/pipeline-guide/en) · [Русский](https://modelmarket.dev/clients/pipeline-guide/ru) · [Español](https://modelmarket.dev/clients/pipeline-guide/es) · [Français](https://modelmarket.dev/clients/pipeline-guide/fr) · [中文](https://modelmarket.dev/clients/pipeline-guide/zh)

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

- JSON: `codex-one-call-2026-09-30.json` · Blueprint: `codex-one-call-2026-09-30-blueprint.json`
- [API / SDK](https://modelmarket.dev/clients/pipeline-guide/fr)
- `run_id`: `paid_ce7dfb28ec21c0ffbc6f65884929aeec`
- `job_id`: `job_dd54651f9104c5c5ac31cc4e`
- `weather`: [0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e](https://basescan.org/tx/0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e)
- `air`: [0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1](https://basescan.org/tx/0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1)

---

Vérification complémentaire de l’accès des agents (3.9.0) : 175 tests ciblés et quatre tests de paiement locaux Anvil ont réussi. Une installation propre a exécuté un graphe gratuit via le SDK en deux requêtes Hub. MCP prepare/invoke/status a terminé un autre graphe gratuit. La commande payante originale a été récupérée par deux GET (manifeste et statut racine), sans clé de portefeuille ni RPC. Le SDK a vérifié les reçus du Hub. Aucun nouveau paiement mainnet n’a été effectué. Le wheel est distribué par le Hub, avec son SHA-256 dans le manifeste signé ; aucune publication PyPI n’a été effectuée.

JSON: `agent-rails-2026-09-30.json`

## Suite : vendeur indépendant, 3.10.1

Codex a ajouté SELLER-OP/1 et déployé Hub avec les migrations 44–45. Le guide détaille protocole et limites. **223 tests ciblés et 6 scénarios Anvil locaux** ont réussi, dont deux règlements entre hubs distincts avec un jeton jetable, l’un avec réponse perdue. Pour chaque scénario indépendant, l’acheteur a payé exactement 4 000 unités une seule fois ; le vendeur a créé et consommé sa facture. Ce sont des tests locaux d’intégration, pas de nouveaux achats mainnet.

En production : manifeste signé, wheel et cinq guides vérifiés, chaîne gratuite MCP, chaîne gratuite SDK avec deux requêtes principales, puis récupération de la commande payante initiale par GET uniquement. Aucun nouveau paiement mainnet depuis le portefeuille de test. Le listing local weather.witness n’a pas de route de paiement direct compatible : la préparation renvoie désormais 409/settlement_route_unsupported au lieu de 500, avant travail et paiement. Son contrat SUB/1 financé par crédit reste inchangé. Aucun pair indépendant de production n’a été mis à jour ni acheté ; cette route a été testée avec deux hubs contrôlés sur Anvil.

Preuves expurgées: `seller-operations-2026-09-30.json`. Aucune clé privée, aucun token d’opération ni paquet de transactions signées n’est publié.

### codex-one-call-2026-09-30-blueprint.json

```json
{
  "nodes": [
    {
      "id": "weather",
      "product_id": "gaia.gateway",
      "capability_id": "gaia.weather.read@v1",
      "source_hub": "https://iot.modelmarket.dev",
      "input": {
        "city": "Berlin"
      }
    },
    {
      "id": "air",
      "product_id": "gaia.gateway",
      "capability_id": "gaia.air.read@v1",
      "source_hub": "https://iot.modelmarket.dev",
      "depends_on": [
        "weather"
      ],
      "input": {
        "city": "Berlin"
      }
    }
  ]
}
```

### agent-rails-2026-09-30.json

```json
{
  "version": "3.9.0",
  "wheel_sha256": "b5a3ccc3ec10be2a2c4ae01dd052d60216e1834751550ba206f63b2446ae4014",
  "guides": [
    "en",
    "ru",
    "es",
    "fr",
    "zh"
  ],
  "mcp_free_run_id": "paid_838b4c9fceefadc04daee59599a8ff2e",
  "mcp_free_job_id": "job_f3dbbfcd48b38769c2bc5959",
  "sdk_free_run_id": "paid_c997741497bb4fad3c0a6c8183cddea1",
  "sdk_free_requests": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "existing_paid_run_id": "paid_ce7dfb28ec21c0ffbc6f65884929aeec",
  "existing_paid_job_id": "job_dd54651f9104c5c5ac31cc4e",
  "paid_recovery_requests": [
    {
      "method": "GET",
      "path": "/.well-known/ai-market.json"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_ce7dfb28ec21c0ffbc6f65884929aeec/pipeline"
    }
  ],
  "new_mainnet_payments": 0,
  "hub_receipts_verified": true
}
```

### seller-operations-2026-09-30.json

```json
{
  "version": "3.10.1",
  "wheel_sha256": "32dd7e248a05f9c4052d7d3dd71470e6b3d183d73a786c7795f1e7f4b87c8d94",
  "protocol": "SELLER-OP/1",
  "guides": [
    "en",
    "ru",
    "es",
    "fr",
    "zh"
  ],
  "older_wheel_preserved": true,
  "mcp_free_run_id": "paid_20e4b10e6eafcb80199cce1b34a759e2",
  "mcp_free_job_id": "job_78bb0fc253938109f00762c1",
  "sdk_free_run_id": "paid_0d1a123a53176be3c66490aef8e35b46",
  "sdk_free_requests": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "existing_paid_run_id": "paid_ce7dfb28ec21c0ffbc6f65884929aeec",
  "existing_paid_job_id": "job_dd54651f9104c5c5ac31cc4e",
  "paid_recovery_requests": [
    {
      "method": "GET",
      "path": "/.well-known/ai-market.json"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_ce7dfb28ec21c0ffbc6f65884929aeec/pipeline"
    }
  ],
  "new_mainnet_payments": 0,
  "hub_receipts_verified": true,
  "local_tests": {
    "focused": 223,
    "anvil": 6,
    "independent_seller_anvil": 2,
    "mainnet_independent_seller_test": false
  },
  "seller_quote_smoke": {
    "sku": "weather.witness@v1",
    "status": "preflight_refused",
    "reason": "listing has no supported seller payout or token",
    "http_status": 409,
    "invoke_sent": false,
    "payment_sent": false,
    "invalid_token_rejected": true,
    "recursive_pipeline_rejected": true
  },
  "production_migrations": [
    44,
    45
  ]
}
```

### independent-seller-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "buyer_hub": "https://modelmarket.dev",
  "seller_hub": "https://independentai.network/hub",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "run_id": "paid_356c3e6931dc6a7f4b3bd2640881e04b",
  "job_id": "job_b9aebbd2aa412d310b14c91e",
  "operation_id": "op_c6d88ad6d742603073eaa6eab5326d38",
  "source_hub": "https://independentai.network/hub",
  "payment_rail": "independent_seller",
  "pay_to": "0xB73d8Bc93B791510C4733C5C5Ac2015a3c2930Ec",
  "tx_hash": "0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919",
  "success": true,
  "status": "completed",
  "final_result": {
    "block_number": 51980340,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "service_usdc": ".002",
  "gas_wei": "603167313432",
  "usd_policy_ceiling": 6000,
  "prior_cost_at_ceiling_usd": "0.016197102150400000",
  "new_cost_at_ceiling_usd": "0.005619003880592000",
  "cumulative_cost_at_ceiling_usd": "0.021816106030992000",
  "approved_total_usd": "1",
  "new_order_limit_usd": ".15",
  "controlled_client_response_loss": true,
  "signed_result_verified": true,
  "http_requests": [
    {
      "method": "GET",
      "host": "modelmarket.dev",
      "path": "/studio/paid-runs/paid_356c3e6931dc6a7f4b3bd2640881e04b/pipeline",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "modelmarket.dev",
      "path": "/ai-market/v2/invoke",
      "http_status": 200
    },
    {
      "method": "GET",
      "host": "modelmarket.dev",
      "path": "/studio/paid-runs/paid_356c3e6931dc6a7f4b3bd2640881e04b/pipeline",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    }
  ],
  "operator_note": "Separate production hub, keys, database and seller wallet; both deployments administered by the same user. Not evidence of an independently owned customer."
}
```

### native-price-oracle-2026-09-30.json

```json
{
  "source": "chainlink_base_eth_usd",
  "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
  "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
  "observations": [
    {
      "price_usd": "2658.74990071",
      "round_id": "55340232221128660926",
      "updated_at": 1790750527,
      "block_number": 51980758,
      "block_timestamp": 1790750863,
      "sequencer_up_since": 1782491507
    },
    {
      "price_usd": "2658.74990071",
      "round_id": "55340232221128660926",
      "updated_at": 1790750527,
      "block_number": 51980758,
      "block_timestamp": 1790750863,
      "sequencer_up_since": 1782491507
    }
  ],
  "margin_percent": 25,
  "max_age_s": 1500,
  "manual_floor_usd": null,
  "native_usd_ceiling": "3323.4373758875",
  "checked_at": 1790750864.630485,
  "rpc_providers": [
    "mainnet.base.org",
    "base-rpc.publicnode.com"
  ],
  "new_mainnet_payments": 0,
  "private_key_used": false,
  "client_version": "3.10.2"
}
```

### witness-prepaid-mainnet-2026-09-30.json

```json
{
  "topup": {
    "tx_hash": "0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e",
    "amount_usdc": ".02",
    "fee_wei": "500743844349",
    "budget_check": {
      "service_usdc": "0.02",
      "native_fee_bound_wei": "4832812118600",
      "native_usd_ceiling": "3328.5750",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981039,
            "block_timestamp": 1790751425,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981039,
            "block_timestamp": 1790751425,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3328.5750",
        "checked_at": 1790751427.5852952
      },
      "l1_upper_bound_wei": "12328121186",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.08608637759766899500",
      "checked_at": 1790751427.585309
    },
    "redeem_status": 200,
    "redeem_result": {
      "success": true,
      "status": "credited",
      "nonce": "0x9078baf0077009ef3f0c29a7baea1458ec130c16600df38260e1e71153e763a1",
      "tx_hash": "0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e",
      "credited_usd": 0.02,
      "chain": "base",
      "paid_usd": 0.02,
      "idempotent_replay": false,
      "protocol_version": "v2"
    }
  },
  "purchase": {
    "result": {
      "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
      "status": "completed",
      "busy": false,
      "bill_of_materials": {
        "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
        "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
        "funding": "buyer_wallet",
        "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
        "status": "completed",
        "budget_usd": 0.002,
        "total_usd": 0.002,
        "remaining_budget_usd": 0.0,
        "payment_unresolved": [],
        "steps": [
          {
            "id": "witness",
            "product_id": "weather-witness",
            "capability_id": "weather.witness@v1",
            "source_hub": "local",
            "status": "succeeded",
            "quoted_usd": 0.002,
            "payment_rail": "seller_direct",
            "terms": {
              "amount_units": "2000",
              "amount_usd": 0.002,
              "chain": "base",
              "chain_id": 8453,
              "decimals": 6,
              "eip712_name": "USD Coin",
              "eip712_version": "2",
              "fee_to": "",
              "fee_units": "0",
              "min_confirmations": 1,
              "offer_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "seller_units": "2000",
              "token": "USDC",
              "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
            },
            "success": true,
            "status_code": 200,
            "receipt": {
              "capability_id": "weather.witness@v1",
              "latency_ms": 1738,
              "list_price_usd": 0.002,
              "nonce": "rcpt_1b670e8c9d8a414658a165fb2aefdf59",
              "price_usd": 0.002,
              "product_id": "weather-witness",
              "signature": {
                "algorithm": "ed25519",
                "pq_algorithm": "ml-dsa-65",
                "pq_public_key": "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",
                "pq_value": "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",
                "value": "EgDG7QkWIX4Qe8U+Wvf23dIQVfP7rEfFTZlmdJZ0dPlb3Nb9syBthPIV42BTadQFH8sglyp9S9/ZHBUK5pPjAw=="
              },
              "success": true,
              "timestamp": "2026-09-30T07:01:33Z"
            },
            "job": {
              "depth": 1,
              "funded_by": "own",
              "job_id": "job_db9c841f8a360f04c891a68b",
              "node": "node_228186546b7fac0f4d89706a",
              "parent": "node_ba3a877444eda0486258c30b"
            },
            "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
            "payment": {
              "amount_usd": 0.002,
              "authorizer": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
              "block_number": 51981171,
              "chain": "base",
              "confirmations": 2,
              "fee_units": "0",
              "nonce": "0x7fe9ed564701050ec2e2633ba60421946eecef2205292c4f8d667e741ac709d0",
              "paid_units": "2000",
              "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "token": "USDC",
              "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
              "verified_at": 1790751691.358382
            },
            "started_at": 1790751691.358526,
            "finished_at": 1790751693.5381346,
            "price_usd": 0.002
          }
        ],
        "created_at": 1790751593.7525403,
        "completed_at": 1790751693.53815,
        "job_id": "job_db9c841f8a360f04c891a68b",
        "signature": {
          "algorithm": "ed25519",
          "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
          "value": "wvBu5M7Yfz0zCMg0jg0c/Eyxa5Vdpx8MVPuoyQaDv6WMcVR6l/MWjQgXHfjRhFmmtM78awfMUxX8G24jma6kDQ==",
          "pq_algorithm": "ml-dsa-65",
          "pq_public_key": "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",
          "pq_value": "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"
        }
      },
      "next_step": null,
      "final_result": {
        "agreement": {
          "agree": true,
          "location_km": 0.0,
          "max_km": 75.0,
          "max_time_apart_s": 7200,
          "reasons": [],
          "time_apart_s": 0
        },
        "air": {
          "attestation": {
            "algorithm": "ed25519",
            "canonical": "device|model|seq|ts|values_sha256",
            "public_key": "k3t0cjTwaxBD9R9DFmx4KbpsPLXX3VEYT4MRLDQeZfI=",
            "value": "Bgmfdy3F5Fmr2zr/dwmeft73N3liNMetH9K8lcyNqE3c01XATspP4BoXZrXmozeM/uUY3al3gohjjVLHxwu6DA=="
          },
          "capability_id": "gaia.air.read@v1",
          "reading": {
            "device_id": "om-aq-01",
            "firmware": "1.0.0",
            "model": "GAIA-AQ1 (Open-Meteo AQ relay)",
            "seq": 184,
            "site": "live-air-eu",
            "ts": "2026-09-30T07:01:32Z",
            "units": {
              "co2_ppm": "ppm",
              "european_aqi": "EAQI",
              "pm10_ugm3": "ug/m3",
              "pm2_5_ugm3": "ug/m3",
              "us_aqi": "US AQI"
            },
            "values": {
              "european_aqi": 22.0,
              "pm10_ugm3": 12.8,
              "pm2_5_ugm3": 9.9,
              "us_aqi": 33.0
            }
          },
          "resolved": {
            "device_id": "om-aq-01",
            "latitude": 52.52,
            "longitude": 13.41,
            "matched_place": "Berlin",
            "requested": "Berlin"
          }
        },
        "children": [
          {
            "capability_id": "gaia.weather.read@v1",
            "funded_by": "own",
            "node": "node_766d429147ff1048f8f0fc11",
            "price_usd": 0.001,
            "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY="
          },
          {
            "capability_id": "gaia.air.read@v1",
            "funded_by": "own",
            "node": "node_db5caa18e04cca2e44466d23",
            "price_usd": 0.001,
            "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY="
          }
        ],
        "funding": "fixed-price",
        "job": {
          "depth": 1,
          "job_id": "job_db9c841f8a360f04c891a68b",
          "node": "node_228186546b7fac0f4d89706a"
        },
        "place": {
          "city": "Berlin"
        },
        "weather": {
          "attestation": {
            "algorithm": "ed25519",
            "canonical": "device|model|seq|ts|values_sha256",
            "public_key": "bdtWcNGNNk2Q6mcblT1OqAdtkncOohceH/G2dlxLDk0=",
            "value": "O7no3SiO0xrS1LohHXoUKncNOim7OKS3zTyJytpi5wEitc+4KSQbfDOArgbkOJ9wybv5j+7QBX+iF2BgbTNWBA=="
          },
          "capability_id": "gaia.weather.read@v1",
          "reading": {
            "device_id": "om-wx-01",
            "firmware": "1.0.0",
            "model": "GAIA-WS1 (Open-Meteo relay)",
            "seq": 231,
            "site": "live-weather-eu",
            "ts": "2026-09-30T07:01:32Z",
            "units": {
              "humidity_pct": "percent",
              "pressure_hpa": "hPa",
              "temperature_c": "cel",
              "wind_mps": "m/s"
            },
            "values": {
              "humidity_pct": 64.0,
              "pressure_hpa": 1020.3,
              "temperature_c": 14.5,
              "wind_mps": 2.82
            }
          },
          "resolved": {
            "device_id": "om-wx-01",
            "distance_km": 0.0,
            "matched_place": "Berlin",
            "relay_latitude": 52.52,
            "relay_longitude": 13.41,
            "requested": "Berlin"
          }
        },
        "witness": "weather-witness/1"
      },
      "detail": "",
      "success": true,
      "price_usd": 0,
      "product_id": "hephaestus",
      "capability_id": "pipeline.run@v1",
      "result": {
        "status": "completed",
        "final_result": {
          "agreement": {
            "agree": true,
            "location_km": 0.0,
            "max_km": 75.0,
            "max_time_apart_s": 7200,
            "reasons": [],
            "time_apart_s": 0
          },
          "air": {
            "attestation": {
              "algorithm": "ed25519",
              "canonical": "device|model|seq|ts|values_sha256",
              "public_key": "k3t0cjTwaxBD9R9DFmx4KbpsPLXX3VEYT4MRLDQeZfI=",
              "value": "Bgmfdy3F5Fmr2zr/dwmeft73N3liNMetH9K8lcyNqE3c01XATspP4BoXZrXmozeM/uUY3al3gohjjVLHxwu6DA=="
            },
            "capability_id": "gaia.air.read@v1",
            "reading": {
              "device_id": "om-aq-01",
              "firmware": "1.0.0",
              "model": "GAIA-AQ1 (Open-Meteo AQ relay)",
              "seq": 184,
              "site": "live-air-eu",
              "ts": "2026-09-30T07:01:32Z",
              "units": {
                "co2_ppm": "ppm",
                "european_aqi": "EAQI",
                "pm10_ugm3": "ug/m3",
                "pm2_5_ugm3": "ug/m3",
                "us_aqi": "US AQI"
              },
              "values": {
                "european_aqi": 22.0,
                "pm10_ugm3": 12.8,
                "pm2_5_ugm3": 9.9,
                "us_aqi": 33.0
              }
            },
            "resolved": {
              "device_id": "om-aq-01",
              "latitude": 52.52,
              "longitude": 13.41,
              "matched_place": "Berlin",
              "requested": "Berlin"
            }
          },
          "children": [
            {
              "capability_id": "gaia.weather.read@v1",
              "funded_by": "own",
              "node": "node_766d429147ff1048f8f0fc11",
              "price_usd": 0.001,
              "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY="
            },
            {
              "capability_id": "gaia.air.read@v1",
              "funded_by": "own",
              "node": "node_db5caa18e04cca2e44466d23",
              "price_usd": 0.001,
              "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY="
            }
          ],
          "funding": "fixed-price",
          "job": {
            "depth": 1,
            "job_id": "job_db9c841f8a360f04c891a68b",
            "node": "node_228186546b7fac0f4d89706a"
          },
          "place": {
            "city": "Berlin"
          },
          "weather": {
            "attestation": {
              "algorithm": "ed25519",
              "canonical": "device|model|seq|ts|values_sha256",
              "public_key": "bdtWcNGNNk2Q6mcblT1OqAdtkncOohceH/G2dlxLDk0=",
              "value": "O7no3SiO0xrS1LohHXoUKncNOim7OKS3zTyJytpi5wEitc+4KSQbfDOArgbkOJ9wybv5j+7QBX+iF2BgbTNWBA=="
            },
            "capability_id": "gaia.weather.read@v1",
            "reading": {
              "device_id": "om-wx-01",
              "firmware": "1.0.0",
              "model": "GAIA-WS1 (Open-Meteo relay)",
              "seq": 231,
              "site": "live-weather-eu",
              "ts": "2026-09-30T07:01:32Z",
              "units": {
                "humidity_pct": "percent",
                "pressure_hpa": "hPa",
                "temperature_c": "cel",
                "wind_mps": "m/s"
              },
              "values": {
                "humidity_pct": 64.0,
                "pressure_hpa": 1020.3,
                "temperature_c": 14.5,
                "wind_mps": 2.82
              }
            },
            "resolved": {
              "device_id": "om-wx-01",
              "distance_km": 0.0,
              "matched_place": "Berlin",
              "relay_latitude": 52.52,
              "relay_longitude": 13.41,
              "requested": "Berlin"
            }
          },
          "witness": "weather-witness/1"
        },
        "bill_of_materials": {
          "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
          "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
          "funding": "buyer_wallet",
          "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
          "status": "completed",
          "budget_usd": 0.002,
          "total_usd": 0.002,
          "remaining_budget_usd": 0.0,
          "payment_unresolved": [],
          "steps": [
            {
              "id": "witness",
              "product_id": "weather-witness",
              "capability_id": "weather.witness@v1",
              "source_hub": "local",
              "status": "succeeded",
              "quoted_usd": 0.002,
              "payment_rail": "seller_direct",
              "terms": {
                "amount_units": "2000",
                "amount_usd": 0.002,
                "chain": "base",
                "chain_id": 8453,
                "decimals": 6,
                "eip712_name": "USD Coin",
                "eip712_version": "2",
                "fee_to": "",
                "fee_units": "0",
                "min_confirmations": 1,
                "offer_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "seller_units": "2000",
                "token": "USDC",
                "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
              },
              "success": true,
              "status_code": 200,
              "receipt": {
                "capability_id": "weather.witness@v1",
                "latency_ms": 1738,
                "list_price_usd": 0.002,
                "nonce": "rcpt_1b670e8c9d8a414658a165fb2aefdf59",
                "price_usd": 0.002,
                "product_id": "weather-witness",
                "signature": {
                  "algorithm": "ed25519",
                  "pq_algorithm": "ml-dsa-65",
                  "pq_public_key": "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",
                  "pq_value": "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",
                  "value": "EgDG7QkWIX4Qe8U+Wvf23dIQVfP7rEfFTZlmdJZ0dPlb3Nb9syBthPIV42BTadQFH8sglyp9S9/ZHBUK5pPjAw=="
                },
                "success": true,
                "timestamp": "2026-09-30T07:01:33Z"
              },
              "job": {
                "depth": 1,
                "funded_by": "own",
                "job_id": "job_db9c841f8a360f04c891a68b",
                "node": "node_228186546b7fac0f4d89706a",
                "parent": "node_ba3a877444eda0486258c30b"
              },
              "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
              "payment": {
                "amount_usd": 0.002,
                "authorizer": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
                "block_number": 51981171,
                "chain": "base",
                "confirmations": 2,
                "fee_units": "0",
                "nonce": "0x7fe9ed564701050ec2e2633ba60421946eecef2205292c4f8d667e741ac709d0",
                "paid_units": "2000",
                "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "token": "USDC",
                "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
                "verified_at": 1790751691.358382
              },
              "started_at": 1790751691.358526,
              "finished_at": 1790751693.5381346,
              "price_usd": 0.002
            }
          ],
          "created_at": 1790751593.7525403,
          "completed_at": 1790751693.53815,
          "job_id": "job_db9c841f8a360f04c891a68b",
          "signature": {
            "algorithm": "ed25519",
            "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
            "value": "wvBu5M7Yfz0zCMg0jg0c/Eyxa5Vdpx8MVPuoyQaDv6WMcVR6l/MWjQgXHfjRhFmmtM78awfMUxX8G24jma6kDQ==",
            "pq_algorithm": "ml-dsa-65",
            "pq_public_key": "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",
            "pq_value": "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"
          }
        }
      },
      "subcontracting": {
        "job_id": "job_db9c841f8a360f04c891a68b",
        "funding": "buyer_wallet",
        "nodes": [
          {
            "node": "node_ba3a877444eda0486258c30b",
            "parent": "",
            "depth": 0,
            "product_id": "hephaestus",
            "capability_id": "pipeline.run@v1",
            "price_usd": 0.0,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-yKlROh9qyPfcrewL0EbuIbu7PLEh4omMZDqPYz4aNbA=",
            "receipt_id": "urn:aimarket:pipeline:paid_580f85c4a2f4deba7a83bc26140fc558"
          },
          {
            "node": "node_228186546b7fac0f4d89706a",
            "parent": "node_ba3a877444eda0486258c30b",
            "depth": 1,
            "product_id": "weather-witness",
            "capability_id": "weather.witness@v1",
            "price_usd": 0.002,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-ENZqx9XQlAqVW9EIAueoRDiU3CQ/zWmWYUfYcNBVMbY=",
            "receipt_id": "urn:uuid:7120b86c-5142-4b45-9b01-a5c5ecaa795e"
          },
          {
            "node": "node_db5caa18e04cca2e44466d23",
            "parent": "node_228186546b7fac0f4d89706a",
            "depth": 2,
            "product_id": "gaia.gateway",
            "capability_id": "gaia.air.read@v1",
            "price_usd": 0.001,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY=",
            "receipt_id": "urn:uuid:645e7e42-42fa-4e42-91d6-b84cb2344b67"
          },
          {
            "node": "node_766d429147ff1048f8f0fc11",
            "parent": "node_228186546b7fac0f4d89706a",
            "depth": 2,
            "product_id": "gaia.gateway",
            "capability_id": "gaia.weather.read@v1",
            "price_usd": 0.001,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY=",
            "receipt_id": "urn:uuid:c18abe0c-33aa-4ea7-9a25-97c7f167293f"
          }
        ],
        "budget_usd": 0.002,
        "spent_usd": 0.002,
        "unspent_budget_usd": 0.0
      },
      "protocol_version": "v2",
      "receipt": {
        "kind": "pipeline.run/1",
        "run_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
        "job_id": "job_db9c841f8a360f04c891a68b",
        "product_id": "hephaestus",
        "capability_id": "pipeline.run@v1",
        "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
        "success": true,
        "parents": [
          {
            "id": "urn:uuid:7120b86c-5142-4b45-9b01-a5c5ecaa795e",
            "digestSRI": "sha256-ENZqx9XQlAqVW9EIAueoRDiU3CQ/zWmWYUfYcNBVMbY="
          }
        ],
        "result_digest": "04b959e9264be0c3203b005819cd8ded9e468532e94647122fba0004aa26571a",
        "bill_digest": "7bb9257690299bad9d875484b5f4741c0a39a6a781bab36b647e5d333744fd4e",
        "signature": {
          "algorithm": "ed25519",
          "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
          "value": "rSfbsQKIdwcJccPjytyKVqcvOZ4Lk1pcQWDm5RnuWIyGA/Y3cCmqNs1I/6kGVQQmRwtj6USCIo+LXip0UgMMCQ==",
          "pq_algorithm": "ml-dsa-65",
          "pq_public_key": "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",
          "pq_value": "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"
        }
      }
    },
    "tx_hashes": {
      "witness": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272"
    },
    "fee_wei": "500681057186",
    "budget_check": {
      "service_usdc": "0.002",
      "native_fee_bound_wei": "4774506722000",
      "native_usd_ceiling": "3328.5750",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981171,
            "block_timestamp": 1790751689,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981171,
            "block_timestamp": 1790751689,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3328.5750",
        "checked_at": 1790751690.875712
      },
      "l1_upper_bound_wei": "11745067220",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.0678923037121811500",
      "checked_at": 1790751690.875724
    }
  },
  "account_starting_grant_usd": 0,
  "conservative_cumulative_usd": "0.047149423922618862625",
  "cumulative_limit_usd": "1",
  "accounting_note": "Earlier runs retain their historical 6000 USD/ETH ceiling; new gas is valued at the saved oracle price plus 25%. Entire 0.02 USDC deposit is counted; later prepaid child debits are not counted twice.",
  "provider_account_after": {
    "balance_usd": 0.018,
    "spent_usd": 0.002,
    "granted_usd": 0,
    "topped_up_usd": 0.02,
    "collateral_usd": 0
  }
}
```

### gas-sponsorship-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.11.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "sponsor": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
  "run_id": "paid_38c0a7c6c2fe992186116a2822205d3d",
  "job_id": "job_dc0b37b785a7f358bfb30b23",
  "tx_hash": "0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857",
  "service_usdc": ".002",
  "sponsor_fee_wei": "516607663289",
  "buyer_gas_wei": "0",
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "message_only_signer": true,
  "sdk_rpc_configured": false,
  "controlled_reply_loss": true,
  "cumulative_conservative_usd": "0.1163241752052936711504319125",
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "calls": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_38c0a7c6c2fe992186116a2822205d3d/pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "funding": {
    "sponsor": "0x663E0C31925EAd877fD9414C2e1862fa50b2650b",
    "payer": "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",
    "tx_hash": "0x73cff1e1da3242a2f3c77e1f7389fc5ed23f7625634975d7dbef2086bcfcfc78",
    "funding_wei": "20000000000000",
    "funding_fee_wei": "133597605703",
    "budget_check": {
      "service_usdc": "0",
      "native_fee_bound_wei": "6235958489800",
      "native_usd_ceiling": "3336.4504743875",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2669.16037951",
            "round_id": "55340232221128660934",
            "updated_at": 1790756921,
            "block_number": 51983794,
            "block_timestamp": 1790756935,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2669.16037951",
            "round_id": "55340232221128660934",
            "updated_at": 1790756921,
            "block_number": 51983794,
            "block_timestamp": 1790756935,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3336.4504743875",
        "checked_at": 1790756935.732915
      },
      "l1_upper_bound_wei": "26359584898",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.07080596666155396807999750",
      "checked_at": 1790756935.7329228
    },
    "prior_total_usd": "0.047149423922618862625",
    "cumulative_conservative_usd": "0.1143241752052936711504319125",
    "budget_limit_usd": "1",
    "funding_counted_in_full": true
  },
  "local_validation": {
    "focused_regression_passed": 178,
    "mcp_after_static_card_sync_passed": 81,
    "oracle_and_relay_passed": 37,
    "anvil_zero_eth_buyer_passed": 1
  },
  "final_result": {
    "block_number": 51983924,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "signed_result_verified": true,
  "steps": [
    {
      "id": "summary",
      "product_id": "prod-logos",
      "capability_id": "logos.federation.summary@v1",
      "source_hub": "https://logos.modelmarket.dev",
      "status": "succeeded",
      "price_usd": 0.0
    },
    {
      "id": "network",
      "product_id": "kova-network",
      "capability_id": "kova.network.status@v1",
      "source_hub": "https://independentai.network/hub",
      "status": "succeeded",
      "price_usd": 0.002,
      "tx_hash": "0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857"
    }
  ]
}
```

### provider-recovery-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.12.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "sponsor": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
  "run_id": "paid_7f29b95f0ebf51092a52883053172f93",
  "job_id": "job_4ca838ba5866031111ed1778",
  "tx_hash": "0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758",
  "service_usdc": ".002",
  "sponsor_fee_wei": "516795861906",
  "buyer_gas_wei": "0",
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "message_only_signer": true,
  "sdk_rpc_configured": false,
  "controlled_reply_loss": true,
  "cumulative_conservative_usd": "0.1183241752052936711504319125",
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "calls": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_7f29b95f0ebf51092a52883053172f93/pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "final_result": {
    "block_number": 51984647,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "signed_result_verified": true,
  "recovery_proof": {
    "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5",
    "isolated_copy_recovered": true,
    "production_ledgers_modified": false,
    "new_payments": 0,
    "new_provider_invokes": 0,
    "status_reads": [
      {
        "method": "GET",
        "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5"
      }
    ],
    "provider_result": {
      "capability_id": "kova.network.status@v1",
      "input_sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
      "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5",
      "product_id": "kova-network",
      "protocol": "PROVIDER-OP/1",
      "result": {
        "block_number": 51984647,
        "chain": "base",
        "chain_id": 8453,
        "findings": [],
        "score": 100,
        "summary": "Base mainnet is reachable through KOVA.",
        "verdict": "pass"
      },
      "result_signature": "SDpaLWz7Xvwpa4jVM515EFOVv3rtqUUH8skEbfXBShKDEQ8vuvgy6rraGxFNXJr9eOZevFArDr7Z3Hxk36BECQ==",
      "signature": "4i9lfCn+KRuVi2NUW49E2DsnziK2nbFivGD+Ciex8VwFkBVZUFDXVedYIvgCSoU2H4ZaVhf7Rp7WLflOsl1lCA==",
      "status": "completed"
    }
  },
  "scope": "Live provider journal after restart; lost seller response simulated in an isolated database copy. Production ledgers were not altered.",
  "provider_gateway_authenticated": true,
  "local_validation": {
    "recovery_payment_and_peer_tests": 76,
    "recovery_and_pipeline_tests": 36,
    "kova_operations_and_api_tests": 22,
    "kova_bound_signature_followup_tests": 9
  }
}
```

### refund-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.13.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "seller": "0xd41bdb11ae589b7b11c1daca1f7b6ae408f0bb20",
  "operator_owned_fixture": true,
  "run_id": "paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc",
  "job_id": "job_da32d04e2b39e575684e9d50",
  "refund_id": "refund_95331477f4fb1e81b122b51b63857f0e",
  "service_usdc": ".001",
  "refunded_usdc": ".001",
  "buyer_gas_wei": "0",
  "transactions": [
    {
      "tx_hash": "0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58",
      "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
      "fee_wei": "620782210434"
    },
    {
      "tx_hash": "0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf",
      "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
      "fee_wei": "487781767367"
    }
  ],
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "buyer_usdc_balance_restored": true,
  "seller_usdc_balance_restored": true,
  "controlled_refund_reply_loss": true,
  "original_bill_unchanged": true,
  "same_refund_retry": true,
  "credit_note": {
    "amount_units": "1000",
    "amount_usdc": "0.001",
    "buyer_gas_fee_units": "0",
    "chain_id": 8453,
    "from": "0xd41bdb11ae589b7b11c1daca1f7b6ae408f0bb20",
    "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
    "kind": "pipeline.refund/1",
    "original_tx_hash": "0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58",
    "refund_id": "refund_95331477f4fb1e81b122b51b63857f0e",
    "refund_tx_hash": "0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf",
    "run_id": "paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc",
    "signature": {
      "algorithm": "ed25519",
      "pq_algorithm": "ml-dsa-65",
      "pq_public_key": "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",
      "pq_value": "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",
      "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
      "value": "uCRKNXnCxZpCl+4d2SitFnEX6PjvYdqq3trKwowCGjPDm7QPKT2SzWzSJJgJ81FI9fekrgy9ti+HIuhSxGcrDA=="
    },
    "step_id": "proof",
    "to": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
    "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
  },
  "final_result": {
    "operator_owned_fixture": true,
    "refund_test": "2026-09-30",
    "result": "delivered"
  },
  "cumulative_conservative_usd": "0.1193241752052936711504319125",
  "gross_purchase_counted_despite_refund": true,
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "same_refund_after_hub_restart": true,
  "original_result_after_hub_restart": true,
  "temporary_listing_removed": true
}
```

### ethereum-profile-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.14.0",
  "chain_id": 1,
  "token_contract": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  "token_metadata": {
    "name": "USD Coin",
    "version": "2",
    "decimals": 6
  },
  "native_price": {
    "source": "chainlink_ethereum_eth_usd",
    "feed": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "sequencer_feed": null,
    "observations": [
      {
        "price_usd": "2683.51528449",
        "round_id": "129127208515966895503",
        "updated_at": 1790760323,
        "block_number": 26089454,
        "block_timestamp": 1790761163,
        "sequencer_up_since": null
      },
      {
        "price_usd": "2683.51528449",
        "round_id": "129127208515966895503",
        "updated_at": 1790760323,
        "block_number": 26089454,
        "block_timestamp": 1790761163,
        "sequencer_up_since": null
      }
    ],
    "margin_percent": 25,
    "max_age_s": 3900,
    "manual_floor_usd": null,
    "native_usd_ceiling": "3354.3941056125",
    "checked_at": 1790761170.358094
  },
  "read_only": true,
  "new_mainnet_transactions": 0,
  "sources": [
    "https://developers.circle.com/stablecoins/usdc-contract-addresses",
    "https://data.chain.link/feeds/ethereum/mainnet/eth-usd",
    "https://reference-data-directory.vercel.app/feeds-mainnet.json"
  ]
}
```
