# Ajouter un nœud à l'Alien Monitor

> 🌐 [English](add-a-monitor-node.md) · [Русский](add-a-monitor-node.ru.md) · [Español](add-a-monitor-node.es.md) · **Français** · [中文](add-a-monitor-node.zh.md)

Il existe **deux** façons pour qu'un élément devienne une bulle sur la carte 3D de l'Alien Monitor.
Choisissez celle qui correspond à ce que vous ajoutez.

## Quel chemin ?

| Votre composant | Chemin | Où c'est documenté |
|---|---|---|
| Un service HTTP actif qui fédère (sert un manifeste `/.well-known/ai-market` signé) | **Autodécouverte** — le crawler du monitor le trouve | [onboard-a-node.md](onboard-a-node.md) + [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md) |
| Un composant de premier plan de l'écosystème qui ne fédère **pas** comme un service actif (un outil, un harnais, une couche interne — MOMUS, BASANOS, DOLOS) | **Nœud codé en dur** — intégré dans le code même du monitor | **ce document** |

Si votre composant fédère déjà, vous n'avez **pas** besoin de ce document — il apparaît
automatiquement. Ce guide concerne le cas codé en dur, et tout son intérêt tient à une règle
durement acquise :

> **Quatre endroits, sinon le nœud disparaît silencieusement.** Le mode Universe (UNI) n'appelle pas
> `build_topology()` ; il construit son graphe à partir d'*entités semées*, et les helpers
> `apply_*_graph` ne font que décorer un nœud qui existe déjà. Un nœud intégré uniquement dans
> `build_topology()` est invisible dans UNI. Intégrez-le à tous les endroits ci-dessous.

L'exemple filé tout au long est **DOLOS** (`alien-monitor/backend/dolos_layers.py`,
`dolos_status.py`), la red team EVM dynamique ajoutée à côté de BASANOS. Remplacez `dolos` / `DOLOS`
par l'id de votre nœud.

## Backend — les endroits requis

Tous les chemins sont sous `alien-monitor/backend/`.

### 1. `<name>_layers.py` — identité et arêtes

```python
from <name>_status import <name>_links, <name>_public_url
from ecosystem_layout import node_position

def <name>_node_spec(*, mode: str = "real") -> dict:
    return {
        "id": "<name>", "label": "<NAME>", "group": "security",  # or your tier
        "icon": "blade", "description": "... what it is, and what it is NOT ...",
        "metrics": {...}, "status": "idle",
        "position": node_position("<name>"),
        "color": "#e5484d", "url": <name>_public_url(), "links": <name>_links(),
    }

def <name>_topology_links() -> list[dict]:
    return [
        {"source": "acex", "target": "<name>", "label": "..."},   # incoming
        {"source": "<name>", "target": "skopos", "label": "..."}, # outgoing
    ]
```

Chaque `source`/`target` **doit être un id de nœud réel** — une arête pendante fait échouer le test
de topologie (`test_every_edge_ends_on_a_node_that_exists`).

### 2. `<name>_status.py` — le décorateur `apply_*_graph` (et toute donnée en direct)

```python
def apply_<name>_graph(nodes: list[dict], *, mode: str = "real") -> None:
    apply_<name>_to_nodes(nodes, fetch_<name>_status_sync())
```

`apply_*_to_nodes` trouve le nœud déjà présent dans la liste (par id) et met à jour ses
`metrics`/`status`. Si votre nœud n'a **aucun daemon actif à interroger** (DOLOS est un harnais CLI),
lisez un artefact de dernière exécution et repliez-vous sur une identité statique — n'inventez jamais
un statut que vous n'avez pas observé.

### 3. `ecosystem_layout.py` — une position qui garde ses distances

```python
NODE_POSITIONS = {
    ...
    "<name>": {"x": 12.5, "y": -8.5, "z": 5.0},
}
```

Gardez-la **≥ 4.5** de tout autre nœud statique et de l'anneau d'oracles, sinon
`test_ecosystem_layout.py` échoue. (DOLOS se trouve à 5.59 de BASANOS.)

### 4. `main.py` — topologie LIVE/TEST (trois modifications)

```python
from <name>_layers import <name>_node_spec, <name>_topology_links   # import

nodes = [ ..., <name>_node_spec() ]                                  # in the node list
links.extend(<name>_topology_links())                               # in the links
...
from <name>_status import apply_<name>_graph
apply_<name>_graph(nodes, mode="real")                             # in the real-metrics path
```

