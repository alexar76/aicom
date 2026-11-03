# Déclarer son écosystème pour qu'il s'affiche correctement

> ## ⚠️ AVERTISSEMENT — À LIRE EN PREMIER
>
> **Les moniteurs et les pairs affichent EXACTEMENT ce que votre hub déclare. Rien de plus.**
>
> Aucun moniteur ne devinera l'adresse publique de vos services, et aucun ne devrait le
> faire : deviner voudrait dire scanner votre hôte à la recherche de ports ouverts et
> publier ce qui répond. Si vous déclarez `http://memory-market:8810`, alors quiconque
> regarde n'importe quelle carte — la vôtre ou celle d'un autre opérateur — verra
> `http://memory-market:8810` : une adresse qui résout sur exactement une machine au monde
> et qui est inutile à toutes les autres.
>
> **Un hub qui ne déclare pas d'adresses publiques n'est pas « mal configuré » d'une façon
> que quelqu'un pourrait corriger pour vous. Il est le seul à connaître la réponse.**

## D'où vient un nœud (ce n'est pas de la découverte)

Un moniteur ne trouve pas vos fournisseurs. Il lit `/.well-known/ai-market.json` et
déballe `ecosystem.nodes` — rien d'autre. Pas de scan de ports, pas de sondage de
sous-domaines, pas de devinette :

```python
# alien-monitor/backend/hub_discovery.py
ecosystem = well_known.get("ecosystem")
declared_nodes = ecosystem.get("nodes") if isinstance(ecosystem, dict) else []
```

La chaîne est donc : **une capacité est publiée sur votre hub → votre hub en construit
`ecosystem.nodes` → le hub le sert → un moniteur le dessine.** Le nœud existe parce qu'il
est enregistré sur le hub, un point c'est tout. Un sous-domaine n'est pas la façon dont on
le trouve ; un sous-domaine est seulement ce que se trouve être son ADRESSE, si vous
publiez le service sous un tel nom.

## Ce qui casse, et pourquoi cela ressemble à un bug de la carte

Un fournisseur est enregistré avec l'adresse que **votre hub** utilise pour l'appeler. Sur
un déploiement mono-machine, cette adresse est un nom de conteneur :

```
http://memory-market:8810
http://truth-layer:8811
http://provenance-ledger:8812
```

Votre hub les publie ensuite dans `/.well-known/ai-market.json` sous `ecosystem.nodes`, et
ce sont elles qu'un moniteur dessine. Le nœud apparaît, il est correctement nommé, il
annonce son nombre de capacités — et son adresse, personne ne peut l'ouvrir. Le lecteur
conclut raisonnablement que la carte est cassée. La carte rapporte fidèlement.

Mesuré sur `hub.attestedmemory.net`, 2026-09-07 : trois fournisseurs, trois noms de
conteneur, trois fiches inutilisables. Sur `independentai.network/hub`, ces mêmes trois
champs portaient `https://kova.independentai.network`,
`https://aegis.independentai.network` et une URL d'invocation publique — même code, mêmes
moniteurs, résultat correct. La différence était la configuration, et jusqu'ici il n'y
avait pas de variable pour la loger : les noms pouvaient être définis
(`AIMARKET_ECOSYSTEM_LABELS`), les adresses non.

## Les trois variables

Définissez-les toutes les trois. Elles répondent à trois questions différentes.

| Variable | Question à laquelle elle répond | Exemple |
|---|---|---|
| `AIMARKET_HUB_URL` | Où **ce hub** est-il joignable ? | `https://hub.example.net` |
| `AIMARKET_ECOSYSTEM_LABELS` | Comment mes fournisseurs s'**appellent**-ils ? | `memory-market:Memory Market,truth-layer:Truth Layer` |
| `AIMARKET_ECOSYSTEM_URLS` | Où mes fournisseurs sont-ils **joignables** ? | `memory-market=https://memory.example.net,truth-layer=https://truth.example.net` |

Détails qui coûtent du temps si on les rate :

