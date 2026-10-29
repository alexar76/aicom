from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from skopos.charts import PALETTE, _apply, chart_layout, prevent_label_overlap, short_path_label

SEVERITY_COLORS = {
    "critical": "#EA4335",
    "high": "#FF6D00",
    "medium": "#FBBC04",
    "low": "#4285F4",
    "info": "#34A853",
}

# Visual grammar — shape + palette token per object type (SKOPOS GA style).
THREAT_GLYPHS: dict[str, dict] = {
    "server": {
        "symbol": "circle",
        "size": 22,
        "color": PALETTE[0],
        "legend": "Server",
        "edge": PALETTE[0],
    },
    "internet": {
        "symbol": "diamond",
        "size": 15,
        "color": PALETTE[4],
        "legend": "Internet",
        "edge": PALETTE[4],
    },
    "public": {
        "symbol": "square",
        "size": 10,
        "color": PALETTE[3],
        "legend": "Public port",
        "edge": "rgba(234,67,53,0.55)",
    },
    "local": {
        "symbol": "circle-open",
        "size": 8,
        "color": PALETTE[1],
        "legend": "Localhost port",
        "edge": "rgba(52,168,83,0.55)",
    },
    "other": {
        "symbol": "cross",
        "size": 8,
        "color": PALETTE[2],
        "legend": "Other bind",
        "edge": "rgba(251,188,4,0.55)",
    },
    "critical": {
        "symbol": "diamond",
        "size": 14,
        "color": SEVERITY_COLORS["critical"],
        "legend": "Critical finding",
        "edge": SEVERITY_COLORS["critical"],
    },
    "high": {
        "symbol": "square",
        "size": 12,
        "color": SEVERITY_COLORS["high"],
        "legend": "High finding",
        "edge": SEVERITY_COLORS["high"],
    },
    "medium": {
        "symbol": "x",
        "size": 11,
        "color": SEVERITY_COLORS["medium"],
        "legend": "Medium finding",
        "edge": SEVERITY_COLORS["medium"],
    },
    "low": {
        "symbol": "circle",
        "size": 9,
        "color": SEVERITY_COLORS["low"],
        "legend": "Low finding",
        "edge": SEVERITY_COLORS["low"],
    },
    "info": {
        "symbol": "circle-open",
        "size": 8,
        "color": SEVERITY_COLORS["info"],
        "legend": "Info finding",
        "edge": SEVERITY_COLORS["info"],
    },
}


def _threat_scene_palette() -> dict:
    """Dark starfield scene — readable GA glyphs on space background."""
    return {
        "template": "plotly_dark",
        "scene_bg": "rgb(6,8,24)",
        "paper_bg": "rgb(4,6,18)",
        "font": "#c5d4e8",
        "title": "#e8eaed",
        "hover_bg": "rgba(8,14,32,0.96)",
        "orbit_inner": "rgba(66,133,244,0.18)",
        "orbit_outer": "rgba(147,52,230,0.16)",
        "edge_core": "rgba(66,133,244,0.45)",
        "edge_wan": "rgba(147,52,230,0.5)",
        "edge_threat": "rgba(255,109,0,0.42)",
        "halo": "rgba(66,133,244,0.15)",
        "marker_line": "rgba(255,255,255,0.55)",
        "legend_bg": "rgba(6,10,26,0.92)",
        "star": "rgba(210,225,255,0.55)",
    }


def _glyph(kind: str) -> dict:
    return THREAT_GLYPHS.get(kind, THREAT_GLYPHS["info"])



def _finding_group_key(f: dict) -> str:
    category = f.get("category") or "general"
    sev = f.get("severity", "info")
    title = (f.get("title") or "").lower()
    if category == "resources" and "disk" in title:
        return f"resources:disk:{sev}"
    if category == "resources" and "memory" in title:
        return f"resources:memory:{sev}"
    if category == "resources" and "load" in title or "cpu" in title:
        return f"resources:cpu:{sev}"
    return f"{sev}:{category}:{f.get('title', '')[:72]}"


