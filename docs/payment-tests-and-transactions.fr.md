# Tests de paiement et transactions

**EN** [English](payment-tests-and-transactions.md) · **RU** [Русский](payment-tests-and-transactions.ru.md) · **ES** [Español](payment-tests-and-transactions.es.md) · **FR** [Français](payment-tests-and-transactions.fr.md) · **ZH** [中文](payment-tests-and-transactions.zh.md)

Vérification enregistrée : **2026-10-23**. Ce guide décrit le checkout, l'affectation des
transactions, le grand livre interne UNI, les tests de reprise et la portée des résultats.

## 1. Preuves et périmètre

Le tableau conserve la vérification initiale ; les résultats les plus récents figurent juste après.

| Vérification | Résultat enregistré | Ce qui était réel ou simulé |
| --- | --- | --- |
| Suite de reprise des paiements | **50 passed, aucun test ignoré** : 25 cas SQLite + 25 PostgreSQL | Stockages, signatures, concurrence et arrêts de processus enfants réels ; transactions synthétiques et réponses chaîne/fournisseur simulées |
| Suite principale Factory | **5 828 passed**, 60 ignorés | Sélection principale ; ses tests de paiement ne doivent pas être ajoutés une seconde fois à ce nombre |
| Exécution PostgreSQL complémentaire | PostgreSQL **18.3**, cluster temporaire arrêté ensuite | Base locale distincte ; aucune base de production utilisée |

