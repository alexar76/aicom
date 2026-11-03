# Qui est dessiné sur la carte, et comment en faire partie

> ## ⚠️ AVERTISSEMENT — À LIRE D'ABORD
>
> **Votre hub déclare. Le moniteur de celui qui regarde décide.**
>
> Un hub doit publier fidèlement tout ce qu'il sait : chaque fournisseur, chaque pair,
> chaque hub dont il a seulement entendu parler. Ce qui mérite d'être *dessiné* est une
> autre question, et elle appartient à celui qui regarde. Un moniteur dessine un nœud
> lorsqu'il existe une preuve que ce nœud participe à l'économie, et une preuve n'est pas
> une affirmation : c'est une capacité dans un catalogue signé, une transaction dans les
> propres registres de celui qui regarde, ou une adresse qu'il a vérifiée lui-même auprès
> de la chaîne.
>
> **Un de vos nœuds peut donc manquer sur la carte de quelqu'un d'autre tout en étant
> parfaitement configuré.** Ce n'est pas un bug de la carte ni un défaut de votre hub. Cela
> signifie que celui qui regarde, à deux sauts de là, n'a pas encore de preuve — et le
> remède est de lui en donner une, non de lui demander de vous croire. Cette page est la
> liste des façons de le faire.
>
> Rien de tout cela n'affecte **votre propre** carte. Un hub dessine toujours ce qu'il
> déploie lui-même.

## La règle, en trois niveaux

La limite tombe au deuxième saut.

| Distance | De qui il s'agit | Dessiné ? |
|---|---|---|
| **saut 0** | le hub propre de ce déploiement et ses propres fournisseurs | **toujours** — nous montrons ce que nous exécutons |
| **saut 1** | un hub avec lequel nous fédérons, ou un hub qui frappe pour être admis | **toujours** — voir ci-dessous |
| **saut 2** | le fournisseur ou le pair de quelqu'un d'autre, atteignable seulement à travers lui | **seulement avec une preuve** |

**Les hubs sont toujours dessinés.** Un hub est une relation de routage, pas une vitrine :
zéro capacité peut être parfaitement exact (un agrégateur dont tout le catalogue est de la
réexportation est filtré à zéro), et un hub en attente d'admission est vide *parce qu'*il
attend. « Qui est là dehors » est précisément la question à laquelle la carte existe pour
répondre.

**Les pairs d'un hub, non.** Au deuxième saut, la carte répète ce qu'un inconnu lui a dit,
au sujet d'un nœud qu'elle n'atteint pas, qu'elle n'interroge pas et dont elle n'a aucun
registre. Le dessiner sans condition, c'est ainsi qu'une carte se remplit de noms dont
personne ne peut rien faire.

## Les trois façons de gagner une sphère au deuxième saut

**Une seule** suffit. Ce sont des OU, pas des ET.

### 1. Il fournit — il propose au moins une capacité

Ce qui est examiné, c'est le **catalogue**, jamais le chiffre d'affaires.