def _aggregate_findings_for_map(findings: list[dict]) -> list[dict]:
    """One visual node per issue class — collapse many docker disk mounts into one."""
    buckets: dict[str, dict] = {}
    for f in findings:
        key = _finding_group_key(f)
        title = f.get("title") or "Finding"
        detail = f.get("detail") or ""
        mount = ""
        if "(" in title and title.endswith(")"):
            mount = title[title.rfind("(") + 1 : -1]

        if key not in buckets:
            label = title
            if key.startswith("resources:disk:"):
                label = "Storage pressure"
            elif key.startswith("resources:memory:"):
                label = "Memory pressure"
            elif key.startswith("resources:cpu:"):
                label = "CPU load"
            buckets[key] = {
                "severity": f.get("severity", "info"),
                "category": f.get("category", "general"),
                "title": label,
                "detail_lines": [],
                "count": 0,
            }
        bucket = buckets[key]
        bucket["count"] += 1
        if mount:
            bucket["detail_lines"].append(f"• {short_path_label(mount)} — {detail}")
        else:
            bucket["detail_lines"].append(f"• {title}: {detail}")

    out: list[dict] = []
    for bucket in buckets.values():
        cnt = bucket["count"]
        lines = bucket["detail_lines"]
        shown = lines[:6]
        detail = "<br>".join(shown)
        if len(lines) > 6:
            detail += f"<br>… +{len(lines) - 6} more"
        title = bucket["title"]
        if cnt > 1:
            title = f"{title} ({cnt})"
        out.append(
            {
                "severity": bucket["severity"],
                "category": bucket["category"],
                "title": title,
                "detail": detail,
            }
        )

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    out.sort(key=lambda x: order.get(x.get("severity", "info"), 9))
    return out[:8]


def _add_starfield(fig: go.Figure, palette: dict, *, seed: int = 42) -> None:
    import random

    rng = random.Random(seed)
    n = 220
    xs = [rng.uniform(-8, 8) for _ in range(n)]
    ys = [rng.uniform(-8, 8) for _ in range(n)]
    zs = [rng.uniform(-3, 10) for _ in range(n)]
    sizes = [rng.choice([1.2, 1.6, 2.0, 2.4]) for _ in range(n)]
    fig.add_trace(
        go.Scatter3d(
            x=xs,
            y=ys,
            z=zs,
            mode="markers",
            marker=dict(size=sizes, color=palette["star"], opacity=0.7),
            hoverinfo="skip",
            showlegend=False,
        )
    )


def _ring_positions(count: int, radius: float, *, z: float = 0.0) -> list[tuple[float, float, float]]:
    if count <= 0:
        return []
    out: list[tuple[float, float, float]] = []
    for i in range(count):
        angle = (2 * math.pi * i) / count
        out.append((round(radius * math.cos(angle), 3), round(radius * math.sin(angle), 3), z))
    return out


def _orbit_ring_trace(radius: float, z: float, *, color: str, n: int = 48) -> go.Scatter3d:
    xs, ys, zs = [], [], []
    for i in range(n + 1):
        ang = (2 * math.pi * i) / n
        xs.append(radius * math.cos(ang))
        ys.append(radius * 0.35 * math.sin(ang))
        zs.append(z + 0.15 * math.sin(ang * 3))
    return go.Scatter3d(
        x=xs,
        y=ys,
        z=zs,
        mode="lines",
        line=dict(color=color, width=1),
        hoverinfo="skip",
        showlegend=False,
    )


def _batched_edges(
    nodes: dict[str, dict],
    edges: list[tuple[str, str]],
    *,
    color: str,
    width: int = 2,
) -> go.Scatter3d | None:
    xs: list[float | None] = []
    ys: list[float | None] = []
    zs: list[float | None] = []
    for a, b in edges:
        if a not in nodes or b not in nodes:
            continue
        na, nb = nodes[a], nodes[b]
        xs.extend([na["x"], nb["x"], None])
        ys.extend([na["y"], nb["y"], None])
        zs.extend([na["z"], nb["z"], None])
    if not xs:
        return None
    return go.Scatter3d(
        x=xs,
        y=ys,
        z=zs,
        mode="lines",
        line=dict(color=color, width=width),
        hoverinfo="skip",
        showlegend=False,
    )


