# Добавление узла в Alien Monitor

> 🌐 [English](add-a-monitor-node.md) · **Русский** · [Español](add-a-monitor-node.es.md) · [Français](add-a-monitor-node.fr.md) · [中文](add-a-monitor-node.zh.md)

Есть **два** способа сделать так, чтобы нечто стало пузырём на 3D-карте Alien Monitor. Выберите тот,
который соответствует тому, что вы добавляете.

## Какой путь?

| Ваш компонент | Путь | Где это описано |
|---|---|---|
| Живой HTTP-сервис, который федерируется (отдаёт подписанный манифест `/.well-known/ai-market`) | **Автообнаружение** — краулер монитора находит его сам | [onboard-a-node.md](onboard-a-node.md) + [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md) |
| Полноценный компонент экосистемы, который **не** федерируется как живой сервис (инструмент, харнесс, внутренний слой — MOMUS, BASANOS, DOLOS) | **Захардкоженный узел** — вшивается в код самого монитора | **этот документ** |

Если ваш компонент уже федерируется, этот документ вам **не** нужен — узел появится автоматически.
Это руководство для случая с хардкодом, и весь его смысл в одном выстраданном правиле:

> **Четыре места, иначе узел молча исчезнет.** Режим Universe (UNI) не вызывает
> `build_topology()`; он строит свой граф из *засеянных сущностей*, а хелперы `apply_*_graph`
> лишь декорируют уже существующий узел. Узел, вшитый только в `build_topology()`, невидим
> в UNI. Пропишите все места ниже.

Сквозной рабочий пример — **DOLOS** (`alien-monitor/backend/dolos_layers.py`,
`dolos_status.py`), динамическая EVM red team, добавленная рядом с BASANOS. Замените `dolos` / `DOLOS`
на id вашего узла.

## Бэкенд — обязательные места

Все пути — относительно `alien-monitor/backend/`.

### 1. `<name>_layers.py` — идентичность и рёбра

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

Каждый `source`/`target` **должен быть реальным id узла** — висячее ребро проваливает тест топологии
(`test_every_edge_ends_on_a_node_that_exists`).

### 2. `<name>_status.py` — декоратор `apply_*_graph` (и любые живые данные)

```python
def apply_<name>_graph(nodes: list[dict], *, mode: str = "real") -> None:
    apply_<name>_to_nodes(nodes, fetch_<name>_status_sync())
```

`apply_*_to_nodes` находит узел, уже присутствующий в списке (по id), и обновляет его `metrics`/`status`.
Если у вашего узла **нет живого демона для опроса** (DOLOS — это CLI-харнесс), читайте артефакт
последнего запуска и откатывайтесь к статической идентичности — никогда не выдумывайте статус, который
вы не наблюдали.

### 3. `ecosystem_layout.py` — позиция, соблюдающая дистанцию

```python
NODE_POSITIONS = {
    ...
    "<name>": {"x": 12.5, "y": -8.5, "z": 5.0},
}
```

Держите её **≥ 4.5** от каждого другого статического узла и от кольца оракулов, иначе
`test_ecosystem_layout.py` провалится. (DOLOS стоит в 5.59 от BASANOS.)

### 4. `main.py` — топология LIVE/TEST (три правки)

```python
from <name>_layers import <name>_node_spec, <name>_topology_links   # import

nodes = [ ..., <name>_node_spec() ]                                  # in the node list
links.extend(<name>_topology_links())                               # in the links
...
from <name>_status import apply_<name>_graph
apply_<name>_graph(nodes, mode="real")                             # in the real-metrics path
```

### 5. `satellite_overlays.py` — декорация UNI

```python
from <name>_status import apply_<name>_graph
steps = ( ..., ("<name>", lambda: apply_<name>_graph(nodes, mode="universe")) )
```

### 6. `universe.py` — засев UNI (место, которое чаще всего пропускают)

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

Затем **вызовите это в обоих местах засева** (`seed_entities()` и путь пересева — найдите
существующий `self._seed_basanos_entity()` и добавьте свой рядом с каждым), и добавьте свои рёбра в
`get_topology_links()`:

```python
from <name>_layers import <name>_topology_links
links.extend(<name>_topology_links())
```

## Фронтенд — опционально, для кастомной карточки деталей

Пузырь отрисовывается автоматически из топологии бэкенда (позиция, цвет, метка), и клик по нему
показывает **типовую** карточку деталей. Кастомная карточка — это лоск, а не требование.

- `frontend/src/components/cards/<Name>Card.tsx` — читает `node.metrics` и любые кастомные поля,
  которые вы задали в `apply_*_to_nodes` (объявите их через `node as unknown as {...}`).
- `frontend/src/components/NodeDetail.tsx` — импортируйте её и маршрутизируйте:
  `{node.id === '<name>' && <<Name>Card node={node} themeColor={themeColor} mobile={mobile} t={t} />}`
- `frontend/src/i18n/locales/{en,ru,es,fr,zh}.json` — добавьте блок `<name>.*` (во все пять). У карточки
  `t('<name>.key', undefined, 'fallback')` отрисует запасной вариант ещё до того, как появятся ключи.
- 3D-сцена (`nodeScenes/`) полностью опциональна; без неё узел использует сферу по умолчанию.

## Проверьте — по образцу `test_<name>_node.py`

Скопируйте `alien-monitor/tests/test_basanos_node.py` и поменяйте имена. Он точно фиксирует
ловушку четырёх мест: в `build_topology` с его рёбрами, засеян в режиме universe, переживает путь
пересева и присутствует в `get_topology_links()` — плюс правило разделения и любое правило честности,
которое нужно вашему узлу.

## Деплой

Монитор — это два голых контейнера `docker run` (`alien-monitor-live` realm `real`,
`alien-monitor` realm `universe`), net=host. Пересоберите образ и пересоздайте их:

```bash
# from the monorepo root, build with the base path the containers serve at ("/")
docker build -f alien-monitor/Dockerfile --build-arg VITE_BASE_PATH=/ -t alien-monitor:live-<tag> .
# recreate each container on the new image, preserving its env/mounts (see redeploy_monitor.sh)
```

> **Ловушка base-path:** `VITE_BASE_PATH` запекается на этапе сборки. Контейнеры отдают по `/`, поэтому
> собирайте с `--build-arg VITE_BASE_PATH=/`, иначе каждый ассет отдаёт 404.

Изменение только в бэкенде (без фронтенда) можно выкатить тонким слоем вместо полной пересборки:
`FROM alien-monitor:live-<prev>` + `COPY backend/<file> /app/backend/<file>`.

## Верификация

```bash
curl -s https://monitor-uni.modelmarket.dev/api/topology \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('<name>' in {n['id'] for n in d['nodes']})"
```

Проверьте **оба** realm-а (`monitor.modelmarket.dev` и `monitor-uni.modelmarket.dev`) — именно на UNI
кусается ловушка четырёх мест. Открывайте карточку узла по прямой ссылке через `?node=<name>`.

---

MIT · часть экосистемы AIMarket. Компаньон к [onboard-a-node.md](onboard-a-node.md) (путь
федерации) и [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md).
