#!/usr/bin/env python3
"""Publish only the metadata consumed by Hub, never the Factory data directory.

Runs inside Factory (or with its data root configured). stdout is a JSON document
to atomically install as /var/lib/aicom/hub-catalog/state/pipeline.json on the host.
The Hub mounts only that export directory, read-only. Schedule refreshes on the host.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "aimarket-hub")]

PRODUCT_FIELDS = {"id", "name", "idea", "state", "category", "delivery_profile",
                  "capability_price_per_call_usd"}
CAP_FIELDS = {"id", "name", "description", "input_schema", "output_schema",
              "price_per_call_usd", "p50_latency_ms", "success_rate_30d", "agent",
              "prompt_template", "suggested_next"}


def public_products(products):
    out = {}
    for pid, product in products.items():
        row = {k: v for k, v in product.items() if k in PRODUCT_FIELDS and isinstance(v, (str, int, float, bool))}
        row["id"] = pid
        if isinstance(product.get("capabilities"), list):
            row["capabilities"] = [{k: v for k, v in cap.items() if k in CAP_FIELDS}
                                   for cap in product["capabilities"] if isinstance(cap, dict)]
        out[pid] = row
    return out


if __name__ == "__main__":
    from aimarket_hub.factory_products_loader import iter_shipped_factory_products
    print(json.dumps({"products": public_products(iter_shipped_factory_products())}, ensure_ascii=False))
