#!/usr/bin/env python3
"""Is what we publish the code we have?

A distribution whose tree has moved on while its version string stayed put is worse than
an unpublished one: `pip install <name>==<same version>` serves an older codebase, so
every fix in the tree is unreachable and the docs describe behaviour that does not exist
in what people install. Nineteen distributions were in that state at once — aimarket-hub
(3.2.1, 42 files), skopos-fleet (0.1.5, 27), aimarket-metis (0.2.0, 14),
aimarket-bridges (0.1.0, whose whole `agent_framework` adapter and its `[agent-framework]`
extra were unreachable while five landing pages told people to install it) — because
nothing compared the two.

What this does: for every first-party pyproject.toml, read the declared name and version,
fetch that exact version's wheel from PyPI, and compare every shipped `.py` byte for byte
against the tree. A difference at the same version is a release blocker.

Usage:
    python3 scripts/verify_published_dist_freshness.py            # all first-party dists
    python3 scripts/verify_published_dist_freshness.py atlas gaia # only these trees
    python3 scripts/verify_published_dist_freshness.py --json     # machine-readable

Second check, same run: two distributions must not install the same TOP-LEVEL import
name. Three of them shipped `mcp_stdio_server` once, and with two installed the module in
site-packages belonged to whichever won the install — the header of
`plugins/aimarket-oracle-gateway/pyproject.toml` still carries that post-mortem. Ten
`*-course` distributions currently ship ten DIFFERENT `courselib` packages, so installing
two courses into one environment silently replaces one course's library with another's.

Exit code 1 if any distribution diverges at its published version, or if two PUBLISHED
distributions collide on an import name. A collision between distributions that are not
on PyPI yet is a pre-publication blocker: it is listed, loudly, but does not fail the run,
because nothing is broken for anyone until the second one is published. Needs network; a
distribution that is not on PyPI, or whose tree version is unpublished, is reported and
does NOT fail the run — the point is drift at an identical version, not release status.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = ("node_modules", ".upstreams", ".venv", ".git", ".claude", "site-packages")
_NAME = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.M)
_VERSION = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.M)
TIMEOUT = 40

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def _first_party_pyprojects() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*pyproject.toml"], cwd=ROOT, capture_output=True, text=True
    )
    paths = []
    for rel in out.stdout.split():
        p = ROOT / rel
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        paths.append(p)
    return sorted(paths)


def _declared(proj: Path) -> tuple[str, str] | None:
    text = proj.read_text(encoding="utf-8", errors="replace")
    name, version = _NAME.search(text), _VERSION.search(text)
    if not (name and version):
        return None
    if name.group(1).startswith("__"):  # cookiecutter-style template
        return None
    return name.group(1), version.group(1)


def _pypi(name: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=TIMEOUT) as r:
            return json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _wheel(url: str) -> zipfile.ZipFile | None:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return zipfile.ZipFile(io.BytesIO(r.read()))
    except Exception:
        return None


def _compare(proj: Path, wheel: zipfile.ZipFile) -> list[str]:
    """Files the wheel ships that differ from, or are missing against, the tree."""
    shipped_tops = {n.split("/")[0] for n in wheel.namelist() if n.endswith(".py")}
    diff: list[str] = []
    for top in sorted(shipped_tops):
        base = proj.parent / top
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            rel = py.relative_to(proj.parent).as_posix()
            # Tests are not part of every wheel; comparing them invents differences.
            if rel.startswith("tests/") or "/tests/" in f"/{rel}":
                continue
            try:
                published = wheel.read(rel)
            except KeyError:
                diff.append(f"+ {rel}  (in the tree, absent from the published wheel)")
                continue
            if hashlib.sha256(published).hexdigest() != hashlib.sha256(py.read_bytes()).hexdigest():
                diff.append(f"~ {rel}")
    return diff


def _import_names(proj: Path) -> set[str]:
    """Top-level importable packages this distribution would install."""
    return {
        d.name
        for d in proj.parent.iterdir()
        if d.is_dir() and (d / "__init__.py").is_file() and d.name != "tests"
        and not any(part in SKIP_PARTS for part in d.parts)
    }


def _collisions(rows: list[dict]) -> dict[str, list[dict]]:
    owners: dict[str, list[dict]] = {}
    for r in rows:
        for name in r.get("imports", ()):
            owners.setdefault(name, []).append(r)
    return {
        name: rs for name, rs in owners.items()
        if len({r["dist"] for r in rs}) > 1
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trees", nargs="*", help="limit to these top-level trees (e.g. atlas gaia)")
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = ap.parse_args(argv)

    rows = []
    for proj in _first_party_pyprojects():
        rel = proj.relative_to(ROOT).as_posix()
        if args.trees and not any(rel == t or rel.startswith(t.rstrip("/") + "/") for t in args.trees):
            continue
        declared = _declared(proj)
        if not declared:
            continue
        name, version = declared
        meta = _pypi(name)
        if meta is None:
            rows.append({"dist": name, "tree": rel, "version": version, "state": "not-on-pypi", "diff": [], "imports": sorted(_import_names(proj))})
            continue
        latest = meta["info"]["version"]
        files = meta["releases"].get(version) or []
        wheels = [f for f in files if f["filename"].endswith(".whl")]
        if not files:
            rows.append({"dist": name, "tree": rel, "version": version, "latest": latest,
                         "state": "tree-ahead", "diff": [], "imports": sorted(_import_names(proj))})
            continue
        if not wheels:
            rows.append({"dist": name, "tree": rel, "version": version, "latest": latest,
                         "state": "sdist-only", "diff": [], "imports": sorted(_import_names(proj))})
            continue
        wheel = _wheel(wheels[0]["url"])
        if wheel is None:
            rows.append({"dist": name, "tree": rel, "version": version, "latest": latest,
                         "state": "wheel-unreachable", "diff": [], "imports": sorted(_import_names(proj))})
            continue
        diff = _compare(proj, wheel)
        rows.append({"dist": name, "tree": rel, "version": version, "latest": latest,
                     "state": "diverged" if diff else "identical", "diff": diff,
                     "imports": sorted(_import_names(proj))})

    diverged = [r for r in rows if r["state"] == "diverged"]
    collisions = _collisions(rows)
    published_collisions = {
        n: rs for n, rs in collisions.items()
        if sum(1 for r in rs if r["state"] != "not-on-pypi") > 1
    }

    if args.json:
        print(json.dumps({
            "rows": rows,
            "diverged": len(diverged),
            "import_name_collisions": {n: [r["dist"] for r in rs] for n, rs in collisions.items()},
            "published_collisions": sorted(published_collisions),
        }, indent=2))
        return 1 if (diverged or published_collisions) else 0

    print(f"{'distribution':32} {'version':10} state")
    for r in sorted(rows, key=lambda r: (r["state"] != "diverged", r["dist"])):
        colour = {"diverged": RED, "identical": GREEN}.get(r["state"], DIM)
        note = r["state"]
        if r["state"] == "diverged":
            note = f"DIVERGED — {len(r['diff'])} shipped file(s) differ at this exact version"
        elif r["state"] == "tree-ahead":
            note = f"tree ahead of PyPI (latest {r.get('latest')}) — unpublished, fine"
        print(f"{colour}{r['dist']:32} {r['version']:10} {note}{OFF}")
        for line in r["diff"][:8]:
            print(f"{DIM}{'':44}{line}{OFF}")
        if len(r["diff"]) > 8:
            print(f"{DIM}{'':44}… and {len(r['diff']) - 8} more{OFF}")

    if collisions:
        print("\nImport-name collisions across distributions:")
        for name, rs in sorted(collisions.items()):
            live = [r for r in rs if r["state"] != "not-on-pypi"]
            colour = RED if len(live) > 1 else YELLOW
            tag = "PUBLISHED COLLISION" if len(live) > 1 else "pre-publication blocker"
            print(f"  {colour}{name:24} {tag}{OFF}")
            for r in sorted(rs, key=lambda r: r["dist"]):
                where = "on PyPI" if r["state"] != "not-on-pypi" else "unpublished"
                print(f"{DIM}      {r['dist']:34} {r['tree']:46} {where}{OFF}")

    failed = bool(diverged or published_collisions)
    if diverged:
        print(f"\n{RED}{len(diverged)} distribution(s) diverged from their published version.{OFF}")
        print("Bump the version in each pyproject.toml (and any plugin class `version`")
        print("attribute that must match) before the next publish, or the fix stays unreachable.")
    if published_collisions:
        print(f"\n{RED}{len(published_collisions)} import name(s) are claimed by more than one "
              f"PUBLISHED distribution.{OFF} Installing both leaves whichever won the install.")
    if not failed:
        print(f"\n{GREEN}Every published distribution matches its tree.{OFF}")
        if collisions:
            print(f"{YELLOW}Rename before publishing the colliding names above.{OFF}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
