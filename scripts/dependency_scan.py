#!/usr/bin/env python3
"""Vulnerability scan of EVERY dependency manifest in the monorepo.

    python3 scripts/dependency_scan.py                 # whole tree, fail on high+
    python3 scripts/dependency_scan.py aimarket-hub    # one subtree
    python3 scripts/dependency_scan.py --level critical
    python3 scripts/dependency_scan.py --json out.json

Why this exists
---------------
A miner was dropped into a production Next.js container through an unauthenticated RCE.
Two scanners were already running and neither could have caught it:

  * `.github/dependabot.yml` watches 5 directories. The monorepo has 116 npm
    projects and 41 Python requirement files. Most of them sit outside that list.
  * `security-scan.yml`'s npm-audit job installs and audits `web/frontend` and the
    TypeScript SDK only, weekly.

So it queries OSV.dev directly from the lockfiles instead of running `npm audit` per
project: no install step, no network of node_modules, transitive versions included,
and the same database GitHub advisories come from. Findings are deduplicated by
(ecosystem, package, version), so 66 lockfiles cost a few hundred queries, not tens
of thousands.

It answers "is the SOURCE vulnerable". It deliberately does NOT answer "is what is
RUNNING vulnerable" — that is the gap that let the miner stay up, because the repo
said 15.5.7 while the container ran 15.5.4. See scripts/deployed_versions.py.

Top-level dirs in INDEPENDENT are skipped on a bare run. Pass the subtree to scan one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"
SKIP_DIRS = {
    "node_modules", ".git", ".next", ".venv", "venv", "dist", "build",
    "__pycache__", ".mypy_cache", ".pytest_cache", "out", ".turbo",
}
# Top-level dirs skipped on a bare run. Pass the subtree to scan one of them.
def _unpublished_root_dirs() -> set[str]:
    map_path = Path(__file__).resolve().parent / "satellite-map.yaml"
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(map_path.read_text()) or {}
    except Exception:
        return set()
    out: set[str] = set()
    for sat in data.get("satellites") or []:
        if not isinstance(sat, dict) or sat.get("github_published") is not False:
            continue
        for p in sat.get("paths") or []:
            top = str(p).split("/")[0]
            if top:
                out.add(top)
    return out


INDEPENDENT = _unpublished_root_dirs()
RANK = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1, "UNKNOWN": 0}


def walk(root: Path, respect_independent: bool = True):
    for base, dirs, files in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS
            and not d.startswith(".cache")
            and not (respect_independent and Path(base) == root and d in INDEPENDENT)
        ]
        yield Path(base), files


def npm_packages(lock: Path) -> set[tuple[str, str, str]]:
    """(ecosystem, name, version) for every resolved package in a lockfile."""
    try:
        data = json.loads(lock.read_text())
    except Exception:
        return set()
    found: set[tuple[str, str, str]] = set()
    # lockfileVersion 2/3
    for path, meta in (data.get("packages") or {}).items():
        if not path or not isinstance(meta, dict):
            continue  # "" is the project itself
        version = meta.get("version")
        name = meta.get("name") or path.split("node_modules/")[-1]
        if version and name and not meta.get("link"):
            found.add(("npm", name, version))
    # lockfileVersion 1
    def walk_deps(deps):
        for name, meta in (deps or {}).items():
            if isinstance(meta, dict) and meta.get("version"):
                found.add(("npm", name, meta["version"]))
                walk_deps(meta.get("dependencies"))
    walk_deps(data.get("dependencies"))
    return found


PIN = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*==\s*([A-Za-z0-9._+!-]+)")


def pip_packages(req: Path) -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    try:
        for line in req.read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            m = PIN.match(line)
            if m:
                found.add(("PyPI", m.group(1), m.group(2)))
    except Exception:
        pass
    return found


def collect(root: Path, respect_independent: bool = True):
    packages: set[tuple[str, str, str]] = set()
    owners: dict[tuple[str, str, str], set[str]] = {}
    for base, files in walk(root, respect_independent):
        for name in files:
            if name == "package-lock.json":
                got = npm_packages(base / name)
            elif name.startswith("requirements") and name.endswith(".txt"):
                got = pip_packages(base / name)
            else:
                continue
            where = str(base.relative_to(root)) or "."
            for key in got:
                packages.add(key)
                owners.setdefault(key, set()).add(where)
    return packages, owners


def osv_batch(packages: list[tuple[str, str, str]]) -> dict[tuple[str, str, str], list[str]]:
    """Ask OSV which of these versions are affected. Returns package -> [vuln ids]."""
    hits: dict[tuple[str, str, str], list[str]] = {}
    for start in range(0, len(packages), 900):
        chunk = packages[start : start + 900]
        body = json.dumps(
            {"queries": [
                {"package": {"ecosystem": eco, "name": name}, "version": version}
                for eco, name, version in chunk
            ]}
        ).encode()
        req = urllib.request.Request(
            OSV_BATCH, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as fh:
                results = json.loads(fh.read()).get("results", [])
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  ! OSV query failed ({exc}); {len(chunk)} packages unchecked", file=sys.stderr)
            continue
        for key, result in zip(chunk, results):
            ids = [v["id"] for v in (result.get("vulns") or [])]
            if ids:
                hits[key] = ids
        print(f"  queried {min(start + len(chunk), len(packages))}/{len(packages)}", file=sys.stderr)
    return hits


def vuln_details(ids: set[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for n, vid in enumerate(sorted(ids), 1):
        try:
            with urllib.request.urlopen(OSV_VULN + vid, timeout=60) as fh:
                out[vid] = json.loads(fh.read())
        except Exception:
            out[vid] = {}
        if n % 25 == 0:
            print(f"  detailed {n}/{len(ids)}", file=sys.stderr)
    return out


def severity_of(vuln: dict) -> str:
    spec = (vuln.get("database_specific") or {}).get("severity")
    if isinstance(spec, str) and spec.upper() in RANK:
        return spec.upper()
    for sev in vuln.get("severity") or []:
        score = str(sev.get("score", ""))
        m = re.search(r"/(?:CR?):([NLMH])", score)
        if "CRITICAL" in score.upper():
            return "CRITICAL"
    # CVSS vector without a label: fall back to the affected ranges' own hint
    return "UNKNOWN"


def fixed_versions(vuln: dict, eco: str, name: str) -> list[str]:
    out: list[str] = []
    for aff in vuln.get("affected") or []:
        pkg = aff.get("package") or {}
        if pkg.get("name") != name or pkg.get("ecosystem") != eco:
            continue
        for rng in aff.get("ranges") or []:
            for ev in rng.get("events") or []:
                if "fixed" in ev:
                    out.append(ev["fixed"])
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("subtree", nargs="?", default=".", help="limit the scan to this path")
    ap.add_argument("--level", default="high", choices=["critical", "high", "moderate", "low"],
                    help="minimum severity that fails the run (default: high)")
    ap.add_argument("--json", help="write the full finding set here")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    target = (root / args.subtree).resolve()
    print(f"scanning {target}", file=sys.stderr)

    # Scanning a subtree ON PURPOSE overrides the independence rule — otherwise
    # `dependency_scan.py <independent-dir>` would silently scan nothing.
    packages, owners = collect(target, respect_independent=target == root)
    print(f"{len(packages)} distinct (ecosystem, package, version) across the tree", file=sys.stderr)
    if not packages:
        print("no manifests found")
        return 0

    hits = osv_batch(sorted(packages))
    if not hits:
        print("\nOK: OSV reports no known vulnerability for any pinned dependency.")
        return 0

    every_id = {vid for ids in hits.values() for vid in ids}
    print(f"{len(hits)} affected packages, {len(every_id)} advisories — fetching details", file=sys.stderr)
    details = vuln_details(every_id)

    findings = []
    for (eco, name, version), ids in hits.items():
        for vid in ids:
            vuln = details.get(vid) or {}
            findings.append({
                "ecosystem": eco, "package": name, "version": version, "id": vid,
                "severity": severity_of(vuln),
                "summary": (vuln.get("summary") or "").strip()[:110],
                "fixed": fixed_versions(vuln, eco, name)[-3:],
                "projects": sorted(owners[(eco, name, version)])[:4],
            })
    findings.sort(key=lambda f: (-RANK[f["severity"]], f["package"], f["version"]))

    if args.json:
        Path(args.json).write_text(json.dumps(findings, indent=2))
        print(f"wrote {args.json}", file=sys.stderr)

    gate = RANK[args.level.upper()]
    blocking = [f for f in findings if RANK[f["severity"]] >= gate]

    by_sev: dict[str, int] = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
    print("\n=== severity totals ===")
    for sev in ("CRITICAL", "HIGH", "MODERATE", "LOW", "UNKNOWN"):
        if by_sev.get(sev):
            print(f"  {sev:<9} {by_sev[sev]}")

    if blocking:
        print(f"\n=== at or above {args.level.upper()} ({len(blocking)}) ===")
        for f in blocking[:60]:
            fix = ", ".join(f["fixed"]) or "no fix published"
            print(f"  {f['severity']:<8} {f['ecosystem']}:{f['package']}@{f['version']}")
            print(f"           {f['id']}  fix: {fix}")
            if f["summary"]:
                print(f"           {f['summary']}")
            print(f"           in: {', '.join(f['projects'])}")
        if len(blocking) > 60:
            print(f"  ... and {len(blocking) - 60} more (use --json)")
        return 1

    print(f"\nOK: nothing at or above {args.level.upper()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
