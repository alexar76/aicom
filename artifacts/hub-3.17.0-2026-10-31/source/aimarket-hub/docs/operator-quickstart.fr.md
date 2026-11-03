# Exploiter ce hub pour vous-même

<!-- sensor-operator-guide -->
> Vous avez une station météo ou un capteur de qualité de l’air ? [Vendez les relevés via votre propre Hub + GAIA](https://github.com/alexar76/aicom/blob/main/docs/sensor-operator.fr.md).
<!-- /sensor-operator-guide -->

[English](operator-quickstart.md) · [Русский](operator-quickstart.ru.md) · [Español](operator-quickstart.es.md) · [Français](operator-quickstart.fr.md) · [中文](operator-quickstart.zh.md)

> La terminologie suit le [glossaire de localisation](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md) canonique. Les noms de produits, identifiants de protocole, URL, commandes CLI et variables d'environnement ne sont jamais traduits.

Vous l'avez cloné ou installé, et la question honnête est ce que vous y gagnez. Cette page est
le chemin complet, dans l'ordre : un hub sur votre machine en une minute, votre propre API
dessus, une adresse publique, une vérification qui vous dit à l'avance si d'autres hubs vous
admettront, puis le coup frappé à la porte. Rien de tout cela ne demande de chaîne, de contrat
ni de compte chez qui que ce soit.

## 1. Une minute, sur votre machine

```bash
pip install "aimarket-hub[pqc]"       # Python 3.11+. Ou avec uv : uvx --from "aimarket-hub[pqc]" aimarket …
aimarket quickstart --name "My hub"
aimarket serve                        # → http://localhost:9083
```

`quickstart` fait ce qu'un hub neuf ne sait pas faire seul, et peut être relancé sans risque :

1. **Enregistre les réglages du hub** dans `data/aimarket.env`, à côté de la base et des clés :
   le rail de crédits activé, la confiance envers les éditeurs évaluée par ce hub
   (`AIMARKET_ORACLE_FAMILY_URL=off`), la signature post-quantique hybride, le nom et un
   **jeton d'administration** généré. Chaque commande `aimarket` lit ce fichier, donc `serve`
   lancé depuis un nouveau terminal démarre avec les mêmes réglages. Le fichier est en `0600` :
   sauvegardez-le avec les clés. Une variable de l'environnement (systemd, `docker run -e`,
   `export`) l'emporte toujours sur lui.
2. **Publie deux capacités qui sont vraiment à vous et qui s'exécutent vraiment**, sans
   fournisseur, modèle ni réseau : `hub.ping@v1`, **gratuite**, qui répond avec un reçu signé
   par votre hub — c'est ce que lance le bac à sable d'admission d'un autre hub — et
   `hub.hello@v1`, payante, qu'un acheteur paie.
3. **Émet une clé d'acheteur** avec un petit solde et affiche les curl d'une vente complète.

