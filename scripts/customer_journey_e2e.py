#!/usr/bin/env python3
"""
Smoke-test customer HTTP journey against a running backend (CI preview/staging).

  BASE_URL=http://127.0.0.1:9080 python scripts/customer_journey_e2e.py

Requires no auth besides generated customer credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from uuid import uuid4


def _post(base: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    url = base.rstrip("/") + path
    data = None
    h = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": raw[:500]}
        return int(e.code), payload


def _get(base: str, path: str, headers: dict | None = None) -> tuple[int, dict]:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, json.loads(raw) if raw else {}


def _patch(base: str, path: str, body: dict, headers: dict | None = None) -> tuple[int, dict]:
    url = base.rstrip("/") + path
    data = json.dumps(body).encode("utf-8")
    h = dict(headers or {})
    h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": raw[:500]}
        return int(e.code), payload


def _delete(base: str, path: str, headers: dict | None = None) -> tuple[int, dict]:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers=dict(headers or {}), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": raw[:500]}
        return int(e.code), payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Customer journey E2E (register → login → CRUD → logout)")
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:9080"))
    args = ap.parse_args()
    base = args.base_url

    suffix = uuid4().hex[:10]
    email = f"journey-{suffix}@e2e.invalid"
    password = "password123"

    code, reg = _post(base, "/api/customer/register", {"email": email, "password": password})
    if code != 200:
        print("register failed", code, reg, file=sys.stderr)
        return 1
    token = reg.get("access_token")
    if not token:
        print("no access_token", reg, file=sys.stderr)
        return 1

    code, logged = _post(base, "/api/customer/login", {"email": email, "password": password})
    if code != 200:
        print("login failed", code, logged, file=sys.stderr)
        return 1

    h = {"Authorization": f"Bearer {token}"}
    code, me = _get(base, "/api/customer/me", h)
    if code != 200 or me.get("email") != email:
        print("me failed", code, me, file=sys.stderr)
        return 1

    code, created = _post(base, "/api/customer/demo-notes", {"title": "E2E", "body": "note"}, h)
    if code != 200:
        print("create note failed", code, created, file=sys.stderr)
        return 1
    note_id = created.get("note", {}).get("id")
    if not note_id:
        print("missing note id", created, file=sys.stderr)
        return 1

    code, listed = _get(base, "/api/customer/demo-notes", h)
    if code != 200 or listed.get("count", 0) < 1:
        print("list failed", code, listed, file=sys.stderr)
        return 1

    code, patched = _patch(
        base,
        f"/api/customer/demo-notes/{note_id}",
        {"title": "E2E-updated", "body": "patched"},
        h,
    )
    if code != 200:
        print("patch failed", code, patched, file=sys.stderr)
        return 1

    code, deleted = _delete(base, f"/api/customer/demo-notes/{note_id}", h)
    if code != 200:
        print("delete failed", code, deleted, file=sys.stderr)
        return 1

    code, empty = _get(base, "/api/customer/demo-notes", h)
    if code != 200 or empty.get("count") != 0:
        print("expected empty notes", code, empty, file=sys.stderr)
        return 1

    code, lo = _post(base, "/api/customer/logout")
    if code != 200 or not lo.get("ok"):
        print("logout failed", code, lo, file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "email": email}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
