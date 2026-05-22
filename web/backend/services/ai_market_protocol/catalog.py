"""Capability catalog derived from shipped pipeline products.

Products MAY declare capabilities explicitly in pipeline.json:

.. code-block:: json

    { "products": { "prod-xxx": { "state": "COMPLETED", "name": "...",
      "capabilities": [
        { "id": "translate.multi@v2", "name": "translate.multi", "version": "v2",
          "description": "...", "input_schema": {...}, "output_schema": {...},
          "price_per_call_usd": 0.40, "p50_latency_ms": 8100,
          "agent": "developer", "prompt_template": "Translate: {text}" }
      ]
    }}}

When a product does NOT declare capabilities the catalog synthesises a
reasonable set from the product name / idea (backward-compatible fallback).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from core.paths import pipeline_json_path

from web.backend.services.ai_market_protocol.config import pilot_tuple


def _read_pipeline_products() -> dict[str, Any]:
    p = pipeline_json_path()
    if not p.exists():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    products = j.get("products") if isinstance(j, dict) else {}
    return products if isinstance(products, dict) else {}


def list_shipped_products() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pid, p in _read_pipeline_products().items():
        state = str((p or {}).get("state") or "").upper()
        if state not in {"COMPLETED", "DEPLOYED_PRODUCTION"}:
            continue
        out.append({"id": pid, "raw": p or {}})
    return out


def parse_capability_ref(capability_id: str) -> tuple[str, str]:
    """Split ``translate@v2`` → (``translate``, ``v2``)."""
    if "@" in capability_id:
        name, ver = capability_id.rsplit("@", 1)
        return name.strip(), ver.strip() or "v1"
    return capability_id.strip(), "v1"


# ---------------------------------------------------------------------------
# Declared capabilities (read from product data)
# ---------------------------------------------------------------------------

def _normalise_declared_cap(product_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single declared capability dict to the internal format."""
    cap_name, ver = parse_capability_ref(str(raw.get("id") or raw.get("name") or "run"))
    inp = raw.get("input_schema") or {
        "type": "object",
        "properties": {"input": {"type": "string"}},
    }
    out_s = raw.get("output_schema") or {
        "type": "object",
        "properties": {"result": {"type": "string"}},
    }
    return {
        "capability_id": raw.get("id") or f"{cap_name}@{ver}",
        "product_id": product_id,
        "name": cap_name,
        "version": ver,
        "description": str(raw.get("description") or ""),
        "input_schema": inp,
        "output_schema": out_s,
        "price_per_call_usd": float(raw.get("price_per_call_usd", 0.35)),
        "p50_latency_ms": int(raw.get("p50_latency_ms", 3000)),
        "success_rate_30d": float(raw.get("success_rate_30d", 0.97)),
        "agent": str(raw.get("agent") or ""),
        "prompt_template": str(raw.get("prompt_template") or ""),
        "suggested_next": raw.get("suggested_next") or [],
    }


def _declared_capabilities(product_id: str, product: dict[str, Any]) -> list[dict[str, Any]]:
    """Return capabilities explicitly declared by the product, if any."""
    declared = product.get("capabilities")
    if not isinstance(declared, list) or len(declared) == 0:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in declared:
        if not isinstance(raw, dict):
            continue
        cap = _normalise_declared_cap(product_id, raw)
        cid = cap["capability_id"]
        if cid not in seen:
            seen.add(cid)
            out.append(cap)
    return out


# ---------------------------------------------------------------------------
# Schema synthesis (fallback)
# ---------------------------------------------------------------------------

def _schema_for(cap_name: str, product_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    text_field = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Primary input text"},
            "locale": {"type": "string", "description": "Target locale (ISO 639-1)"},
            "locales": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Target locales for multi-translate",
            },
        },
        "required": ["text"],
    }
    if cap_name.startswith("translate"):
        inp = text_field
        out = {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                }
            },
        }
    elif cap_name.startswith("legal"):
        inp = {
            "type": "object",
            "properties": {
                "documents": {"type": "object", "additionalProperties": {"type": "string"}},
                "jurisdiction": {"type": "string"},
            },
            "required": ["documents"],
        }
        out = {
            "type": "object",
            "properties": {
                "issues": {"type": "array", "items": {"type": "string"}},
                "risk_level": {"type": "string"},
            },
        }
    elif cap_name.startswith("summarize"):
        inp = text_field
        out = {"type": "object", "properties": {"summary": {"type": "string"}}}
    else:
        inp = {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "context": {"type": "object"},
            },
            "required": ["task"],
        }
        out = {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "product": {"type": "string", "const": product_name[:80]},
            },
        }
    return inp, out


