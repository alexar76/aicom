#!/usr/bin/env python3
"""Remove non-owner collaborators from a GitHub repo after satellite mirror push."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Never remove the repo owner or known human collaborators.
# Benjamin Ayivoh and other humans stay — only self-inserting AI/CI bots are pruned.
_KEEP_LOGIN = {
    "alexar76",
    "benjaminayivoh1",  # Benjamin Ayivoh — human co-author (aicom-coauthors.txt)
}


def _token() -> str:
    return os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or ""


def _request(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = raw[:300]
        return e.code, payload


def _blocked_login(login: str) -> bool:
    low = login.lower()
    if low in {x.lower() for x in _KEEP_LOGIN}:
        return False
    blocked_bits = (
        "bot",
        "dependabot",
        "github-actions",
        "cursor",
        "copilot",
        "claude",
        "anthropic",
        "openai",
        "composer",
        "devin",
        "swe-agent",
        "openhands",
    )
    return any(b in low for b in blocked_bits)


def prune_collaborators(org: str, repo: str, *, dry_run: bool = False) -> tuple[int, list[str]]:
    token = _token()
    if not token:
        return 1, ["missing GH_PAT or GITHUB_TOKEN"]

    removed: list[str] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({"per_page": 100, "page": page})
        status, payload = _request(
            "GET",
            f"https://api.github.com/repos/{org}/{repo}/collaborators?{qs}",
            token,
        )
        if status != 200 or not isinstance(payload, list):
            return 1, [f"list collaborators HTTP {status}: {payload}"]
        if not payload:
            break
        for collab in payload:
            login = str((collab or {}).get("login") or "")
            if not login or not _blocked_login(login):
                continue
            if dry_run:
                removed.append(f"would-remove:{login}")
                continue
            del_status, del_payload = _request(
                "DELETE",
                f"https://api.github.com/repos/{org}/{repo}/collaborators/{login}",
                token,
            )
            if del_status not in (204, 404):
                return 1, [f"DELETE {login} HTTP {del_status}: {del_payload}"]
            removed.append(login)
        if len(payload) < 100:
            break
        page += 1
    return 0, removed


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    dry_run = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    if len(args) < 2:
        print("usage: prune_github_collaborators.py ORG REPO [--dry-run]", file=sys.stderr)
        return 2
    code, notes = prune_collaborators(args[0], args[1], dry_run=dry_run)
    for note in notes:
        print(note)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
