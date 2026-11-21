"""Figures for the HISTOR subregistry article (2026-11-21).

    python3 make_figures.py counts-2026-11-21.json OUTDIR
Outputs: cover.png (1600x672), flow.{png,svg}, coverage.{png,svg}.
Numbers: counts-2026-11-21.json from count.py over a walk of https://histor.modelmarket.dev/v0.1/servers?version=latest.
Colours: categorical slots of the dataviz reference palette already validated for the 2026-11-19 article (blue #2a78d6,
orange #eb6834) plus neutral greys; every mark also carries a text label.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

R = json.loads(Path(sys.argv[1]).read_text())
A = Path(sys.argv[2]); A.mkdir(parents=True, exist_ok=True)
BLUE, ORANGE, GREY, GREY2 = "#2a78d6", "#eb6834", "#c9c7c0", "#e6e4de"
SURF, INK, INK2, RULE = "#fcfcfb", "#0b0b0b", "#52514e", "#dedcd5"
MONO = ["Menlo", "DejaVu Sans Mono"]
plt.rcParams.update({"font.family": ["Helvetica", "Arial Unicode MS", "DejaVu Sans"], "svg.fonttype": "none",
                     "text.color": INK, "figure.facecolor": SURF, "axes.facecolor": SURF})


def n(x):
    return f"{x:,}"


def save(fig, name, svg=True, dpi=200):
    fig.savefig(A / f"{name}.png", dpi=dpi, facecolor=fig.get_facecolor())
    if svg:
        fig.savefig(A / f"{name}.svg", facecolor=fig.get_facecolor())
    plt.close(fig)


def box(ax, x, y, w, h, title, body, ec=RULE, fc="#ffffff", lw=1.2, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.012", fc=fc, ec=ec, lw=lw, ls=ls))
    ax.text(x + 0.025, y + h - 0.028, title, fontsize=10.5, weight="bold", va="top")
    ax.text(x + 0.025, y + h - 0.072, body, fontsize=8.8, color=INK2, va="top", linespacing=1.4)


def arrow(ax, a, b, label=None, dx=0.02):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=13, color=INK2, lw=1.2))
    if label:
        ax.text((a[0] + b[0]) / 2 + dx, (a[1] + b[1]) / 2, label, fontsize=8.4, color=INK2, va="center", linespacing=1.35)


# 1. Where an entry comes from and who reads it (portrait, phone-friendly).
fig = plt.figure(figsize=(7.2, 8.2))
ax = fig.add_axes((0, 0, 1, 1)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
ax.text(0.04, 0.968, "One registry entry, two sources", fontsize=13.5, weight="bold", va="center")
box(ax, 0.04, 0.80, 0.43, 0.13, "Official MCP registry",
    "registry.modelcontextprotocol.io\nwhat the publisher declared:\nname, version, remotes, packages")
box(ax, 0.53, 0.80, 0.43, 0.13, "HISTOR crawler",
    "tools/list of each remote (no\ncredentials) and of each npm/PyPI\npackage version; signed log", ec=BLUE)
box(ax, 0.04, 0.55, 0.92, 0.15, "HISTOR's copy of the registry",
    "server and the official _meta stored as read, never rewritten\n"
    "+ _meta[\"dev.modelmarket.histor/observed\"] on the latest version:\n"
    "per remote or package: lastStatus, toolCount, toolSetDigest, unchangedSince, changes", ec=BLUE, lw=1.6)
arrow(ax, (0.25, 0.80), (0.25, 0.70), "hourly updated_since,\nweekly full walk")
arrow(ax, (0.745, 0.80), (0.745, 0.70), "joined by server\nname")
ax.text(0.5, 0.505, "GET /v0.1/servers  ·  /v0.1/servers/{name}/versions/{version|latest}",
        fontsize=8.8, family=MONO, ha="center", va="center")
arrow(ax, (0.5, 0.55), (0.5, 0.525))
box(ax, 0.04, 0.255, 0.285, 0.205, "Copilot policy",
    "\"MCP Registry URL\"\nin organisation or\nenterprise settings\n(GitHub docs; public\npreview; not tested\nby us)", ec=GREY, ls=(0, (3, 2)))
box(ax, 0.357, 0.255, 0.285, 0.205, "A reviewer",
    "curl and jq, or\ncheck_list.py: was this\nserver ever read, and\nwhen did its tools\nlast change?")
box(ax, 0.674, 0.255, 0.285, 0.205, "Your own copy",
    "HISTOR with an allow\nlist, upstream =\nhistor.modelmarket.dev:\nonly your servers, our\nobservations kept", ec=ORANGE)
for x in (0.18, 0.5, 0.82):
    arrow(ax, (0.5, 0.488), (x, 0.462))
ax.text(0.04, 0.16, "The copy changes nothing the registry sent. What HISTOR adds sits under its own key, as the registry's\n"
        "aggregator guidance asks. A server HISTOR could not read says why (http-401, robots-disallowed, …)\n"
        "instead of carrying a tool count.", fontsize=8.4, color=INK2, va="center", linespacing=1.45)
ax.text(0.04, 0.07, "Live since 2026-11-21 10:27:59Z. Source: histor/subregistry.py in github.com/alexar76/histor.",
        fontsize=8.2, color=INK2, va="center")
save(fig, "flow")

# 2. What the observed block says for each server (latest entries).
C = R["categories"]
cats = [("recorded", "tool list recorded", BLUE),
        ("credentials", "asks for credentials\n(401 / 403)", ORANGE),
        ("robots", "robots.txt disallows\nor unreadable", "#a8a6a0"),
        ("failed", "failed: package did not\ninstall or exited, 404,\nprotocol, timeout, …", GREY),
        ("not_tried", "not attempted: package\ntype, transport or\ntemplated URL", GREY2),
        ("no_block", "no observation block\nyet", "#f1f0ec")]
total = R["servers"]
fig = plt.figure(figsize=(7.2, 7.4))
fig.text(0.05, 0.955, f"What HISTOR could say about {n(total)} servers", fontsize=13.5, weight="bold", va="center")
fig.text(0.05, 0.915, "Latest version of each server in the copy, one category per server (first match wins)",
         fontsize=9, color=INK2, va="center")
ax = fig.add_axes((0.38, 0.30, 0.56, 0.56))
for i, (k, label, colour) in enumerate(cats):
    v = C.get(k, 0)
    y = len(cats) - 1 - i
    ax.barh(y, v, height=0.62, color=colour, edgecolor=INK2 if colour in ("#f1f0ec", GREY2) else colour, lw=0.6)
    ax.text(v + total * 0.012, y, f"{n(v)}  ({100 * v / total:.1f} %)", va="center", fontsize=9.4, weight="bold")
    ax.text(-total * 0.02, y, label, ha="right", va="center", fontsize=9, linespacing=1.25)
ax.set_xlim(0, max(C.values()) * 1.42); ax.set_yticks([]); ax.set_ylim(-0.6, len(cats) - 0.4)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(RULE); ax.tick_params(axis="x", colors=INK2, labelsize=8.5, length=0)
ax.xaxis.grid(True, color=RULE, lw=0.8); ax.set_axisbelow(True)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: n(int(v))))
rec = R["recorded"]
fig.text(0.05, 0.19, f"Of the {n(rec['servers'])} with a recorded tool list, {n(rec['last_read_not_ok'])} have it only from an earlier read (the latest\n"
         f"failed or robots.txt now disallows). {n(rec['changed_at_least_once'])} changed their tool list at least once since HISTOR\n"
         f"first recorded it; {n(rec['changed_in_last_7_days'])} in the 7 days before the walk.",
         fontsize=9.2, va="center", linespacing=1.45)
w = R["walk"]
fig.text(0.05, 0.075, f"Source: {w['entries']:,} entries read from histor.modelmarket.dev/v0.1/servers?version=latest, "
         f"{R['as_of'][:10]} (walk ended\n{R['as_of'][11:16]} UTC). Observations are HISTOR's own reads without credentials; "
         "a 401 means the server needs\nan account, not that it is broken.", fontsize=8.2, color=INK2, va="center", linespacing=1.45)
save(fig, "coverage")

# 3. Cover: registry rows, each with what was seen next to it.
import random  # noqa: E402

rng = random.Random(21)
fig = plt.figure(figsize=(8, 3.36))
ax = fig.add_axes((0, 0, 1, 1)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
weights = [C.get(k, 0) for k, _, _ in cats]
colours = [c for _, _, c in cats]
for row in range(11):
    y = 0.86 - row * 0.072
    width = 0.16 + rng.random() * 0.17
    ax.add_patch(FancyBboxPatch((0.47, y - 0.018), width, 0.036, boxstyle="round,pad=0,rounding_size=0.01", fc=GREY2, ec="none"))
    ax.add_patch(FancyBboxPatch((0.47 + width + 0.015, y - 0.018), 0.05, 0.036, boxstyle="round,pad=0,rounding_size=0.01",
                                fc=RULE, ec="none"))
    c = rng.choices(colours, weights)[0]
    ax.add_patch(FancyBboxPatch((0.88, y - 0.022), 0.075, 0.044, boxstyle="round,pad=0,rounding_size=0.012", fc=c,
                                ec=INK2 if c in ("#f1f0ec", GREY2) else c, lw=0.6))
ax.text(0.47, 0.935, "registry entry", fontsize=9, color=INK2, va="center", family=MONO)
ax.text(0.88, 0.935, "observed", fontsize=9, color=BLUE, va="center", family=MONO)
ax.text(0.05, 0.66, "The MCP registry,\nwith what each\nserver actually served", fontsize=22, weight="bold", va="center", linespacing=1.15)
ax.text(0.05, 0.3, "v0.1 API · 69,634 servers · tool lists,\n401s and changes from HISTOR's log", fontsize=11.5, color=INK2,
        va="center", linespacing=1.4)
fig.savefig(A / "cover.png", dpi=200, facecolor=SURF)
plt.close(fig)
print("ok")
