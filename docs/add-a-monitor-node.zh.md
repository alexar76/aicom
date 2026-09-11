# 为 Alien Monitor 添加一个节点

> 🌐 [English](add-a-monitor-node.md) · [Русский](add-a-monitor-node.ru.md) · [Español](add-a-monitor-node.es.md) · [Français](add-a-monitor-node.fr.md) · **中文**

有**两种**方式可以让某个东西成为 Alien Monitor 3D 地图上的一个气泡。请选择与你所添加内容相匹配的那一种。

## 选择哪条路径？

| Your component | Path | Where it's documented |
|---|---|---|
| 一个联邦化的实时 HTTP 服务（提供经过签名的 `/.well-known/ai-market` manifest） | **自动发现** —— monitor 的爬虫会找到它 | [onboard-a-node.md](onboard-a-node.md) + [ecosystem-autodiscovery.md](ecosystem-autodiscovery.md) |
| 一个**不**作为实时服务进行联邦的一等生态系统组件（一个工具、一个测试框架、一个内部层 —— MOMUS、BASANOS、DOLOS） | **硬编码节点** —— 直接接入 monitor 自身的代码 | **本文档** |

如果你的组件已经进行了联邦，那你**不**需要这份文档 —— 它会自动出现。本指南针对的是硬编码这种情况，而它的全部要点就是一条来之不易的规则：

> **四个地方，否则节点会悄无声息地消失。** Universe（UNI）模式不会调用
> `build_topology()`；它从*种子实体（seeded entities）*构建自己的图，而 `apply_*_graph` 辅助函数
> 只会装饰一个已经存在的节点。仅接入 `build_topology()` 的节点在 UNI 中是不可见的。请把下面所有
> 地方都接上。

全文贯穿的示例是 **DOLOS**（`alien-monitor/backend/dolos_layers.py`、
`dolos_status.py`），它是在 BASANOS 旁边新增的动态 EVM 红队。把 `dolos` / `DOLOS` 替换成
你自己节点的 id。

## 后端 —— 必须处理的地方

所有路径都位于 `alien-monitor/backend/` 之下。

### 1. `<name>_layers.py` —— 身份与边

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

每个 `source`/`target` **都必须是一个真实存在的节点 id** —— 悬空的边会导致拓扑测试
（`test_every_edge_ends_on_a_node_that_exists`）失败。

### 2. `<name>_status.py` —— `apply_*_graph` 装饰器（以及任何实时数据）

```python
def apply_<name>_graph(nodes: list[dict], *, mode: str = "real") -> None:
    apply_<name>_to_nodes(nodes, fetch_<name>_status_sync())
```

`apply_*_to_nodes` 会在列表中（按 id）找到已经存在的节点，并更新它的 `metrics`/`status`。
如果你的节点**没有可轮询的实时守护进程**（DOLOS 是一个 CLI 测试框架），那就读取上一次运行的产物，并
回退到一个静态身份 —— 绝不要编造一个你没有实际观测到的状态。

### 3. `ecosystem_layout.py` —— 一个保持距离的位置

```python
NODE_POSITIONS = {
    ...
    "<name>": {"x": 12.5, "y": -8.5, "z": 5.0},
}
```

让它与其他每一个静态节点以及 oracle 环的距离都 **≥ 4.5**，否则
`test_ecosystem_layout.py` 会失败。（DOLOS 距离 BASANOS 为 5.59。）

### 4. `main.py` —— LIVE/TEST 拓扑（三处修改）

```python
from <name>_layers import <name>_node_spec, <name>_topology_links   # import

nodes = [ ..., <name>_node_spec() ]                                  # in the node list
links.extend(<name>_topology_links())                               # in the links
...
from <name>_status import apply_<name>_graph
apply_<name>_graph(nodes, mode="real")                             # in the real-metrics path
```

### 5. `satellite_overlays.py` —— UNI 装饰

```python
from <name>_status import apply_<name>_graph
steps = ( ..., ("<name>", lambda: apply_<name>_graph(nodes, mode="universe")) )
```

### 6. `universe.py` —— UNI 种子（最常被遗漏的地方）

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

然后**在两个种子点都调用它**（`seed_entities()` 以及重新播种（reseed）路径 —— 搜索现有的
`self._seed_basanos_entity()`，并在每一处旁边加上你自己的），再把你的边加进
`get_topology_links()`：

```python
from <name>_layers import <name>_topology_links
links.extend(<name>_topology_links())
```

## 前端 —— 可选，用于自定义详情卡片

气泡会根据后端拓扑（位置、颜色、标签）自动渲染，点击它会显示一个**通用**详情卡片。自定义卡片属于
锦上添花，不是必需项。

- `frontend/src/components/cards/<Name>Card.tsx` —— 读取 `node.metrics` 以及你在
  `apply_*_to_nodes` 中设置的任何自定义字段（通过 `node as unknown as {...}` 声明它们）。
- `frontend/src/components/NodeDetail.tsx` —— 导入它并进行路由：
  `{node.id === '<name>' && <<Name>Card node={node} themeColor={themeColor} mobile={mobile} t={t} />}`
- `frontend/src/i18n/locales/{en,ru,es,fr,zh}.json` —— 添加一个 `<name>.*` 块（五种语言都要）。卡片中的
  `t('<name>.key', undefined, 'fallback')` 即使在这些键还不存在时，也会渲染那个 fallback。
- 3D 场景（`nodeScenes/`）完全是可选的；没有它时，节点会使用默认的球体。

## 测试 —— 照着 `test_<name>_node.py` 来做

复制 `alien-monitor/tests/test_basanos_node.py` 并替换其中的名字。它精确地锁定了"四个地方"这个
陷阱：出现在 `build_topology` 及其边中、在 universe 模式下被播种、能挺过 reseed 路径、并出现在
`get_topology_links()` 中 —— 此外还有分隔规则，以及你的节点所需的任何诚实性规则。

## 部署

monitor 是两个裸 `docker run` 容器（`alien-monitor-live` 对应 realm `real`，`alien-monitor` 对应
realm `universe`），net=host。重新构建镜像并重建它们：

```bash
# from the monorepo root, build with the base path the containers serve at ("/")
docker build -f alien-monitor/Dockerfile --build-arg VITE_BASE_PATH=/ -t alien-monitor:live-<tag> .
# recreate each container on the new image, preserving its env/mounts (see redeploy_monitor.sh)
```

> **Base-path 陷阱：** `VITE_BASE_PATH` 是在构建时被烘焙进去的。容器在 `/` 下提供服务，所以要用
> `--build-arg VITE_BASE_PATH=/` 来构建，否则每一个资源都会 404。

只涉及后端（不涉及前端）的改动，可以作为一个薄层发布，而不必完整重建：
`FROM alien-monitor:live-<prev>` + `COPY backend/<file> /app/backend/<file>`。

## 验证

```bash
curl -s https://monitor-uni.modelmarket.dev/api/topology \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('<name>' in {n['id'] for n in d['nodes']})"
```

**两个** realm 都要检查（`monitor.modelmarket.dev` 和 `monitor-uni.modelmarket.dev`）—— "四个地方"这个
陷阱正是在 UNI 那个上咬人的。用 `?node=<name>` 深链接到某个节点的卡片。

---

MIT · AIMarket 生态系统的一部分。与 [onboard-a-node.md](onboard-a-node.md)（联邦路径）和
[ecosystem-autodiscovery.md](ecosystem-autodiscovery.md) 配套。
