# Acheter des crédits par carte (Stripe Checkout)

> **English:** [card-topup.md](./card-topup.md) · **Русский:** [card-topup.ru.md](./card-topup.ru.md) · **Español:** [card-topup.es.md](./card-topup.es.md) · **中文:** [card-topup.zh.md](./card-topup.zh.md)
>
> Code : [`card_topup.py`](../aimarket_hub/card_topup.py) · routes dans [`hub_routes/accounts.py`](../aimarket_hub/hub_routes/accounts.py) · [`credits.py`](../aimarket_hub/credits.py) (`deposit`) · tests [`test_card_topup.py`](../tests/test_card_topup.py)

La [recharge en USDC](credits-topup.fr.md) permet à un agent doté d'un portefeuille d'alimenter son
compte de crédits. Une personne avec une carte et sans portefeuille ne le pouvait pas. Cette porte
accepte une carte comme n'importe quelle boutique et inscrit l'argent sur la **même** ligne du
registre qu'une recharge USDC (`CreditsLedger.deposit`, type `topup`) ; ensuite, tout ce qui passe
par le rail de crédits — appels payants, [mandats](mandates.fr.md), sous-traitance, A2A — fonctionne
de la même façon.

**Statut.** Disponible depuis le 2026-10-20 (3.16.0), **désactivé par défaut**. Vérifié dans le sandbox officiel de Stripe les 20–21 octobre 2026 : paiements sans taxe, paiement Managed Payments avec TVA non nulle, remboursements complets avec et sans taxe, et litige. Le périmètre exact et les lacunes sont détaillés ci-dessous. Aucun argent réel n'a été transféré.

<a id="sandbox-verification"></a>
## Vérifié dans le sandbox officiel de Stripe

Ces vérifications utilisent Checkout hébergé par Stripe, des cartes de test, de vraies réponses de Stripe API et des événements signés transmis par la CLI officielle de Stripe à un hub local isolé. Elles sont distinctes des tests unitaires qui simulent Stripe à la frontière HTTP. Le [rapport de vérification](evidence/stripe-sandbox-2026-10-21.json) contient les montants, identifiants d'événements, résultats de livraison et contrôles du registre ; ses horodatages sont en UTC.

| Scénario | Résultat observé |
|---|---|
| `off` : paiement sans taxe | 5 $ payés, exactement 5 $ crédités une fois via `checkout.session.completed` ; une nouvelle livraison n'a ajouté aucun crédit. |
| `stripe_tax` | Création et ouverture de Checkout vérifiées dans le sandbox. Paiement, taxe non nulle, remboursement et litige dans ce mode **non vérifiés**. |
| `managed_payments` + `exclusive` | Acheteur de test aux Pays-Bas : 5 $ + 1,05 $ de TVA (21 %) = 6,05 $ USD ; `paid`, calcul fiscal `complete`, responsabilité `stripe`. `refresh` a crédité exactement 5 $ une fois. Le webhook du paiement initial n'a pas été vérifié lors de cet essai. |
| Remboursement complet avec taxe | Stripe API a renvoyé `succeeded` pour 6,05 $, dont 1,05 $ de taxe. L'événement signé `charge.refunded` a reçu HTTP 200 et le statut du hub est devenu `refunded`. Le remboursement a été demandé par l'opérateur ; un remboursement automatique à l'initiative de Stripe n'a pas été testé. |
| Remboursement complet sans taxe (`off`) | 5 $ remboursés, statut `succeeded` ; `charge.refunded` signé a reçu HTTP 200 et le statut est devenu `refunded`. |
| Litige sans taxe (`off`) | La carte `4000 0000 0000 0259` a produit un vrai litige de sandbox de 5 $, motif `fraudulent`, statut Stripe `needs_response` ; `charge.dispute.created` a placé la recharge en `disputed`. |
| Événements répétés et tardifs | Stripe a renvoyé les événements de paiement, remboursement et litige. Les statuts `refunded`/`disputed` ont résisté au paiement tardif ; chaque compte a gardé une seule écriture `topup` de 5 $, sans crédit supplémentaire. |
| Taxe incluse (`inclusive`) | La validation des montants est couverte par des tests locaux ; Checkout payé et remboursement dans le sandbox officiel **non vérifiés**. |