* `AIMARKET_ECOSYSTEM_LABELS` sépare par `:` — la valeur est un nom.
* `AIMARKET_ECOSYSTEM_URLS` sépare par **`=`** — la valeur est une URL et contient déjà un
  deux-points.
* Les entrées sont indexées par **`publisher_id`**, l'identifiant sous lequel la capacité a
  été publiée : ni le nom affiché, ni l'identifiant produit.
  `GET /ai-market/v2/manifest` le montre.
* Tout ce qui n'est pas `http://…` ou `https://…` est ignoré plutôt que publié. Une entrée
  mal formée laisse l'adresse dérivée en place ; elle ne vide pas le nœud.
* Une adresse déclarée **l'emporte** sur toute adresse dérivable de l'URL d'invocation.
  C'est tout l'intérêt : votre hub appelle un fournisseur par un chemin et le monde
  l'atteint par un autre.
* `AIMARKET_HUB_URL` doit être votre adresse **publique**. Un hub qui annonce
  `http://localhost:9084` demande à chaque pair d'appeler sa propre boucle locale.

## Comment le déployer

1. **Publiez les services.** Une déclaration est une promesse ; rendez-la vraie d'abord. Un
   sous-domaine par fournisseur est le motif de cet écosystème (`kova.`, `aegis.`,
   `charon.`) :

   * ajoutez un enregistrement DNS `A` par nom, pointant vers l'hôte ;
   * ajoutez un bloc `server` nginx par nom, en proxy vers le port local ;
   * émettez les certificats (`certbot --nginx -d memory.example.net …`) — HTTP-01 exige
     que le DNS résolve **d'abord**, donc procédez dans cet ordre.

   Des chemins sur un seul domaine (`https://example.net/memory`) fonctionnent aussi et ne
   demandent ni nouveau DNS ni nouveau certificat, mais le service doit tolérer d'être
   servi sous un préfixe — la plupart servent `/v1/…` à leur racine et ne le tolèrent pas.

2. **Définissez les variables** là où votre déploiement conserve l'environnement (`.env`,
   un bloc `environment:` de compose, un `EnvironmentFile` systemd).

3. **Redémarrez le hub.** Elles sont lues à la construction du document well-known.

4. **Vérifiez** — ne le supposez pas :

   ```bash
   curl -s https://hub.example.net/.well-known/ai-market.json \
     | python3 -c 'import json,sys; d=json.load(sys.stdin); \
       print([(n["name"], n["url"]) for n in (d.get("ecosystem") or {}).get("nodes") or []])'
   ```

   Chaque adresse de cette liste doit pouvoir être collée dans un navigateur **depuis une
   autre machine**. Ouvrez ensuite le nœud sur un moniteur : une adresse publique déclarée
   s'affiche comme un lien cliquable ; une adresse interne s'affiche en texte gris étiqueté
   **internal address** et n'est jamais proposée comme lien.

## Checklist

- [ ] chaque service fournisseur répond sur une adresse publique
- [ ] `AIMARKET_HUB_URL` est l'adresse publique de ce hub, pas la boucle locale
- [ ] `AIMARKET_ECOSYSTEM_LABELS` nomme chaque fournisseur
- [ ] `AIMARKET_ECOSYSTEM_URLS` adresse chaque fournisseur, `=` comme séparateur
- [ ] `publisher_id` utilisé comme clé, pris dans le manifeste
- [ ] document well-known vérifié depuis une **autre** machine
- [ ] la fiche du nœud sur un moniteur montre un lien, pas « internal address »

## Voir aussi

* [federation-admission.fr.md](./federation-admission.fr.md) — comment un hub pair est admis.
* [federation-peer-keys.fr.md](./federation-peer-keys.fr.md) — comment sa clé est épinglée.
* [who-gets-a-sphere.fr.md](./who-gets-a-sphere.fr.md) — pourquoi un de vos nœuds peut ne pas être dessiné sur la carte d'un autre, et les trois façons d'y remédier.
