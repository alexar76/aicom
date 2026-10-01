"""DIKTYON — graph metrics.

Graphs arrive as an edge list, which is the only shape that survives JSON without argument.
Everything is computed exactly: Brandes for betweenness, Dijkstra for weighted paths, Kruskal
with union-find for the spanning tree. Sizes are bounded so an O(V*E) metric cannot be used
to bill the operator's CPU to a caller.
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict, deque
from typing import Any

from uni.capabilities import Capability, Catalogue, InvalidInput, choice, integer, number, rounded

OBJ = {"type": "object"}
MAX_NODES = 2000
MAX_EDGES = 20000

EDGES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["source", "target"],
        "properties": {
            "source": {"type": "string"},
            "target": {"type": "string"},
            "weight": {"type": "number", "exclusiveMinimum": 0},
        },
    },
}


class Graph:
    def __init__(self, nodes: list[str], adj: dict[str, dict[str, float]], directed: bool):
        self.nodes = nodes
        self.adj = adj
        self.directed = directed


def _graph(p: dict[str, Any], *, weighted: bool = False) -> Graph:
    raw = p.get("edges")
    if not isinstance(raw, list):
        raise InvalidInput("edges must be an array of {source, target} objects")
    if len(raw) > MAX_EDGES:
        raise InvalidInput(f"edges is limited to {MAX_EDGES} entries, got {len(raw)}")
    directed = bool(p.get("directed", False))
    adj: dict[str, dict[str, float]] = defaultdict(dict)
    nodes: dict[str, None] = {}
    for i, e in enumerate(raw):
        if not isinstance(e, dict):
            raise InvalidInput(f"edges[{i}] must be an object")
        src, dst = e.get("source"), e.get("target")
        if not isinstance(src, str) or not isinstance(dst, str) or not src or not dst:
            raise InvalidInput(f"edges[{i}] needs non-empty string source and target")
        if len(src) > 200 or len(dst) > 200:
            raise InvalidInput(f"edges[{i}] has a node id longer than 200 characters")
        w = e.get("weight", 1.0)
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            raise InvalidInput(f"edges[{i}].weight must be a number")
        w = float(w)
        if weighted and w <= 0:
            raise InvalidInput(f"edges[{i}].weight must be positive for a distance metric")
        nodes[src] = None
        nodes[dst] = None
        # A repeated edge keeps the SHORTEST weight rather than the last one seen: a
        # duplicate in an edge list is almost always two observations of one link.
        prev = adj[src].get(dst)
        adj[src][dst] = w if prev is None else min(prev, w)
        if not directed:
            prev = adj[dst].get(src)
            adj[dst][src] = w if prev is None else min(prev, w)
    extra = p.get("nodes")
    if isinstance(extra, list):
        for n in extra:
            if isinstance(n, str) and n:
                nodes.setdefault(n, None)
    if len(nodes) > MAX_NODES:
        raise InvalidInput(f"graph is limited to {MAX_NODES} nodes, got {len(nodes)}")
    if not nodes:
        raise InvalidInput("graph has no nodes")
    for n in nodes:
        adj.setdefault(n, {})
    return Graph(sorted(nodes), dict(adj), directed)


def _bfs_hops(g: Graph, start: str) -> dict[str, int]:
    seen = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in g.adj.get(cur, {}):
            if nxt not in seen:
                seen[nxt] = seen[cur] + 1
                q.append(nxt)
    return seen


def degree(p: dict[str, Any]) -> Any:
    g = _graph(p)
    out = {}
    for n in g.nodes:
        row: dict[str, Any] = {"out_degree": len(g.adj.get(n, {}))}
        if g.directed:
            row["in_degree"] = sum(1 for m in g.nodes if n in g.adj.get(m, {}))
            row["degree"] = row["in_degree"] + row["out_degree"]
        else:
            row["degree"] = row.pop("out_degree")
        out[n] = row
    key = "degree"
    ranked = sorted(g.nodes, key=lambda n: (-out[n][key], n))
    return {"nodes": len(g.nodes), "directed": g.directed, "degree": out,
            "most_connected": ranked[:10]}


def pagerank(p: dict[str, Any]) -> Any:
    g = _graph(p)
    damping = number(p, "damping", 0.85, minimum=0.0, maximum=0.999)
    iterations = integer(p, "iterations", 60, minimum=1, maximum=500)
    n = len(g.nodes)
    rank = {node: 1.0 / n for node in g.nodes}
    for _ in range(iterations):
        nxt = {node: (1 - damping) / n for node in g.nodes}
        dangling = 0.0
        for node in g.nodes:
            outs = g.adj.get(node, {})
            if not outs:
                dangling += rank[node]
                continue
            share = damping * rank[node] / len(outs)
            for target in outs:
                nxt[target] += share
        if dangling:
            # A sink must redistribute its mass or the vector leaks and the ranks stop
            # summing to one — the classic silent PageRank bug.
            spread = damping * dangling / n
            for node in nxt:
                nxt[node] += spread
        rank = nxt
    total = sum(rank.values()) or 1.0
    rank = {k: v / total for k, v in rank.items()}
    ranked = sorted(g.nodes, key=lambda x: (-rank[x], x))
    return {"pagerank": {k: rounded(v) for k, v in rank.items()},
            "ranked": ranked[:20], "iterations": iterations, "damping": damping}


def components(p: dict[str, Any]) -> Any:
    g = _graph(p)
    # Undirected reachability even on a directed graph: this reports WEAKLY connected
    # components, and says so, rather than quietly answering a different question.
    undirected: dict[str, set[str]] = {n: set() for n in g.nodes}
    for src, outs in g.adj.items():
        for dst in outs:
            undirected[src].add(dst)
            undirected[dst].add(src)
    seen: set[str] = set()
    groups = []
    for node in g.nodes:
        if node in seen:
            continue
        stack, group = [node], []
        seen.add(node)
        while stack:
            cur = stack.pop()
            group.append(cur)
            for nxt in undirected[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        groups.append(sorted(group))
    groups.sort(key=lambda gr: (-len(gr), gr[0]))
    return {"count": len(groups), "kind": "weakly connected" if g.directed else "connected",
            "largest_size": len(groups[0]), "components": groups[:50]}


def shortest_path(p: dict[str, Any]) -> Any:
    g = _graph(p, weighted=True)
    source = p.get("source")
    target = p.get("target")
    if not isinstance(source, str) or source not in g.adj:
        raise InvalidInput("source must be a node present in the edge list")
    if not isinstance(target, str) or target not in g.adj:
        raise InvalidInput("target must be a node present in the edge list")
    dist = {source: 0.0}
    prev: dict[str, str] = {}
    heap = [(0.0, source)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, math.inf):
            continue
        if node == target:
            break
        for nxt, w in g.adj.get(node, {}).items():
            nd = d + w
            if nd < dist.get(nxt, math.inf):
                dist[nxt] = nd
                prev[nxt] = node
                heapq.heappush(heap, (nd, nxt))
    if target not in dist:
        return {"reachable": False, "path": [], "distance": None}
    path, cur = [target], target
    while cur != source:
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return {"reachable": True, "path": path, "hops": len(path) - 1,
            "distance": rounded(dist[target])}


def betweenness(p: dict[str, Any]) -> Any:
    """Brandes' algorithm on the unweighted graph."""
    g = _graph(p)
    if len(g.nodes) > 500:
        raise InvalidInput("betweenness is limited to 500 nodes")
    score = {n: 0.0 for n in g.nodes}
    for s in g.nodes:
        stack: list[str] = []
        preds: dict[str, list[str]] = {n: [] for n in g.nodes}
        sigma = {n: 0.0 for n in g.nodes}
        dist = {n: -1 for n in g.nodes}
        sigma[s] = 1.0
        dist[s] = 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in g.adj.get(v, {}):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    preds[w].append(v)
        delta = {n: 0.0 for n in g.nodes}
        while stack:
            w = stack.pop()
            for v in preds[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w]) if sigma[w] else 0.0
            if w != s:
                score[w] += delta[w]
    if not g.directed:
        score = {k: v / 2 for k, v in score.items()}
    n = len(g.nodes)
    scale = ((n - 1) * (n - 2) / (1 if g.directed else 2)) if n > 2 else 0
    normalised = {k: (v / scale if scale else 0.0) for k, v in score.items()}
    ranked = sorted(g.nodes, key=lambda x: (-normalised[x], x))
    return {"betweenness": {k: rounded(v) for k, v in normalised.items()},
            "ranked": ranked[:20], "normalised": True}


