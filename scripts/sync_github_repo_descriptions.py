#!/usr/bin/env python3
"""Sync GitHub repo descriptions from scripts/satellite-map.yaml."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

MAP_PATH = Path(__file__).resolve().parent / "satellite-map.yaml"


def _load_map() -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required: pip install pyyaml")
    return yaml.safe_load(MAP_PATH.read_text(encoding="utf-8")) or {}


def _token() -> str:
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""
    if token:
        return token
    try:
        import subprocess

        origin = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""
    m = re.search(r"https://[^:/]+:([^@]+)@", origin)
    return m.group(1) if m else ""


def _patch_repo_fields(
    org: str, repo: str, *, description: str, homepage: str, token: str
) -> tuple[bool, str]:
    url = f"https://api.github.com/repos/{org}/{repo}"
    body: dict[str, str] = {}
    if description.strip():
        body["description"] = description.strip()
    if homepage.strip():
        body["homepage"] = homepage.strip()
    if not body:
        return True, "skip (empty)"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload, method="PATCH")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 201):
                return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 404 and repo.endswith(".wiki"):
            return True, "skip (wiki repo — description not supported via API)"
        return False, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return False, str(e)
    return True, "ok"


def _patch_description(org: str, repo: str, description: str, token: str) -> tuple[bool, str]:
    return _patch_repo_fields(org, repo, description=description, homepage="", token=token)


def main() -> int:
    only = sys.argv[1:] if len(sys.argv) > 1 else []
    data = _load_map()
    org = os.environ.get("SATELLITE_GITHUB_ORG") or data.get("org") or "alexar76"
    token = _token()
    if not token:
        print("error: set GH_PAT or GITHUB_TOKEN (or git origin with token)", file=sys.stderr)
        return 2

    errors = 0
    for sat in data.get("satellites") or []:
        sat_id = sat.get("id") or ""
        if only and sat_id not in only:
            continue
        repo = sat.get("repo") or sat_id
        desc = (sat.get("description") or "").strip()
        homepage = (sat.get("homepage") or "").strip()
        if sat_id == "profile" or repo == org:
            print(f"  skip {sat_id}: profile repo (no description API)")
            continue
        if not desc and not homepage:
            print(f"  skip {sat_id}: no description/homepage in satellite-map.yaml")
            continue
        ok, msg = _patch_repo_fields(org, repo, description=desc, homepage=homepage, token=token)
        if ok:
            suffix = f" ({msg})" if msg != "ok" else ""
            print(f"  ✓ {org}/{repo}{suffix}")
        else:
            print(f"  ✗ {org}/{repo}: {msg}", file=sys.stderr)
            errors += 1

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
