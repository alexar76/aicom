"""A satellite's advertised test count must be one number, not four.

Sixteen satellites ship a `docs/badges/tests.svg` on the landing page of their published
GitHub repo. Eleven of them advertised a number the suite had long passed — `atlas` said
101 against 514, `gaia` said 45 against 277, `momus` 171 against 393 — and the numbers
disagreed with each other *inside one repo*: `helios/README-es.md` and `README-ru.md` said
39 while the EN README and the badge said 45, and a shields.io URL with the count baked
into it said something different again from its own `alt` text.

The root cause is that the badge is generated and then thrown away: `skopos` and `gaia`
run `scripts/generate_tests_badge.py` in CI and only *print* the result ("informational"),
so the committed SVG is a hand-stamped snapshot that drifts forever.

This guard cannot know the true count for every satellite — each needs its own interpreter
and dependency set. What it CAN do, with no environment at all, is require that every place
one satellite states its count agrees with every other place: the SVG, the optional
`tests.json`, each README's `alt=` text, each shields.io URL with a number in it, and the
"N tests passing" prose. A hand edit to one of them now fails here instead of shipping.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Trees that are not first-party published satellites.
SKIP_PARTS = (
    "node_modules",
    ".upstreams",   # vendored snapshots of other repos
    ".venv",
    ".git",
    ".claude",      # agent worktrees / transient checkouts, not first-party source
    "npm-reserve",  # name reservations, no suite of their own
)

_SVG_LABEL = re.compile(r'aria-label="tests:\s*(\d+)\s')
_ALT = re.compile(r'alt="(\d+)\s+tests?(?:\s+(?:passing|passed))?"')
_SHIELDS = re.compile(r'img\.shields\.io/badge/tests-(\d+)')
_PROSE = re.compile(r'\*\*(\d+)\*\*\s+(?:tests?|pytest)\b|\b(\d+)\s+tests?\s+pass(?:ing|ed)?\b')


def _badge_dirs() -> list[Path]:
    out = []
    for svg in ROOT.rglob("docs/badges/tests.svg"):
        if any(part in SKIP_PARTS for part in svg.parts):
            continue
        out.append(svg)
    return sorted(out)


def _satellite_root(svg: Path) -> Path:
    # <satellite>/docs/badges/tests.svg  ->  <satellite>
    return svg.parent.parent.parent


def _claims(svg: Path) -> dict[str, set[int]]:
    """Every number this satellite states about its own test count, by source."""
    found: dict[str, set[int]] = defaultdict(set)
    text = svg.read_text(encoding="utf-8", errors="replace")
    m = _SVG_LABEL.search(text)
    if m:
        found[svg.relative_to(ROOT).as_posix()].add(int(m.group(1)))

    payload = svg.parent / "tests.json"
    if payload.is_file():
        try:
            msg = str(json.loads(payload.read_text(encoding="utf-8")).get("message", ""))
        except (json.JSONDecodeError, OSError):
            msg = ""
        n = re.match(r"(\d+)", msg)
        if n:
            found[payload.relative_to(ROOT).as_posix()].add(int(n.group(1)))

    sat = _satellite_root(svg)
    for md in sorted(sat.glob("README*.md")) + sorted(sat.glob("docs/README*.md")):
        if any(part in SKIP_PARTS for part in md.parts):
            continue
        body = md.read_text(encoding="utf-8", errors="replace")
        key = md.relative_to(ROOT).as_posix()
        for rx in (_ALT, _SHIELDS):
            for hit in rx.finditer(body):
                found[key].add(int(hit.group(1)))
        for hit in _PROSE.finditer(body):
            found[key].add(int(hit.group(1) or hit.group(2)))
    return found


def test_there_are_badges_to_check():
    """A guard that scans nothing passes for the wrong reason."""
    dirs = _badge_dirs()
    assert len(dirs) >= 10, f"only found {len(dirs)} tests badges — the walk is broken"


@pytest.mark.parametrize(
    "svg", _badge_dirs(), ids=lambda p: _satellite_root(p).name
)
def test_one_satellite_states_one_test_count(svg: Path):
    claims = _claims(svg)
    numbers = {n for values in claims.values() for n in values}
    if not numbers:
        pytest.skip(f"{svg.relative_to(ROOT)} states no number (placeholder badge)")
    assert len(numbers) == 1, (
        f"{_satellite_root(svg).name} advertises {sorted(numbers)} in different places:\n  "
        + "\n  ".join(f"{src}: {sorted(v)}" for src, v in sorted(claims.items()))
        + "\nRegenerate with scripts/generate_tests_badge.py --count <n> and update every README."
    )