**Un défaut d'ordre détecté et corrigé.** Lors du premier essai, Stripe a livré le litige avant la fin du paiement ; l'ancien gestionnaire a répondu `ignored`. Le hub cherche désormais la Checkout Session par PaymentIntent, vérifie son association à une recharge locale et rapproche le paiement selon le mode fiscal enregistré avant d'inscrire le remboursement ou le litige. Un échec de recherche renvoie une erreur permettant une nouvelle tentative. Un vrai remboursement a ensuite été volontairement livré avant le paiement : il a été enregistré correctement et la livraison tardive du paiement a conservé `refunded`. L'ordre « litige avant paiement » est également couvert par un test de régression ; le renvoi a récupéré le premier litige et un nouvel essai paiement/litige a réussi. Les contrôles de session et de montants restent appliqués.

**Politique de solde confirmée :** remboursements et litiges enregistrent le statut et journalisent le compte, sans retirer automatiquement le crédit ni bloquer le compte. Chaque compte testé conservait 5 $. L'opérateur décide et applique toute correction du solde.

**Non vérifiés dans le sandbox officiel :** remboursements partiels, remboursements asynchrones en échec, gain/perte d'un litige, litiges Managed Payments et paiements/remboursements `stripe_tax` et `inclusive`. Le succès dans le sandbox ne confirme pas l'éligibilité à Managed Payments en production ; le mode de production reste une décision de l'opérateur.

