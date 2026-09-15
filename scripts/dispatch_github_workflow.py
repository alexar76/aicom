#!/usr/bin/env python3
"""Dispatch a GitHub Actions workflow on alexar76/* (uses GH_PAT / git remote token)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request


def _token() -> str:
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""
    if token:
        return token
    try:
        origin = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""
    m = re.search(r"https://[^:/]+:([^@]+)@", origin)
    return m.group(1) if m else ""


def dispatch(org: str, repo: str, workflow_file: str, ref: str = "main") -> tuple[bool, str]:
    token = _token()
    if not token:
        return False, "missing GH_PAT, GITHUB_TOKEN, or git remote token"
    url = f"https://api.github.com/repos/{org}/{repo}/actions/workflows/{workflow_file}/dispatches"
    body = json.dumps({"ref": ref}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:300]}"


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "usage: dispatch_github_workflow.py <repo> <workflow.yml> [ref]",
            file=sys.stderr,
        )
        return 2
    org = os.environ.get("SATELLITE_GITHUB_ORG", "alexar76")
    repo, wf = sys.argv[1], sys.argv[2]
    ref = sys.argv[3] if len(sys.argv) > 3 else "main"
    ok, msg = dispatch(org, repo, wf, ref)
    if ok:
        print(f"  ✓ {org}/{repo} → {wf} ({ref}) {msg}")
        return 0
    print(f"  ✗ {org}/{repo} → {wf}: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