Preuves : [JUnit des paiements](../artifacts/quality-audit-2026-10-23/payments-sqlite-postgres.xml),
[manifeste de vérification](../artifacts/quality-audit-2026-10-23/verification.json),
[rapport qualité complet](quality-audit-2026-10-23.md).
Une suite locale verte **ne prouve pas un nouveau transfert d'argent réel**. Le
[compte rendu de déploiement daté](../artifacts/payment-production-deploy-2026-10-23/deployment-summary.json)
précise lui aussi qu'aucun paiement positif de bout en bout ni remboursement en chaîne avec des fonds réels n'a été exécuté.
Les transactions réelles historiques figurent dans le [journal en chaîne](onchain-journal.md)
et le [cas d'invocation payante](case-study-paid-invoke.md) : des preuves datées, pas un contrôle de disponibilité actuel.

Le paramétrage PostgreSQL concerne le grand livre UNI. Commerce de Factory et les stockages KOVA/SaaS gardent leurs propres bases SQLite ; cela ne valide pas un stockage PostgreSQL des commandes checkout.

### Audit complémentaire : erreurs et scénarios critiques

Dernière vérification : **6 139 passed, 84 sous-tests ; 24 sondes live volontairement ignorées** dans la suite locale complète ; **450 contrôles paiement/UNI sans omission financière**. Un passage séparé en production a réussi **32 tests : 24 live et 8 contrats, sans omission**. Les **13 fonctions financières critiques** atteignent 100% des lignes/branches, seuils imposés. Couverture globale : **60.8% lignes / 50.0% branches**. L’audit des dépendances reste sans vulnérabilité signalée.

Les derniers tests ajoutent sept scénarios sur les deux variantes de stockage : hash vide ou d’un autre réseau, devis consommé pendant l’attente du verrou asynchrone réel, ancien devis sans montant, nouvelle tentative du transfert fixé, réseau persistant non pris en charge et conflit d’insertion de commande. Une commande concurrente réellement validée renvoie **409**, sans licence supplémentaire ni divulgation de sa clé. Voir les [limites de confirmation](../tests/test_payment_confirmation_boundaries.py) et les [preuves actuelles](quality-audit-2026-10-23.md#braces-resolution). La fonction de finalisation n’a aucune branche statique ; son nettoyage sur exception est testé. Ce pourcentage concerne les fonctions critiques nommées, pas toutes les intégrations ni tous les incidents possibles en production.

Des tests HTTP couvrent les erreurs avant/après commit de la commande, les écritures du stockage d'attente,
les clés de devis absentes/tronquées, ainsi que RPC et historique indisponibles. Un **503** préserve la reprise
avec la même transaction ; un commit incertain conserve son affectation à usage unique. Un état `confirmed`
sans commande validée en base n'est jamais un succès. Restaurez la clé d'origine depuis sa sauvegarde,
sans la remplacer par une nouvelle.
Un historique vide/de type incorrect ou un historique UNI inaccessible bloque le règlement. Un fichier de paiements en attente corrompu est conservé jusqu’à sa restauration ; les identifiants RPC sont exclus des erreurs publiques et des journaux checkout.
Les soldes Solana doivent être finis et positifs ou nuls ; montants SPL bruts et décimales sont validés.
Les tests Ed25519 réels refusent signatures malformées, clés de petit ordre et preuves d'un autre client,
site ou transfert. Les tests de remboursement refusent les retraits inconnus, inéligibles,
déjà diffusés ou aux montants invalides, sans créditer de fonds.

Voir [résultats complémentaires et limites](quality-audit-2026-10-23.md#follow-up).

### Production et les 34 omissions initiales

Les **34 cas initialement ignorés ont été exécutés**. Cinq cas utilisent un volume temporaire sensible à la casse ; trois cas Compose analysent les vraies configurations avec des valeurs synthétiques, sans résoudre les fichiers secrets de déploiement ; deux contrôles CSS suivent les imports actuels et la feuille de polices locale ; le badge KOVA indique **59 tests réellement réussis**. Les erreurs de configuration font désormais échouer le test au lieu de l’ignorer.

Les 23 cas live initiaux ont tourné en production, avec un nouveau contrôle d’invoke non payé. Le health public de SKOPOS doit préserver la confidentialité ; le statut de flotte est lu avec la clé opérateur, et une requête sans paiement doit recevoir **402**. Le runner SSH garde les clés en mémoire, lie les tunnels à loopback et les ferme ensuite. Aucun canal de paiement, transfert, émission de licence ou travail LLM n’est déclenché. La suite locale conserve ses 24 sondes live désactivées par défaut ; les mêmes cas ont réussi en production. Les sélections se recoupent et leurs nombres ne doivent pas être additionnés sans distinction.

**88 cas de règlement** ont été ajoutés sur SQLite et PostgreSQL : pannes de signature et de triggers réels, huit arrêts brutaux de processus enfants après insertion du reçu, répétitions concurrentes, réserves épuisées et historique ancien incomplet. Solde, grand livre, retrait/réserve et reçu signé sont validés ensemble ; une panne annule tout. Une répétition renvoie le reçu stocké ; les clés complètes restent distinctes même si leurs 128 premiers caractères sont identiques. Un reçu JSON de type incorrect ou un montant inconnu bloque l’opération. Un ancien reçu ou une réserve manquante bloque l’opération jusqu’au rapprochement. Les sept nouvelles cibles à 100% sont `charge`, `withdraw_to_chain`, `hold`, `spend_hold`, `release_hold`, `_credit` de `UniWalletService`, et `issue_receipt`.

**Les corrections UNI restent locales et n’ont pas été déployées par cet audit.** Les sondes vérifient la version active, pas la présence des corrections. Voir les [preuves pour chaque omission](quality-audit-2026-10-23.md#skip-resolution).

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-live-contracts \
  "$PYTHON" scripts/run_ecosystem_live_tests.py --ssh-host factory-vps \
  --skopos-ssh-host skopos-vps
```

## 2. Une transaction de checkout, étape par étape

1. Le client authentifié appelle `POST /api/payment/create`. Le serveur prend le prix du catalogue,
   ignore le montant fourni par le client et émet un **devis d'une heure** lié au client, au produit,
   au site, au réseau, au jeton et au destinataire. Factory accepte **USDT/USDC**, pas ETH/SOL comme montant en USD.
2. Le client transfère le jeton annoncé sur le réseau annoncé. `payment_id` identifie le devis interne ;
   `tx_hash` identifie la transaction blockchain. Ni le hash ni une réponse HTTP réussie ne prouvent le paiement.
3. `GET /api/payment/proof/{payment_id}?tx_hash=...` fournit le message à signer.
   `POST /api/payment/confirm/{payment_id}` reçoit `tx_hash` et `payer_signature`. La preuve lie le
   transfert à l'achat de ce client et à son site. EVM prend en charge EIP-191 et la vérification EIP-1271 des portefeuilles de contrat.
4. Le reçu, le réseau, le jeton, le destinataire, le montant et les confirmations sont contrôlés.
   La tolérance de montant de Factory est **0,1 %** ; `AIFACTORY_PAYMENT_MIN_CONFIRMATIONS` vaut
   **2** par défaut, minimum 1. Consultez la configuration effective via `GET /api/payment/chains` ;
   les autres services ont leurs propres règles.
5. Le registre persistant d'affectation empêche de réutiliser un transfert entre checkout, pilot,
   financement de canal, invocation payante et recharge UNI. La casse du hash EVM ou l'absence de `0x`
   ne contournent pas la protection ; les signatures Solana restent sensibles à la casse.
   Un achat réussi crée **une commande et une licence**.

| Résultat / état | Sens et action |
| --- | --- |
| `pending` | Le devis existe ; le règlement n'est pas terminé |
| `pending_confirmation` | Le même transfert attend des confirmations ; réessayer avec le même hash |
| `confirmed` | Commande/licence créées ou retrouvées ; conserver la réponse et `order_id` |
| Métadonnées `claim_review` | Preuve du payeur manquante/invalide, ou paiement tardif/heure inconnue ; conserver le dossier pour l'opérateur |
| Ancien `confirming` après redémarrage | Reprise dans un état réessayable, sans bloquer définitivement un client ayant payé |

Les devis terminés quittent le stockage d'attente : une lecture ultérieure peut renvoyer **404**.
Cela ne prouve pas la perte du paiement ; consultez les commandes du client. Une nouvelle tentative
retrouve la commande déjà validée en base. Un changement de prix ou une rotation de la clé de connexion
ne modifie pas le devis scellé. Un devis expiré peut récupérer un transfert effectué à temps au prix initial ;
un paiement tardif ou d'heure inconnue exige une revue. Sauvegardez `checkout_quote.key` avec les devis ;
ne copiez pas son contenu dans les journaux ou la documentation.

## 3. Séparer achat, crédit et remboursement

- Le checkout achète une licence ; il **ne crédite pas en plus des UNI dépensables**. Le financement
  du portefeuille passe par `/api/uni/topup/confirm`, avec la même protection d'usage unique.
- La recharge par carte du hub vérifie la signature du webhook Stripe et récupère la session checkout
  enregistrée ; l'événement ne peut choisir ni le client ni le montant crédité. Les livraisons répétées ou
  concurrentes créditent une seule fois ; une session impayée ou de l'argent test sur un hub live ne crédite rien.
  Les tests couvrent aussi webhook perdu, frais/taxes, remboursements, litiges et annulation avant la fin du paiement.
- Dans le grand livre UNI, `balance_uni` est l'argent **non réservé**, `hold_uni` l'argent réservé.
  Réserver 600 sur 1 000 laisse 400 disponibles, sans soustraire la réserve une seconde fois jusqu'à zéro.
  `hold_charge` consomme la réserve ; `charge` consomme le solde disponible. Les instantanés du livre doivent correspondre au portefeuille.
- Un retrait échoué utilise `refund_due` persistant : solde, écriture de remboursement et état final
  sont validés atomiquement. Relance, redémarrage et workers concurrents doivent rembourser une seule fois.
  Les frais ne sont pas une recette avant un versement réussi ; les anciens frais sont extournés au remboursement.
- Une transaction envoyée ou de résultat inconnu **ne se rembourse pas automatiquement** : il faut
  d'abord la rapprocher pour éviter de payer le versement et le remboursement interne. Le compte rendu
  actuel indique que l'adaptateur de versement UNI réel en chaîne n'est pas implémenté ; une demande en file ne prouve pas une diffusion.
- KOVA refuse les transferts antérieurs à la facture. SaaS lie facture/paiement à une seule clé API.
  eSIM persiste l'intention d'achat avant l'appel fournisseur : un timeout ambigu devient
  `procurement_pending`, puis est rapproché par l'ID de transaction fournisseur avant tout nouvel achat.

## 4. Matrice de régression

| Invariant | Tests principaux |
| --- | --- |
| Prix serveur, destinataire, stablecoin, reçu, montant et confirmations | [Prix](../tests/test_payment_price_control.py), [sécurité](../tests/test_payment_security.py), [régressions d'audit](../tests/test_payment_audit_regressions.py) |
| Un transfert entre portes ; liaison payeur/site ; revue opérateur | [Usage unique](../tests/test_payment_transfer_single_use.py) |
| Attente des confirmations, relance et visibilité de la commande | [API d'attente](../tests/test_payment_confirm_pending_api.py) |
| KOVA → SaaS ; devis ; véritable `os._exit(9)` avant/après commit de licence ; réserves/remboursements/frais UNI | [Reprise SQLite/PostgreSQL](../tests/test_payment_chain_recovery.py) |
| Résultat fournisseur eSIM ambigu, redémarrage et protection contre l'achat en double | [Reprise boutique](https://github.com/alexar76/esim-operator-kit/blob/main/store/test/procurement-recovery.test.js), [règlement rails](https://github.com/alexar76/esim-operator-kit/blob/main/rails/test/settlement.test.js) |
| Isolation des identifiants Stripe, signature webhook, crédit unique et annulations | [Intégration des secrets](../tests/test_hub_card_secret_scope.py), [cartes du hub](https://github.com/alexar76/aimarket-hub/blob/main/tests/test_card_topup.py) |
| Reprise après erreurs HTTP/stockage/RPC ; historique corrompu ; champs du devis | [Intégration des erreurs](../tests/test_payment_failure_recovery.py) |
| Ed25519 réel, encodages invalides, échec du contrat ; éligibilité et rollback du remboursement | [Preuves cryptographiques](../tests/test_payment_claim_crypto.py), [gardes de remboursement](../tests/test_payment_refund_guards.py) |
| Sauvegarde de la clé, corruption et publication atomique entre workers | [Tests de clé persistante](../tests/test_payment_quote_key.py) |

## 5. Exécution locale

Depuis la racine du dépôt, utilisez Python 3.12, les requirements racine et les sources locales de
`aimarket-hub` installés dans l'environnement de test. L'environnement audité est `.venv-quality` ;
`AIFACTORY_TEST_PYTHON` sélectionne un autre environnement préparé. Voir la préparation dans le
[rapport qualité](quality-audit-2026-10-23.md#reproduction). Les fixtures isolent les stockages et simulent
les paiements externes ; ne recopiez pas leurs options stub en production.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
  "$PYTHON" -m pytest -q -ra --timeout=60 \
  tests/test_payment_chain_recovery.py \
  tests/test_payment_failure_recovery.py \
  tests/test_payment_confirmation_boundaries.py \
  tests/test_uni_settlement_atomicity.py tests/test_uni_settlement_boundaries.py \
  tests/test_payment_claim_crypto.py \
  tests/test_payment_quote_key.py \
  tests/test_payment_refund_guards.py \
  tests/test_payment_security.py \
  tests/test_payment_price_control.py \
  tests/test_payment_transfer_single_use.py \
  tests/test_payment_confirm_pending_api.py \
  tests/test_payment_audit_regressions.py
```

Sans `PAYMENT_FIX_TEST_PG_URL`, les cas PostgreSQL sont **ignorés**, pas réussis. Pour les 50 cas initiaux et les nouveaux scénarios d’erreur,
utilisez un cluster PostgreSQL local jetable. La fixture crée et supprime des schémas : **ne ciblez
jamais une base de production**. Le bloc exige les outils PostgreSQL dans `PATH` et le port local 55487 libre ;
le sous-shell arrête le cluster même si les tests échouent.

```bash
(
  set -eu
  PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
  payment_pg_dir=$(mktemp -d /tmp/aicom-payment-pg.XXXXXX)
  initdb -D "$payment_pg_dir/db" -U aicom_test \
    --auth-local=trust --auth-host=trust --no-locale --encoding=UTF8
  pg_ctl -D "$payment_pg_dir/db" -l "$payment_pg_dir/server.log" \
    -o "-h 127.0.0.1 -p 55487 -k $payment_pg_dir" -w start
  trap 'pg_ctl -D "$payment_pg_dir/db" -m fast -w stop' EXIT
  PAYMENT_FIX_TEST_PG_URL=postgresql://aicom_test@127.0.0.1:55487/postgres \
    USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
    "$PYTHON" -m pytest -q -ra --timeout=60 tests/test_payment_chain_recovery.py \
      tests/test_payment_failure_recovery.py tests/test_payment_claim_crypto.py \
      tests/test_payment_refund_guards.py tests/test_payment_quote_key.py \
      tests/test_payment_confirmation_boundaries.py \
      tests/test_uni_settlement_atomicity.py tests/test_uni_settlement_boundaries.py
)
```

Exécutez aussi les scénarios distincts du hub et eSIM. Les cas Node.js exigent Node 20+ et les dépendances installées depuis le lockfile de chaque paquet. Stripe et le fournisseur sont simulés : ces tests ne débitent aucune carte et n’achètent aucune eSIM.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
hub_test_python=$("$PYTHON" -c 'import sys; print(sys.executable)')
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
  "$PYTHON" -m pytest -q --timeout=60 tests/test_hub_card_secret_scope.py
(
  cd aimarket-hub
  "$hub_test_python" -m pytest -q tests/test_card_topup.py
)
node --test esim-kit/store/test/procurement-recovery.test.js
node --test esim-kit/rails/test/settlement.test.js
```

Un code de sortie non nul, timeout, erreur de collecte ou test ignoré ne prouve pas la réussite du
scénario concerné. Ces commandes ne diffusent aucune transaction blockchain.

Les runners Factory exigent **100% des lignes et branches mesurées pour les 13 fonctions du coverage gate**. CI fournit désormais un PostgreSQL isolé ; les 450 cas financiers ont aussi réussi sur PostgreSQL 16. Le contrôle local complet nécessite `PAYMENT_FIX_TEST_PG_URL` vers un cluster temporaire de test. Un rapport absent, malformé ou sans branches échoue. La couverture globale reste distincte.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
PAYMENT_FIX_TEST_PG_URL="${PAYMENT_FIX_TEST_PG_URL:?use a disposable PostgreSQL test cluster}" \
  USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-quality \
  AIFACTORY_PYTEST_HARD_CAP_SEC=1800 \
  "$PYTHON" scripts/run_factory_pytest_ci.py --timeout-method=signal
```

## 6. Rapprocher une transaction réelle

Conservez réseau/chain ID, hash canonique, contrat du jeton ou mint, destinataire, montant brut et
décimales, reçu/bloc/confirmations, heure du bloc, `payment_id`, `order_id`, porte d'affectation et IDs
du livre/des reçus. Comparez-les au devis et au client authentifié ; excluez clés privées, jetons d'accès
et contenu des licences des preuves publiques. HTTP **400/422** indique des données invalides/non vérifiées ;
**401/403**, un problème d'authentification, de propriétaire ou de preuve ; **409**, un conflit d'usage/revue ;
**503**, une vérification ou un stockage désactivé/indisponible. Consultez le détail : aucune erreur ne justifie à elle seule de faire repayer le client.

Un administrateur autorisé consulte `/api/payment/admin/claims` et approuve via
`/api/payment/admin/claims/{payment_id}/approve` ; les contrôles du devis, de la chaîne et d'usage unique
restent actifs. Revenir à une ancienne version du logiciel n'annule pas un transfert blockchain :
rapprochez avant de rembourser ou de créer un autre paiement. Configuration :
[activation des paiements](payment-enable-runbook.md), [réseaux](chain-networks.md),
[UNI et LIVE](uni-and-live.fr.md), [recharges par carte du hub](https://github.com/alexar76/aimarket-hub/blob/main/docs/card-topup.md).