def _synthesize_capabilities(pid: str, p: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate synthetic capabilities from product keywords (backward compat)."""
    name = str(p.get("name") or f"Product {pid[:8]}")
    idea = str(p.get("idea") or "")
    blob = f"{name} {idea}".lower()
    caps: list[dict[str, Any]] = []

    def add(cid: str, title: str, desc: str, base_usd: float, p50_ms: int, next_hints: list[str] | None = None):
        cap_name, ver = parse_capability_ref(cid)
        inp, out = _schema_for(cap_name, name)
        caps.append({
            "capability_id": cid,
            "product_id": pid,
            "name": cap_name,
            "version": ver,
            "description": desc,
            "input_schema": inp,
            "output_schema": out,
            "price_per_call_usd": base_usd,
            "p50_latency_ms": p50_ms,
            "success_rate_30d": 0.97,
            "agent": "",
            "prompt_template": "",
            "suggested_next": next_hints or [],
        })

    add("run@v1", "run", f"Execute primary workflow for {name}", 0.35, 4200, [f"{pid}/summarize@v1"])
    add("summarize@v1", "summarize", f"Summarize content produced by {name}", 0.25, 2800, [])

    if re.search(r"translat|localiz|i18n|language", blob):
        add("translate.multi@v2", "translate.multi", "Translate text to multiple locales in one call",
            0.40, 8100, [f"{pid}/legal.review_localized@v1"])
        add("legal.review_localized@v1", "legal.review_localized",
            "Review localized documents for compliance risks", 1.20, 11400, [])
    if re.search(r"legal|compliance|contract|regulat", blob) and not any(
        c["name"] == "legal.review_localized" for c in caps
    ):
        add("legal.review@v1", "legal.review", "Review documents for legal and compliance issues", 1.10, 10200, [])
    if re.search(r"fraud|risk|score|analyt", blob):
        add("score.risk@v1", "score.risk", "Score risk signals for the domain workflow", 0.55, 620, [])
    return caps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _capability_defs_for_product(pid: str, p: dict[str, Any]) -> list[dict[str, Any]]:
    """Declared capabilities first, synthesised fallback when none declared."""
    declared = _declared_capabilities(pid, p)
    if declared:
        return declared
    return _synthesize_capabilities(pid, p)


def list_capabilities() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in list_shipped_products():
        out.extend(_capability_defs_for_product(row["id"], row["raw"]))
    return out


def get_capability(product_id: str, capability_id: str) -> dict[str, Any] | None:
    for c in list_capabilities():
        if c["product_id"] == product_id and c["capability_id"] == capability_id:
            return c
    return None


def build_manifest(*, base_url: str) -> dict[str, Any]:
    caps = list_capabilities()
    tools: list[dict[str, Any]] = []
    for c in caps:
        tools.append({
            "name": f"{c['product_id']}.{c['name']}@{c['version']}",
            "description": c["description"],
            "input_schema": c["input_schema"],
            "output_schema": c["output_schema"],
            "price_per_call_usd": c["price_per_call_usd"],
            "p50_latency_ms": c["p50_latency_ms"],
            "success_rate_30d": c["success_rate_30d"],
            "product_id": c["product_id"],
            "capability_id": c["capability_id"],
        })
    manifest = {
        "protocol_version": "v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": base_url,
        "products_count": len(list_shipped_products()),
        "capabilities_count": len(caps),
        "tools": tools,
        "capabilities": caps,
    }
    from web.backend.services.ai_market_protocol.signing import manifest_signature

    manifest["signature"] = manifest_signature(manifest)
    return manifest
