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

It reads package-lock.json, requirements*.txt, uv.lock, Cargo.lock and pubspec.lock.
A manifest it cannot read is an incomplete scan (exit 2), never a clean one.
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

try:  # Python 3.11+; tomli is the same parser for older interpreters.
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"
SKIP_DIRS = {
    "node_modules", ".git", ".next", ".venv", "venv", "dist", "build",
    "__pycache__", ".mypy_cache", ".pytest_cache", "out", ".turbo",
    ".claude",
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


class IncompleteScan(RuntimeError):
    """The scanner cannot establish a clean result."""


def walk(root: Path, respect_independent: bool = True):
    for base, dirs, files in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS
            and not d.startswith(".cache")
            and not (respect_independent and Path(base) == root and d in INDEPENDENT)
            # Pinned upstream checkouts are gitignored, so CI never sees them: a bare
            # run skips them to match, and a subtree scanned on purpose includes them.
            and not (respect_independent and d == ".upstreams")
        ]
        yield Path(base), files


def npm_packages(lock: Path) -> set[tuple[str, str, str]]:
    """(ecosystem, name, version) for every resolved package in a lockfile."""
    try:
        data = json.loads(lock.read_text())
    except (OSError, ValueError) as exc:
        raise IncompleteScan(f"cannot parse {lock}") from exc
    if not isinstance(data, dict):
        raise IncompleteScan(f"cannot parse {lock}")
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


# Extras ("uvicorn[standard]==0.30.6") belong to the name, not to the pin.
PIN = re.compile(r"^\s*([A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9._+!-]+)")


def pip_packages(req: Path) -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    try:
        lines = req.read_text().splitlines()
    except (OSError, ValueError) as exc:
        raise IncompleteScan(f"cannot read {req}") from exc
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith("#"):
            continue
        m = PIN.match(line)
        if m:
            found.add(("PyPI", m.group(1), m.group(2)))
        elif "==" in line.split(";", 1)[0]:
            # An exact pin this cannot read would otherwise drop out unchecked.
            raise IncompleteScan(f"cannot parse the pin on line {number} of {req}")
    return found


def toml_lock(lock: Path) -> dict:
    if tomllib is None:
        raise IncompleteScan(f"cannot parse {lock}: reading TOML needs Python 3.11+ or tomli")
    try:
        data = tomllib.loads(lock.read_text())
    except (OSError, ValueError) as exc:
        raise IncompleteScan(f"cannot parse {lock}") from exc
    if not isinstance(data.get("package", []), list):
        raise IncompleteScan(f"cannot parse {lock}")
    return data


# The project itself, local paths and git checkouts have no registry version to look up.
UV_LOCAL = {"editable", "virtual", "path", "directory", "git"}


def uv_packages(lock: Path) -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for pkg in toml_lock(lock).get("package", []):
        source = pkg.get("source") if isinstance(pkg, dict) else None
        if not isinstance(source, dict):
            raise IncompleteScan(f"cannot parse {lock}: a package has no source")
        if "registry" in source or "url" in source:
            if not pkg.get("name") or not pkg.get("version"):
                raise IncompleteScan(f"cannot parse {lock}: {pkg.get('name')} has no version")
            found.add(("PyPI", pkg["name"], pkg["version"]))
        elif not UV_LOCAL & source.keys():
            raise IncompleteScan(f"cannot parse {lock}: unknown source for {pkg.get('name')}")
    return found


def cargo_packages(lock: Path) -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for pkg in toml_lock(lock).get("package", []):
        source = pkg.get("source") if isinstance(pkg, dict) else ""
        if source is None or str(source).startswith(("git+", "path+")):
            continue  # a workspace member, path or git dependency
        if not str(source).startswith(("registry+", "sparse+")) or not pkg.get("name") \
                or not pkg.get("version"):
            raise IncompleteScan(f"cannot parse {lock}: unreadable package entry")
        found.add(("crates.io", pkg["name"], pkg["version"]))
    return found


