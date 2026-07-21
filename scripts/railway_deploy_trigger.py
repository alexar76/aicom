#!/usr/bin/env python3
"""
Trigger a Railway redeploy via the public GraphQL API (same as the dashboard).

Requires:
  - RAILWAY_TOKEN — account or workspace token (Bearer)
  - RAILWAY_SERVICE_ID — service UUID (Ctrl+K → Copy in Railway)
  - RAILWAY_ENVIRONMENT_ID — environment UUID (production/staging id, not the display name)

Optional:
  - Path to JSON from factory: data/state/<product_id>/railway_deploy.json
    (still needs RAILWAY_ENVIRONMENT_ID env — project JSON stores names, not GraphQL ids)

Usage:
  RAILWAY_TOKEN=... RAILWAY_SERVICE_ID=... RAILWAY_ENVIRONMENT_ID=... \\
    python scripts/railway_deploy_trigger.py

  python scripts/railway_deploy_trigger.py --product-id prod-xxxxxxxxxxxx

Exit 0 on GraphQL success (no top-level errors).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPHQL_URL = os.environ.get("RAILWAY_GRAPHQL_URL", "https://backboard.railway.com/graphql/v2")

MUTATION = """
mutation ServiceInstanceRedeploy($environmentId: String!, $serviceId: String!) {
  serviceInstanceRedeploy(environmentId: $environmentId, serviceId: $serviceId)
}
"""


def _post_graphql(token: str, query: str, variables: dict, project_access_token: str | None) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if project_access_token:
        headers["Project-Access-Token"] = project_access_token
    else:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Railway serviceInstanceRedeploy")
    ap.add_argument("--product-id", help="Read metadata from data/state/<id>/railway_deploy.json")
    args = ap.parse_args()

    token = (os.environ.get("RAILWAY_TOKEN") or "").strip()
    project_access = (os.environ.get("RAILWAY_PROJECT_ACCESS_TOKEN") or "").strip() or None
    service_id = (os.environ.get("RAILWAY_SERVICE_ID") or "").strip()
    environment_id = (os.environ.get("RAILWAY_ENVIRONMENT_ID") or "").strip()

    if args.product_id:
        js = REPO_ROOT / "data" / "state" / args.product_id / "railway_deploy.json"
        if js.is_file():
            meta = json.loads(js.read_text(encoding="utf-8"))
            sid = str(meta.get("railway_service_id") or "").strip()
            if sid:
                service_id = sid or service_id
            # Optional future: persist env UUID in JSON from admin settings
            eid = str(meta.get("railway_environment_id") or "").strip()
            if eid:
                environment_id = eid or environment_id

    if not token and not project_access:
        print("Set RAILWAY_TOKEN (Bearer) or RAILWAY_PROJECT_ACCESS_TOKEN", file=sys.stderr)
        return 2
    if not service_id:
        print("Set RAILWAY_SERVICE_ID or railway_service_id in railway_deploy.json", file=sys.stderr)
        return 2
    if not environment_id:
        print(
            "Set RAILWAY_ENVIRONMENT_ID (UUID from Railway dashboard / GraphQL — not the display name)",
            file=sys.stderr,
        )
        return 2

    try:
        data = _post_graphql(
            token,
            MUTATION,
            {"environmentId": environment_id, "serviceId": service_id},
            project_access,
        )
    except urllib.error.HTTPError as e:
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1

    if data.get("errors"):
        print(json.dumps(data["errors"], indent=2), file=sys.stderr)
        return 1

    print(json.dumps(data.get("data"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