### 5. `satellite_overlays.py` — décoration UNI

```python
from <name>_status import apply_<name>_graph
steps = ( ..., ("<name>", lambda: apply_<name>_graph(nodes, mode="universe")) )
```

### 6. `universe.py` — semis UNI (l'endroit le plus souvent oublié)

```python
def _seed_<name>_entity(self) -> None:
    if "<name>" in self.entities:
        return
    from <name>_layers import <name>_node_spec
    spec = <name>_node_spec(mode="universe")
    ent = EcosystemEntity(spec["id"], spec["label"], "security", spec["group"],
                          icon=spec.get("icon"), description=spec.get("description"))
    ent.position = spec["position"]; ent.url = spec.get("url")
    ent.metrics = dict(spec.get("metrics") or {}); ent.status = spec.get("status", "idle")
    ent.color = spec.get("color", "#e5484d")
    self.entities[ent.id] = ent
```

Ensuite, **appelez-le aux deux emplacements de semis** (`seed_entities()` et le chemin de re-semis —
cherchez un `self._seed_basanos_entity()` existant et ajoutez le vôtre à côté de chacun), et ajoutez
vos liens dans `get_topology_links()` :

```python
from <name>_layers import <name>_topology_links
links.extend(<name>_topology_links())
```

## Frontend — optionnel, pour une carte de détail personnalisée

La bulle est rendue automatiquement à partir de la topologie backend (position, couleur, libellé), et
cliquer dessus affiche une carte de détail **générique**. Une carte personnalisée est une finition,
pas une exigence.

- `frontend/src/components/cards/<Name>Card.tsx` — lisez `node.metrics` et tout champ personnalisé
  que vous avez défini dans `apply_*_to_nodes` (déclarez-les via `node as unknown as {...}`).
- `frontend/src/components/NodeDetail.tsx` — importez-la et routez :
  `{node.id === '<name>' && <<Name>Card node={node} themeColor={themeColor} mobile={mobile} t={t} />}`
- `frontend/src/i18n/locales/{en,ru,es,fr,zh}.json` — ajoutez un bloc `<name>.*` (les cinq). Le
  `t('<name>.key', undefined, 'fallback')` de la carte rend le fallback même avant que les clés
  existent.
- Une scène 3D (`nodeScenes/`) est entièrement optionnelle ; sans elle, le nœud utilise la sphère par
  défaut.

## Testez-le — reproduisez `test_<name>_node.py`

Copiez `alien-monitor/tests/test_basanos_node.py` et changez les noms. Il verrouille exactement le
piège des quatre endroits : dans `build_topology` avec ses arêtes, semé en mode universe, survivant au
chemin de re-semis, et présent dans `get_topology_links()` — plus la règle de séparation et toute
règle d'honnêteté dont votre nœud a besoin.

## Déploiement

Le monitor consiste en deux conteneurs `docker run` nus (`alien-monitor-live` realm `real`,
`alien-monitor` realm `universe`), net=host. Reconstruisez l'image et recréez-les :

```bash
# from the monorepo root, build with the base path the containers serve at ("/")
docker build -f alien-monitor/Dockerfile --build-arg VITE_BASE_PATH=/ -t alien-monitor:live-<tag> .
# recreate each container on the new image, preserving its env/mounts (see redeploy_monitor.sh)
```

> **Piège du base-path :** `VITE_BASE_PATH` est figé au moment du build. Les conteneurs servent à `/`,
> donc buildez avec `--build-arg VITE_BASE_PATH=/` sinon chaque asset renvoie une 404.

Un changement backend seul (sans frontend) peut être livré comme une couche fine plutôt qu'un rebuild
complet : `FROM alien-monitor:live-<prev>` + `COPY backend/<file> /app/backend/<file>`.

## Vérification

```bash
curl -s https://monitor-uni.modelmarket.dev/api/topology \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('<name>' in {n['id'] for n in d['nodes']})"
```

Vérifiez les **deux** realms (`monitor.modelmarket.dev` et `monitor-uni.modelmarket.dev`) — c'est
dans UNI que le piège des quatre endroits se manifeste. Créez un lien direct vers la carte d'un nœud
avec `?node=<name>`.

---

MIT · fait partie de l'écosystème AIMarket. Complément de [onboard-a-node.md](onboard-a-node.md) (le
chemin de fédération) et de [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md).
