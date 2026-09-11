# HEPHAESTUS — la forge : chiffrer un graphe de capacités avant de le payer

> **English:** [hephaestus-studio.md](./hephaestus-studio.md) · **Русский:** [hephaestus-studio.ru.md](./hephaestus-studio.ru.md) · **Español:** [hephaestus-studio.es.md](./hephaestus-studio.es.md) · **中文:** [hephaestus-studio.zh.md](./hephaestus-studio.zh.md)
>
> Comment piloter la page : [hephaestus-user-guide.fr.md](./hephaestus-user-guide.fr.md) · À quoi cela sert : [hephaestus-use-cases.fr.md](./hephaestus-use-cases.fr.md)
>
> Noyau : [`hephaestus/`](https://github.com/alexar76/hephaestus/tree/main/). Nœud du moniteur : `hephaestus`. Exécuteur : `POST /ai-market/pipelines`. · **Installation et captures:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

## Ce que c'est

HEPHAESTUS compose une chaîne de capacités du marché, **en chiffre le coût avant que quoi que ce soit
soit payé**, la soumet à l'exécuteur de pipelines et conserve le bill of materials (nomenclature)
signé qui revient — y compris le saut (hop) fautif lorsqu'une chaîne échoue.

Ce n'est pas un constructeur de workflows généraliste. Chaque nœud est une ligne réelle du manifeste
signé du hub, avec un prix, une latence déclarée et une quantité déclarée de preuves quant à sa
fiabilité. Toute la différence est là : un tel graphe peut répondre à *combien cela va coûter* et *qui
l'a cassé*, ce qu'aucune quantité de rectangles dessinés ne donne.

Deux surfaces, séparées à dessein :

| Surface | Rôle |
|---------|------|
| Nœud `hephaestus` dans Alien Monitor | **Observation.** Exécutions réelles — coût, sauts, saut fautif — et quelle part du catalogue est réellement câblable. |
| Page du studio | **Construction.** Choisir des capacités, remplir les paramètres, voir le devis, soumettre. |

Le moniteur observe ; il n'héberge pas l'éditeur. Une surface d'observation qui invente un flux est
pire qu'une surface vide : sans exécution enregistrée, le panneau le dit exactement.

## La page du studio

Le hub la sert sur **`/studio`**, et ce n'est pas un choix arbitraire : le catalogue à
partir duquel elle compose est le manifeste signé du hub lui-même, et son CORS est
fail-closed — une page hébergée ailleurs ne pourrait pas le lire. Même origine, sans pont
et sans second domaine.

L'exécution est également de même origine. L'exécuteur de pipelines est un autre service
que le navigateur ne peut pas joindre en cross-origin, donc le hub relaie une requête via
`POST /studio/run`. Ce relais est volontairement étroit :

* la destination vient de `AIMARKET_PIPELINE_EXECUTOR_URL` sur le hub, **jamais du corps de
  la requête** — un relais qui prend sa cible chez l'appelant est un gadget SSRF quel que
  soit son nom, et celui-ci est joignable depuis n'importe quel navigateur ;
* non configuré signifie `503` en nommant la variable, pas une supposition sur un port
  local ;
* le corps est vérifié en forme et en taille avant que quoi que ce soit quitte le hub, avec
  la même limite de seize nœuds que celle de l'exécuteur ;
* aucune donnée d'authentification de l'appelant n'est relayée : le chemin d'exécution du
  studio est le chemin gratuit (sandbox), et une exécution payante va directement à
  l'exécuteur avec son propre canal.

La réponse porte `trace_url`, si bien que la page renvoie vers le bill of materials signé
plutôt que de demander de croire son propre résumé.

```bash
cd hephaestus/studio && npm install && npm run build   # produit dist/, servi sur /studio
```

Ce dépôt ne versionne pas les sorties de build : le bundle est donc produit par une étape
Node dans l'image du hub (l'image d'exécution est uniquement Python). Un déploiement qui
manquerait tout de même de `hephaestus/studio/dist` répond `503` en nommant le build absent,
plutôt qu'un 404.

En dessous de 900px de **largeur réelle** du conteneur, les trois colonnes deviennent une à la fois — catalogue, canevas,
vérifications — commutées depuis une barre inférieure : à 375px une palette et un inspecteur
ne laissent au canevas que quelques pixels, et le canevas est le panneau qui doit rester
utilisable. Le devis reste dans l'en-tête dans les deux dispositions : c'est la raison d'être
de la page. Ajouter un module amène au canevas et en toucher un amène à ses paramètres, si
bien qu'un appui ne tombe jamais sur un panneau invisible.

Le seuil est mesuré sur l'élément via un `ResizeObserver`, il n'est pas demandé au viewport :
une fenêtre peut être physiquement étroite tout en annonçant un viewport CSS large — un user
agent de bureau sur un téléphone, une fenêtre mise à l'échelle ou dézoomée, un cadre embarqué
— et la media query reste fausse dans tous ces cas alors que le canevas est réduit à une bande.

## Assistants : un objectif résolu contre le catalogue

Un assistant, c'est un objectif et une liste ordonnée de **rôles**. Un rôle est un prédicat
sur ce qu'une capacité *déclare* — les champs qu'elle produit, ceux qu'elle exige, la forme
de son identifiant — jamais sur un `product_id` inscrit en dur. Un assistant ne peut donc pas
proposer une ligne qui n'est pas en vente, et il continue de fonctionner quand le catalogue
change ; une liste de recettes curées ne fait ni l'un ni l'autre.

La résolution choisit une capacité par rôle, dans cet ordre : combien de données le saut
reçoit du précédent, puis combien il reste à saisir à la main, puis si la ligne a des
observations mesurées derrière elle, et enfin le prix. Le prix vient en dernier
volontairement : la chaîne la moins chère qui ne fait pas le travail n'est pas une économie.

Deux garde-fous, tous deux nés du fait que le catalogue réel a battu la version naïve :

* **`consumes`** — au moins un champ câblé doit correspondre à ce que le rôle est censé
  recevoir. Sans lui, `platon.random@v1` s'appariait à `platon.beacon@v1` sur `num_bytes` :
  le tirage renvoie son propre paramètre en sortie et la balise accepte ce paramètre en
  entrée, si bien que les deux se câblent proprement et ne vérifient rien. Un saut qui
  consomme les *paramètres* du précédent ne consomme pas son *résultat*.
* **`sameProductAsPrevious`** — pour du matériel cryptographique, c'est une question de
  justesse, pas de préférence. `proof` est un nom de champ, pas un format : le résolveur a
  volontiers passé une preuve VRF de `platon.random@v1` à `chronos.verify@v1`, un
  vérificateur VDF, parce que les deux l'appellent `proof`. Cette chaîne facture le premier
  saut puis échoue sur une preuve que le second ne sait pas lire. Les données ordinaires —
  une lecture, une localisation — restent libres, car là un second avis venant d'un
  fournisseur *différent* vaut mieux qu'un avis du même.

Un objectif dont tous les rôles ne peuvent être remplis est renvoyé **indisponible, avec le
rôle qui a échoué**, et le menu l'affiche avec cette raison au lieu de le cacher. Aujourd'hui
deux des quatre sont indisponibles, et les deux raisons sont de vrais manques : personne ne
vend de vérificateur pour les tirages de `platon`, et `atlas.situation.brief@v1` exige un
cadre (`west/south/east/north`) qu'aucune capacité du catalogue ne produit —
`atlas.point.read@v1` émet un objet `point`. Un assistant qui écarterait en silence l'étape
manquante remettrait à quelqu'un une chaîne faisant autre chose que ce que son titre promet,
et cette personne paierait avant de s'en apercevoir.

## Le devis

Deux règles gardent le chiffre honnête, verrouillées par les tests de [`hephaestus/tests/estimate.test.ts`](https://github.com/alexar76/hephaestus/blob/main/tests/estimate.test.ts) :

1. **Une capacité sans prix est nommée, jamais considérée comme gratuite.** Elle est exclue du total
   et listée à part : un total qui absorbe silencieusement l'inconnu n'est pas un devis.
2. **L'argent est additionné en micro-dollars entiers.** Les prix réels du catalogue sont des lectures
   de capteur à $0.001 et des appels d'oracle à $0.004 ; additionner cela en virgule flottante dérive
   précisément dans les chiffres qui composent le total.

Là où le hub route vers un pair, c'est le prix routé qui est utilisé : chiffrer le prix du
fournisseur sous-évaluerait chaque saut fédéré du montant des frais de routage.

La latence est donnée comme le chemin le plus long selon les latences déclarées, c'est-à-dire un
**plancher** : l'exécuteur parcourt aujourd'hui les sauts en séquence, donc une exécution réelle ne
peut pas être plus rapide. Les capacités sans latence déclarée comptent pour zéro et sont listées
nommément, de sorte que le chiffre n'est jamais gonflé par une supposition.

## Une fiabilité à laquelle on peut se fier — la règle `reputation_basis`

Le manifeste du hub publie un `success_rate_30d` pour chaque ligne. Pour une ligne que personne n'a
jamais invoquée, ce nombre est une valeur neutre délibérée : le crawler ignore les taux de succès
déclarés par le pair, car un pair capable de s'attribuer 99 % dominerait le routage dès le premier
indexage.

Conséquence : les 76 lignes du catalogue en production publiaient `0.5`, et rien dans le document ne
distinguait un un-sur-deux mesuré d'un substitut non observé. Le manifeste porte désormais la preuve
à côté du nombre :

| Champ | Signification |
|-------|---------------|
| `observations_30d` | Invocations observées par le hub émetteur sur les 30 derniers jours. |
| `reputation_basis` | `measured` — le taux vaut succès/tentatives sur cette fenêtre. `unobserved` — rien n'a été exécuté ; le taux est un substitut. |
| `by_hub[*].trust_basis` | Jumeau au niveau du pair : `measured`, `unobserved`, ou `self` pour le hub émetteur lui-même. |

**La règle pour tout consommateur, y compris notre propre interface : se fonder sur
`reputation_basis`, jamais sur le nombre.** Quand la base n'est pas `measured`, afficher « aucun appel
pour l'instant », et non un score. Le noyau écarte purement la valeur au lieu de la transmettre
([`hephaestus/src/catalog.ts`](https://github.com/alexar76/hephaestus/blob/main/src/catalog.ts)) ; un hub antérieur à ces champs se lit
`unknown`, ce qui n'équivaut pas à « mauvais ».

Dès qu'une capacité a été invoquée, le manifeste sert le taux **mesuré** — le commentaire du crawler
affirmait depuis toujours que le hub le calcule lui-même ; personne ne le faisait, si bien que `0.5`
était figé dans chaque manifeste signé.

## Composabilité — pourquoi certaines lignes ne peuvent pas être câblées

Une capacité n'est composable que si elle déclare des champs d'entrée (un objet `properties`, même
vide — « ne prend rien » est une réponse) **et** un schéma de sortie non vide. Les lignes qui échouent
à l'un des deux sont trouvables et tarifées, mais ne peuvent pas être reliées à un voisin, et le
studio le dit plutôt que de dessiner un port qui ne mène nulle part.

Trois lacunes côté sources ont été comblées pour rendre le catalogue composable :

* **Platon, 9 capacités.** L'agrégateur oracle-family fédérait Platon par identifiant, description et
  prix seulement, donc chaque ligne héritait du défaut « aucun champ » d'oracle-core, alors que Platon
  documente lui-même `num_bytes`, `client_seed`, `prompt`, `round`, `question` et les autres.
  L'agrégateur transmet désormais les déclarations propres de Platon au lieu de les redire : tout ce
  qui est redit à la main est la dérive qui a un jour mis `platon.verify@v1` en vente.
* **ATLAS, 6 SKU.** `output_schema` était totalement absent : six artefacts de décision payants dont
  un acheteur ne pouvait connaître la forme du résultat qu'en en payant un. Les schémas reflètent
  maintenant ce que construisent les gestionnaires, et la suite valide la sortie réelle contre eux dans
  les deux sens : le schéma ne peut ni trop promettre, ni prendre du retard sur le gestionnaire.
* **Les capacités qui ne prennent réellement aucune entrée** (`platon.state@v1`,
  `platon.commit@v1`, `gaia.fleet.status@v1`) déclarent un `properties` explicitement vide. C'est
  correct, pas cassé : « ne prend rien » et « ne le dit pas » sont deux états distincts, et le studio
  les affiche différemment.

## Ce que l'exécuteur peut exprimer, et ce qu'il ne peut pas

Le studio refuse un graphe que l'exécuteur ne saurait pas exécuter, en donnant la raison, plutôt que
d'exporter un JSON qui échouera plus tard — ou pire, qui réussira en alimentant un saut depuis le
mauvais ascendant.

* **Au plus 16 capacités par pipeline** (`PipelineRequest.nodes`). Découpez un travail plus grand en
  étapes.
* **Un seul parent porteur de données par saut.** `input_from` nomme un unique nœud, donc une seule
  connexion entrante peut être marquée comme source de données ; les autres n'expriment que l'ordre.
* **Les sauts s'exécutent en séquence.** L'estimation de latence est un plancher, pas une prévision.

### `input_from` nomme un nœud

`input_from` est déclaré comme identifiant de nœud et était implémenté comme un booléen : toute valeur
vraie injectait le résultat du saut terminé en dernier. Dans une chaîne droite, cela coïncide. Dans un
DAG, non : un saut à deux parents recevait le résultat de celui que le tri topologique avait terminé
en second, de sorte qu'un graphe convergent pouvait être dessiné, chiffré, payé et alimenté depuis le
mauvais ascendant, avec une signature valide sur le bill of materials.

Le champ nomme maintenant le parent qu'il désigne, et les résultats sont conservés par nœud, si bien
qu'un ascendant lointain peut aussi être nommé. Une valeur ne correspondant à aucun nœud connu
conserve l'ancien comportement « dernier résultat », de sorte que les appelants existants ne sont pas
affectés.

## Exécuter : qui exécute, et qui paie

Un saut que cette fabrique n'héberge pas est routé vers l'invoke fédéré du hub, car le studio
compose depuis le catalogue du hub — soixante-seize lignes, toutes chez des pairs — tandis que
l'exécuteur en héberge neuf. Avant ce routage, tout graphe qu'un visiteur pouvait construire
répondait `404 capability not found`.

Ce qu'il fallait décider, c'était l'argent, pas le code :

* **Aucune donnée d'authentification de l'exécuteur n'est jamais jointe.** Un bouton Run non
  authentifié qui dépense le solde de l'opérateur est un robinet ouvert, et chaque reçu qu'il
  produirait nommerait le mauvais acheteur.
* **L'identité d'essai du visiteur circule de bout en bout** — navigateur → hub → exécuteur →
  hub — via `X-AIMarket-Sandbox-Visitor`. Le hub mesure un solde renouvelable par visiteur :
  relayer l'identifiant du visiteur plutôt que celui du service fait la différence entre un
  solde chacun et un seul seau épuisé pour tous.
* **Un saut qui exige de l'argent échoue en tant que ce saut.** `402` pour paiement requis,
  `429` pour un solde épuisé — motif visible, jamais de débit silencieux. Le devis dit tout de
  même ce que cela aurait coûté.
* **Le bill of materials enregistre le champ `payer` par saut** — `local`, `trial`, `channel`
  ou `unpaid` — de sorte qu'une exécution gratuite n'est jamais la preuve signée d'un achat.

Au-delà de l'offre gratuite, un saut se règle sur un canal de paiement contrôlé par l'appelant,
et l'enregistrement nomme ce canal.

## Relire une exécution

L'exécuteur signe un bill of materials par exécution et le persiste. Avant ces routes, rien ne pouvait
le relire : l'attribution de faute au saut — la preuve sur laquelle reposent un litige et toute
pénalité (slashing) qui en découle — n'était visible que par l'auteur du POST initial.

| Route | Renvoie |
|-------|---------|
| `GET /ai-market/pipelines?limit=N` | Exécutions récentes en **projection expurgée** : coût, sauts, statut par saut, faute. |
| `GET /ai-market/pipelines/{trace_id}` | Le bill of materials **signé**, à l'identique. |

La séparation est délibérée. Une signature couvre l'objet tel qu'il a été écrit : filtrer la réponse
par identifiant renverrait donc quelque chose d'invérifiable. Énumérer pose le problème inverse : un
flux public d'exécutions publierait quel canal de paiement a financé quoi, ainsi que les nonces de
reçu par saut, qui sont des clés de recherche de reçus publics portant des montants. Le listing retire
donc `channel_id` et `receipt_nonce`, et chaque ligne indique le chemin vers son propre original
signé.

### Faute

L'échec d'un pipeline est la faute du saut qui a échoué, jamais celle du graphe entier. Le bill of
materials nomme le saut fautif et disculpe explicitement les sauts amont qui ont fait leur travail,
afin qu'un litige ne vise que le fournisseur responsable :

```json
{
  "policy": "hop-level",
  "at_fault": {"id": "v", "capability_id": "metis.verify@v1", "status_code": 500},
  "not_at_fault": ["s"],
  "not_executed": ["d"]
}
```

## Soumettre un graphe

Un plan devient le corps de requête de l'exécuteur. Seuls les nœuds de capacité voyagent : déclencheurs
et sorties sont la façon dont une personne lit un canevas, non des sauts facturés à quiconque :

```json
{
  "nodes": [
    {"id": "s", "product_id": "prod-mcp", "capability_id": "web.search@v1",
     "input": {"query": "a claim"}, "depends_on": []},
    {"id": "v", "product_id": "prod-metis", "capability_id": "metis.verify@v1",
     "input": {"claim": "a claim"}, "depends_on": ["s"], "input_from": "s"}
  ]
}
```

```bash
curl -s -X POST https://magic-ai-factory.com/ai-market/pipelines \
  -H 'content-type: application/json' --data @blueprint.json
```

La réponse porte `trace_id`, le `bill_of_materials` signé et `final_result`.

## Où se trouve quoi

| Chemin | Quoi |
|--------|------|
| [`hephaestus/src/catalog.ts`](https://github.com/alexar76/hephaestus/blob/main/src/catalog.ts) | Manifeste → catalogue de capacités ; la règle de réputation |
| [`hephaestus/src/estimate.ts`](https://github.com/alexar76/hephaestus/blob/main/src/estimate.ts) | Devis coût et latence |
| [`hephaestus/src/blueprint.ts`](https://github.com/alexar76/hephaestus/blob/main/src/blueprint.ts) | Validation ; plan → `PipelineRequest` |
| [`hephaestus/src/wizards.ts`](https://github.com/alexar76/hephaestus/blob/main/src/wizards.ts) | Objectifs → rôles → une chaîne sur le catalogue du jour |
| `alien-monitor/backend/hephaestus_status.py` | Interroge les exécutions et l'état du catalogue pour le nœud |
| `alien-monitor/frontend/src/components/HephaestusRuns.tsx` | Le panneau d'observation |
| `web/backend/services/ai_market_protocol/pipelines.py` | Exécuteur, stockage des traces, projection |

Le noyau est sans dépendance et sans DOM à dessein : il doit servir la page du studio et toute autre
surface ayant besoin de chiffrer ou convertir un plan, il ne peut donc pas embarquer les partis pris
d'un framework d'interface.

```bash
cd hephaestus && npm install && npm run check    # types + 57 tests
```

## Limites à énoncer clairement

* Un devis n'est pas une offre ferme. Les prix proviennent d'un manifeste signé au moment de la
  lecture, et un fournisseur peut les modifier avant l'exécution.
* `reputation_basis: measured` signifie que quelqu'un a invoqué la capacité via *ce* hub, sur 30
  jours. C'est une preuve, pas une garantie.
* Un bill of materials signé prouve ce que cet exécuteur a enregistré. Il ne prouve pas que le
  résultat était correct : c'est le rôle de la couche de vérification.