def closeness(p: dict[str, Any]) -> Any:
    g = _graph(p)
    out = {}
    for node in g.nodes:
        hops = _bfs_hops(g, node)
        reachable = len(hops) - 1
        total = sum(hops.values())
        # Wasserman-Faust: scaled by the reachable fraction, so a node in a small component
        # does not outrank a well-connected node in a large one.
        out[node] = ((reachable / total) * (reachable / (len(g.nodes) - 1))
                     if total and len(g.nodes) > 1 else 0.0)
    ranked = sorted(g.nodes, key=lambda x: (-out[x], x))
    return {"closeness": {k: rounded(v) for k, v in out.items()}, "ranked": ranked[:20],
            "definition": "Wasserman-Faust, scaled for unreachable nodes"}


def mst(p: dict[str, Any]) -> Any:
    g = _graph(p, weighted=True)
    if g.directed:
        raise InvalidInput("a minimum spanning tree is defined on an undirected graph")
    edges = sorted(
        {(min(a, b), max(a, b), w) for a, outs in g.adj.items() for b, w in outs.items()},
        key=lambda e: (e[2], e[0], e[1]),
    )
    parent = {n: n for n in g.nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    chosen, total = [], 0.0
    for a, b, w in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            chosen.append({"source": a, "target": b, "weight": rounded(w)})
            total += w
    roots = {find(n) for n in g.nodes}
    return {"edges": chosen, "total_weight": rounded(total),
            "spans_whole_graph": len(roots) == 1,
            "forest_components": len(roots)}


def cycles(p: dict[str, Any]) -> Any:
    g = _graph(p)
    colour: dict[str, int] = {n: 0 for n in g.nodes}
    found: list[str] = []

    def walk(node: str, path: list[str]) -> bool:
        colour[node] = 1
        path.append(node)
        for nxt in sorted(g.adj.get(node, {})):
            if not g.directed and len(path) >= 2 and nxt == path[-2]:
                continue  # an undirected edge is not a cycle traversed back and forth
            if colour.get(nxt) == 1:
                found.extend(path[path.index(nxt):] + [nxt])
                return True
            if colour.get(nxt) == 0 and walk(nxt, path):
                return True
        path.pop()
        colour[node] = 2
        return False

    import sys as _sys
    limit = _sys.getrecursionlimit()
    _sys.setrecursionlimit(max(limit, MAX_NODES * 4))
    try:
        has = any(walk(n, []) for n in g.nodes if colour[n] == 0)
    finally:
        _sys.setrecursionlimit(limit)
    return {"has_cycle": has, "example_cycle": found, "directed": g.directed}


def topological_sort(p: dict[str, Any]) -> Any:
    g = _graph(p)
    if not g.directed:
        raise InvalidInput("a topological order is only defined on a directed graph")
    indeg = {n: 0 for n in g.nodes}
    for outs in g.adj.values():
        for dst in outs:
            indeg[dst] += 1
    ready = sorted(n for n, d in indeg.items() if d == 0)
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for nxt in sorted(g.adj.get(node, {})):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
        ready.sort()
    if len(order) != len(g.nodes):
        return {"ordered": False, "order": [], "reason": "graph contains a cycle",
                "unresolved": sorted(n for n in g.nodes if n not in set(order))}
    return {"ordered": True, "order": order, "levels": len(set(indeg.values()))}


def clustering(p: dict[str, Any]) -> Any:
    g = _graph(p)
    if g.directed:
        raise InvalidInput("the clustering coefficient here is defined on an undirected graph")
    local = {}
    for node in g.nodes:
        nbrs = sorted(g.adj.get(node, {}))
        k = len(nbrs)
        if k < 2:
            local[node] = 0.0
            continue
        links = sum(
            1 for i, a in enumerate(nbrs) for b in nbrs[i + 1:] if b in g.adj.get(a, {})
        )
        local[node] = 2 * links / (k * (k - 1))
    avg = sum(local.values()) / len(local) if local else 0.0
    return {"local": {k: rounded(v) for k, v in local.items()},
            "average": rounded(avg)}


def bipartite(p: dict[str, Any]) -> Any:
    g = _graph(p)
    colour: dict[str, int] = {}
    for start in g.nodes:
        if start in colour:
            continue
        colour[start] = 0
        q = deque([start])
        while q:
            node = q.popleft()
            for nxt in g.adj.get(node, {}):
                if nxt not in colour:
                    colour[nxt] = 1 - colour[node]
                    q.append(nxt)
                elif colour[nxt] == colour[node]:
                    return {"bipartite": False, "conflict_edge": [node, nxt]}
    return {"bipartite": True,
            "left": sorted(n for n, c in colour.items() if c == 0),
            "right": sorted(n for n, c in colour.items() if c == 1)}


def diameter(p: dict[str, Any]) -> Any:
    g = _graph(p)
    if len(g.nodes) > 800:
        raise InvalidInput("diameter is limited to 800 nodes")
    best, pair, total, counted = 0, [], 0, 0
    for node in g.nodes:
        hops = _bfs_hops(g, node)
        for other, d in hops.items():
            if other == node:
                continue
            total += d
            counted += 1
            if d > best:
                best, pair = d, [node, other]
    connected = counted == len(g.nodes) * (len(g.nodes) - 1) if len(g.nodes) > 1 else True
    return {"diameter": best if connected else None,
            "eccentric_pair": pair,
            "average_path_length": rounded(total / counted) if counted else None,
            "connected": connected,
            "note": None if connected else "graph is disconnected — diameter is infinite"}


CATALOGUE = Catalogue(
    product_id="diktyon",
    name="DIKTYON Graph Metrics",
    description="Centrality, connectivity, ordering and spanning structure over edge-list graphs",
    capabilities=[
        Capability("graph.degree@v1", "Degree, in-degree and out-degree per node with the most connected ranked",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA, "directed": {"type": "boolean"}}},
                   OBJ, 0.003, 40, degree, {"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]}),
        Capability("graph.pagerank@v1", "PageRank with damping and correct redistribution of dangling mass",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA, "directed": {"type": "boolean"}, "damping": {"type": "number"}, "iterations": {"type": "integer"}}},
                   OBJ, 0.015, 220, pagerank, {"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "c", "target": "a"}], "directed": True}),
        Capability("graph.components@v1", "Connected (or weakly connected) components, largest first",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA, "directed": {"type": "boolean"}}},
                   OBJ, 0.004, 50, components, {"edges": [{"source": "a", "target": "b"}, {"source": "c", "target": "d"}]}),
        Capability("graph.shortest-path@v1", "Dijkstra shortest path between two nodes with the route and total distance",
                   {"type": "object", "required": ["edges", "source", "target"], "properties": {"edges": EDGES_SCHEMA, "source": {"type": "string"}, "target": {"type": "string"}, "directed": {"type": "boolean"}}},
                   OBJ, 0.008, 90, shortest_path, {"edges": [{"source": "a", "target": "b", "weight": 2}, {"source": "b", "target": "c", "weight": 3}], "source": "a", "target": "c"}),
        Capability("graph.betweenness@v1", "Brandes betweenness centrality, normalised",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA, "directed": {"type": "boolean"}}},
                   OBJ, 0.020, 320, betweenness, {"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "c", "target": "d"}]}),
        Capability("graph.closeness@v1", "Closeness centrality, Wasserman-Faust scaled for unreachable nodes",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA, "directed": {"type": "boolean"}}},
                   OBJ, 0.012, 180, closeness, {"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]}),
        Capability("graph.minimum-spanning-tree@v1", "Kruskal minimum spanning tree or forest with total weight",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA}},
                   OBJ, 0.008, 100, mst, {"edges": [{"source": "a", "target": "b", "weight": 1}, {"source": "b", "target": "c", "weight": 5}, {"source": "a", "target": "c", "weight": 2}]}),
        Capability("graph.cycles@v1", "Cycle detection with one concrete example cycle when present",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA, "directed": {"type": "boolean"}}},
                   OBJ, 0.006, 80, cycles, {"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "c", "target": "a"}], "directed": True}),
        Capability("graph.topological-sort@v1", "Deterministic topological order, or the nodes a cycle leaves unresolved",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA, "directed": {"type": "boolean"}}},
                   OBJ, 0.005, 60, topological_sort, {"edges": [{"source": "build", "target": "test"}, {"source": "test", "target": "deploy"}], "directed": True}),
        Capability("graph.clustering-coefficient@v1", "Local and average clustering coefficient of an undirected graph",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA}},
                   OBJ, 0.008, 110, clustering, {"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "a", "target": "c"}]}),
        Capability("graph.bipartite@v1", "Two-colouring test with the two sides, or the edge that breaks it",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA}},
                   OBJ, 0.004, 50, bipartite, {"edges": [{"source": "a", "target": "x"}, {"source": "b", "target": "x"}]}),
        Capability("graph.diameter@v1", "Diameter, the eccentric pair and average path length, honest about disconnection",
                   {"type": "object", "required": ["edges"], "properties": {"edges": EDGES_SCHEMA, "directed": {"type": "boolean"}}},
                   OBJ, 0.015, 240, diameter, {"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "c", "target": "d"}]}),
    ],
)
