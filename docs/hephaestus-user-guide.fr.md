# HEPHAESTUS — guide de l'utilisateur

> **English:** [hephaestus-user-guide.md](./hephaestus-user-guide.md) · **Русский:** [hephaestus-user-guide.ru.md](./hephaestus-user-guide.ru.md) · **Español:** [hephaestus-user-guide.es.md](./hephaestus-user-guide.es.md) · **中文:** [hephaestus-user-guide.zh.md](./hephaestus-user-guide.zh.md)
>
> La page : **[modelmarket.dev/studio](https://modelmarket.dev/studio)** · Comment cela fonctionne à l'intérieur : [hephaestus-studio.fr.md](./hephaestus-studio.fr.md) · À quoi cela sert : [hephaestus-use-cases.fr.md](./hephaestus-use-cases.fr.md) · **Installation et captures:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

## Ce que l'on peut y faire, en un paragraphe

Choisir des capacités sur le marché, les relier, voir ce que coûte la chaîne **avant** de
l'exécuter, l'exécuter, et conserver un enregistrement signé de ce qui s'est passé — y
compris quelle étape est fautive si l'une échoue. Sans compte. Les premières exécutions sont
gratuites.

## Ouvrir

Rendez-vous sur **[modelmarket.dev/studio](https://modelmarket.dev/studio)**. La page ouvre
non pas sur un canevas vide mais sur un exemple qui fonctionne : deux capacités déjà
reliées, chiffrées et prêtes à tourner. L'en-tête montre exactement la raison d'être de la
page :

```
$0.0030 · 2 hops · ≥101 ms          5 free runs left · every hop has an observed success rate
```

* **$0.0030** — ce que coûte l'exécution de ce graphe. Somme issue de la liste de prix en direct.
* **2 hops** — les étapes payantes. `Start` et `Result` ne sont pas des étapes : elles
  marquent le début et la fin du graphe.
* **≥101 ms** — un plancher, pas une prévision : aujourd'hui les étapes s'exécutent l'une
  après l'autre, donc une exécution réelle ne peut pas être plus rapide.
* **5 free runs left** — votre solde, compté sur un identifiant aléatoire stocké dans ce
  navigateur. Ce n'est pas un compte, et cela ne dit rien de vous.

![La page au chargement : catalogue à gauche, un graphe à deux sauts, l’estimation dans l’en-tête](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/opens-on-a-real-chain.png)

*Voilà la page au chargement : une chaîne déjà fonctionnelle et déjà chiffrée.*

## Partir d'un objectif, pas d'un identifiant de capacité

Soixante-seize lignes nommées `gaia.verify@v1` forment un catalogue, pas une réponse. Si ce
que l'on veut est *une mesure défendable dans une discussion*, il faut d'abord savoir que la
lecture et le verdict sur celle-ci sont deux achats distincts et que l'un alimente l'autre.

Le bouton **Wizards** de l'en-tête énonce l'objectif à la place. Chaque entrée montre la
chaîne qu'elle construirait à partir du catalogue du jour, déjà chiffrée, avant tout
chargement :

![Le menu des assistants ouvert : deux objectifs avec leur chaîne et leur prix, deux avec la raison pour laquelle ils ne peuvent pas être construits](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/wizards-are-goals.png)

*Des objectifs et ce que chacun coûterait — et les deux que le catalogue ne satisfait pas
aujourd'hui.*

Un clic et la chaîne arrive sur la toile, câblée et pré-remplie, exactement comme si elle
avait été montée à la main. Rien n'est ensuite caché : c'est un graphe ordinaire, que l'on
peut modifier, re-chiffrer ou jeter.

Les objectifs que le marché **ne peut pas** satisfaire restent dans la liste avec leur
raison — par exemple *« rien de ce qui est en vente ici ne remplit l'étape d'une synthèse
qui accepte une localisation »*. Ce n'est pas une erreur de votre côté : c'est un manque
dans l'offre actuelle, et il vaut mieux le savoir avant de bâtir un achat autour.

Deux choses qu'un assistant ne fera jamais. Il ne raccourcira pas une chaîne pour rendre un
objectif crédible : si une étape n'a aucun candidat, l'objectif entier est indisponible. Et
il ne reliera pas deux sauts au seul motif d'un nom de champ partagé : un saut doit
consommer le *résultat* du précédent et, dès qu'il s'agit de matériel cryptographique, venir
du même fournisseur. Ces deux règles existent parce que le catalogue contient réellement des
paires qui semblent connectables et ne le sont pas.

## Les trois panneaux

| Panneau | À quoi il sert |
|---------|----------------|
| **Catalogue** (à gauche) | Toutes les capacités en vente : identifiant, prix, et la quantité de preuves derrière leur fiabilité. Filtre par id ou description. Un clic pour ajouter. |
| **Canevas** (au centre) | Le graphe. Glisser pour déplacer ; du point sous un module au point au-dessus d'un autre pour relier. Un clic sur la liaison bascule le fait qu'elle porte des données. |
| **Paramètres / Vérifications / Dernière exécution** (à droite) | Les champs du module sélectionné, tout ce qui cloche dans le graphe, et ce que la dernière exécution a renvoyé. |

Sur un téléphone, les trois deviennent un à la fois, commutés depuis la barre du bas.

<p>
  <img src="../hephaestus/docs/screenshots/mobile-canvas.png" alt="La page à 390px : le graphe" width="220">
  <img src="../hephaestus/docs/screenshots/mobile-catalogue.png" alt="L’onglet catalogue à 390px" width="220">
</p>

*La même page à 390px : « Catalogue » et « Toile » se changent depuis la barre du bas.*

## Lire une ligne du catalogue

```
gaia.weather.read@v1
$0.0010   127 calls (30d), 99.2% ok
```

Le prix est ce qui vous sera facturé, frais de routage compris. La seconde ligne est une
**preuve, pas une note** : elle n'apparaît que si quelqu'un a réellement invoqué cette
capacité via ce hub durant les trente derniers jours. Quand personne ne l'a fait, il est
écrit **« no calls yet »** — et c'est l'état honnête de 49 des 76 lignes du jour. Ce n'est
pas une mauvaise note : c'est l'absence de note.

Une ligne peut être grisée avec un motif tel que *« declares no output schema — nothing
downstream can use it »*. Celles-là ne se relient à rien, et la page le dit plutôt que de
vous laisser dessiner un port qui ne mène nulle part.

## Remplir les paramètres

Sélectionnez un module. Ses champs sont exactement ceux que le fournisseur a publiés, rien
d'inventé. Les champs obligatoires portent `*`. Certaines capacités ne prennent aucune
entrée et le disent.

**Un champ peut lire depuis une étape antérieure au lieu d'une valeur littérale.** Écrivez :

```
${read.reading}
```

et à l'exécution la valeur vient de l'étape nommée `read`. `${read}` transmet le résultat
entier de cette étape ; `${read.reading.values.temperature_c}` va chercher à l'intérieur ;
`seen at ${read.ts}` l'insère dans une phrase. C'est ce qui fait d'une chaîne un pipeline
plutôt qu'une liste d'appels séparés, et c'est ce que démontre l'exemple d'ouverture.

Une référence est vérifiée avant que vous puissiez exécuter : elle doit nommer une étape
présente sur le canevas, pas elle-même, et une étape dont l'exécution est garantie avant.
Sinon, **Vérifications** dit laquelle et pourquoi.

![Le vérificateur sélectionné ; ses champs reading et attestation contiennent ${read.reading} et ${read.attestation}](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/references-in-the-fields.png)

*Un champ qui lit un saut antérieur. Le panneau des vérifications indique quel champ va où.*

## Vérifications

Tout ce qui empêcherait le graphe de tourner, en une liste et en clair :

* `"gaia.verify@v1" needs "reading" (object)` — un champ obligatoire est vide.
* `"Start" is not connected to anything` — un module inatteignable.
* `Pipelines take at most 16 capabilities` — la limite de l'exécuteur ; découpez le travail.
* `"check" is fed by 2 connections at once` — une étape reçoit ses données d'une seule étape
  amont ; marquez une unique liaison comme source de données.

Les avertissements sont jaunes et ne bloquent pas : une capacité sans prix publié, ou qui ne
déclare pas ce qu'elle renvoie, reste utilisable — vous en savez simplement moins.

## Exécuter

**Run** soumet le graphe. Ce qui revient est un enregistrement réel, pas un résumé :

```
tr_c87f3be013e4
$0.0030 · 2 hops · 771 ms
✓ gaia.weather.read@v1 · $0.0010
✓ gaia.verify@v1 · $0.0020
signed bill of materials →
```

Suivez le lien pour l'original signé — le document même sur lequel un litige s'appuierait. Si
une étape échoue, l'enregistrement nomme l'étape fautive et disculpe explicitement celles
qui ont fait leur travail :

```
at fault: gaia.verify@v1 (HTTP 500) · cleared: read
```

**Copy request** place le JSON exact dans le presse-papier : le même graphe peut être exécuté
depuis un terminal, un job de CI ou votre propre agent. La page est un confort, pas un
passage obligé.

![Une exécution terminée : identifiant de trace, les deux sauts avec leur prix, et le verdict](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/signed-bill-of-materials.png)

*Après l’exécution : l’identifiant de trace, chaque saut avec son coût, et le verdict du vérificateur.*

## Ce que cela coûte, et qui paie

* **Exécutions gratuites.** Chaque visiteur reçoit un petit solde renouvelable, compté sur
  l'identifiant aléatoire de ce navigateur. Videz le stockage et vous êtes un nouveau
  visiteur avec un nouveau solde : c'est un essai, pas une frontière de sécurité.
* **Ce que l'offre gratuite exclut.** Les capacités qui composent leur réponse avec un modèle
  payant dépensent un budget réel à chaque appel : elles ne sont donc pas gratuites. Ces
  étapes reviennent en demandant un paiement.
* **Personne n'est débité en silence.** Sans solde et sans canal à vous, une étape payante
  échoue avec un motif. Le devis vous dit tout de même ce qu'elle aurait coûté.
* **Payer pour de vrai.** Au-delà de l'offre gratuite, une étape a besoin d'un canal de
  paiement que vous contrôlez. Les exécutions se règlent dessus, et l'enregistrement nomme le
  canal plutôt que le service qui a relayé votre requête.

## Limites à connaître avant de construire

* **16 capacités** par exécution.
* **Une seule source de données par étape** — plusieurs étapes peuvent devoir finir avant,
  mais une seule transmet son résultat.
* **Les étapes s'enchaînent une par une.** Le chiffre de latence est un plancher.
* **Un devis n'est pas une offre ferme.** Les prix viennent d'une liste signée au moment de
  la lecture, et un fournisseur peut les changer avant votre exécution.
* **Un enregistrement signé prouve ce que l'exécuteur a fait, pas que la réponse est juste.**
  La véracité du résultat est l'affaire des capacités de vérification — et vous pouvez en
  placer une dans le graphe, ce que fait précisément l'exemple d'ouverture.

## Si quelque chose semble anormal

| Ce que vous voyez | Ce que cela veut dire |
|-------------------|-----------------------|
| `no calls yet` sur chaque ligne | Personne n'a invoqué ces capacités via ce hub depuis trente jours. Honnête, pas cassé. |
| Une étape échoue en `402` | Elle exige un paiement et aucun canal n'est joint. |
| Une étape échoue en `429` | Votre solde gratuit est épuisé pour l'instant ; il se renouvelle. |
| `unresolved reference: …` | L'étape amont a tourné mais n'a pas renvoyé le champ référencé. Son schéma de sortie dit ce qu'elle renvoie. |
| `executor_not_configured` | Ce déploiement n'a pas d'exécuteur de pipelines. C'est un opérateur qui corrige, pas vous. |
| Le catalogue est vide | La page n'a pas pu lire le manifeste du hub. Comme c'est le hub qui la sert, cela signifie en général que le hub est injoignable. |
