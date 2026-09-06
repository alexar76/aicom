# HEPHAESTUS — cas d'usage

> **English:** [hephaestus-use-cases.md](./hephaestus-use-cases.md) · **Русский:** [hephaestus-use-cases.ru.md](./hephaestus-use-cases.ru.md) · **Español:** [hephaestus-use-cases.es.md](./hephaestus-use-cases.es.md) · **中文:** [hephaestus-use-cases.zh.md](./hephaestus-use-cases.zh.md)
>
> Comment piloter la page : [hephaestus-user-guide.fr.md](./hephaestus-user-guide.fr.md) · Comment cela fonctionne à l'intérieur : [hephaestus-studio.fr.md](./hephaestus-studio.fr.md) · **Installation et captures:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

Chaque chaîne ci-dessous est construite avec des capacités en vente **aujourd'hui** — 76 lignes
entre GAIA, la famille d'oracles et ATLAS — aux prix que publie réellement la liste en direct.
Le JSON est ce que donne `Copy request`, si bien que chacune s'exécute telle quelle depuis un
terminal ou un agent.

---

## 1. Une mesure de capteur que l'on peut défendre

**Pour qui :** quiconque fonde une décision sur un nombre venu de l'appareil d'un autre.
**Coût :** $0.0030 · **2 sauts** · couvert par l'offre gratuite.

Une mesure seule est une affirmation. Cette chaîne achète la mesure puis achète un second avis
dessus — auprès d'un vérificateur statistique qui contrôle les bornes, la vitesse de variation
et l'accord avec les appareils voisins — et conserve un enregistrement signé des deux étapes.

```json
{"nodes": [
  {"id": "read", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
   "input": {}, "depends_on": [], "source_hub": "https://iot.modelmarket.dev"},
  {"id": "check", "product_id": "gaia.gateway", "capability_id": "gaia.verify@v1",
   "input": {"reading": "${read.reading}", "attestation": "${read.attestation}"},
   "depends_on": ["read"], "source_hub": "https://iot.modelmarket.dev"}
]}
```

Ce qui revient est un verdict, pas une impression :

```json
{"verified": false, "score": 0.6667, "summary": "failed: sibling:pressure_hpa",
 "checks": [{"name": "known_device", "ok": true}, {"name": "device_attestation", "ok": true}]}
```

**Pourquoi cela vaut de l'argent :** le vérificateur a contredit le capteur et a dit quel
contrôle avait échoué. C'est la différence entre « nous avions une mesure » et « nous avions une
mesure et savions à quel point s'y fier ». C'est la chaîne sur laquelle le studio ouvre.

---

## 2. Un tirage pour lequel personne n'a besoin d'être cru

**Pour qui :** qui organise une loterie, une attribution, un échantillon d'audit aléatoire.
**Coût :** ~$0.0060 · **2 sauts**.

`platon.random@v1` renvoie des octets aléatoires avec une preuve de reproductibilité et une
signature Ed25519 ; `chronos.eval@v1` est une fonction à retard vérifiable — la preuve qu'un
temps séquentiel réel s'est écoulé. Les enchaîner donne un tirage qu'on ne peut ni relancer
après coup ni avoir calculé à l'avance.

```json
{"nodes": [
  {"id": "seed", "product_id": "prod-platon", "capability_id": "platon.random@v1",
   "input": {"num_bytes": 32}, "depends_on": [],
   "source_hub": "https://oracles.modelmarket.dev/family"},
  {"id": "delay", "product_id": "prod-chronos", "capability_id": "chronos.eval@v1",
   "input": {"seed": "${seed.random_hex}", "difficulty": 200},
   "depends_on": ["seed"], "source_hub": "https://oracles.modelmarket.dev/family"}
]}
```

**Pourquoi cela vaut de l'argent :** publiez la trace et les participants vérifient le tirage
eux-mêmes. Vous ne demandez pas qu'on vous croie.

---

## 3. Répéter le coût avant de figer une architecture

**Pour qui :** celui qui doit répondre « combien coûtera ce pipeline à un million d'appels ? ».
**Coût :** $0 — vous n'appuyez jamais sur Run.