def _node_scatter(items: list[dict], *, kind: str, palette: dict) -> go.Scatter3d:
    g = _glyph(kind)
    hover = [
        f"<b>{it['label']}</b>"
        + (f"<br>{it['detail']}" if it.get("detail") else "")
        + "<extra></extra>"
        for it in items
    ]
    return go.Scatter3d(
        x=[it["x"] for it in items],
        y=[it["y"] for it in items],
        z=[it["z"] for it in items],
        mode="markers",
        name=g["legend"],
        marker=dict(
            symbol=g["symbol"],
            size=[it.get("size", g["size"]) for it in items],
            color=[it.get("color", g["color"]) for it in items],
            opacity=0.96,
            line=dict(width=1.5, color=palette["marker_line"]),
        ),
        hovertemplate=hover,
        showlegend=True,
    )


def resource_gauge_metrics(snap: dict, *, locale: str = "en") -> list[tuple[float, str, str]]:
    from skopos.i18n import t

    mem_pct = snap.get("mem_used_pct") or 0
    cpu_idle = snap.get("cpu_idle_pct") or 50
    cpu_used = max(0, min(100, 100 - cpu_idle))
    load = snap.get("load_1") or 0
    cores = max(snap.get("cpu_cores") or 1, 1)
    load_pct = min(100, load / cores * 100)
    return [
        (round(cpu_used, 1), t("security.gauge_cpu", locale), PALETTE[0]),
        (round(mem_pct, 1), t("security.gauge_memory", locale), PALETTE[1]),
        (round(load_pct, 1), t("security.gauge_load", locale), PALETTE[2]),
    ]


def _gauge_steps() -> list[dict]:
    return [
        {"range": [0, 60], "color": "#e8f0fe"},
        {"range": [60, 85], "color": "#fef7e0"},
        {"range": [85, 100], "color": "#fce8e6"},
    ]


def chart_resource_gauge(value: float, title: str, color: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": title, "font": {"size": 14}},
            domain={"x": [0, 1], "y": [0, 1]},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": color},
                "steps": _gauge_steps(),
            },
        )
    )
    base = {k: v for k, v in chart_layout().items() if k != "margin"}
    fig.update_layout(
        **base,
        height=240,
        margin=dict(l=24, r=24, t=48, b=16),
    )
    return fig


def chart_resource_gauges(snap: dict) -> go.Figure:
    """Legacy combined figure — prefer chart_resource_gauge() in separate columns."""
    metrics = resource_gauge_metrics(snap)
    fig = make_subplots(
        rows=1,
        cols=3,
        specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]],
        horizontal_spacing=0.08,
    )
    for col, (val, title, color) in enumerate(metrics, start=1):
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=val,
                title={"text": title, "font": {"size": 14}},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": color},
                    "steps": _gauge_steps(),
                },
            ),
            row=1,
            col=col,
        )
    fig.update_layout(
        **chart_layout(),
        height=280,
        title="Resource utilization",
    )
    return fig


