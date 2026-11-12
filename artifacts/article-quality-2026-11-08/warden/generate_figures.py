"""Deterministic SVG technical figures. Input data comes from generate_fixtures.py.

Usage: python3 generate_figures.py --out /tmp/warden-quality-2026-11-08
SVG/PNG canonical copies are stored with the article in PromoMaterials.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
args = argparse.ArgumentParser()
args.add_argument("--out", type=Path, required=True)
out = args.parse_args().out
out.mkdir(parents=True, exist_ok=True)
data = json.loads((HERE / "fixture-results.json").read_text())

INK = "#142C40"
MUTED = "#4C6476"
TEAL = "#087F77"
AMBER = "#9B5B04"
FONT = "Arial, Helvetica, sans-serif"


def text(x, y, label, size=28, color=INK, weight=400, anchor="start", mono=False):
    family = "monospace" if mono else FONT
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(str(label))}</text>')


def rect(x, y, w, h, fill, stroke="none", radius=20):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'


def path(d, color=MUTED):
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="4" marker-end="url(#arrow)"/>'


def svg(width, height, title, content):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">'
            f'<title>{escape(title)}</title><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#4C6476"/></marker></defs>'
            '<rect width="100%" height="100%" fill="#F5F8FA"/>' + "".join(content) + '</svg>\n')


c = [
    text(72, 80, "A running process can have no admitted MCP tools", 43, weight=700),
    text(72, 125, "ARGUS implementation paths · recorded incident state on 6 November 2026", 26, MUTED),
    rect(72, 177, 1456, 132, INK),
    text(106, 228, "ARGUS process remains running", 33, "#FFFFFF", 700),
    text(106, 274, "Container liveness does not depend on every MCP server being usable.", 26, "#CEE0EC"),
    rect(1156, 203, 330, 76, "#DBF3EC"),
    text(1321, 251, 'status: "ok"', 31, TEAL, 700, "middle", True),
    rect(72, 382, 352, 164, "#FFFFFF", "#B6C8D4"),
    text(104, 431, "Hub tools/list", 32, weight=700),
    text(104, 475, "names · descriptions", 26, MUTED),
    text(104, 513, "input/output schemas", 26, MUTED),
    path("M 424 464 H 494"),
    rect(510, 382, 410, 164, "#E7EFF9", "#91ACC8"),
    text(546, 433, "WARDEN checks", 32, weight=700),
    text(546, 477, "Includes comparison with", 26, MUTED),
    text(546, 515, "the approved snapshot", 26, MUTED),
    path("M 920 424 H 980 V 393 H 1074"),
    text(984, 367, "allow", 26, TEAL),
    rect(1090, 348, 438, 100, "#E8F4F1", "#9FCAC0"),
    text(1122, 390, "connected", 30, TEAL, 700, mono=True),
    text(1122, 429, "vetted tools can be exposed", 26, MUTED),
    path("M 920 505 H 1008 V 540 H 1074"),
    text(984, 484, "drift", 26, AMBER),
    rect(1090, 490, 438, 112, "#FFF0D7", "#C9933D"),
    text(1122, 535, "blocked", 30, AMBER, 700, mono=True),
    text(1122, 577, "TOOL_DEF_DRIFT · no tools", 26, AMBER),
    path("M 248 546 V 688 H 1074"),
    text(420, 664, "tools/list cannot be read", 26, MUTED),
    rect(1090, 634, 438, 100, "#EDF0F5", "#B4BECC"),
    text(1122, 676, "failed", 30, MUTED, 700, mono=True),
    text(1122, 716, "read / launch / connect failure", 26, MUTED),
    rect(72, 800, 1456, 234, "#FFF8EA", "#DDC28D"),
    text(108, 852, "Recorded after the rollout, on all three ARGUS instances", 32, weight=700),
    text(108, 906, "connected 0     blocked 1     failed 0", 32, AMBER, 700, mono=True),
    text(108, 956, "Review → human TTY approval → restart was still pending.", 28, INK),
    text(108, 1001, "Highlighted branch = incident state. Other branches show possible implementation paths.", 26, MUTED),
]
(out / "mcp-admission-states.svg").write_text(svg(1600, 1080, "Process liveness and MCP admission are independent states", c))

c = [
    text(72, 80, "What actually stays equal", 43, weight=700),
    text(72, 127, "Local gateway renderer fixture · weather_now · full definition equality", 27, MUTED),
    rect(72, 178, 1456, 82, INK, radius=16),
    text(106, 231, "Fixture input", 27, "#FFFFFF", 700),
    text(665, 231, "Price USD", 26, "#FFFFFF", 700, "middle"),
    text(875, 231, "Free calls", 26, "#FFFFFF", 700, "middle"),
    text(1064, 231, "Trial", 26, "#FFFFFF", 700, "middle"),
    text(1325, 231, "Definition", 26, "#FFFFFF", 700, "middle"),
]
for i, case in enumerate(data["cases"]):
    y = 276 + 87 * i
    c.append(rect(72, y, 1456, 75, "#FFFFFF" if i % 2 == 0 else "#EDF3F6", radius=10))
    c.append(text(106, y + 48, case["case"], 28, weight=700 if i == 0 else 400))
    c.append(text(665, y + 48, f'{case["price_usd"]:.3f}', 29, INK, anchor="middle", mono=True))
    c.append(text(875, y + 48, case["trial_quota"], 29, INK, anchor="middle", mono=True))
    c.append(text(1064, y + 48, "on" if case["trial_enabled"] else "off", 28, INK, anchor="middle"))
    label = "REFERENCE" if i == 0 else "SAME" if case["equal_to_baseline"] else "CHANGED"
    color = MUTED if i == 0 else TEAL if case["equal_to_baseline"] else AMBER
    c.append(text(1325, y + 48, label, 26, color, 700, "middle"))
c.extend([
    text(72, 786, "Same: positive price 0.001 → 0.05; trial allowance 5 → 9.", 29, TEAL, 700),
    text(72, 835, "Changed: paid → free, or the trial phrase switched off.", 29, AMBER, 700),
    text(72, 902, "Chosen fixture inputs rendered locally; not a production rate or benchmark.", 26, MUTED),
])
(out / "tool-definition-fixture-matrix.svg").write_text(svg(1600, 958, "Definition equality under five local gateway fixture inputs", c))
print(json.dumps({"svg_files": sorted(p.name for p in out.glob("*.svg"))}))
