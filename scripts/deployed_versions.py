#!/usr/bin/env python3
"""What is ACTUALLY RUNNING out there, and is it vulnerable?

    python3 scripts/deployed_versions.py --host hub.example
    python3 scripts/deployed_versions.py --host hub.example --key ~/.ssh/id_ed25519_factory
    python3 scripts/deployed_versions.py --host X --package next --json drift.json

Why this exists
---------------
scripts/dependency_scan.py answers "is the SOURCE vulnerable". That is not the
question that matters during an incident.

A production Next.js container was compromised through an unauthenticated RCE.
By the time it was noticed the repository had already been bumped to a patched
release — so every source-side scanner, and dependabot, and `npm audit` in CI,
all reported green. The containers were still running the vulnerable build,
because images are built at deploy time and nothing had been redeployed.
Source-side green, production owned.

This closes that gap: it reads the installed versions out of the running containers
themselves, checks them against OSV, and — because the fix is usually already
committed — says plainly when a REDEPLOY is the remediation.

It is read-only. It runs `docker ps` and reads package metadata; it never restarts,
pulls, writes or deletes anything. Acting on what it finds is a separate, deliberate
step.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"
RANK = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1, "UNKNOWN": 0}


class IncompleteScan(RuntimeError):
    """Missing inventory or vulnerability data cannot establish a clean runtime."""

# Read the version of every direct dependency out of a running Node container.
# Direct dependencies only: that is what a redeploy actually changes, and pulling the
# full transitive tree out of every container is minutes of work for noise.
NODE_PROBE = r"""
const fs=require('fs');const path=require('path');
function find(dir,depth){if(depth>3)return null;
  try{if(fs.existsSync(path.join(dir,'package.json'))&&fs.existsSync(path.join(dir,'node_modules')))return dir;}catch(e){}
  try{for(const e of fs.readdirSync(dir,{withFileTypes:true})){
    if(!e.isDirectory()||e.name==='node_modules'||e.name.startsWith('.'))continue;
    const r=find(path.join(dir,e.name),depth+1); if(r)return r;}}catch(e){}
  return null;}
