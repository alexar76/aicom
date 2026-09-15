"""Persisted iteration canvas graph (nodes/edges) per product — lightweight Miro-style board."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.paths import data_root as factory_data_root

logger = logging.getLogger(__name__)

DEFAULT_CANVAS: dict[str, Any] = {
    "version": 1,
    "nodes": [],
    "edges": [],
}


def canvas_path(product_id: str) -> Path:
    safe = "".join(c for c in product_id if c.isalnum() or c in "-_")[:80] or "unknown"
    p = factory_data_root() / "state" / safe / "iteration_canvas.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_canvas(product_id: str) -> dict[str, Any]:
    path = canvas_path(product_id)
    if not path.is_file():
        return dict(DEFAULT_CANVAS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("nodes"), list) and isinstance(raw.get("edges"), list):
            return raw
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("iteration_canvas read %s: %s", product_id, e)
    return dict(DEFAULT_CANVAS)


def put_canvas(product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("nodes and edges must be arrays")
    if len(nodes) > 200 or len(edges) > 400:
        raise ValueError("canvas too large")
    doc = {"version": int(payload.get("version") or 1), "nodes": nodes, "edges": edges}
    path = canvas_path(product_id)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc
