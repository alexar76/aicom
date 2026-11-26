"""Figures for the MCP 2026-07-28 adoption article (2026-11-26).

    python3 make_figures.py results.json data/dependency_sample.json OUTDIR
Outputs: cover.png (1600x672), probe.{png,svg}, adoption.{png,svg}, dependency.{png,svg}.
Numbers come only from results.json (count_protocols.py) and dependency_sample.json (sample_dependencies.py).
Colours: slot 1 of the validated categorical palette (blue #2a78d6) for "answers 2026-07-28", a neutral grey for
"answers an initialize-era revision"; every mark also carries a text label, and the article repeats the figures in tables.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

R = json.loads(Path(sys.argv[1]).read_text())
D = json.loads(Path(sys.argv[2]).read_text())
A = Path(sys.argv[3]); A.mkdir(parents=True, exist_ok=True)
BLUE, GREY, GREY2 = "#2a78d6", "#c9c7c0", "#e6e4de"
SURF, INK, INK2, RULE = "#fcfcfb", "#0b0b0b", "#52514e", "#dedcd5"
MONO = ["Menlo", "DejaVu Sans Mono"]
MODERN = R["modern"]
plt.rcParams.update({"font.family": ["Helvetica", "Arial Unicode MS", "DejaVu Sans"], "svg.fonttype": "none",
                     "text.color": INK, "figure.facecolor": SURF, "axes.facecolor": SURF})


def n(x):
    return f"{x:,}"


def save(fig, name, svg=True, dpi=200):
    fig.savefig(A / f"{name}.png", dpi=dpi, facecolor=fig.get_facecolor())
    if svg:
        fig.savefig(A / f"{name}.svg", facecolor=fig.get_facecolor())
    plt.close(fig)


def box(ax, x, y, w, h, title, body, ec=RULE, fc="#ffffff", lw=1.2, ls="-", mono_title=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.012", fc=fc, ec=ec, lw=lw, ls=ls))
    ax.text(x + 0.022, y + h - 0.026, title, fontsize=10, weight="bold", va="top",
            family=MONO if mono_title else None)
    ax.text(x + 0.022, y + h - 0.066, body, fontsize=8.6, color=INK2, va="top", linespacing=1.4)


def arrow(ax, a, b):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=13, color=INK2, lw=1.2))


def legend(fig, x, y):
    for i, (colour, label) in enumerate(((BLUE, f"answered in {MODERN}"), (GREY, "answered in an initialize-era revision"))):
        fig.patches.append(Rectangle((x + i * 0.31, y - 0.008), 0.022, 0.016, transform=fig.transFigure, fc=colour, ec="none"))
        fig.text(x + 0.03 + i * 0.31, y, label, fontsize=8.8, color=INK2, va="center")


# ---- 1. How one read decides the era (portrait, phone-friendly) ---------------------------------------------------
fig = plt.figure(figsize=(7.2, 8.6))
ax = fig.add_axes((0, 0, 1, 1)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
ax.text(0.04, 0.972, "How one read decides which revision a server speaks", fontsize=13.2, weight="bold", va="center")
box(ax, 0.04, 0.835, 0.92, 0.105, "1. POST server/discover",
    "no handshake first; the request itself says 2026-07-28 (in _meta and in the\n"
    "MCP-Protocol-Version header). Over stdio the same message goes to the process.", ec=BLUE, lw=1.6)
ax.text(0.04, 0.795, "What comes back", fontsize=9.2, color=INK2, va="center")
rows = [
    ("A result with supportedVersions that\nlists 2026-07-28",
     "Recorded as 2026-07-28. tools/list follows\nwith no session and no initialize.", BLUE, "-"),
    ("The modern error -32022 with a\nlist of versions the server supports",
     "A modern server. One retry with a listed\nversion; if it lists only older revisions,\ncontinue as below.", BLUE, "-"),
    ("HTTP 400/401/403/404/405 with no\nmodern error, a JSON-RPC error such\nas -32601, or a result that is no\nDiscoverResult",
     "An initialize-era server (the specification's\nbackward-compatibility rule). HISTOR sends\ninitialize offering 2025-06-18 and records\nthe version the server answers with.", GREY, "-"),
    ("Timeout, rate limit, 5xx, redirect, or a\nmalformed reply that looks modern",
     "The read fails. No revision is recorded and\nthe server is not counted in this article.", GREY, (0, (3, 2))),
]
y = 0.775
for left, right, colour, ls in rows:
    h = 0.142 if left.count("\n") < 3 else 0.156
    y -= h + 0.016
    ax.add_patch(FancyBboxPatch((0.04, y), 0.42, h, boxstyle="round,pad=0,rounding_size=0.012", fc="#ffffff", ec=RULE, lw=1.2))
    ax.text(0.062, y + h / 2, left, fontsize=8.8, va="center", linespacing=1.4)
    ax.add_patch(FancyBboxPatch((0.54, y), 0.42, h, boxstyle="round,pad=0,rounding_size=0.012", fc="#ffffff", ec=colour,
                                lw=1.6 if colour == BLUE else 1.2, ls=ls))
    ax.text(0.562, y + h / 2, right, fontsize=8.8, color=INK2, va="center", linespacing=1.4)
    arrow(ax, (0.465, y + h / 2), (0.535, y + h / 2))
ax.text(0.04, 0.062, "A server that answers both ways is recorded as 2026-07-28, because the modern request goes first.\n"
        "Offering 2025-06-18 in initialize means a server that also speaks 2025-11-25 shows up as 2025-06-18.\n"
        "Source: histor/mcpclient.py and sandbox/histor_observe.py in github.com/alexar76/histor.",
        fontsize=8.2, color=INK2, va="center", linespacing=1.5)
save(fig, "probe")

# ---- 2. Share answering 2026-07-28, four populations --------------------------------------------------------------
rem, pk = R["remote"], R["packages"]
dom = rem["registrableDomains"]
bars = [
    ("PyPI packages", pk["byRegistryType"]["pypi"][MODERN]["n"], pk["byRegistryType"]["pypi"]["_total"]),
    ("Remote servers,\nper registry entry", rem["byVersion"][MODERN]["n"], rem["serversReadOkInWindow"]),
    ("Remote servers,\nper registrable domain", dom["modern"]["n"], dom["total"]),
    ("npm packages", pk["byRegistryType"]["npm"][MODERN]["n"], pk["byRegistryType"]["npm"]["_total"]),
]
fig = plt.figure(figsize=(7.2, 6.3))
fig.text(0.05, 0.95, f"Who answers MCP {MODERN}, four months after it shipped", fontsize=13.2, weight="bold", va="center")
fig.text(0.05, 0.905, "Servers of the official MCP registry that HISTOR read without credentials; latest successful read of each",
         fontsize=8.8, color=INK2, va="center")
legend(fig, 0.05, 0.855)
ax = fig.add_axes((0.31, 0.33, 0.50, 0.47))
for i, (label, k, total) in enumerate(bars):
    yy = len(bars) - 1 - i
    share = 100 * k / total
    ax.barh(yy, share, height=0.5, color=BLUE, edgecolor="none")
    ax.barh(yy, 100 - share - 0.6, left=share + 0.6, height=0.5, color=GREY, edgecolor="none")   # 2px-style surface gap
    ax.text(102, yy + 0.07, f"{share:.1f} %", va="center", fontsize=11, weight="bold")
    ax.text(102, yy - 0.2, f"{n(k)} of {n(total)}", va="center", fontsize=8.4, color=INK2)
    ax.text(-3, yy, label, ha="right", va="center", fontsize=9.2, linespacing=1.3)
ax.set_xlim(0, 100); ax.set_ylim(-0.55, len(bars) - 0.45); ax.set_yticks([])
ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xticklabels(["0", "25", "50", "75", "100 %"])
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(RULE); ax.tick_params(axis="x", colors=INK2, labelsize=8.4, length=0)
ax.xaxis.grid(True, color=RULE, lw=0.8); ax.set_axisbelow(True)
top = rem["largestModernPublisher"]
fig.text(0.05, 0.205, f"One publisher ({top['domain']}) holds {n(top['modernEntries'])} of the {n(rem['byVersion'][MODERN]['n'])} remote entries that answer "
         f"{MODERN}; that is why the\nremote figure is also given per registrable domain ({n(dom['mixed']['n'])} more domains are mixed and counted "
         "as not moved).", fontsize=8.8, va="center", linespacing=1.45)
fig.text(0.05, 0.085, f"Sources: remote servers, HISTOR's log, latest ok read between {R['remoteWindow'][0][:10]} and {R['remoteWindow'][1][:10]} 16:00 UTC "
         f"(remote_protocols.csv).\nPackages: sandbox runs {pk['window'][0][:10]} to {pk['window'][1][:10]} in the public snapshot of 2026-11-23 "
         "(package_observations.jsonl.gz).\nNot counted: servers that asked for credentials, disallowed the crawler or failed to answer.",
         fontsize=8.0, color=INK2, va="center", linespacing=1.5)
save(fig, "adoption")

# ---- 3. The dependency line and what the server answered ----------------------------------------------------------
panels = [
    ("PyPI: 300 packages drawn at random", D["pypi"]["table"],
     [("mcp, 2.x allowed", "depends on mcp,\n2.x allowed"), ("fastmcp, 4.x allowed", "depends on fastmcp,\n4.x allowed"),
      ("mcp, capped below 2", "depends on mcp,\ncapped below 2"), ("fastmcp, capped below 4", "depends on fastmcp,\ncapped below 4"),
      ("no direct mcp or fastmcp dependency", "neither named\ndirectly")]),
    ("npm: 300 packages drawn at random", D["npm"]["table"],
     [("@modelcontextprotocol/server or core (2.x)", "@modelcontextprotocol/\nserver or core (2.x)"),
      ("@modelcontextprotocol/sdk (1.x line)", "@modelcontextprotocol/\nsdk (1.x line)"),
      ("no direct dependency on the official SDK", "official SDK not\nnamed directly")]),
]
fig = plt.figure(figsize=(7.2, 7.2))
fig.text(0.05, 0.957, "The dependency line decides", fontsize=13.2, weight="bold", va="center")
fig.text(0.05, 0.92, "What each sampled package declares for its MCP SDK, and the revision it answered in the sandbox",
         fontsize=8.8, color=INK2, va="center")
legend(fig, 0.05, 0.878)
geom = [(0.33, 0.515, 0.46, 0.30), (0.33, 0.215, 0.46, 0.185)]
for (title, table, order), g in zip(panels, geom):
    ax = fig.add_axes(g)
    fig.text(0.05, g[1] + g[3] + 0.027, title, fontsize=9.8, weight="bold", va="center")
    for i, (key, label) in enumerate(order):
        yy = len(order) - 1 - i
        m, l = table.get(key, {}).get("modern", 0), table.get(key, {}).get("legacy", 0)
        ax.barh(yy, m, height=0.5, color=BLUE, edgecolor="none")
        ax.barh(yy, l, left=m + (1.5 if m else 0), height=0.5, color=GREY, edgecolor="none")
        ax.text(m + l + 6, yy, f"{m} answered {MODERN},  {l} did not", va="center", fontsize=8.8)
        ax.text(-5, yy, label, ha="right", va="center", fontsize=8.6, linespacing=1.3)
    ax.set_xlim(0, 230); ax.set_ylim(-0.55, len(order) - 0.45); ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(RULE); ax.tick_params(axis="x", colors=INK2, labelsize=8.2, length=0)
    ax.xaxis.grid(True, color=RULE, lw=0.8); ax.set_axisbelow(True); ax.set_xticks([0, 50, 100, 150, 200])
    ax.set_xlim(0, 330)
fig.text(0.05, 0.105, f"Sample: seed {D['seed']}, from the {n(D['pypi']['population'])} PyPI and {n(D['npm']['population'])} npm entries with a successful sandbox run. "
         "The dependency is read\nfrom registry metadata of the exact version that ran (requires_dist on PyPI; dependencies and peerDependencies\n"
         "on npm). Nothing was installed for this figure. Data: dependency_sample.json.",
         fontsize=8.0, color=INK2, va="center", linespacing=1.5)
save(fig, "dependency")

# ---- 4. Cover: three hundred-square grids --------------------------------------------------------------------------
fig = plt.figure(figsize=(8, 3.36))
ax = fig.add_axes((0, 0, 1, 1)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
grids = [("PyPI", round(100 * bars[0][1] / bars[0][2])), ("remote", round(100 * bars[1][1] / bars[1][2])),
         ("npm", round(100 * bars[3][1] / bars[3][2]))]
cell, gap = 0.0105, 0.0035
for gi, (name, filled) in enumerate(grids):
    x0 = 0.478 + gi * 0.172
    for k in range(100):
        col, row = k % 10, k // 10
        x = x0 + col * (cell + gap)
        yv = 0.30 + row * (cell + gap) * (8 / 3.36)
        ax.add_patch(Rectangle((x, yv), cell, cell * (8 / 3.36), fc=BLUE if k < filled else GREY2, ec="none"))
    ax.text(x0, 0.2, name, fontsize=10, family=MONO, color=INK2, va="center")
    ax.text(x0 + 10 * (cell + gap) - gap, 0.2, f"{filled} %", fontsize=12, weight="bold", va="center", ha="right")
ax.text(0.05, 0.64, "Which MCP servers\nspeak 2026-07-28?", fontsize=22, weight="bold", va="center", linespacing=1.15)
ax.text(0.05, 0.31, "Counted per server on the official\nregistry, four months after the\nstateless revision shipped",
        fontsize=11.2, color=INK2, va="center", linespacing=1.4)
fig.savefig(A / "cover.png", dpi=200, facecolor=SURF)
plt.close(fig)
print("ok")
