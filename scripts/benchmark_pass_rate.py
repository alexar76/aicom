#!/usr/bin/env python3
"""
Benchmark pass-rate over 20-50 fresh product ideas.

Usage example:
  python scripts/benchmark_pass_rate.py --ideas-file ideas.txt --base-url http://127.0.0.1:8081 --count 20 --production-mode
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


def _load_ideas(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def _create_product(base_url: str, idea: str, production_mode: bool) -> str:
    r = requests.post(
        f"{base_url.rstrip('/')}/api/admin/products/create",
        json={"idea": idea, "production_mode": production_mode},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["product_id"]


def _fetch_products(base_url: str) -> dict[str, Any]:
    r = requests.get(f"{base_url.rstrip('/')}/api/admin/pipeline/products?limit=1000&offset=0", timeout=20)
    if r.status_code in (401, 403):
        raise PermissionError("admin_endpoint_unauthorized")
    r.raise_for_status()
    data = r.json()
    products = data.get("products") or []
    return {p.get("id"): p for p in products if isinstance(p, dict) and p.get("id")}


def _fetch_products_local_state() -> dict[str, Any]:
    """
    Fallback for local runs without admin token:
    read pipeline state directly from mounted data dir.
    """
    state_paths = [
        Path("/app/data/state/pipeline.json"),
        Path("data/state/pipeline.json"),
    ]
    for sp in state_paths:
        if not sp.exists():
            continue
        raw = json.loads(sp.read_text(encoding="utf-8"))
        products = raw.get("products") or {}
        if isinstance(products, dict):
            return {str(pid): pdata for pid, pdata in products.items() if isinstance(pdata, dict)}
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ideas-file", required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:8081")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--timeout-min", type=int, default=60)
    ap.add_argument("--production-mode", action="store_true")
    ap.add_argument("--output", default="benchmark_report.json")
    args = ap.parse_args()

    ideas = _load_ideas(Path(args.ideas_file))[: max(1, args.count)]
    if not ideas:
        raise SystemExit("No ideas provided.")

    product_ids: list[str] = []
    for idea in ideas:
        pid = _create_product(args.base_url, idea, args.production_mode)
        product_ids.append(pid)

    deadline = time.time() + (args.timeout_min * 60)
    terminal = {"COMPLETED", "FAILED", "DEPLOYED_PRODUCTION"}
    states: dict[str, str] = {}
    while time.time() < deadline:
        try:
            products = _fetch_products(args.base_url)
        except PermissionError:
            products = _fetch_products_local_state()
        for pid in product_ids:
            p = products.get(pid)
            if not p:
                continue
            st = str(p.get("state") or "")
            states[pid] = st
        if all(states.get(pid) in terminal for pid in product_ids):
            break
        time.sleep(10)

    completed = sum(1 for pid in product_ids if states.get(pid) in {"COMPLETED", "DEPLOYED_PRODUCTION"})
    failed = sum(1 for pid in product_ids if states.get(pid) == "FAILED")
    unresolved = len(product_ids) - completed - failed
    pass_rate = completed / max(1, len(product_ids))

    report = {
        "count": len(product_ids),
        "completed": completed,
        "failed": failed,
        "unresolved": unresolved,
        "pass_rate": round(pass_rate, 3),
        "production_mode": bool(args.production_mode),
        "products": [{"id": pid, "state": states.get(pid, "UNKNOWN")} for pid in product_ids],
        "generated_at": time.time(),
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
