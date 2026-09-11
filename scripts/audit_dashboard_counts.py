#!/usr/bin/env python3
"""Compare admin dashboard counts with public storefront truth (run inside app container or repo venv)."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")


def main() -> int:
    from web.backend.api.products import (
        _get_products_map,
        _public_storefront_grid_accepts,
        build_storefront_categories_response,
        count_showcase_listable_products,
        is_shipped_pipeline_product_state,
    )
    from web.backend.api.admin.dashboard.helpers import _fast_pipeline_metrics

    products = _get_products_map()
    eligible = [pid for pid, p in products.items() if _public_storefront_grid_accepts(pid, p)]
    shipped_sql = sum(
        1 for p in products.values() if is_shipped_pipeline_product_state(p.get("state"))
    )
    pipeline, _dist = _fast_pipeline_metrics()
    cats = build_storefront_categories_response()
    counted = count_showcase_listable_products()

    report = {
        "pipeline_total": len(products),
        "shipped_state_sql": shipped_sql,
        "storefront_eligible_scan": len(eligible),
        "categories_total_count": cats.get("total_count"),
        "count_showcase_fn": counted,
        "dashboard_sql_completed": pipeline.get("completed_products"),
        "dashboard_sql_total": pipeline.get("total_products"),
        "states": {},
    }
    for p in products.values():
        s = str(p.get("state") or "NONE").upper()
        report["states"][s] = report["states"].get(s, 0) + 1

    ok = (
        report["categories_total_count"] == report["storefront_eligible_scan"]
        and report["count_showcase_fn"] == report["storefront_eligible_scan"]
    )
    report["consistent"] = ok
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
