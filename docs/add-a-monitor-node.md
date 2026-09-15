# Add a node to the Alien Monitor

> 🌐 **English** · [Русский](add-a-monitor-node.ru.md) · [Español](add-a-monitor-node.es.md) · [Français](add-a-monitor-node.fr.md) · [中文](add-a-monitor-node.zh.md)

There are **two** ways for something to become a bubble on the Alien Monitor's 3D map. Pick the one
that matches what you are adding.

## Which path?

| Your component | Path | Where it's documented |
|---|---|---|
| A live HTTP service that federates (serves a signed `/.well-known/ai-market` manifest) | **Autodiscovery** — the monitor's crawler finds it | [onboard-a-node.md](onboard-a-node.md) + [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md) |
| A first-class ecosystem component that does **not** federate as a live service (a tool, a harness, an internal layer — MOMUS, BASANOS, DOLOS) | **Hardcoded node** — wired into the monitor's own code | **this document** |

If your component already federates, you do **not** need this document — it appears automatically.
This guide is for the hardcoded case, and its whole point is one hard-won rule:

> **Four places, or the node silently vanishes.** Universe (UNI) mode does not call
> `build_topology()`; it builds its graph from *seeded entities*, and the `apply_*_graph` helpers
> only decorate a node that already exists. A node wired into `build_topology()` alone is invisible
> in UNI. Wire all of the places below.

The worked example throughout is **DOLOS** (`alien-monitor/backend/dolos_layers.py`,
`dolos_status.py`), the dynamic EVM red team added beside BASANOS. Replace `dolos` / `DOLOS` with
your node's id.

## Backend — the required places

All paths are under `alien-monitor/backend/`.

### 1. `<name>_layers.py` — identity and edges

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

Every `source`/`target` **must be a real node id** — a dangling edge fails the topology test
(`test_every_edge_ends_on_a_node_that_exists`).

### 2. `<name>_status.py` — the `apply_*_graph` decorator (and any live data)

```python
def apply_<name>_graph(nodes: list[dict], *, mode: str = "real") -> None:
    apply_<name>_to_nodes(nodes, fetch_<name>_status_sync())
```

`apply_*_to_nodes` finds the node already in the list (by id) and updates its `metrics`/`status`.
If your node has **no live daemon to poll** (DOLOS is a CLI harness), read a last-run artifact and
fall back to a static identity — never invent a status you did not observe.

### 3. `ecosystem_layout.py` — a position that keeps its distance

```python
NODE_POSITIONS = {
    ...
    "<name>": {"x": 12.5, "y": -8.5, "z": 5.0},
}
```

Keep it **≥ 4.5** from every other static node and from the oracle ring, or
`test_ecosystem_layout.py` fails. (DOLOS sits 5.59 from BASANOS.)

### 4. `main.py` — LIVE/TEST topology (three edits)

```python
from <name>_layers import <name>_node_spec, <name>_topology_links   # import

nodes = [ ..., <name>_node_spec() ]                                  # in the node list
links.extend(<name>_topology_links())                               # in the links
...
from <name>_status import apply_<name>_graph
apply_<name>_graph(nodes, mode="real")                             # in the real-metrics path
```

### 5. `satellite_overlays.py` — UNI decoration

```python
from <name>_status import apply_<name>_graph
steps = ( ..., ("<name>", lambda: apply_<name>_graph(nodes, mode="universe")) )
```

### 6. `universe.py` — UNI seeding (the place most often missed)

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

Then **call it in both seed sites** (`seed_entities()` and the reseed path — search for an
existing `self._seed_basanos_entity()` and add yours next to each), and add your links in
`get_topology_links()`:

```python
from <name>_layers import <name>_topology_links
links.extend(<name>_topology_links())
```

## Frontend — optional, for a custom detail card

The bubble renders automatically from the backend topology (position, colour, label), and clicking
it shows a **generic** detail card. A custom card is polish, not a requirement.

- `frontend/src/components/cards/<Name>Card.tsx` — read `node.metrics` and any custom fields you
  set in `apply_*_to_nodes` (declare them via `node as unknown as {...}`).
- `frontend/src/components/NodeDetail.tsx` — import it and route:
  `{node.id === '<name>' && <<Name>Card node={node} themeColor={themeColor} mobile={mobile} t={t} />}`
- `frontend/src/i18n/locales/{en,ru,es,fr,zh}.json` — add a `<name>.*` block (all five). The card's
  `t('<name>.key', undefined, 'fallback')` renders the fallback even before the keys exist.
- A 3D scene (`nodeScenes/`) is entirely optional; without one the node uses the default sphere.

## Test it — mirror `test_<name>_node.py`

Copy `alien-monitor/tests/test_basanos_node.py` and swap names. It pins exactly the four-places
trap: in `build_topology` with its edges, seeded in universe mode, surviving the reseed path, and
present in `get_topology_links()` — plus the separation rule and any honesty rule your node needs.

## Deploy

The monitor is two bare `docker run` containers (`alien-monitor-live` realm `real`,
`alien-monitor` realm `universe`), net=host. Rebuild the image and recreate them:

```bash
# from the monorepo root, build with the base path the containers serve at ("/")
docker build -f alien-monitor/Dockerfile --build-arg VITE_BASE_PATH=/ -t alien-monitor:live-<tag> .
# recreate each container on the new image, preserving its env/mounts (see redeploy_monitor.sh)
```

> **Base-path trap:** `VITE_BASE_PATH` is baked at build time. The containers serve at `/`, so build
> with `--build-arg VITE_BASE_PATH=/` or every asset 404s.

A backend-only change (no frontend) can ship as a thin layer instead of a full rebuild:
`FROM alien-monitor:live-<prev>` + `COPY backend/<file> /app/backend/<file>`.

## Verify

```bash
curl -s https://monitor-uni.modelmarket.dev/api/topology \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('<name>' in {n['id'] for n in d['nodes']})"
```

Check **both** realms (`monitor.modelmarket.dev` and `monitor-uni.modelmarket.dev`) — the UNI one is
where the four-places trap bites. Deep-link a node's card with `?node=<name>`.

---

MIT · part of the AIMarket ecosystem. Companion to [onboard-a-node.md](onboard-a-node.md) (the
federation path) and [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md).