def pub_packages(lock: Path) -> set[tuple[str, str, str]]:
    """pubspec.lock is YAML that `dart pub` always writes in one layout. Read that
    layout without needing PyYAML, and refuse anything else."""
    try:
        lines = lock.read_text().splitlines()
    except (OSError, ValueError) as exc:
        raise IncompleteScan(f"cannot read {lock}") from exc
    packages: dict[str, dict[str, str]] = {}
    section = current = None
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, sep, value = line.strip().partition(":")
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not sep or indent % 2:
            raise IncompleteScan(f"cannot parse line {number} of {lock}")
        if indent == 0:
            section, current = key, None
            if key == "packages" and value not in ("", "{}"):
                raise IncompleteScan(f"cannot parse line {number} of {lock}")
        elif section != "packages":
            continue
        elif indent == 2:
            current = packages.setdefault(key, {})
        elif current is None:
            raise IncompleteScan(f"cannot parse line {number} of {lock}")
        elif indent == 4:
            current[key] = value
    found: set[tuple[str, str, str]] = set()
    for name, meta in packages.items():
        if meta.get("source") == "hosted" and meta.get("version"):
            found.add(("Pub", name, meta["version"]))
        elif meta.get("source") not in ("sdk", "path", "git"):
            raise IncompleteScan(f"cannot parse {lock}: {name} has no hosted version")
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
            elif name == "uv.lock":
                got = uv_packages(base / name)
            elif name == "Cargo.lock":
                got = cargo_packages(base / name)
            elif name == "pubspec.lock":
                got = pub_packages(base / name)
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
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise IncompleteScan(f"OSV query failed; {len(chunk)} packages unchecked") from exc
        if not isinstance(results, list) or len(results) != len(chunk):
            raise IncompleteScan("OSV returned an incomplete batch")
        for key, result in zip(chunk, results):
            if not isinstance(result, dict) or result.get("next_page_token"):
                raise IncompleteScan("OSV returned an invalid or paginated result")
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
        except Exception as exc:
            raise IncompleteScan(f"OSV advisory unavailable: {vid}") from exc
        if not isinstance(out[vid], dict) or out[vid].get("id") != vid:
            raise IncompleteScan(f"OSV advisory invalid: {vid}")
        if n % 25 == 0:
            print(f"  detailed {n}/{len(ids)}", file=sys.stderr)
    return out


# CVSS v3.x base metric weights, from FIRST's specification (section 7.4).
CVSS3 = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62},
    "C": {"H": 0.56, "L": 0.22, "N": 0.0},
    "I": {"H": 0.56, "L": 0.22, "N": 0.0},
    "A": {"H": 0.56, "L": 0.22, "N": 0.0},
}
CVSS3_PR = {"U": {"N": 0.85, "L": 0.62, "H": 0.27}, "C": {"N": 0.85, "L": 0.68, "H": 0.5}}


def cvss3_score(vector: str):
    """Base score of a CVSS:3.0 or 3.1 vector, or None for anything else."""
    parts = vector.split("/")
    if parts[0] not in ("CVSS:3.0", "CVSS:3.1"):
        return None
    metrics = dict(p.split(":", 1) for p in parts[1:] if ":" in p)
    try:
        scope = metrics["S"]
        pr = CVSS3_PR[scope][metrics["PR"]]
        w = {k: CVSS3[k][metrics[k]] for k in CVSS3}
    except KeyError:
        return None
    iss = 1 - (1 - w["C"]) * (1 - w["I"]) * (1 - w["A"])
    impact = 6.42 * iss if scope == "U" else 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * w["AV"] * w["AC"] * pr * w["UI"]
    total = impact + exploitability if scope == "U" else 1.08 * (impact + exploitability)
    # The specification's Roundup, done in integers so float noise cannot bump a score.
    n = round(min(total, 10) * 100000)
    return n / 100000 if n % 10000 == 0 else (n // 10000 + 1) / 10


def cvss3_rating(score: float) -> str:
    return "CRITICAL" if score >= 9 else "HIGH" if score >= 7 else "MODERATE" if score >= 4 else "LOW"


def severity_of(vuln: dict) -> str:
    spec = (vuln.get("database_specific") or {}).get("severity")
    if isinstance(spec, str) and spec.upper() in RANK:
        return spec.upper()
    best = "UNKNOWN"
    for sev in vuln.get("severity") or []:
        score = str(sev.get("score", ""))
        if "CRITICAL" in score.upper():
            return "CRITICAL"
        base = cvss3_score(score)
        if base is not None and RANK[cvss3_rating(base)] > RANK[best]:
            best = cvss3_rating(base)
    # CVSS v2 and v4 vectors are not scored here; UNKNOWN keeps the gate closed on them.
    return best


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
    try:
        packages, owners = collect(target, respect_independent=target == root)
    except IncompleteScan as exc:
        print(f"INCOMPLETE: {exc}", file=sys.stderr)
        return 2
    print(f"{len(packages)} distinct (ecosystem, package, version) across the tree", file=sys.stderr)
    if not packages:
        print("no manifests found")
        return 0

    try:
        hits = osv_batch(sorted(packages))
    except IncompleteScan as exc:
        print(f"INCOMPLETE: {exc}", file=sys.stderr)
        return 2
    if not hits:
        print("\nOK: OSV reports no known vulnerability for any pinned dependency.")
        return 0

    every_id = {vid for ids in hits.values() for vid in ids}
    print(f"{len(hits)} affected packages, {len(every_id)} advisories — fetching details", file=sys.stderr)
    try:
        details = vuln_details(every_id)
    except IncompleteScan as exc:
        print(f"INCOMPLETE: {exc}", file=sys.stderr)
        return 2

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

    if by_sev.get("UNKNOWN"):
        print("INCOMPLETE: advisories with unknown severity require review", file=sys.stderr)
        return 2
    print(f"\nOK: nothing at or above {args.level.upper()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