> **Une capacité gratuite compte exactement autant qu'une payante.** `access_mode:
> public_free` au prix `0.00`, c'est de la participation : quelque chose est donné, et
> quelqu'un peut s'en servir. Un nœud qui donne une capacité est dessiné ; un nœud qui en
> vend neuf est dessiné ; la règle ne les classe pas.

C'est la voie ordinaire. Publiez une capacité sur votre hub et votre nœud sera sur toutes
les cartes qui atteignent votre hub.

### 2. Il consomme — il a transigé avec nous

Un nœud qui apparaît comme `consumer_hub` dans le flux d'invocations de celui qui regarde
est dessiné même avec un catalogue vide. Un service construit avec nos outils qui achète
chaque heure et n'expose rien qui lui soit propre participe autant que n'importe quel
vendeur — et le cacher voudrait dire qu'un moniteur cache ses propres clients.

La preuve, ici, ce sont les registres de celui qui regarde : rien ne vous est demandé
d'autre que de commercer.

### 3. Il règle sur la chaîne — un escrow ou un portefeuille vérifiés

La voie qui ne dépend de la comptabilité de personne.

Un hub publie l'escrow par lequel il règle et le portefeuille sur lequel ses factures sont
payées ; chaque hub réexporte ce que ses pairs ont déclaré ; et le moniteur **demande à la
chaîne** :

* un **contrat** — l'adresse contient-elle du code ? Un escrow jamais déployé n'en a pas.
* un **portefeuille** — a-t-il déjà transigé ? Sur une EOA, c'est son nonce.

Si l'une des deux répond oui, le nœud est dessiné — et sa sphère s'ouvre sur ces
transactions, de sorte que le lecteur peut refaire la vérification au lieu de croire qui que
ce soit.

> **Déclaré n'est pas vérifié.** Une adresse est une chaîne de caractères que n'importe qui
> peut publier. Tant que le moniteur ne l'a pas confirmée auprès de la chaîne qu'il lit, la
> fiche du nœud indique *déclaré, non vérifié* et le nœud n'en tire rien. Une déclaration
> portant sur une chaîne que le moniteur ne peut pas lire n'est jamais présumée bonne : elle
> est signalée comme non vérifiée, car « nous n'avons pas pu regarder » et « ce n'est pas
> là » sont deux affirmations différentes.

## Ce que votre hub publie sur son propre argent, automatiquement

`/.well-known/ai-market.json` gagne un bloc `contracts` :

```json
"contracts": {
  "version": 1,
  "chain": "base",
  "chain_id": 8453,
  "network": "Base",
  "explorer": "https://basescan.org",
  "entries": [
    { "role": "escrow", "name": "AIMarketEscrow", "address": "0x12Db…2CF2",
      "explorer": "https://basescan.org/address/0x12Db…2CF2",
      "note": "payment channels are funded and settled here" },
    { "role": "wallet", "name": "settlement wallet", "address": "0x1218…Ad0a",
      "note": "invoices for this hub are paid to this address" },
    { "role": "token", "name": "USDC", "address": "0x8335…2913" }
  ]
}
```

**Il n'y a rien à configurer.** Les adresses sont lues dans la configuration de paiement et
le registre de déploiement avec lesquels le hub fonctionne déjà :

| Entrée | D'où elle vient | Publiée quand |
|---|---|---|
| `escrow` | `AIMARKET_ESCROW_EVM_ADDRESS`, sinon le registre de déploiement de la chaîne active | il en existe un |
| `wallet` | `AIMARKET_PAYMENT_RECIPIENT` | **et** `payment_configured` est vrai |
| `token` | l'adresse USDC/USDT de la chaîne active | il en existe une |

Ainsi, un hub qui déploie un escrow commence à le déclarer dès sa requête suivante, et un
hub qui n'en a pas reste muet. Il n'y a pas d'interrupteur à oublier ni de second endroit à
mettre à jour — c'est la seule raison pour laquelle on peut se fier au fait que la
déclaration soit encore vraie après un redéploiement.

Deux choses ne sont délibérément **pas** publiées :

* **Le portefeuille, si les paiements ne sont pas réellement vérifiés sur la chaîne.** Même
  verrou que `payment_configured` : un hub qui crédite n'importe quel `tx_hash` sans le
  contrôler n'a pas à désigner un portefeuille comme si l'argent qui y arrive signifiait
  quelque chose.
* **Tout ce qui, dans un realm scellé (`AIMARKET_CHAIN_REALM=uni`), nomme un actif réel.**
  Une bulle publie son propre déploiement Anvil, marqué `"simulated": true`, sans lien vers
  un explorateur — `basescan.org/address/<adresse anvil>` est une vraie page sur une chaîne
  qui n'a jamais entendu parler de votre contrat.

Rien de tout cela n'est une divulgation nouvelle. L'adresse de l'escrow figure dans chaque
ouverture de canal, et le destinataire dans chaque `accepts[].payTo` x402 auquel votre hub a
jamais répondu. Les publier signifie seulement qu'un lecteur n'a plus besoin d'acheter
quelque chose pour les connaître.

## Ce qui parvient à un inconnu, et ce qui n'y parvient pas

```
votre hub  ──déclare──▶  un hub qui fédère avec vous  ──réexporte──▶  un moniteur
   contracts: {...}          peers[].contracts: {...}      demande à la chaîne
```

La réexportation est automatique et relue à **chaque** exploration. Déployez un escrow
aujourd'hui et les hubs qui vous connaissent le réexportent à leur passage suivant ;
retirez-le et ils cessent. Aucune action d'opérateur, d'aucun côté.

La déclaration d'un pair est bornée et revalidée à chaque saut — 8 entrées au maximum,
uniquement de vraies adresses EVM, uniquement des URLs d'explorateur `http(s)` — du côté qui
publie *et* de nouveau dans le moniteur. Un validateur qui ne tourne que là où les données
sont écrites n'est pas un validateur.

## Lire les transactions

Chaque adresse déclarée sur la fiche d'un nœud porte deux liens :

* **voir les transactions →** — le scanner propre de ce moniteur
  (`/api/chain/address/<adr>`), qui fonctionne aussi dans la bulle, où aucun explorateur
  public n'existe ;
* **explorateur ↗** — l'explorateur de blocs public, lorsque la chaîne en a un.

## L'exception délibérée

Une règle a besoin d'une dérogation, sinon la première exception légitime devient une raison
de supprimer la règle. Sur le moniteur :

```bash
ALIEN_KEEP_SILENT_NODES=fedchild:https://example.dev,fedchild:https://other.dev
```

Ids de nœuds exacts, séparés par des virgules. Ces nœuds sont dessinés quoi que dise la
règle.

Les omissions ne sont jamais silencieuses, dans un sens comme dans l'autre : chaque tick qui
écarte un nœud journalise son id et le décompte, si bien que « la carte n'affiche pas X » a
toujours une réponse dans le journal.

## Liste de contrôle — pour que votre nœud apparaisse sur les cartes des autres

- [ ] au moins une capacité publiée sur votre hub (une **gratuite** suffit), **ou**
- [ ] vous invoquez des capacités du hub sur la vue duquel vous voulez apparaître, **ou**
- [ ] un escrow déployé et `AIMARKET_ESCROW_EVM_ADDRESS` renseigné — vérifiable sur une chaîne publique
- [ ] `payment_configured: true` si vous voulez que votre portefeuille soit publié aussi
- [ ] `curl https://votre.hub/.well-known/ai-market.json` depuis une **autre** machine montre
      un bloc `contracts` avec les adresses attendues
- [ ] chacune de ces adresses s'ouvre dans un explorateur public et montre ce qui est attendu
- [ ] l'adresse publique de votre hub est renseignée (`AIMARKET_HUB_URL`), sinon rien de ce
      qui précède n'est atteignable

## Voir aussi

* [ecosystem-declaration.fr.md](./ecosystem-declaration.fr.md) — déclarer vos fournisseurs
  pour qu'ils s'affichent avec des adresses utilisables.
* [federation-admission.md](./federation-admission.md) — comment un hub pair est admis.
* [federation-peer-keys.md](./federation-peer-keys.md) — comment l'identité d'un pair est épinglée.