const root=find(process.cwd(),0)||find('/app',0)||find('/',0);
if(!root){throw new Error('No Node application manifest found')}
const pkg=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
const out={};
for(const name of Object.keys(pkg.dependencies||{})){
  out[name]=JSON.parse(fs.readFileSync(path.join(root,'node_modules',name,'package.json'),'utf8')).version;
  if(typeof out[name]!=='string'||!out[name])throw new Error('Missing installed dependency version');
}
console.log(JSON.stringify({root:root,name:pkg.name||null,deps:out}));
"""


def ssh(host: str, key: str | None, command: str) -> str:
    argv = ["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes"]
    if key:
        argv += ["-i", key, "-o", "IdentitiesOnly=yes"]
    argv += [f"root@{host}", command]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise IncompleteScan(f"SSH inventory unavailable for {host}") from exc
    if done.returncode != 0:
        raise IncompleteScan(f"SSH inventory failed for {host} (exit {done.returncode})")
    return done.stdout


def containers(host: str, key: str | None) -> list[str]:
    out = ssh(host, key, "docker ps --format '{{.Names}}'")
    return [line.strip() for line in out.splitlines() if line.strip()]


def node_deps(host: str, key: str | None, container: str) -> dict:
    probe = shlex.quote(NODE_PROBE)
    # An absent Node executable is a deliberate skip; failed exec/invalid metadata
    # is an inventory error, even if other containers answered successfully.
    shell = 'if command -v node >/dev/null 2>&1; then exec node -e "$1"; else printf \'{"skipped":"no-node"}\\n\'; fi'
    out = ssh(host, key, f"docker exec {shlex.quote(container)} sh -c {shlex.quote(shell)} sh {probe}")
    try:
        data = json.loads(out)
    except ValueError as exc:
        raise IncompleteScan(f"Invalid Node inventory from {host}/{container}") from exc
    if isinstance(data, dict) and data.get("skipped") == "no-node":
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("deps"), dict):
        raise IncompleteScan(f"Missing Node inventory from {host}/{container}")
    if any(not isinstance(n, str) or not n or not isinstance(v, str) or not v for n, v in data["deps"].items()):
        raise IncompleteScan(f"Invalid dependency version from {host}/{container}")
    return data


def osv_lookup(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], list[str]]:
    """pairs of (package, version) in npm -> advisory ids."""
    hits: dict[tuple[str, str], list[str]] = {}
    for start in range(0, len(pairs), 900):
        chunk = pairs[start : start + 900]
        body = json.dumps({"queries": [
            {"package": {"ecosystem": "npm", "name": n}, "version": v} for n, v in chunk
        ]}).encode()
        req = urllib.request.Request(OSV_BATCH, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as fh:
                payload = json.loads(fh.read())
        except Exception as exc:
            raise IncompleteScan("OSV query failed; runtime dependencies remain unchecked") from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or len(results) != len(chunk):
            raise IncompleteScan("OSV returned an incomplete batch")
        for key, result in zip(chunk, results):
            if not isinstance(result, dict) or result.get("next_page_token"):
                raise IncompleteScan("OSV returned an invalid or paginated result")
            vulns = result.get("vulns", [])
            if not isinstance(vulns, list) or any(
                not isinstance(v, dict) or not isinstance(v.get("id"), str) or not v["id"] for v in vulns
            ):
                raise IncompleteScan("OSV returned invalid vulnerability identifiers")
            ids = [v["id"] for v in vulns]
            if ids:
                hits[key] = ids
    return hits


def severity(vid: str) -> str:
    try:
        with urllib.request.urlopen(OSV_VULN + vid, timeout=45) as fh:
            data = json.loads(fh.read())
    except Exception as exc:
        raise IncompleteScan(f"OSV advisory unavailable: {vid}") from exc
    if not isinstance(data, dict) or data.get("id") != vid:
        raise IncompleteScan(f"OSV advisory invalid: {vid}")
    metadata = data.get("database_specific")
    spec = metadata.get("severity") if isinstance(metadata, dict) else None
    if not isinstance(spec, str) or spec.upper() not in RANK or spec.upper() == "UNKNOWN":
        raise IncompleteScan(f"OSV advisory severity unavailable: {vid}")
    return spec.upper()


# Scratch copies and vendored trees are not deployable sources; comparing a live
# container against one produces confident nonsense.
IGNORED_TREES = {"node_modules", ".git", ".next", ".venv", "worktrees", "dist", "build"}


def repo_versions(root: Path, package: str) -> dict[str, tuple[str, str]]:
    """project path -> (pinned version, package.json name) for the redeploy target."""
    found: dict[str, tuple[str, str]] = {}
    for lock in root.rglob("package-lock.json"):
        if any(part in IGNORED_TREES for part in lock.parts):
            continue
        try:
            data = json.loads(lock.read_text())
        except Exception:
            continue
        meta = (data.get("packages") or {}).get(f"node_modules/{package}")
        if not (isinstance(meta, dict) and meta.get("version")):
            continue
        try:
            project_name = json.loads((lock.parent / "package.json").read_text()).get("name") or ""
        except Exception:
            project_name = ""
        found[str(lock.parent.relative_to(root))] = (meta["version"], project_name)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", action="append", required=True, help="repeatable")
    ap.add_argument("--key", help="ssh identity file")
    ap.add_argument("--package", action="append", default=[],
                    help="also report repo-vs-running drift for this package (repeatable)")
    ap.add_argument("--level", default="high", choices=["critical", "high", "moderate", "low"])
    ap.add_argument("--json", help="write the full report here")
    args = ap.parse_args()
    try:
        return audit(args)
    except IncompleteScan as exc:
        print(f"INCOMPLETE: {exc}", file=sys.stderr)
        if args.json:
            Path(args.json).write_text(json.dumps({"status": "incomplete", "error": str(exc)}, indent=2)+"\n")
        return 2


def audit(args) -> int:
    root = Path(__file__).resolve().parent.parent
    report: list[dict] = []
    running: dict[tuple[str, str], list[str]] = {}

    for host in args.host:
        names = containers(host, args.key)
        print(f"{host}: {len(names)} running containers", file=sys.stderr)
        for name in names:
            info = node_deps(host, args.key, name)
            deps = info.get("deps") or {}
            if not deps:
                continue
            print(f"  {name}: {len(deps)} direct deps", file=sys.stderr)
            report.append({"host": host, "container": name, "app": info.get("name"), "deps": deps})
            for pkg, ver in deps.items():
                running.setdefault((pkg, ver), []).append(f"{host}/{name}")

    if not report:
        raise IncompleteScan("No Node dependency inventory obtained; non-Node services require a separate probe")

    hits = osv_lookup(sorted(running))
    gate = RANK[args.level.upper()]
    blocking: list[dict] = []
    for (pkg, ver), ids in hits.items():
        worst = "UNKNOWN"
        for vid in ids:
            sev = severity(vid)
            if RANK[sev] > RANK[worst]:
                worst = sev
        if RANK[worst] >= gate:
            blocking.append({"package": pkg, "running": ver, "severity": worst,
                             "advisories": ids[:4], "where": running[(pkg, ver)]})
    blocking.sort(key=lambda f: -RANK[f["severity"]])

    print("\n=== running in production ===")
    for entry in report:
        print(f"  {entry['host']}/{entry['container']}  ({entry['app'] or '?'})  "
              f"{len(entry['deps'])} direct deps")

    if blocking:
        print(f"\n=== vulnerable AT OR ABOVE {args.level.upper()} ({len(blocking)}) ===")
        for f in blocking[:40]:
            print(f"  {f['severity']:<8} {f['package']}@{f['running']}   {', '.join(f['advisories'])}")
            print(f"           running on: {', '.join(f['where'])}")
    else:
        print(f"\nOK: nothing running is vulnerable at or above {args.level.upper()}.")

    # The whole point: name the packages where the fix is already committed, because
    # for those the remediation is not a patch, it is a rebuild.
    watch = set(args.package) | {f["package"] for f in blocking}
    # Which repo project built which container: match on the package.json name the
    # container reports. Without this the report compares a named app container
    # against every unrelated lockfile in the tree and calls each difference drift.
    app_of: dict[str, str] = {}
    for entry in report:
        if entry.get("app"):
            app_of[f"{entry['host']}/{entry['container']}"] = entry["app"]
    drift: list[dict] = []
    for pkg in sorted(watch):
        pinned = repo_versions(root, pkg)
        if not pinned:
            continue
        for (p, ver), where in running.items():
            if p != pkg:
                continue
            for place in where:
                app = app_of.get(place)
                for project, (repo_ver, project_name) in pinned.items():
                    if app and project_name and project_name != app:
                        continue
                    if repo_ver != ver:
                        drift.append({"package": pkg, "running": ver, "repo": repo_ver,
                                      "project": project, "where": [place]})
    if drift:
        print("\n=== SOURCE IS AHEAD OF PRODUCTION — redeploy closes these ===")
        for d in drift[:40]:
            print(f"  {d['package']}: running {d['running']}  ->  repo {d['repo']}  ({d['project']})")
            print(f"           on: {', '.join(d['where'])}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"status": "complete", "running": report, "vulnerable": blocking, "drift": drift}, indent=2))
        print(f"\nwrote {args.json}", file=sys.stderr)

    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
