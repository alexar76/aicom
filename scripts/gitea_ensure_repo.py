#!/usr/bin/env python3
"""Ensure a Gitea repository exists (push-to-create is disabled on our hosts)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


def _git_credential(host: str) -> tuple[str, str]:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input=f"protocol=http\nhost={host}\n\n",
        capture_output=True,
        text=True,
        check=True,
    )
    cred: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            cred[k] = v
    user = cred.get("username", "")
    password = cred.get("password", "")
    if not user or not password:
        raise RuntimeError(f"no git credentials for host {host}")
    return user, password


def _auth_header(base: str) -> dict[str, str]:
    token = os.environ.get("GITEA_TOKEN", "").strip()
    if token:
        return {"Authorization": f"token {token}"}
    host = urllib.parse.urlsplit(base).netloc
    user, password = _git_credential(host)
    import base64

    basic = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {basic}"}


def _api(base: str, path: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, str]:
    url = f"{base.rstrip('/')}/api/v1{path}"
    data = None
    headers = {"Accept": "application/json", **_auth_header(base)}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def ensure_repo(base: str, owner: str, repo: str, *, private: bool = True) -> bool:
    code, _ = _api(base, f"/repos/{owner}/{repo}")
    if code == 200:
        return False
    if code != 404:
        raise RuntimeError(f"unexpected status {code} checking {owner}/{repo}")
    payload = {
        "name": repo,
        "private": private,
        "auto_init": False,
    }
    # Prefer org repo creation when targeting an org namespace.
    create_code, create_body = _api(base, f"/orgs/{owner}/repos", method="POST", body=payload)
    if create_code not in (201, 409, 404, 403):
        raise RuntimeError(f"failed to create {owner}/{repo}: HTTP {create_code}: {create_body[:300]}")
    if create_code in (201, 409):
        return True
    create_code, create_body = _api(base, "/user/repos", method="POST", body=payload)
    if create_code in (201, 409):
        return True
    raise RuntimeError(f"failed to create {owner}/{repo}: HTTP {create_code}: {create_body[:300]}")


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: gitea_ensure_repo.py <api_base> <owner> <repo>", file=sys.stderr)
        return 2
    base, owner, repo = sys.argv[1], sys.argv[2], sys.argv[3]
    created = ensure_repo(base, owner, repo)
    print(f"created={created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