Avec Docker — depuis un clone de [ce dépôt](https://github.com/alexar76/aimarket-hub) :

```bash
docker compose run --rm hub quickstart --name "My hub"
docker compose up -d                  # → http://127.0.0.1:9083
```

Réglages, clés et base vivent sur le volume `hub_data`. Chaque commande ci-dessous fonctionne de
la même façon sous la forme `docker compose run --rm hub <commande>`.

## 2. Votre propre API

```bash
aimarket add weather.now@v1 --url https://api.example.com/weather \
  --price 0.002 --pay-to 0xYourWallet --description "Current weather for a city"
```

Le hub envoie un POST `{"input": …, "product_id": …, "capability_id": …}` à votre URL et attend
`200` avec un objet JSON (ou `{"result": …}`). La recherche, MCP, A2A, l'offre x402 et le reçu
signé viennent du hub. `--pay-to` est le portefeuille que l'acheteur paie en USDC, directement au
vendeur : le hub ne détient jamais cet argent et n'en prend rien. Sans `--pay-to`, une offre
payante ne peut être réglée que depuis des comptes de crédit de votre propre hub, qu'un acheteur
routé depuis un autre hub ne possède pas.

`add` écrit dans votre propre base, il n'y a donc pas de caution d'éditeur à vous payer à
vous-même ; les inconnus qui publient sur votre hub passent par la porte contrôlée décrite
[plus bas](#laisser-dautres-publier-sur-votre-hub). En mode production (`AIFACTORY_PROD=1`),
chaque réponse du fournisseur doit être signée : passez `--provider-pubkey` et voyez la signature
dans [`examples/hello-capability/server.py`](../examples/hello-capability/server.py). Toutes les
options : `aimarket add --help`.

## 3. Une adresse publique

Les autres hubs n'admettent qu'une adresse `https` qu'ils peuvent joindre. Choisissez :

- **Un VPS et un domaine.** Pointez le nom vers la machine et placez n'importe quel proxy TLS
  devant `127.0.0.1:9083`. Avec [Caddy](https://caddyserver.com/), toute la configuration tient
  en :

  ```
  hub.example.com {
      reverse_proxy 127.0.0.1:9083
  }
  ```

- **Une plateforme avec volume persistant** — Railway, Render ou Fly fournissent un nom `https`
  sans domaine à vous. Montez le volume sur `/app/data` : clés, base et réglages sont l'identité
  de votre hub, et un redéploiement sans eux est un autre hub. Fichiers et étapes :
  [lancer sur une plateforme](run-on-a-platform.fr.md).
- **L'installation de production complète** — systemd, nginx, sauvegardes, supervision :
  [déploiement en production](production-deployment.fr.md).

Indiquez ensuite au hub son adresse. Elle figure dans chaque document que le hub signe :

```bash
aimarket quickstart --url https://hub.example.com   # met à jour les réglages ; garde le jeton et les clés
```

## 4. Vérifier avant de frapper

```bash
aimarket doctor
```

`doctor` exécute contre votre adresse publique le même assay d'admission que les autres hubs
vous font passer, et dit quoi corriger pour chaque contrôle en échec. Sur une adresse locale,
il vérifie tout sauf la joignabilité et annonce le verdict que vous obtiendrez une fois le hub
public. Le veto LLM n'est pas consulté ici ; un hub qui l'utilise peut encore refuser.

## 5. Frapper à la porte

```bash
curl -X POST https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  -d '{"hub_url": "https://hub.example.com", "hub_name": "My hub"}'
```

La réponse contient `assay_url`, où vous lisez le verdict. Le hub qui reçoit lance votre
`hub.ping@v1` gratuite ; la preuve est un reçu signé. Un `pass` sur un hub à admission
automatique met vos propres capacités dans son catalogue, sa recherche et son routage, et votre
hub sur sa carte ; modelmarket.dev admet automatiquement. Votre hub lit la fédération dès le
premier démarrage, à partir des seeds versionnées. Tout le chemin d'admission :
[rejoindre la fédération](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.fr.md).

## 6. Ce que cela rapporte, honnêtement

- **Votre propre API :** chaque vente est payée sur votre portefeuille, directement au vendeur.
  Le hub ne garde rien.
- **Courtage :** `AIMARKET_ROUTING_FEE_BPS` (1 % par défaut) quand votre hub route la vente d'une
  capacité d'un autre hub sur le rail de crédits. Une vente que l'acheteur paie directement au
  vendeur via x402 ne porte aucuns frais.
- **Les ventes des autres :** une commission sur les vendeurs qui publient sur votre hub — section 7.
- **Demande :** le trafic d'acheteurs dans la fédération reste faible. Les compteurs en direct
  sont publics (`https://verify.modelmarket.dev/demand.json`) ; lisez-les avant de compter sur
  quoi que ce soit. Un hub coûte un petit VPS et se rentabilise d'abord comme vitrine de votre
  propre API : MCP, x402, A2A et reçus signés en une commande.

## 7. Une place de marché à vous

Un hub est aussi une vitrine pour les services des autres : un catalogue de niche sous votre
nom (un secteur, une langue, une région), avec le catalogue de la fédération derrière dès le
premier jour.

- **Votre marque.** `AIMARKET_HUB_NAME` et `AIMARKET_HUB_URL` signent chaque page ; un
  déploiement qui n'est pas celui de référence n'affiche aucun lien vers le site d'un autre.
- **Les vendeurs se publient eux-mêmes.** Un compte de crédit est une identité d'éditeur : le
  vendeur émet une clé, dépose sa caution depuis son solde et publie — voir
  [laisser d'autres publier](#laisser-dautres-publier-sur-votre-hub). Vous fixez la caution avec
  `AIMARKET_SUPPLY_MIN_STAKE_USD`.
- **Votre commission.** Sur une vente payée depuis un compte de crédit,
  `AIMARKET_PUBLISHER_SHARE_BPS` (70 % par défaut) va au solde du vendeur et le reste vous
  revient ; router la vente d'une capability d'un autre hub ajoute `AIMARKET_ROUTING_FEE_BPS`.
  Un vendeur qui publie avec son propre portefeuille est payé directement via x402 et vous ne
  prenez rien sur cette vente : cette porte reste la sienne.
- **Les acheteurs rechargent en USDC** sur un portefeuille à vous
  ([recharge de crédits](credits-topup.fr.md)), ou vous les créditez après tout paiement que
  vous encaissez vous-même.

Ce qui reste à votre charge, pas à celle du logiciel :

- Un solde est l'argent de votre client dans votre comptabilité (`stats/live` →
  `outstanding_credit_usd`), et la part gagnée par un vendeur est aussi un solde. Payer un
  vendeur est un virement que vous faites : le hub n'envoie aucune valeur.
- Conditions, remboursements, impôts et tout ce que votre juridiction exige de qui détient des
  soldes prépayés ou vend pour le compte d'autrui, c'est à vous de les régler. Le code ne prend
  pas position.

## Signatures post-quantiques dès le premier démarrage

Le post-quantique a deux moitiés, aux rôles différents :

- **`[pqc]` permet au hub de voir ses pairs.** Il installe le vérificateur ML-DSA-65. La
  vérification d'une signature post-quantique échoue en mode fermé, donc un hub qui ne l'a pas
  n'indexe jamais un pair qui signe en hybride — et tous les hubs AIMarket le font.
- **`AIMARKET_PQC=1` fait signer le hub en hybride** (quickstart l'enregistre pour un nouveau hub). Son manifeste, son document de découverte et
  ses reçus portent une signature ML-DSA-65 à côté de la signature Ed25519, et les pairs épinglent
  votre clé post-quantique dès qu'ils la voient pour la première fois.

La clé post-quantique est un second fichier à côté de la clé classique :
`<AIMARKET_SIGNING_KEY_PATH>_mldsa`, par défaut `data/hub_signing_key_mldsa`. Sauvegardez les deux
ensemble et gardez-les sur un même volume. Si vous perdez le fichier ML-DSA, chaque pair qui l'a
épinglé rejette votre hub jusqu'à ce qu'il le ré-épingle (`POST /federation/peers/repin`).
Contexte : [migration post-quantique](https://github.com/alexar76/aicom/blob/main/docs/pqc-migration.fr.md).

## Comment vous êtes payé

Il y a deux rails, et vous pouvez utiliser l'un ou les deux.

| | Crédits (`X-API-Key`) | Canaux (`X-Payment-Channel`) |
|---|---|---|
| Mise en place | une variable d'environnement | un contrat de séquestre (escrow) que vous déployez sur Base + 5 réglages préalables |
| Plus petit montant facturable | 0,00001 $ | 0,01 $ (centimes entiers, arrondis au supérieur) |
| Qui détient l'argent | vous, prépayé | vous, prépayé (dépôt on-chain) |
| Ce qu'il faut à l'acheteur | un client HTTP | un portefeuille approvisionné et une signature typed data |

**Crédits** est le rail qui fonctionne avec `AIFACTORY_CRYPTO_ENABLED=0`, la valeur par défaut. Une
fois activé, un prix affiché signifie de l'argent : une capability payante répond `402` avec les
rails qu'elle accepte, et une invocation portant une `X-API-Key` valide réserve le prix avant que
le fournisseur ne s'exécute, l'encaisse en cas de succès et le rend en cas d'échec.

```
POST /ai-market/v2/accounts                    # un acheteur émet une clé (avec limite de débit)
GET  /ai-market/v2/account                     # le solde de l'acheteur
GET  /ai-market/v2/account/ledger              # chaque mouvement sur son propre argent
POST /ai-market/v2/accounts/{id}/credit        # vous le rechargez  (admin bearer)
POST /ai-market/v2/accounts/{id}/status        # vous le désactivez  (admin bearer)
GET  /ai-market/v2/stats/live                  # summary.credits : gagné et dû
```

L'argent n'entre que par `/credit`, et cette route n'appartient qu'à vous. Quel que soit votre
moyen d'être payé — une facture, un paiement en ligne, un virement de stablecoin que vous avez vu
arriver —, vous appelez `/credit` une fois l'argent reçu. Le hub ne prétend pas avoir encaissé
quoi que ce soit.

### Ce que vous prenez en charge

Un solde prépayé, c'est l'argent de votre client dans votre registre. C'est précisément pour cela
que `stats/live` publie `outstanding_credit_usd` à côté de `credits_earned_usd` : le premier est
un passif, le second un revenu, et un hub qui ne les distingue pas finit par dépenser l'un en
croyant que c'est l'autre. Rien dans le hub ne peut envoyer de valeur, donc les remboursements,
c'est vous qui les faites.

### Réglages

| Variable | Défaut | Signification |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | le rail lui-même |
| `AIMARKET_CREDITS_OPEN_SIGNUP` | `1` | un inconnu peut-il émettre sa propre clé |
| `AIMARKET_CREDITS_FREE_GRANT_USD` | `0.05` | solde de départ d'une clé auto-émise |
| `AIMARKET_CREDITS_SIGNUPS_PER_HOUR` | `5` | plafond par adresse des inscriptions en libre-service |
| `AIMARKET_ECOSYSTEM_FILE` | `ecosystem.json` à côté de la base | quels comptes, serveurs et portefeuilles forment votre propre écosystème : leurs appels sont SELF, pas une demande externe ; voir [classes de trafic](traffic-classes.fr.md) |
| `AIMARKET_OPERATOR_ACCOUNTS` | vide | ancien raccourci pour `self.accounts` de ce fichier (ids de compte séparés par des virgules) ; fusionné avec lui |
| `AIMARKET_ROUTING_FEE_BPS` | `100` | votre part quand vous servez d'intermédiaire pour la capability d'un autre hub |
| `AIMARKET_PQC` | non défini = auto | non défini : un nouveau hub signe en hybride (Ed25519 + ML-DSA-65), un hub doté d'une clé ML-DSA continue de signer avec, un hub Ed25519 seul le reste ; `1` / `0` l'imposent |

## Laisser d'autres publier sur votre hub

Un compte de crédits est une identité, pas seulement un portefeuille : c'est aussi par lui que
quelqu'un publie une capability chez vous, sans modifier `.env`, sans redémarrage, sans
blockchain.

```bash
curl -X POST $HUB/ai-market/v2/accounts                      # ils obtiennent une clé
curl -X POST $HUB/ai-market/v2/accounts/<id>/credit \
     -H "Authorization: Bearer $ADMIN" -d '{"amount_usd": 30}'   # vous encaissez leur argent
curl -X POST $HUB/ai-market/v2/supply/stake \
     -H "X-API-Key: <key>" -d '{"amount_usd": 25}'               # ils déposent une caution
curl -X POST $HUB/ai-market/v2/supply/register \
     -H "X-API-Key: <key>" -d @manifest.json                     # ils publient
```

La clé parle pour exactement un éditeur : son propre compte. Elle ne peut pas déposer de caution
pour un autre ni publier au nom de quelqu'un d'autre, ce que le jeton de publication partagé n'a
jamais pu empêcher.

La caution est un vrai débit sur leur solde : c'est donc de l'argent que vous détenez et pouvez
amputer par slashing (mécanisme de pénalité). Elle est enregistrée comme un type de garantie à
part, distinct de la sentinelle de développement, et satisfait le contrôle de caution de
production. La voie on-chain existe toujours et exige toujours un `tx_hash` vérifié, mais un hub
dont l'image n'embarque pas le vérificateur de dépôts n'est plus forcé de choisir entre « aucune
garantie » et « un contrôle inutilisable ».

Confiance envers les éditeurs : avec `AIMARKET_ORACLE_FAMILY_URL=off`, il n'y a aucun oracle à
consulter, donc les éditeurs reçoivent l'amorçage neutre documenté et le contrôle de confiance ne
s'applique pas. Pointez-la vers une instance LUMEN que vous exploitez si vous voulez une notation.

## Payer vos vendeurs

Quand l'éditeur d'une capability possède ici un compte de crédits, chaque vente conclue se
répartit automatiquement : `AIMARKET_PUBLISHER_SHARE_BPS` (70 % par défaut) lui est crédité, le
reste est à vous. C'est la voie de rémunération des vendeurs que le hub n'a jamais eue : le
registre des canaux ne peut pas envoyer de valeur, et la seule table d'obligations rembourse les
déposants, pas les fournisseurs. Avant cela, un vendeur pouvait publier, être invoqué et devoir
quand même vous demander de lui virer à la main un dixième de centime.

`stats/live` rend compte de la répartition honnêtement : `credits_earned_usd` est le brut (ce que
les acheteurs ont dépensé), `publisher_payouts_usd` ce qui est allé aux vendeurs et
`operator_net_usd` ce que vous avez gardé. Un appel échoué ne paie personne : le versement passe
par le même encaissement que celui qui débite l'acheteur.

## Servir d'intermédiaire pour d'autres hubs

Quand vous acheminez une invocation vers un pair pour lequel vous n'avez pas vendu, la commission
d'acheminement est **réservée avant de demander quoi que ce soit au pair**, sur le rail qu'utilise
l'acheteur. Un appelant sans paiement reçoit un `402` indiquant la commission ; un pair qui refuse
ne coûte rien à l'acheteur ; un pair qui facture moins que son prix publié est réglé au montant le
plus faible. Si vous ne voulez pas facturer l'intermédiation, réglez
`AIMARKET_ROUTING_FEE_BPS=0` : c'est la désactivation, pas un en-tête manquant.

Un canal adossé à un séquestre ne peut pas autoriser une commission d'acheminement (il n'existe
aucune autorisation signée pour elle), donc cette combinaison est refusée au lieu d'être
comptabilisée comme un revenu que vous ne pourriez jamais encaisser. Les acheteurs sur cette voie
doivent utiliser un compte de crédits.

### Revendre un pair payant

L'intermédiation ne fait circuler de l'argent que si vous pouvez payer l'autre partie. Ouvrez un
compte de crédits chez le pair et indiquez-le :

```bash
export AIMARKET_PEER_API_KEYS="https://peer.example=aimk_your_key_there"
```

Un appel acheminé vers ce pair devient alors une revente : votre acheteur paie le prix du
catalogue plus votre commission, vous payez le pair depuis votre compte chez lui, et la commission
est votre marge. Sans clé, le `402` du pair arrive chez un acheteur qui n'a pas de compte là-bas et
ne peut rien en faire ; c'est pourquoi la fédération en production n'a jamais contenu que des
pairs gratuits.

Les hubs pairs sont appelés sur leur `/ai-market/v2/invoke`, pas sur leur `mcp_endpoint` : cet
endpoint parle MCP JSON-RPC sur SSE et répond à une enveloppe acheminée par `Method not found`
dans un corps `text/event-stream`. L'acheminement de hub à hub était impossible tant que cela
n'était pas corrigé.

## Accepter des paiements x402

Une vente de catalogue va directement au vendeur. Le 402 indique le `payout_address` de l'annonce
et un `nonce` de facture, et seul son corps JSON porte un `payment_secret` tel que
`nonce = sha256(payment_secret)`. L'acheteur paie ce portefeuille on-chain avec un
`transferWithAuthorization` EIP-3009 signé sur le nonce, puis réessaie avec
`X-Payment: <tx hash>` (ou `PAYMENT-SIGNATURE`), `X-Payment-Nonce` et `X-Payment-Secret`. Le
secret prouve que c'est bien cet acheteur qui a payé : la transaction et son nonce deviennent
publics dès qu'ils sont minés. Le hub vérifie le transfert et ne détient jamais l'argent
(`aimarket_hub/settle.py`) : seul paie le transfert qu'a déplacé cette autorisation, et chaque
autorisation est une créance distincte, donc deux autorisations dans une même transaction achètent
deux appels. Lors d'un appel fédéré, un paiement accompagne votre clé de pair seulement si le hub
l'a réglé sur cette même requête, avec son propre nonce et en gardant le secret. Un hub sans clé
pour ce pair et qui n'a rien réglé est un relais : il transmet les en-têtes de paiement de
l'acheteur, secret compris. Chaque paiement est lié (un simple transfert au vendeur est refusé ;
`AIMARKET_SETTLE_REQUIRE_BINDING=0` est ignoré), donc l'outillage d'acheteur écrit pour un hub
antérieur, qui n'envoyait que `X-Payment` et `X-Payment-Nonce`, est refusé tant qu'il n'envoie pas
aussi le secret. La passerelle MCP l'accepte sous le nom `x_payment_secret`, et le pont A2A le
présente lui-même. La migration `040` ajoute la colonne de facture qui le conserve, et
`X-Payment-Secret` figure dans la liste des en-têtes autorisés par CORS, donc un client navigateur
sur une origine de `AIMARKET_CORS_ORIGINS` peut aussi l'utiliser. `AIMARKET_X402_ACCEPT=0` conserve
le mode découverte seule.

Les crédits et les canaux de paiement restent des commodités de prépaiement. Ce n'est pas par eux
qu'un éditeur doté d'un portefeuille est payé.

## Laisser des inconnus vous trouver

Deux portes d'observation sont toujours ouvertes et toutes deux mènent à la quarantaine, pas à une
confiance immédiate : un `POST /federation/announce` non authentifié, et la découverte réciproque,
quand un pair vous explore et s'identifie. Dans les deux cas, le pair est placé en `pending` avec
`trusted=false`. Un test en bac à sable s'exécute ensuite automatiquement ; un `pass` l'indexe sans
clic sur Approve. Fail et review restent en attente pour `/operator`. Une table d'aperçu distincte
conserve ce qu'un pair en attente prétend proposer ; ces lignes ne peuvent jamais atteindre la
recherche ni l'acheminement, car elles ne sont pas du tout dans la table `capabilities`. Voir
`docs/join-the-federation.md`.

## Voler de vos propres ailes

Deux valeurs par défaut pointent vers le déploiement de référence, et vous ne voulez
probablement ni l'une ni l'autre :

- **Confiance envers les éditeurs.** `AIMARKET_ORACLE_FAMILY_URL` pointe par défaut vers
  l'instance LUMEN d'un autre opérateur. Si vous la laissez, votre capacité à publier dépend de sa
  disponibilité : une capability publiée pendant qu'il est injoignable est stockée sans note, et
  chacune de ses invocations répond 502. `off` signifie que ce hub n'a pas d'oracle de confiance :
  les éditeurs reçoivent l'amorçage neutre documenté et le contrôle ne s'applique pas. Pointez-la
  vers votre propre instance si vous en exploitez une.
- **Graines de la fédération.** La liste de graines fournie, ce sont les propres satellites du hub
  de référence. C'est un catalogue à parcourir, pas une offre qui vous appartient ; voir
  `AIMARKET_SEED_LIST`.

## Nom

Le code est sous Apache-2.0 (MIT ailleurs dans l'écosystème) et vous pouvez l'exploiter
commercialement, fixer vos propres commissions et les garder toutes ; rien ne détourne une part
où que ce soit. Il n'y a pas de licence de marque : n'appelez donc pas votre déploiement
« AIMarket » et ne laissez pas entendre une approbation. « Implements the AIMarket Protocol » et
« interoperates with <peer> » sont exacts et acceptables. Personne ne peut se dire « certified »
ou « conformant » : il n'existe pas encore de suite de conformité.
