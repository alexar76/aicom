#!/usr/bin/env python3
"""Enable GitHub Pages (GitHub Actions source) on a repo if not already configured."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _token() -> str:
    return os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""


def _request(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def ensure_pages(org: str, repo: str, *, build_type: str = "workflow") -> tuple[bool, str]:
    token = _token()
    if not token:
        return False, "missing GH_PAT or GITHUB_TOKEN"

    base = f"https://api.github.com/repos/{org}/{repo}/pages"
    status, raw = _request("GET", base, token)
    if status == 200:
        try:
            current = json.loads(raw)
        except json.JSONDecodeError:
            current = {}
        if current.get("build_type") == build_type:
            return True, "already enabled"
        patch_body: dict = {"build_type": build_type}
        if build_type == "legacy":
            patch_body["source"] = {"branch": "main", "path": "/"}
        status, raw = _request("PUT", base, token, patch_body)
        if status in (200, 204):
            return True, f"migrated to {build_type}"
        return False, f"PUT pages HTTP {status}: {raw[:200]}"
    if status != 404:
        return False, f"GET pages HTTP {status}"

    body: dict = {"build_type": build_type}
    if build_type == "legacy":
        body["source"] = {"branch": "main", "path": "/"}
    status, raw = _request("POST", base, token, body)
    if status == 201:
        return True, "enabled"
    return False, f"POST pages HTTP {status}: {raw[:200]}"


def dispatch_pages_workflow(org: str, repo: str, *, workflow_file: str = "pages.yml") -> tuple[bool, str]:
    token = _token()
    if not token:
        return False, "missing GH_PAT or GITHUB_TOKEN"
    url = f"https://api.github.com/repos/{org}/{repo}/actions/workflows/{workflow_file}/dispatches"
    status, raw = _request("POST", url, token, {"ref": "main"})
    if status == 204:
        return True, "workflow dispatched"
    return False, f"dispatch HTTP {status}: {raw[:200]}"


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) < 2:
        print("usage: ensure_github_pages.py ORG REPO [--legacy] [--dispatch-pages]", file=sys.stderr)
        return 2
    build_type = "legacy" if "--legacy" in argv else "workflow"
    dispatch = "--dispatch-pages" in argv
    args = [a for a in argv if not a.startswith("--")]
    ok, msg = ensure_pages(args[0], args[1], build_type=build_type)
    if not ok:
        print(f"ensure_github_pages: {msg}", file=sys.stderr)
        return 1
    print(f"ensure_github_pages: {args[0]}/{args[1]} — {msg}")
    if dispatch:
        ok2, msg2 = dispatch_pages_workflow(args[0], args[1])
        if not ok2:
            print(f"ensure_github_pages: dispatch failed — {msg2}", file=sys.stderr)
            return 1
        print(f"ensure_github_pages: {args[0]}/{args[1]} — {msg2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
