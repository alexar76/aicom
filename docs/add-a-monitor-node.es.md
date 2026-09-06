# Añadir un nodo al Alien Monitor

> 🌐 [English](add-a-monitor-node.md) · [Русский](add-a-monitor-node.ru.md) · **Español** · [Français](add-a-monitor-node.fr.md) · [中文](add-a-monitor-node.zh.md)

Hay **dos** maneras de que algo se convierta en una burbuja en el mapa 3D del Alien Monitor. Elige la
que corresponda a lo que estás añadiendo.

## ¿Qué ruta?

| Tu componente | Ruta | Dónde está documentado |
|---|---|---|
| Un servicio HTTP en vivo que federa (sirve un manifiesto `/.well-known/ai-market` firmado) | **Autodescubrimiento** — el crawler del monitor lo encuentra | [onboard-a-node.md](onboard-a-node.md) + [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md) |
| Un componente de primera clase del ecosistema que **no** federa como servicio en vivo (una herramienta, un harness, una capa interna — MOMUS, BASANOS, DOLOS) | **Nodo hardcodeado** — cableado en el propio código del monitor | **este documento** |

Si tu componente ya federa, **no** necesitas este documento — aparece automáticamente.
Esta guía es para el caso hardcodeado, y todo su sentido se reduce a una regla ganada a base de golpes:

> **Cuatro lugares, o el nodo desaparece en silencio.** El modo Universe (UNI) no llama a
> `build_topology()`; construye su grafo a partir de *entidades sembradas*, y los ayudantes
> `apply_*_graph` solo decoran un nodo que ya existe. Un nodo cableado únicamente en `build_topology()`
> es invisible en UNI. Cablea todos los lugares que se indican a continuación.

El ejemplo trabajado a lo largo del documento es **DOLOS** (`alien-monitor/backend/dolos_layers.py`,
`dolos_status.py`), el red team dinámico de EVM añadido junto a BASANOS. Reemplaza `dolos` / `DOLOS`
por el id de tu nodo.

## Backend — los lugares obligatorios

Todas las rutas están bajo `alien-monitor/backend/`.

### 1. `<name>_layers.py` — identidad y aristas

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

Cada `source`/`target` **debe ser un id de nodo real** — una arista colgante hace fallar el test de
topología (`test_every_edge_ends_on_a_node_that_exists`).

### 2. `<name>_status.py` — el decorador `apply_*_graph` (y cualquier dato en vivo)

```python
def apply_<name>_graph(nodes: list[dict], *, mode: str = "real") -> None:
    apply_<name>_to_nodes(nodes, fetch_<name>_status_sync())
```

`apply_*_to_nodes` encuentra el nodo que ya está en la lista (por id) y actualiza sus
`metrics`/`status`. Si tu nodo **no tiene un daemon en vivo que sondear** (DOLOS es un harness de CLI),
lee un artefacto de la última ejecución y recurre a una identidad estática — nunca inventes un estado
que no hayas observado.

### 3. `ecosystem_layout.py` — una posición que mantiene su distancia

```python
NODE_POSITIONS = {
    ...
    "<name>": {"x": 12.5, "y": -8.5, "z": 5.0},
}
```

Mantenla **≥ 4.5** de cualquier otro nodo estático y del anillo de oráculos, o
`test_ecosystem_layout.py` falla. (DOLOS está a 5.59 de BASANOS.)

### 4. `main.py` — topología LIVE/TEST (tres ediciones)

```python
from <name>_layers import <name>_node_spec, <name>_topology_links   # import

nodes = [ ..., <name>_node_spec() ]                                  # in the node list
links.extend(<name>_topology_links())                               # in the links
...
from <name>_status import apply_<name>_graph
apply_<name>_graph(nodes, mode="real")                             # in the real-metrics path
```

### 5. `satellite_overlays.py` — decoración UNI

```python
from <name>_status import apply_<name>_graph
steps = ( ..., ("<name>", lambda: apply_<name>_graph(nodes, mode="universe")) )
```

### 6. `universe.py` — sembrado UNI (el lugar que más se olvida)

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

Luego **llámalo en ambos sitios de sembrado** (`seed_entities()` y la ruta de resembrado — busca un
`self._seed_basanos_entity()` existente y añade el tuyo junto a cada uno), y añade tus enlaces en
`get_topology_links()`:

```python
from <name>_layers import <name>_topology_links
links.extend(<name>_topology_links())
```

## Frontend — opcional, para una tarjeta de detalle personalizada

La burbuja se renderiza automáticamente a partir de la topología del backend (posición, color,
etiqueta), y al hacer clic muestra una tarjeta de detalle **genérica**. Una tarjeta personalizada es
un pulido, no un requisito.

- `frontend/src/components/cards/<Name>Card.tsx` — lee `node.metrics` y cualquier campo personalizado
  que hayas establecido en `apply_*_to_nodes` (decláralos mediante `node as unknown as {...}`).
- `frontend/src/components/NodeDetail.tsx` — impórtala y enrútala:
  `{node.id === '<name>' && <<Name>Card node={node} themeColor={themeColor} mobile={mobile} t={t} />}`
- `frontend/src/i18n/locales/{en,ru,es,fr,zh}.json` — añade un bloque `<name>.*` (los cinco). El
  `t('<name>.key', undefined, 'fallback')` de la tarjeta renderiza el fallback incluso antes de que las
  claves existan.
- Una escena 3D (`nodeScenes/`) es completamente opcional; sin ella el nodo usa la esfera por defecto.

## Pruébalo — replica `test_<name>_node.py`

Copia `alien-monitor/tests/test_basanos_node.py` e intercambia los nombres. Fija exactamente la trampa
de los cuatro lugares: en `build_topology` con sus aristas, sembrado en modo universe, sobreviviendo a
la ruta de resembrado, y presente en `get_topology_links()` — además de la regla de separación y
cualquier regla de honestidad que tu nodo necesite.

## Despliegue

El monitor son dos contenedores `docker run` a secas (`alien-monitor-live` realm `real`,
`alien-monitor` realm `universe`), net=host. Reconstruye la imagen y vuelve a crearlos:

```bash
# from the monorepo root, build with the base path the containers serve at ("/")
docker build -f alien-monitor/Dockerfile --build-arg VITE_BASE_PATH=/ -t alien-monitor:live-<tag> .
# recreate each container on the new image, preserving its env/mounts (see redeploy_monitor.sh)
```

> **Trampa del base-path:** `VITE_BASE_PATH` se hornea en tiempo de build. Los contenedores sirven en
> `/`, así que compila con `--build-arg VITE_BASE_PATH=/` o cada asset dará 404.

Un cambio solo de backend (sin frontend) puede enviarse como una capa fina en lugar de una
reconstrucción completa: `FROM alien-monitor:live-<prev>` + `COPY backend/<file> /app/backend/<file>`.

## Verificar

```bash
curl -s https://monitor-uni.modelmarket.dev/api/topology \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('<name>' in {n['id'] for n in d['nodes']})"
```

Comprueba **ambos** realms (`monitor.modelmarket.dev` y `monitor-uni.modelmarket.dev`) — el de UNI es
donde muerde la trampa de los cuatro lugares. Enlaza directamente la tarjeta de un nodo con
`?node=<name>`.

---

MIT · parte del ecosistema AIMarket. Complemento de [onboard-a-node.md](onboard-a-node.md) (la ruta de
federación) y [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md).
