#!/usr/bin/env python3
"""
Poll Admin pipeline until a product reaches a target state (e.g. COMPLETED).

Env or CLI:
  --base URL       API base (default http://127.0.0.1:9081 or DEMO_BASE_URL)
  --token JWT      Bearer token (or ADMIN_TOKEN)
  --product-id ID
  --wait-state S   comma-separated acceptable states (default COMPLETED,DEPLOYED_PRODUCTION)
  --interval SEC   default 15
  --timeout SEC    default 7200

Also reads TOKEN from env if --token omitted (after you export from demo.sh).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request


def _get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default=os.environ.get("DEMO_BASE_URL") or "http://127.0.0.1:9080",
    )
    ap.add_argument("--token", default=os.environ.get("ADMIN_TOKEN") or os.environ.get("TOKEN") or "")
    ap.add_argument("--product-id", required=True)
    ap.add_argument("--wait-state", default="COMPLETED,DEPLOYED_PRODUCTION")
    ap.add_argument("--interval", type=float, default=15.0)
    ap.add_argument("--timeout", type=float, default=7200.0)
    args = ap.parse_args()

    token = str(args.token).strip()
    if not token:
        print("Missing JWT: pass --token or set ADMIN_TOKEN", file=sys.stderr)
        return 2

    base = str(args.base).rstrip("/")
    pid = args.product_id.strip()
    ok_states = {s.strip().upper() for s in args.wait_state.split(",") if s.strip()}
    deadline = time.time() + float(args.timeout)

    while time.time() < deadline:
        data = _get_json(f"{base}/api/admin/pipeline/products?limit=500&offset=0", token)
        products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            print("Unexpected pipeline response", file=sys.stderr)
            return 3
        for row in products:
            if str(row.get("id")) != pid:
                continue
            st = str(row.get("state") or "").upper()
            print(f"[wait_pipeline_product] {pid} state={st}", flush=True)
            if st in ok_states:
                print(f"OK reached state {st}")
                return 0
            if st == "FAILED":
                print(f"FAILED: {row.get('failure_reason') or row.get('last_error')}", file=sys.stderr)
                return 1
        time.sleep(float(args.interval))

    print("Timeout waiting for pipeline", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
