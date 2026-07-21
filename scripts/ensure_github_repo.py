#!/usr/bin/env python3
"""Create a GitHub repo under the org/user if it does not exist yet."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def _token() -> str:
    return os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""


def _request(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload: dict[str, Any] | str = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = raw[:300]
        return e.code, payload


def ensure_repo(org: str, repo: str, *, description: str = "", private: bool = False) -> tuple[bool, str]:
    token = _token()
    if not token:
        return False, "missing GH_PAT or GITHUB_TOKEN"

    status, _ = _request("GET", f"https://api.github.com/repos/{org}/{repo}", token)
    if status == 200:
        return True, "exists"
    if status != 404:
        return False, f"GET repos/{org}/{repo} HTTP {status}"

    body: dict[str, Any] = {
        "name": repo,
        "private": private,
        "auto_init": False,
        "has_issues": True,
        "has_projects": False,
        "has_wiki": False,
    }
    if description.strip():
        body["description"] = description.strip()

    # User-owned org repos: POST /orgs/{org}/repos; personal account: POST /user/repos
    for url in (f"https://api.github.com/orgs/{org}/repos", "https://api.github.com/user/repos"):
        status, payload = _request("POST", url, token, body)
        if status in (201, 202):
            return True, "created"
        if status == 422 and isinstance(payload, dict):
            errors = payload.get("errors") or []
            if any(e.get("message") == "name already exists on this account" for e in errors if isinstance(e, dict)):
                return True, "exists"
        if status not in (404, 403):
            msg = payload.get("message") if isinstance(payload, dict) else str(payload)
            return False, f"POST {url} HTTP {status}: {msg}"

    return False, "could not create repo (check token org scope)"


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) < 2:
        print("usage: ensure_github_repo.py ORG REPO [description]", file=sys.stderr)
        return 2
    org, repo = argv[0], argv[1]
    desc = argv[2] if len(argv) > 2 else ""
    ok, msg = ensure_repo(org, repo, description=desc)
    if ok:
        print(f"  ✓ {org}/{repo} ({msg})")
        return 0
    print(f"  ✗ {org}/{repo}: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