Assemblez le graphe envisagé. L'en-tête donne le prix par exécution d'après la liste signée,
ventilé par saut, plus un plancher de latence. Multipliez par votre volume. Remplacez un saut
par un fournisseur moins cher et regardez le chiffre bouger.

Deux choses que le devis refuse de faire, et c'est pour cela qu'il sert :

* une capacité sans prix est **nommée**, jamais comptée comme gratuite ;
* l'argent est additionné en micro-dollars entiers, car un catalogue de lectures à $0.001 ne
  survit pas intact à une addition en virgule flottante.

**Pourquoi cela en vaut la peine :** la réponse est défendable. Elle vient de prix qu'un pair a
signés, pas d'un tableur que quelqu'un a saisi.

---

## 4. Une preuve pour un litige

**Pour qui :** quiconque paie plusieurs fournisseurs dans un même flux.
**Coût :** l'exécution que vous avez déjà faite.

Quand une chaîne échoue, le bill of materials signé nomme le saut fautif et **disculpe
explicitement** ceux qui ont fait leur travail :

```json
{"policy": "hop-level",
 "at_fault": {"id": "check", "capability_id": "gaia.verify@v1", "status_code": 500},
 "not_at_fault": ["read"], "not_executed": []}
```

Chaque saut enregistre aussi qui l'a payé — `trial`, `channel` ou `local` — de sorte qu'une
exécution gratuite ne passe jamais pour un achat.

**Pourquoi cela vaut de l'argent :** sans faute par saut, une chaîne échouée est une facture et
une dispute. Avec elle, le fournisseur amont est payé, le fautif est identifié, et il existe un
document signé à montrer. L'échelle de pénalités de l'écosystème lit exactement cela.

---

## 5. Savoir si une capacité vaut l'achat

**Pour qui :** un intégrateur qui choisit entre des offres.
**Coût :** gratuit, dans la limite du solde.

Le catalogue publie, par ligne : le prix, la latence déclarée, si elle déclare seulement ses
entrées et sorties, et la quantité de preuves derrière sa fiabilité. Aujourd'hui c'est **27
lignes avec un taux de succès mesuré et 49 sans aucun** — et pour le second groupe la page écrit
« no calls yet » au lieu d'afficher une valeur de remplissage comme s'il s'agissait d'une note.

Ajoutez la ligne, remplissez ses champs, exécutez-la une fois sur l'offre gratuite, lisez le
résultat réel. Puis décidez.

**Pourquoi cela en vaut la peine :** vous évaluez sur votre propre entrée, pas sur une démo
choisie par le vendeur, et vous découvrez en une minute si le schéma correspond à la réalité.

---

## 6. Confier un graphe à votre propre agent

**Pour qui :** qui construit un agent censé acheter du travail plutôt que le simuler.
**Coût :** ce que coûte le graphe, sur votre canal.

Assemblez et vérifiez le graphe à la main, appuyez sur **Copy request**, collez le JSON dans
votre agent. Il envoie le même corps à l'exécuteur et reçoit le même enregistrement signé. Le
studio est l'endroit où une personne réfléchit à la forme ; l'agent l'exécute mille fois.

```bash
curl -s -X POST https://magic-ai-factory.com/ai-market/pipelines \
  -H 'content-type: application/json' --data @graph.json
```

**Pourquoi cela en vaut la peine :** ce que vous avez testé est, octet pour octet, ce qui tourne.

---

## Ce à quoi cela ne sert PAS

* **Un moteur de workflow généraliste.** Pas de boucles, de branches, de reprises ni de nœuds
  HTTP, et les ajouter échangerait le seul avantage présent ici : chaque nœud est une ligne de
  marché tarifée et vérifiable.
* **Un outil de transformation de données.** Les valeurs sont acheminées entre sauts avec
  `${hop.field}`, non remodelées. La transformation est une capacité que quelqu'un vend.
* **Un endroit pour des secrets.** Les champs partent chez le fournisseur. N'écrivez rien dans
  un champ que vous ne lui remettriez pas directement.
* **La preuve qu'une réponse est vraie.** Un enregistrement signé prouve ce que l'exécuteur a
  fait. La justesse du résultat est l'affaire d'un saut de vérification : voir le premier cas.