def chart_disk_usage(disks: list[dict], *, top_n: int = 12) -> go.Figure:
    rows = [d for d in disks if d.get("use_pct") is not None and d.get("mount") != ""]
    if not rows:
        return _apply(go.Figure(), 300)

    df = pd.DataFrame(rows)
    docker_markers = ("/overlay2/", "/overlayfs/", "/rootfs/overlay", "/docker/")
    df["is_docker"] = df["mount"].astype(str).map(lambda m: any(x in m for x in docker_markers))
    system = df[~df["is_docker"]].sort_values("use_pct", ascending=False)
    docker = df[df["is_docker"]].sort_values("use_pct", ascending=False).head(8)
    df = pd.concat([system, docker], ignore_index=True).drop_duplicates(subset=["mount"])
    df = df.sort_values("use_pct", ascending=False).head(top_n).copy()
    df["mount_label"] = df["mount"].map(short_path_label)

    seen: dict[str, int] = {}
    unique_labels: list[str] = []
    for mount, label in zip(df["mount"], df["mount_label"]):
        count = seen.get(label, 0)
        if count:
            suffix = mount.rstrip("/").split("/")[-1][:8]
            unique_labels.append(f"{label} ({suffix})")
        else:
            unique_labels.append(label)
        seen[label] = count + 1
    df["mount_label"] = unique_labels
    df = df.sort_values("use_pct", ascending=True)

    fig = px.bar(
        df,
        y="mount_label",
        x="use_pct",
        orientation="h",
        color="use_pct",
        color_continuous_scale=["#34A853", "#FBBC04", "#EA4335"],
        range_color=[0, 100],
        title="Disk usage by mount",
        labels={"mount_label": "Mount", "use_pct": "Used %"},
        custom_data=["mount"],
    )
    fig.update_traces(
        hovertemplate="Mount: %{customdata[0]}<br>Used: %{x:.1f}%<extra></extra>",
        texttemplate="%{x:.0f}%",
        textposition="outside",
        cliponaxis=False,
    )
    base = {k: v for k, v in chart_layout().items() if k != "margin"}
    fig.update_layout(
        **base,
        showlegend=False,
        height=max(300, 38 * len(df) + 96),
        yaxis_title="",
        xaxis_title="Used %",
        xaxis=dict(range=[0, 100]),
        margin=dict(l=24, r=48, t=64, b=40),
    )
    prevent_label_overlap(fig)
    return fig


def chart_port_matrix(ports: list[dict]) -> go.Figure:
    if not ports:
        fig = go.Figure()
        fig.add_annotation(text="No listening ports detected", showarrow=False)
        return _apply(fig, 320)
    df = pd.DataFrame(ports)
    df["status"] = df["bind_scope"].map(
        {"public": "Open (public)", "localhost": "Closed (localhost)", "other": "Other bind"}
    )
    df["label"] = df.apply(lambda r: f"{r['proto']}/{r['port']}", axis=1)
    fig = px.scatter(
        df,
        x="port",
        y="status",
        color="status",
        size=[12] * len(df),
        hover_name="label",
        hover_data=["address", "process"],
        color_discrete_map={
            "Open (public)": "#EA4335",
            "Closed (localhost)": "#34A853",
            "Other bind": "#FBBC04",
        },
        title="Port exposure map",
    )
    fig.update_layout(**chart_layout(), height=380)
    return fig


def chart_findings_bar(findings: list[dict]) -> go.Figure:
    if not findings:
        fig = go.Figure()
        fig.add_annotation(text="No findings — looking good", showarrow=False, font=dict(size=16))
        return _apply(fig, 320)
    df = pd.DataFrame(findings)
    g = df.groupby("severity").size().reset_index(name="count")
    order = ["critical", "high", "medium", "low", "info"]
    g["severity"] = pd.Categorical(g["severity"], categories=order, ordered=True)
    g = g.sort_values("severity")
    fig = px.bar(
        g,
        x="severity",
        y="count",
        color="severity",
        color_discrete_map=SEVERITY_COLORS,
        title="Security findings by severity",
    )
    fig.update_layout(**chart_layout(), showlegend=False, height=360)
    return fig


def chart_findings_timeline(all_findings: list[dict]) -> go.Figure:
    if not all_findings:
        return _apply(go.Figure(), 300)
    df = pd.DataFrame(all_findings)
    g = df.groupby(["severity"]).size().reset_index(name="count")
    fig = px.pie(g, names="severity", values="count", color="severity", color_discrete_map=SEVERITY_COLORS)
    fig.update_layout(**chart_layout(), title="Finding distribution", height=360)
    return fig


def chart_network_io(snap: dict) -> go.Figure:
    rx = snap.get("net_rx_bytes") or 0
    tx = snap.get("net_tx_bytes") or 0
    fig = go.Figure(
        data=[
            go.Bar(
                x=["RX bytes", "TX bytes"],
                y=[rx, tx],
                marker_color=[PALETTE[0], PALETTE[1]],
            )
        ]
    )
    fig.update_layout(**chart_layout(), title="Network I/O (cumulative counters)", height=320)
    return fig


