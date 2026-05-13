"""
Railway deploy hook after DevOps for ``full_software`` products.

Reads toggles from ``general.railway_*`` in ``/app/config.yaml`` (Admin → Settings).
Secrets **must** be supplied via ``RAILWAY_TOKEN`` in the environment — never YAML.

Factory records intent under ``data/state/<product_id>/railway_deploy.json`` so operators
can wire GitHub Actions / Railway Git deploy as a separate CI step; see
``docs/deploy-full-software-cloud.md``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from core.paths import config_path
from core.config_merge import load_merged_config
from core.paths import data_root, state_dir

logger = logging.getLogger(__name__)

CONFIG_PATH = config_path()


def railway_token_configured() -> bool:
    return bool((os.environ.get("RAILWAY_TOKEN") or "").strip())


def _read_general() -> dict[str, Any]:
    try:
        raw = load_merged_config(CONFIG_PATH)
        if not isinstance(raw, dict):
            return {}
        g = raw.get("general")
        return g if isinstance(g, dict) else {}
    except Exception as e:
        logger.debug("railway_deploy: could not read config: %s", e)
        return {}


def _spec_delivery_profile(product_id: str) -> str | None:
    p = data_root() / "specs" / product_id / "specification.json"
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict):
            raw = doc.get("delivery_profile")
            return str(raw).strip() if raw else None
    except Exception:
        return None
    return None


def try_railway_deploy_after_devops(product_id: str) -> dict[str, Any]:
    """Sync helper (call via asyncio.to_thread from pipeline worker)."""
    g = _read_general()
    if not bool(g.get("railway_deploy_enabled", False)):
        return {"skipped": True, "reason": "disabled"}

    if not railway_token_configured():
        logger.warning(
            "railway_deploy: enabled in settings but RAILWAY_TOKEN not set — skipping %s",
            product_id,
        )
        return {"skipped": True, "reason": "no_railway_token"}

    dp = _spec_delivery_profile(product_id)
    if dp != "full_software":
        return {"skipped": True, "reason": "not_full_software", "delivery_profile": dp}

    project_id = str(g.get("railway_project_id") or "").strip()
    environment = str(g.get("railway_environment") or "").strip()
    environment_id = str(g.get("railway_environment_id") or "").strip()
    service_id = str(g.get("railway_service_id") or "").strip()

    rec: dict[str, Any] = {
        "product_id": product_id,
        "railway_project_id": project_id,
        "railway_environment": environment,
        "railway_environment_id": environment_id,
        "railway_service_id": service_id,
        "requested_at": time.time(),
        "note": (
            "Wire GitHub → Railway or a CI job that calls Railway’s API; "
            "see docs/deploy-full-software-cloud.md."
        ),
    }

    out_dir = state_dir() / product_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "railway_deploy.json"
    out_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("railway_deploy: recorded for %s -> %s", product_id, out_path)

    return {"recorded": True, "path": str(out_path), "railway_project_id": project_id or None}
