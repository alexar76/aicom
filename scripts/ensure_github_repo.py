#!/usr/bin/env python3
"""Create a GitHub repo under the org/user if it does not exist yet."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


# GitHub refuses a repository description over 350 characters with a bare
# "Repository creation failed." (HTTP 422) — HISTOR's first publish hit exactly that.
GITHUB_DESCRIPTION_MAX = 350


def clamp_description(text: str, limit: int = GITHUB_DESCRIPTION_MAX) -> str:
    """The description GitHub will accept: whole words, an ellipsis when cut."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return cut + "…"


def error_detail(payload: dict[str, Any] | str) -> str:
    """GitHub's message plus the per-field errors it puts beside it (the part that says why)."""
    if not isinstance(payload, dict):
        return str(payload)[:300]
    parts = [str(payload.get("message") or "")]
    for err in payload.get("errors") or []:
        if isinstance(err, dict):
            parts.append(str(err.get("message") or f"{err.get('field')}: {err.get('code')}"))
        else:
            parts.append(str(err))
    return " — ".join(p for p in parts if p)[:400]


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


def _token_kind(token: str) -> str:
    """Classic tokens list their scopes in X-OAuth-Scopes; fine-grained ones send no such header."""
    req = urllib.request.Request("https://api.github.com/user", method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            scopes = resp.headers.get("X-OAuth-Scopes")
            login = json.loads(resp.read().decode() or "{}").get("login", "?")
    except Exception:  # noqa: BLE001 - a hint, never a failure of its own
        return "token type unknown"
    if scopes is None:
        return f"fine-grained token of {login}"
    return f"classic token of {login}, scopes: {scopes or 'none'}"


def _no_reason_hint(org: str, repo: str, token: str) -> str:
    # A 422 with no per-field errors is what GitHub answers when the token may push to existing
    # repositories but not create one — a fine-grained token limited to selected repositories.
    return (
        f"GitHub gave no reason ({_token_kind(token)}). That usually means this token cannot create "
        f"repositories. Create {org}/{repo} by hand at https://github.com/new (public, empty: no README, "
        f"license or .gitignore) and rerun; a fine-grained token must also cover the new repository "
        f"(Repository access: All repositories, or add {repo}) with Contents and Administration: Read and write."
    )


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
        body["description"] = clamp_description(description)

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
            detail = error_detail(payload)
            if status == 422 and isinstance(payload, dict) and not payload.get("errors"):
                detail += " — " + _no_reason_hint(org, repo, token)
            return False, f"POST {url} HTTP {status}: {detail}"

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