def chart_threat_3d(
    snap: dict,
    findings: list[dict],
    *,
    title: str = "3D threat topology",
) -> go.Figure:
    """Classic threat topology on a starfield: server core, port ring, findings, WAN."""
    palette = _threat_scene_palette()
    server = snap.get("server_name") or "server"
    host = snap.get("host") or ""

    nodes: dict[str, dict] = {}
    core_port_edges: list[tuple[str, str]] = []
    threat_edges: list[tuple[str, str]] = []

    ports = snap.get("ports") or []
    public = [p for p in ports if p.get("bind_scope") == "public"][:10]
    local = [p for p in ports if p.get("bind_scope") == "localhost"][:6]
    other = [p for p in ports if p.get("bind_scope") not in ("public", "localhost")][:4]

    for i, (p, pos) in enumerate(zip(public, _ring_positions(len(public), 3.0, z=1.0))):
        g = _glyph("public")
        x, y, z = pos
        nid = f"port_{p.get('port')}"
        nodes[nid] = {
            "id": nid,
            "label": f"Public {p.get('proto', 'tcp')}/{p.get('port')}",
            "x": x,
            "y": y,
            "z": z,
            "kind": "public",
            "size": g["size"],
            "color": g["color"],
            "detail": p.get("process") or p.get("address") or "",
        }
        core_port_edges.append(("core", nid))

    for i, (p, pos) in enumerate(zip(local, _ring_positions(len(local), 1.9, z=-0.4))):
        g = _glyph("local")
        x, y, z = pos
        nid = f"local_{p.get('port')}"
        nodes[nid] = {
            "id": nid,
            "label": f"Local {p.get('proto', 'tcp')}/{p.get('port')}",
            "x": x,
            "y": y,
            "z": z,
            "kind": "local",
            "size": g["size"],
            "color": g["color"],
        }
        core_port_edges.append(("core", nid))

    for i, (p, pos) in enumerate(zip(other, _ring_positions(len(other), 2.6, z=0.3))):
        g = _glyph("other")
        x, y, z = pos
        nid = f"other_{p.get('port')}"
        nodes[nid] = {
            "id": nid,
            "label": f"{p.get('proto', 'tcp')}/{p.get('port')}",
            "x": x,
            "y": y,
            "z": z,
            "kind": "other",
            "size": g["size"],
            "color": g["color"],
        }
        core_port_edges.append(("core", nid))

    aggregated = _aggregate_findings_for_map(findings)
    sev_z = {"critical": 4.2, "high": 3.6, "medium": 3.0, "low": 2.4, "info": 1.8}
    sev_r = {"critical": 5.2, "high": 4.8, "medium": 4.4, "low": 4.0, "info": 3.6}
    for i, f in enumerate(aggregated):
        sev = f.get("severity", "info")
        g = _glyph(sev)
        angle = (2 * math.pi * i) / max(len(aggregated), 1)
        radius = sev_r.get(sev, 4.2)
        x = round(radius * math.cos(angle), 3)
        y = round(radius * math.sin(angle), 3)
        z = sev_z.get(sev, 3.0)
        fid = f"finding_{i}"
        nodes[fid] = {
            "id": fid,
            "label": f.get("title") or "Alert",
            "x": x,
            "y": y,
            "z": z,
            "kind": sev,
            "size": g["size"],
            "color": g["color"],
            "detail": f.get("detail") or "",
        }
        threat_edges.append(("core", fid))

    g_core = _glyph("server")
    g_inet = _glyph("internet")
    nodes["core"] = {
        "id": "core",
        "label": server,
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "kind": "server",
        "size": g_core["size"] + 4,
        "color": g_core["color"],
        "detail": host,
    }
    nodes["internet"] = {
        "id": "internet",
        "label": "Internet",
        "x": 0.0,
        "y": 0.0,
        "z": 7.0,
        "kind": "internet",
        "size": g_inet["size"] + 2,
        "color": g_inet["color"],
    }

    fig = go.Figure()
    _add_starfield(fig, palette)
    fig.add_trace(_orbit_ring_trace(1.9, -0.4, color=palette["orbit_inner"]))
    fig.add_trace(_orbit_ring_trace(3.0, 1.0, color=palette["orbit_inner"]))
    fig.add_trace(_orbit_ring_trace(4.5, 3.0, color=palette["orbit_outer"]))
    fig.add_trace(_orbit_ring_trace(2.2, 7.0, color=palette["orbit_outer"]))

    for edge_fn, edges, color, width in (
        (_batched_edges, core_port_edges, palette["edge_core"], 2),
        (_batched_edges, [("core", "internet")], palette["edge_wan"], 3),
        (_batched_edges, threat_edges, palette["edge_threat"], 2),
    ):
        trace = edge_fn(nodes, edges, color=color, width=width)
        if trace:
            fig.add_trace(trace)

    # Soft halo around server core
    fig.add_trace(
        go.Scatter3d(
            x=[0],
            y=[0],
            z=[0],
            mode="markers",
            marker=dict(size=34, color=palette["halo"], symbol="circle"),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    grouped: dict[str, list[dict]] = {}
    for n in nodes.values():
        grouped.setdefault(n["kind"], []).append(n)

    for kind, items in grouped.items():
        fig.add_trace(_node_scatter(items, kind=kind, palette=palette))

    fig.update_layout(
        template=palette["template"],
        paper_bgcolor=palette["paper_bg"],
        plot_bgcolor=palette["paper_bg"],
        font=dict(family="Inter, system-ui, sans-serif", size=13, color=palette["font"]),
        title=dict(
            text=f"{title} — {server}",
            x=0.02,
            font=dict(size=16, color=palette["title"]),
        ),
        height=620,
        margin=dict(l=0, r=0, t=64, b=0),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            bgcolor=palette["legend_bg"],
            font=dict(size=11, color=palette["font"]),
        ),
        scene=dict(
            bgcolor=palette["scene_bg"],
            xaxis=dict(visible=False, showbackground=False),
            yaxis=dict(visible=False, showbackground=False),
            zaxis=dict(visible=False, showbackground=False),
            aspectmode="cube",
            dragmode="orbit",
            camera=dict(eye=dict(x=1.5, y=1.45, z=1.05)),
        ),
        hoverlabel=dict(bgcolor=palette["hover_bg"], font_size=13, font_color="#e8f4ff"),
        meta=dict(stats_chart="threat_universe"),
    )
    return fig


def chart_multi_server_overview(snapshots: list[dict], findings_map: dict[str, list[dict]]) -> go.Figure:
    if not snapshots:
        fig = go.Figure()
        fig.add_annotation(text="Run a security scan first", showarrow=False)
        return _apply(fig, 360)
    rows = []
    for s in snapshots:
        name = s.get("server_name")
        payload = s.get("payload") or {}
        crit = sum(1 for f in findings_map.get(name, []) if f.get("severity") == "critical")
        high = sum(1 for f in findings_map.get(name, []) if f.get("severity") == "high")
        rows.append(
            {
                "server": name,
                "memory_pct": payload.get("mem_used_pct") or 0,
                "cpu_used": max(0, 100 - (payload.get("cpu_idle_pct") or 50)),
                "critical": crit,
                "high": high,
                "public_ports": len([p for p in (payload.get("ports") or []) if p.get("bind_scope") == "public"]),
            }
        )
    df = pd.DataFrame(rows)
    fig = px.scatter(
        df,
        x="memory_pct",
        y="cpu_used",
        size="public_ports",
        color="critical",
        hover_name="server",
        size_max=40,
        color_continuous_scale=["#34A853", "#EA4335"],
        title="Fleet overview — resources vs exposure",
        labels={"memory_pct": "Memory %", "cpu_used": "CPU used %", "critical": "Critical findings"},
    )
    fig.update_layout(**chart_layout(), height=420)
    return fig
