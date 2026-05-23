"""Load shipped factory products from SQLite (primary) and pipeline.json (fallback)."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SHIPPED = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION"})


def _data_root() -> Path:
    env = os.environ.get("AIFACTORY_DATA_ROOT", "").strip()
    if env:
        return Path(env)
    try:
        from core.paths import data_root

        return data_root()
    except ImportError:
        return Path("data")


def _pipeline_db_path() -> Path:
    env = os.environ.get("SQLITE_PATH", "").strip()
    if env:
        return Path(env)
    return _data_root() / "state" / "pipeline.db"


def _enrich_product(pid: str, row: dict[str, Any]) -> dict[str, Any]:
    """Attach name / delivery_profile from on-disk marketing + spec when present."""
    root = _data_root()
    product = dict(row)
    product.setdefault("id", pid)

    mpath = root / "state" / pid / "marketing_content.json"
    if mpath.is_file():
        try:
            doc = json.loads(mpath.read_text(encoding="utf-8"))
            m = doc.get("marketing") if isinstance(doc, dict) else {}
            if isinstance(m, dict):
                if m.get("product_name"):
                    product["name"] = m["product_name"]
                if m.get("category") and not product.get("category"):
                    product["category"] = m["category"]
        except (json.JSONDecodeError, OSError):
            pass

    spath = root / "specs" / pid / "specification.json"
    if spath.is_file():
        try:
            doc = json.loads(spath.read_text(encoding="utf-8"))
            spec = doc.get("specification") if isinstance(doc, dict) else doc
            if isinstance(spec, dict):
                if spec.get("product_name") and not product.get("name"):
                    product["name"] = spec["product_name"]
                if spec.get("delivery_profile"):
                    product["delivery_profile"] = spec["delivery_profile"]
        except (json.JSONDecodeError, OSError):
            pass

    return product


def _read_products_from_sqlite() -> dict[str, dict[str, Any]]:
    db = _pipeline_db_path()
    if not db.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    try:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT id, idea, state, category, spec, tags, error, created_at, updated_at "
                "FROM products"
            ).fetchall()
            for row in rows:
                pid = str(row["id"] or "")
                if not pid:
                    continue
                base = {
                    "id": pid,
                    "idea": row["idea"],
                    "state": row["state"],
                    "category": row["category"],
                    "error": row["error"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                if row["spec"]:
                    try:
                        base["spec"] = json.loads(row["spec"])
                    except json.JSONDecodeError:
                        base["spec"] = row["spec"]
                if row["tags"]:
                    try:
                        base["tags"] = json.loads(row["tags"])
                    except json.JSONDecodeError:
                        base["tags"] = row["tags"]
                out[pid] = _enrich_product(pid, base)
        finally:
            con.close()
    except sqlite3.Error as exc:
        logger.debug("SQLite products read failed: %s", exc)
    return out


def _read_products_from_sql_store() -> dict[str, dict[str, Any]]:
    """Read products via stdlib sqlite (no orchestrator / prometheus import chain)."""
    return _read_products_from_sqlite()


def iter_shipped_factory_products(
    pipeline_json_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Merge SQL store with pipeline.json; return COMPLETED/DEPLOYED products only."""
    products = _read_products_from_sql_store()

    path: Path | None
    if pipeline_json_path:
        path = Path(pipeline_json_path)
    else:
        try:
            from core.paths import pipeline_json_path as _factory_pipeline_path

            path = _factory_pipeline_path()
        except ImportError:
            path = _data_root() / "state" / "pipeline.json"

    if path and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("products") if isinstance(data, dict) else {}
            if isinstance(raw, dict):
                for pid, pdata in raw.items():
                    if pid not in products and isinstance(pdata, dict):
                        products[pid] = _enrich_product(pid, pdata)
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("pipeline.json read skipped: %s", exc)

    return {
        pid: pdata
        for pid, pdata in products.items()
        if str((pdata or {}).get("state") or "").upper() in _SHIPPED
    }


def get_factory_product(
    product_id: str,
    pipeline_json_path: str | Path | None = None,
) -> dict[str, Any] | None:
    return iter_shipped_factory_products(pipeline_json_path).get(product_id)