Références : [cartes et litiges de test Stripe](https://docs.stripe.com/testing#disputes), [API de remboursement](https://docs.stripe.com/api/refunds/create), [recherche de Checkout Session par PaymentIntent](https://docs.stripe.com/api/checkout/sessions/list).

## Sommaire

- [Vérifié dans le sandbox officiel de Stripe](#sandbox-verification)
- [En bref](#en-bref)
- [Ce que voit l'acheteur](#ce-que-voit-lacheteur)
- [Ce que vérifie le hub](#ce-que-vérifie-le-hub)
- [Taxe sur les ventes : trois modes](#taxe-sur-les-ventes--trois-modes)
- [Un webhook jamais arrivé](#un-webhook-jamais-arrivé)
- [Remboursements et litiges](#remboursements-et-litiges)
- [Limites et réglages](#limites-et-réglages)
- [Ce que cette porte ne fait pas](#ce-que-cette-porte-ne-fait-pas)
- [Opérateur](#opérateur)
- [Tester dans le sandbox Stripe, pas à pas](#tester-dans-le-sandbox-stripe-pas-à-pas)

## En bref

```bash
# 1. Ouvrir un paiement de 10 $ de crédit pour votre compte.
curl -s -X POST $HUB/ai-market/v2/account/topup/card -H "X-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d '{"amount_usd": 10}'
# → 201 {"topup_id": "ctp_…", "checkout_url": "https://checkout.stripe.com/…", "status": "open",
#        "amount_usd": 10, "charge_usd": 10, "fee_usd": 0, "expires_at": "…", "status_url": "…"}

# 2. Une personne ouvre checkout_url et paie. Stripe la renvoie vers status_url.

# 3. Le crédit arrive quand Stripe confirme ; l'état se lit à tout moment :
curl -s $HUB/ai-market/v2/card-topups/ctp_…
```

Un agent ne peut pas payer par carte lui-même : il transmet `checkout_url` à son humain et attend
(ou interroge l'état). C'est tout l'intérêt de cette porte : l'humain paie, l'agent dépense dans les
limites de son [mandat](mandates.fr.md).

## Ce que voit l'acheteur

Une page hébergée par Stripe (`checkout.stripe.com`) avec une ligne : « Prepaid credit on <hôte du
hub>: $10.00 » (plus « incl. $x card fee » si l'opérateur fixe un supplément). Avec un mode de taxe
actif, la page demande aussi une adresse de facturation et affiche la taxe ; avec Managed Payments
apparaissent les conditions et le nom de vendeur de Stripe. La page expire au bout d'**une heure** ;
un nouveau paiement est à une requête. Après le paiement, Stripe renvoie l'acheteur vers
`status_url`, qui répond en JSON avec l'état de la recharge.

Aucun numéro de carte n'atteint le hub : il n'en voit jamais. Le périmètre PCI reste chez Stripe.

## Ce que vérifie le hub

Stripe appelle `POST /ai-market/v2/stripe/webhook`. Avant de lire quoi que ce soit, la
`Stripe-Signature` doit être valide : HMAC-SHA256 sur `t.payload` avec le secret de l'endpoint, `t`
de moins de cinq minutes, comparaison à temps constant (plusieurs signatures `v1` sont acceptées
pendant la rotation d'un secret). Ensuite la session de l'événement est confrontée à la ligne ouverte
par le hub — jamais l'inverse :

| Vérification | Pourquoi |
|---|---|
| l'id de recharge est un id ouvert par ce hub | un événement nomme une recharge ; il ne peut pas en créer une |
| l'id de session est celui que Stripe a donné à l'ouverture | une session payée d'un autre paiement ne peut pas passer pour celle-ci |
| `payment_status == "paid"` | une session terminée mais non payée (asynchrone) ne crédite encore rien |
| `currency == "usd"` et les montants correspondent au débit demandé par le hub, selon le mode de taxe d'ouverture ([plus bas](#taxe-sur-les-ventes--trois-modes)) | le montant et le compte sont ceux du hub, pas de l'événement |
| avec une clé réelle (`sk_live_…`, `rk_live_…`), la session est `livemode` | l'argent de test ne crédite jamais un hub réel |

Le crédit va au compte lié à l'ouverture, pour le montant demandé. Ni le supplément carte ni la taxe
ne sont crédités. La ligne du registre a pour référence l'id de session : un événement relivré — ou
deux livraisons simultanées — ne crédite qu'une fois. Stripe connaît l'id de la recharge, jamais le
compte.

Les événements sur autre chose sont acquittés (`200`) et ignorés, pour que Stripe ne les relance pas
pendant des jours. `checkout.session.expired` clôt la ligne.

## Taxe sur les ventes : trois modes

Qui calcule et doit la taxe sur les ventes (TVA/VAT, GST, sales tax américaine) est une décision de
l'opérateur. C'est un seul réglage, `AIMARKET_CARD_TOPUP_TAX`, et le hub garde le mode **dans la
ligne de chaque paiement** : un paiement ouvert sous un mode est vérifié sous ce mode même si
l'opérateur change le réglage avant le paiement.

| Mode | Vendeur | Qui calcule la taxe | Qui la déclare et la verse | Frais Stripe en plus des frais carte |
|---|---|---|---|---|
| `off` (défaut) | l'opérateur | personne, dans Stripe | l'opérateur, hors Stripe | — |
| `stripe_tax` | l'opérateur | Stripe Tax, d'après l'adresse de l'acheteur | l'opérateur (Stripe Tax prépare les rapports) | tarif Stripe Tax |
| `managed_payments` | **Stripe** (marchand officiel, merchant of record) | Stripe | Stripe | 3,5 % par transaction |

**Ce qui change dans le paiement ouvert par le hub :**

| Mode | Paramètres supplémentaires de la Checkout Session | Version de l'API |
|---|---|---|
| `off` | aucun | `2024-06-20` |
| `stripe_tax` | `automatic_tax[enabled]=true`, `billing_address_collection=required`, `price_data[tax_behavior]`, `product_data[tax_code]` | `2024-06-20` |
| `managed_payments` | `managed_payments[enabled]=true`, `price_data[tax_behavior]`, `product_data[tax_code]`. Ni `automatic_tax`, ni `billing_address_collection`, ni paramètres de moyens de paiement : Stripe les refuse à côté de Managed Payments, car il collecte l'adresse et choisit les moyens lui-même. | `2025-03-31.basil` (la première avec Managed Payments) ; le hub relit aussi ce paiement avec elle |

**Taxe en sus ou incluse.** `AIMARKET_CARD_TOPUP_TAX_BEHAVIOR` :

- `exclusive` (défaut) : la taxe s'ajoute. Une recharge de 10 $ pour un acheteur d'un pays à 21 % de
  TVA lui coûte 12,10 $ ; le hub vérifie que l'`amount_subtotal` de la session vaut exactement 10 $
  et que `amount_total` vaut exactement `amount_subtotal + total_details.amount_tax` — aucune remise
  ni autre ligne ne peut le déplacer. 10 $ de crédit sont crédités ; les 2,10 $ sont notés dans la
  ligne comme `tax_usd`.
- `inclusive` : la taxe est dans le prix. L'acheteur paie 10 $, taxe comprise, l'opérateur reçoit
  moins ; le hub vérifie que `amount_total` vaut exactement 10 $ et que la taxe n'est pas négative.
  10 $ de crédit sont crédités.

**Le code fiscal du produit** : `AIMARKET_CARD_TOPUP_TAX_CODE`, par défaut `txcd_10000000`
(« General — Electronically Supplied Services »). Pour une place de marché de capacités d'IA,
`txcd_10105002` (« IA en tant que service — cloud — usage professionnel ») ou `txcd_10701410`
(« Services d'information fournis par voie électronique — usage professionnel ») peuvent mieux
convenir ; le bon code est une question pour l'expert-comptable de l'opérateur. Avec Managed
Payments, le code doit figurer dans la liste Stripe « Eligible for Managed Payments ».

**Un réglage que le hub ne comprend pas ferme la porte** plutôt que d'ouvrir des paiements au
hasard : un mode inconnu, un code fiscal qui n'est pas `txcd_` + 8 chiffres ou un comportement autre
que `exclusive`/`inclusive` font afficher au well-known `"enabled": false` avec la raison.

**Ce que voient l'acheteur et le well-known.** `payment_rails.credits.topup_card.tax` vaut
`{"mode": "off"}` ou `{"mode", "behavior", "seller_of_record": "operator" | "stripe"}`. Une fois
payée, l'état de la recharge porte `tax: {mode, behavior, tax_usd}`.

### Managed Payments : à lire avant de l'activer

Stripe décide qui peut l'utiliser, et ses conditions comptent ici :

- **Ventes directes uniquement.** La page d'éligibilité de Stripe indique que le produit doit être
  vendu « directement aux clients, et non via une plateforme ou une place de marché ». Le hub est une
  place de marché : le crédit acheté ici se dépense en capacités de fournisseurs indépendants. Que
  Stripe accepte du crédit prépayé d'une place de marché en Managed Payments relève de Stripe ;
  demandez-lui avant de compter dessus.
- **Produits numériques et automatisés uniquement**, avec un code fiscal éligible ; entreprise dans
  un pays pris en charge (la liste comprend les pays de l'UE, le Royaume-Uni, la Suisse, la Norvège,
  les États-Unis, le Canada, l'Australie, Hong Kong, le Japon et Singapour).
- **Stripe peut rembourser** un achat sous 60 jours pour éviter une rétrofacturation, et applique
  les délais de rétractation. Chaque remboursement arrive au hub comme `charge.refunded`
  ([plus bas](#remboursements-et-litiges)).
- Activez-le dans le Dashboard (Settings → Managed Payments) avant de régler le mode, sinon Stripe
  refusera d'ouvrir le paiement (`502 stripe_refused`, rien n'est débité).

### Stripe Tax : avant de l'activer

Dans le Dashboard : Tax → réglages (adresse d'origine, code fiscal par défaut) et **immatriculations**
— Stripe Tax ne collecte la taxe que là où l'opérateur est immatriculé. Sans immatriculation pour le
pays de l'acheteur, la taxe est nulle, ce que le hub accepte (`amount_tax: 0`).

## Un webhook jamais arrivé

`POST /ai-market/v2/card-topups/{id}/refresh` demande la session à Stripe et applique les mêmes
vérifications. Quiconque détient l'id peut l'appeler (avec une limite par appelant) : il ne peut
créditer que le compte lié au paiement. Une recharge payée n'est donc jamais perdue à cause d'une
livraison perdue.

## Remboursements et litiges

- **`charge.refunded`** : un remboursement fait dans Stripe (par l'opérateur ou, avec Managed
  Payments, par Stripe lui-même) passe la recharge en `refunded` et journalise une erreur avec le
  compte et le montant. Le crédit n'est **pas** repris automatiquement : il est peut-être déjà
  dépensé, et rendre un solde négatif est une décision, pas un réflexe. L'opérateur le corrige à la main.
- **`charge.dispute.created`** : une rétrofacturation passe la recharge en `disputed` et journalise
  une erreur. Le compte n'est pas gelé automatiquement.

## Limites et réglages

| Variable | Défaut | Effet |
|---|---|---|
| `AIMARKET_CARD_TOPUP_MIN_USD` | `5` | Recharge minimale (jamais sous les 0,50 $ de Stripe). |
| `AIMARKET_CARD_TOPUP_MAX_USD` | `100` | Recharge maximale par paiement. |
| `AIMARKET_CARD_TOPUP_DAILY_USD` | `200` | Le plus qu'un compte peut acheter par carte en 24 h. Les paiements ouverts comptent jusqu'à expiration (1 heure), car chacun peut encore être payé ; une recharge remboursée ou contestée continue de compter, car son crédit reste sur le compte. Des paiements ouverts au même instant sont vérifiés les uns contre les autres : ensemble, ils ne peuvent pas dépasser la limite. |
| `AIMARKET_CARD_TOPUP_FEE_PCT` | `0` | Supplément en pourcentage, affiché avant paiement et non crédité. `0` : l'opérateur absorbe les frais de carte. Là où les suppléments carte sont restreints, gardez `0`. |
| `AIMARKET_CARD_TOPUP_FEE_FIXED_USD` | `0` | Supplément fixe par paiement. |
| `AIMARKET_CARD_TOPUP_TAX` | `off` | `off`, `stripe_tax` ou `managed_payments` ([plus haut](#taxe-sur-les-ventes--trois-modes)). |
| `AIMARKET_CARD_TOPUP_TAX_BEHAVIOR` | `exclusive` | `exclusive` (en sus) ou `inclusive` (dans le prix). |
| `AIMARKET_CARD_TOPUP_TAX_CODE` | `txcd_10000000` | Le code fiscal du produit chez Stripe. |

La limite quotidienne est ce qui borne une carte volée : le litige arrive quand le crédit est
peut-être déjà dépensé, et le hub ne peut pas récupérer un crédit dépensé.

## Ce que cette porte ne fait pas

- **Reprendre du crédit** après un remboursement ou un litige : journalisé, corrigé à la main.
- **Geler un compte** en cas de litige.
- **Émettre des factures.** Stripe envoie son propre reçu à l'e-mail du payeur si le compte Stripe
  est configuré ainsi (avec Managed Payments, toujours). La facture légale au nom de l'opérateur et
  la comptabilisation de la vente relèvent de l'opérateur et de sa juridiction.

## Opérateur

### Ouvrir la porte

1. Un compte Stripe au nom de l'opérateur. **Son pays ne peut pas être changé ensuite** ; pour de
   l'argent réel, ce doit être le pays de l'entité juridique qui reçoit les versements.
2. Une **clé restreinte** avec une seule permission, *Checkout Sessions: Write* (Developers → API
   keys → Create restricted key → Custom permissions). C'est tout ce qu'il faut au hub : ouvrir un
   paiement et le relire. Mettez-la dans `STRIPE_SECRET_KEY_FILE` (docker secret) ou `STRIPE_SECRET_KEY`.
3. Un endpoint de webhook dans le Dashboard : `https://<hub>/ai-market/v2/stripe/webhook`,
   événements `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   `checkout.session.expired`, `charge.dispute.created`, `charge.refunded`. Son secret de signature
   va dans `STRIPE_WEBHOOK_SECRET_FILE` (ou `STRIPE_WEBHOOK_SECRET`).
4. `AIMARKET_CARD_TOPUP_ENABLED=1` ; le rail de crédits doit être actif (`AIMARKET_CREDITS_ENABLED=1`).
5. En option, un mode de taxe (`AIMARKET_CARD_TOPUP_TAX`) après les étapes de ce mode dans le Dashboard.

Le well-known indique si la porte est ouverte et, sinon, pourquoi :
`payment_rails.credits.topup_card` = `{"enabled", "provider": "stripe-checkout", "create",
"status", "currency", "min_usd", "max_usd", "daily_usd", "fee_pct", "fee_fixed_usd", "tax"}` ou
`{"enabled": false, "reason": "…"}`.

### Routes

| Route | Qui | Quoi |
|---|---|---|
| `POST /ai-market/v2/account/topup/card` | la `X-API-Key` du compte | ouvrir un paiement (`{"amount_usd"}`) → `201` avec `checkout_url` ; 6 par minute et par compte |
| `GET /ai-market/v2/card-topups/{id}` | quiconque a l'id | état ; le compte seulement pour sa propre clé |
| `POST /ai-market/v2/card-topups/{id}/refresh` | quiconque a l'id | rapprochement avec Stripe, crédit si payé |
| `POST /ai-market/v2/stripe/webhook` | Stripe (signé) | événements |
| `GET /ai-market/v2/account/topups` | la clé du compte | liste `card_topups` à côté des recharges USDC `topups` |

### Erreurs

| Code | `error` | Sens |
|---|---|---|
| 400 | `amount_invalid`, `amount_out_of_range` | pas en centimes entiers, ou hors min/max |
| 400 | `signature_invalid` | la signature du webhook n'est pas valide (rien n'est lu) |
| 401 | `api_key_required` | `X-API-Key` absente ou inconnue |
| 429 | `daily_topup_limit`, `too_many_attempts` | limite quotidienne dépassée (paiements ouverts compris) ou trop de paiements par minute |
| 502 | `stripe_refused` | Stripe n'a pas ouvert le paiement (par exemple Managed Payments non activé ou permission de clé manquante) ; rien n'est débité |
| 503 | `card_topup_unavailable`, `stripe_unavailable` | la porte est fermée (la raison l'explique) ou Stripe est injoignable |

Le webhook répond `{"received": true, "outcome": …}` : `credited`, `already_credited`, `pending`,
`refused` (montants incohérents : journalisé comme erreur, rien n'est crédité), `expired`,
`disputed`, `refunded` ou `ignored`.

### Table

`card_topups` (migrations 056 et 057) : une ligne par paiement — `topup_id`, `account_id`,
`amount_cents` (crédit), `charge_cents` (ce que paie la carte hors taxe), `status` (`new` → `open` →
`credited` / `expired` / `failed` / `disputed` / `refunded`), `session_id`, `payment_intent`,
`livemode`, `credited_mc`, `tax_mode`, `tax_behavior`, `tax_cents`, horodatages.

## Tester dans le sandbox Stripe, pas à pas

C'est ainsi que la porte a été éprouvée le 2026-10-20 ; refaites-le avant le passage en réel et
après tout changement de mode de taxe. Aucun argent réel ne circule ici.

1. **Un sandbox.** Inscrivez-vous sur stripe.com et sautez toutes les étapes d'activation
   (documents, compte bancaire). Dans le Dashboard, ouvrez le sandbox (un bandeau « Sandbox » en haut).
2. **Une clé restreinte** avec *Checkout Sessions: Write* seulement. Copiez-la et enregistrez-la
   directement depuis le presse-papiers, pour qu'elle ne soit jamais collée dans un chat ou un
   terminal : `pbpaste > ~/.aimarket-stripe-test-key && chmod 600 ~/.aimarket-stripe-test-key`.
3. **La Stripe CLI**, pour amener les événements du sandbox à un hub sur votre machine. Si Homebrew
   refuse (Command Line Tools trop anciennes), prenez la version macOS des releases officielles sur
   GitHub et vérifiez sa somme avec `stripe-mac-checksums.txt`. Puis `stripe login` et choisissez le
   **sandbox** (ni le compte réel, ni l'ancien « Test mode »).
4. **Le secret de webhook de la CLI :** `stripe listen --print-secret > ~/.aimarket-stripe-whsec`.
5. **Un hub local** avec `AIMARKET_CREDITS_ENABLED=1 AIMARKET_CARD_TOPUP_ENABLED=1
   STRIPE_SECRET_KEY_FILE=~/.aimarket-stripe-test-key STRIPE_WEBHOOK_SECRET_FILE=~/.aimarket-stripe-whsec`
   (et le mode de taxe testé).
6. **Relayer les événements :** `stripe listen --forward-to http://127.0.0.1:<port>/ai-market/v2/stripe/webhook
   --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.expired,charge.dispute.created,charge.refunded`.
   `stripe trigger checkout.session.completed` doit afficher `[200]` : la signature est valide (avec
   un mauvais secret, ce serait `[400]`).
7. **Un paiement :** `POST /ai-market/v2/account/topup/card {"amount_usd": 5}` avec la clé d'un
   compte ; une personne ouvre `checkout_url` et paie avec `4242 4242 4242 4242`, une date future et
   un CVC quelconques.
8. **Vérifier :** la CLI affiche `checkout.session.completed` → `[200]` ; la recharge est `credited` ;
   le registre du compte a exactement une ligne `topup` pour elle. Puis `stripe events resend <evt_…>` :
   de nouveau `[200]`, et le solde ne bouge pas.
9. **En option :** un litige avec la carte `4000 0000 0000 0259` → la recharge passe en `disputed` ;
   un remboursement fait dans le Dashboard → `refunded`.
