"""
Catalog hardening sweep
======================
One-shot remediation for legacy catalog items:
- enforce naming quality
- evaluate release contract
- auto-route non-compliant products back to developer rework
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from web.backend.services.product_naming import resolve_product_name
from web.backend.services.release_cockpit import evaluate_release_cockpit


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _read_spec_inner(data_root: str, product_id: str) -> dict[str, Any] | None:
    raw = _read_json(Path(data_root) / "specs" / product_id / "specification.json")
    spec = raw.get("specification")
    return spec if isinstance(spec, dict) else None


def _read_marketing_inner(data_root: str, product_id: str) -> dict[str, Any] | None:
    raw = _read_json(Path(data_root) / "state" / product_id / "marketing_content.json")
    m = raw.get("marketing")
    return m if isinstance(m, dict) else None


def _persist_name(data_root: str, product_id: str, name: str) -> tuple[bool, bool]:
    spec_path = Path(data_root) / "specs" / product_id / "specification.json"
    mkt_path = Path(data_root) / "state" / product_id / "marketing_content.json"

    spec_written = False
    mkt_written = False

    spec_raw = _read_json(spec_path)
    if isinstance(spec_raw, dict):
        spec = spec_raw.get("specification")
        if isinstance(spec, dict):
            spec["product_name"] = name
            spec_raw["specification"] = spec
            spec_written = _write_json(spec_path, spec_raw)

    mkt_raw = _read_json(mkt_path) if mkt_path.exists() else {"marketing": {}}
    if isinstance(mkt_raw, dict):
        marketing = mkt_raw.get("marketing")
        if not isinstance(marketing, dict):
            marketing = {}
        marketing["product_name"] = name
        mkt_raw["marketing"] = marketing
        mkt_written = _write_json(mkt_path, mkt_raw)

    return spec_written, mkt_written


def _active_dev_fixing(task_queue: list[dict[str, Any]], product_id: str) -> bool:
    return any(
        t.get("product_id") == product_id
        and t.get("agent_type") == "developer"
        and t.get("status") in ("pending", "running")
        and t.get("state") == "DEV_FIXING"
        for t in task_queue
    )


def harden_catalog_products(
    *,
    products: dict[str, Any],
    task_queue: list[dict[str, Any]],
    data_root: str = "/app/data",
    now: float | None = None,
) -> dict[str, Any]:
    now_ts = now or time.time()
    used_names: set[str] = set()
    results: list[dict[str, Any]] = []
    rerouted = 0

    for product_id, product in products.items():
        if not isinstance(product, dict):
            continue
        state = str(product.get("state") or "").upper()
        if state not in {"COMPLETED", "DEPLOYED_PRODUCTION"}:
            continue

        spec = _read_spec_inner(data_root, product_id)
        marketing = _read_marketing_inner(data_root, product_id)
        resolved_name, is_template = resolve_product_name(
            product_id=product_id,
            product=product,
            spec=spec,
            marketing=marketing,
            used_names=used_names,
            data_root=data_root,
        )
        spec_written, mkt_written = _persist_name(data_root, product_id, resolved_name)

        cockpit = evaluate_release_cockpit(product_id, data_root=data_root)
        go = cockpit.get("go_no_go") == "go"
        rerouted_now = False
        if not go and not _active_dev_fixing(task_queue, product_id):
            product["state"] = "BUG_FOUND"
            product["updated_at"] = now_ts
            task_queue.append(
                {
                    "id": f"task-{uuid.uuid4().hex[:12]}",
                    "product_id": product_id,
                    "agent_type": "developer",
                    "state": "DEV_FIXING",
                    "status": "pending",
                    "retry_count": 0,
                    "max_retries": 3,
                    "input_data": {
                        "product_id": product_id,
                        "idea": product.get("idea", ""),
                        "quality_gates_feedback": {
                            "passed": False,
                            "source": "catalog_hardening",
                            "reasons": cockpit.get("issues") or ["release_contract_failed"],
                            "release_cockpit": cockpit,
                        },
                        "qa_gate_blocked": True,
                        "quality_repair_round": int(product.get("quality_repair_round") or 0) + 1,
                        "quality_repair_max": 10,
                    },
                    "created_at": now_ts,
                    "priority": 4,
                    "auto_requeue_reason": "catalog_hardening_release_contract",
                }
            )
            rerouted_now = True
            rerouted += 1

        results.append(
            {
                "product_id": product_id,
                "name": resolved_name,
                "is_template": is_template,
                "spec_updated": spec_written,
                "marketing_updated": mkt_written,
                "release_go": go,
                "release_issues": cockpit.get("issues") or [],
                "rerouted_to_dev_fixing": rerouted_now,
            }
        )

    return {
        "status": "ok",
        "processed": len(results),
        "rerouted": rerouted,
        "products": results,
    }
