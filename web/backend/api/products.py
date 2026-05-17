"""
Products API
============
Endpoints for the storefront product listing and details.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from core.logging_utils import log_suppressed
from core.paths import (
    arch_dir,
    code_dir,
    data_root,
    pipeline_db_path,
    pipeline_json_path,
    product_state_dir,
    specs_dir,
    state_dir,
    telemetry_dir,
)
from web.backend.schemas.products import ProductListQuery
from web.backend.services.demo_quality import assess_product_demo
from web.backend.services.marketplace_quality import (
    evaluate_marketplace_quality,
    marketplace_listing_card_fields,
)
from web.backend.services.product_followup import public_storefront_blocked
from web.backend.services.product_naming import resolve_product_name
from web.backend.services.storefront_visibility import is_mid_repair_storefront_visible
from web.backend.services.product_brief import build_stakeholder_brief
from web.backend.services.storefront_pricing import (
    DEFAULT_STOREFRONT_PRICE_USDT,
    resolve_storefront_price_usdt,
)
from marketplace_taxonomy import MARKETPLACE_CATEGORY_IDS, canonical_marketplace_category

logger = logging.getLogger(__name__)

# Storefront-only: marketing landings tab (not a Director / LLM vertical topic).
LANDINGS_LISTING_SLUG = "landings"
LISTING_CATEGORY_IDS = tuple(MARKETPLACE_CATEGORY_IDS) + (LANDINGS_LISTING_SLUG,)


def _use_sqlite_pipeline() -> bool:
    from core.pipeline_database import pipeline_uses_sql_store

    return pipeline_uses_sql_store()


def _sql_store_available() -> bool:
    from core.pipeline_database import pipeline_database_url, pipeline_db_backend

    if pipeline_db_backend() == "postgres":
        return bool(pipeline_database_url())
    return _sqlite_db_path().exists()


def _sqlite_db_path() -> Path:
    return pipeline_db_path()


def _sqlite_product_to_json_shape(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize SQLite row dict to the same shape as pipeline.json product entries."""
    meta = dict(raw.get("metadata") or {})
    pid = raw["id"]
    return {
        "id": pid,
        "idea": raw.get("idea", ""),
        "state": raw.get("state", ""),
        "created_at": raw.get("created_at", 0),
        "updated_at": raw.get("updated_at", 0),
        "spec": meta.get("spec"),
        "architecture": meta.get("architecture"),
        "category": meta.get("category"),
        "tags": meta.get("tags"),
        "tasks": [],
    }


def _get_products_map() -> dict[str, dict[str, Any]]:
    """Storefront product map: SQLite when USE_SQLITE=true, else pipeline.json."""
    if _use_sqlite_pipeline() and _sql_store_available():
        try:
            from core.pipeline_database import create_sync_pipeline_manager

            sm = create_sync_pipeline_manager()
            out: dict[str, dict[str, Any]] = {}
            for row in sm.get_all_products():
                shaped = _sqlite_product_to_json_shape(row)
                out[shaped["id"]] = shaped
            sm.close()
            return out
        except Exception as e:
            logger.warning("SQLite storefront load failed, falling back to JSON: %s", e)

    data = _load_pipeline_data()
    return dict(data.get("products", {}))


def _get_product_entry(product_id: str) -> Optional[dict[str, Any]]:
    if _use_sqlite_pipeline() and _sql_store_available():
        try:
            from core.pipeline_database import create_sync_pipeline_manager

            sm = create_sync_pipeline_manager()
            row = sm.get_product(product_id)
            sm.close()
            if row:
                return _sqlite_product_to_json_shape(row)
        except Exception as e:
            logger.warning("SQLite get_product failed: %s", e)

    data = _load_pipeline_data()
    return data.get("products", {}).get(product_id)

router = APIRouter(prefix="/api/products", tags=["products"])

# Category taxonomy (landings first — separate shelf from vertical “programs”)
CATEGORIES = [
    {
        "id": LANDINGS_LISTING_SLUG,
        "name": "Landing pages",
        "icon": "layout",
        "description": "Marketing landings and promo sites only",
    },
    {"id": "ai_ml", "name": "AI/ML", "icon": "brain", "description": "AI/ML tools, chatbots, prediction engines"},
    {"id": "devtools", "name": "DevTools", "icon": "code", "description": "Developer tools, CI/CD, code analysis"},
    {"id": "fintech", "name": "FinTech", "icon": "wallet", "description": "Finance, crypto, payments"},
    {"id": "saas", "name": "SaaS", "icon": "cloud", "description": "General SaaS platforms"},
    {"id": "ecommerce", "name": "E-Commerce", "icon": "shopping-cart", "description": "Online stores, marketplaces"},
    {"id": "iot", "name": "IoT", "icon": "cpu", "description": "IoT, embedded systems"},
    {"id": "security", "name": "Security", "icon": "shield", "description": "Security tools, scanners"},
    {"id": "productivity", "name": "Productivity", "icon": "zap", "description": "Productivity apps, collaboration"},
]

CATEGORY_IDS = list(MARKETPLACE_CATEGORY_IDS)


def _is_marketing_landing_listing(product: dict[str, Any], spec_inner: Optional[dict[str, Any]]) -> bool:
    return _resolved_delivery_profile(product, spec_inner) == "marketing_landing"


def _canonical_marketplace_category(marketing: dict, product: dict) -> str:
    """Map marketing / pipeline category to a CATEGORY_IDS slug or ``uncategorized``.

    Listing and tab counts use the same rules so storefront numbers stay consistent.
    Pipeline ``product["category"]`` wins over marketing LLM ``category`` when the latter is noise.
    """
    return canonical_marketplace_category(marketing, product)


def _load_pipeline_data() -> dict:
    """Load pipeline.json data."""
    pipeline_file = pipeline_json_path()
    if pipeline_file.exists():
        try:
            with open(pipeline_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"products": {}}


def _get_product_name(pid: str) -> str:
    """Get product name from spec file."""
    name = ""
    spec_path = specs_dir(pid) / "specification.json"
    if spec_path.exists():
        try:
            with open(spec_path, "r") as f:
                spec_data = json.load(f)
            spec = spec_data.get("specification", {})
            name = str(spec.get("product_name", "")).strip()
        except Exception:
            log_suppressed(logger, "resolve_product_name marketing read failed for %s", pid)
    return name or f"Product {pid[:8]}"


def _load_specification_from_disk(pid: str) -> Optional[dict]:
    """Return inner `specification` object from specs file (PM output)."""
    spec_path = specs_dir(pid) / "specification.json"
    if not spec_path.exists():
        return None
    try:
        with open(spec_path, "r") as f:
            spec_data = json.load(f)
        return spec_data.get("specification") or None
    except Exception:
        return None


def _spec_inner_for_storefront(pid: str, product: dict[str, Any]) -> Optional[dict[str, Any]]:
    """PM inner specification dict — prefer disk artifact; else SQLite ``spec`` / embedded ``specification``."""
    inner = _load_specification_from_disk(pid)
    if isinstance(inner, dict) and inner:
        return inner
    raw = product.get("spec")
    if raw is None:
        meta = product.get("metadata")
        if isinstance(meta, dict):
            raw = meta.get("spec")
    if not isinstance(raw, dict):
        return None
    nested = raw.get("specification")
    if isinstance(nested, dict) and nested:
        return nested
    return raw


def _resolved_delivery_profile(product: dict[str, Any], spec_inner: Optional[dict[str, Any]]) -> Optional[str]:
    """Explicit delivery_profile only — do not guess full_software for legacy rows missing metadata."""
    from agents.product_profile import normalize_delivery_profile

    raw = None
    if isinstance(spec_inner, dict) and spec_inner.get("delivery_profile"):
        raw = spec_inner.get("delivery_profile")
    elif product.get("delivery_profile"):
        raw = product.get("delivery_profile")
    elif isinstance(product.get("metadata"), dict) and product["metadata"].get("delivery_profile"):
        raw = product["metadata"].get("delivery_profile")
    if raw is None:
        return None
    return normalize_delivery_profile(str(raw))


def _storefront_stack_label(tech_stack: dict[str, Any]) -> str:
    if not isinstance(tech_stack, dict):
        return ""
    parts: list[str] = []
    for key in ("frontend", "backend", "database"):
        v = tech_stack.get(key)
        if isinstance(v, str):
            s = v.strip()
            if s and s.lower() not in ("none", "n/a", "static hosting only", ""):
                parts.append(s)
    label = " · ".join(parts[:4])
    return label[:140] if label else ""


def _load_architecture_from_disk(pid: str) -> Optional[dict]:
    """Return inner `architecture` object from architect output file."""
    arch_path = arch_dir(pid) / "architecture.json"
    if not arch_path.exists():
        return None
    try:
        with open(arch_path, "r") as f:
            data = json.load(f)
        return data.get("architecture") or None
    except Exception:
        return None


def _load_marketing(pid: str) -> dict:
    """Load marketing content for a product."""
    mkt_file = product_state_dir(pid) / "marketing_content.json"
    if mkt_file.exists():
        try:
            with open(mkt_file, "r") as f:
                return json.load(f).get("marketing", {})
        except Exception:
            log_suppressed(logger, "load marketing failed for %s", pid)
    return {}


def _load_sales(pid: str) -> dict:
    """Load sales config for a product."""
    sales_file = product_state_dir(pid) / "sales_config.json"
    if sales_file.exists():
        try:
            with open(sales_file, "r") as f:
                return json.load(f).get("sales_data", {})
        except Exception:
            log_suppressed(logger, "load marketing failed for %s", pid)
    return {}


def build_storefront_categories_response() -> dict[str, Any]:
    """Build ``GET /api/products/categories`` JSON — single pass used by storefront + admin counts cache."""
    products = _get_products_map()

    category_counts: dict[str, int] = {}
    landings_count = 0
    for pid, product in products.items():
        if not _public_storefront_grid_accepts(pid, product):
            continue

        spec_inner = _spec_inner_for_storefront(pid, product)
        if _is_marketing_landing_listing(product, spec_inner):
            landings_count += 1
            continue

        marketing = _load_marketing(pid)
        category = _canonical_marketplace_category(marketing, product)
        category_counts[category] = category_counts.get(category, 0) + 1

    result = []
    for cat in CATEGORIES:
        cat_id = cat["id"]
        if cat_id == LANDINGS_LISTING_SLUG:
            count = landings_count
        else:
            count = category_counts.get(cat_id, 0)
        result.append({
            "id": cat_id,
            "name": cat["name"],
            "icon": cat["icon"],
            "description": cat["description"],
            "product_count": count,
        })

    uncategorized = category_counts.get("uncategorized", 0)
    if uncategorized > 0:
        result.append({
            "id": "uncategorized",
            "name": "Other",
            "icon": "folder",
            "description": "Uncategorized products",
            "product_count": uncategorized,
        })

    total_visible = landings_count + sum(category_counts.values())
    return {"categories": result, "total_count": total_visible}


@router.get("/categories")
async def list_categories():
    """List all product categories with counts — only counting products that are
    actually visible on the storefront (shipped, or mid-repair with prior listing; see ``_public_storefront_grid_accepts``).

    This must stay in sync with the filters in list_products().
    """
    from web.backend.services.storefront_counts_cache import get_storefront_categories_cached

    return get_storefront_categories_cached()


def _marketplace_quality_allowed(pid: str, product: Optional[dict[str, Any]] = None) -> tuple[bool, dict[str, Any]]:
    """Whether this build meets storefront quality rules (demo + optional QA telemetry)."""
    if product is None:
        product = _get_product_entry(pid) or {}
    spec_inner = _spec_inner_for_storefront(pid, product)
    dpr = _resolved_delivery_profile(product, spec_inner)
    ev = evaluate_marketplace_quality(pid, specification=spec_inner, delivery_profile=dpr)
    return bool(ev.get("eligible")), ev


def _admin_force_list(pid: str) -> bool:
    """Human override: list on storefront even when marketplace quality gates fail."""
    try:
        from web.backend.services.product_followup import admin_force_list_enabled

        return admin_force_list_enabled(pid)
    except Exception:
        return False


def _touch_storefront_established_listing(pid: str) -> None:
    """Persist follow-up flag the first time a build is publicly listable (shipped + quality or force)."""
    try:
        from web.backend.services.product_followup import (
            merge_mark_storefront_established_listing,
            storefront_established_listing_enabled,
        )

        if storefront_established_listing_enabled(pid):
            return
        merge_mark_storefront_established_listing(pid)
    except Exception:
        logger.debug("touch storefront_established_listing failed for %s", pid, exc_info=True)


def is_shipped_pipeline_product_state(state: Any) -> bool:
    """True when the product row is a finished pipeline build (same family as storefront ship states)."""
    s = str(state or "").strip().upper()
    return s in ("COMPLETED", "DEPLOYED_PRODUCTION")


def public_storefront_listing_eligible(pid: str, product: dict[str, Any]) -> tuple[bool, list[str]]:
    """Same gates as ``list_products`` / admin pipeline hints — shipped, code on disk, not hidden, quality or force."""
    state = (product.get("state") or "").upper()
    if not _product_has_code(pid):
        return False, ["no_generated_code_on_disk_or_empty_manifest"]
    if public_storefront_blocked(pid):
        return False, ["hidden_from_public_storefront"]
    if is_mid_repair_storefront_visible(
        pid,
        product,
        state_upper=state,
        has_generated_code=True,
        storefront_blocked=False,
    ):
        return True, ["listed_during_remediation_keeps_prior_storefront_visibility"]
    if state not in ("COMPLETED", "DEPLOYED_PRODUCTION"):
        return False, ["pipeline_state_not_shipped"]
    mq_ok, mq_ev = _marketplace_quality_allowed(pid, product)
    force = _admin_force_list(pid)
    if not mq_ok and not force:
        rs = mq_ev.get("reasons") if isinstance(mq_ev, dict) else None
        if isinstance(rs, list) and rs:
            return False, [str(x) for x in rs[:15]]
        return False, ["marketplace_quality_not_eligible"]
    if force and not mq_ok:
        _touch_storefront_established_listing(pid)
        return True, ["listed_via_admin_force_list"]
    _touch_storefront_established_listing(pid)
    return True, []


def _product_has_code(pid: str) -> bool:
    """Check if a product has actual generated code files on disk."""
    manifest_path = code_dir(pid) / "code_manifest.json"
    if not manifest_path.exists():
        return False
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        files = manifest.get("files", [])
        if not files:
            return False
        code_dir_path = code_dir(pid)
        for f_entry in files:
            fpath = f_entry.get("path") or f_entry.get("file_path", "")
            if fpath and (code_dir_path / fpath).exists():
                return True
        return False
    except Exception:
        return False


def _public_storefront_grid_accepts(pid: str, product: dict[str, Any]) -> bool:
    """Single source of truth for public grid inclusion (keep in sync with public_storefront_listing_eligible)."""
    state = (product.get("state") or "").upper()
    if not _product_has_code(pid):
        return False
    if public_storefront_blocked(pid):
        return False
    if is_mid_repair_storefront_visible(
        pid,
        product,
        state_upper=state,
        has_generated_code=True,
        storefront_blocked=False,
    ):
        return True
    if state not in ("COMPLETED", "DEPLOYED_PRODUCTION"):
        return False
    mq_ok, _ = _marketplace_quality_allowed(pid, product)
    force = _admin_force_list(pid)
    if not mq_ok and not force:
        return False
    if mq_ok or force:
        _touch_storefront_established_listing(pid)
    return True


def count_showcase_listable_products() -> int:
    """How many products appear on the public storefront grid (same as ``total_count`` in ``/categories``).

    Uses the shared bounded-latency cache so admin metrics and pipeline catalog stay responsive.
    """
    try:
        from web.backend.services.storefront_counts_cache import get_storefront_categories_cached

        d = get_storefront_categories_cached()
        return int(d.get("total_count", 0))
    except Exception as e:
        logger.warning("count_showcase_listable_products: cache failed (%s)", e)
        try:
            return int(build_storefront_categories_response().get("total_count", 0))
        except Exception:
            return 0


@router.get("")
async def list_products(
    query: ProductListQuery = Depends(),
):
    """List all products available on the storefront, optionally filtered by category.

    Products without actual generated code files on disk are excluded
    (incomplete sandbox products should not appear in the marketplace).

    Additionally, listings enforce **marketplace quality** for first-time ship; products that already
    met storefront rules keep their card visible while the pipeline re-opens them for fixes
    (see ``product_followup.storefront_established_listing``).
    """
    try:
        category = query.normalized_category()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    products_dir = state_dir()
    products = []

    if category and category not in LISTING_CATEGORY_IDS and category != "uncategorized":
        return {"products": [], "count": 0, "category": category}

    if products_dir.exists():
        try:
            data_products = _get_products_map()
            used_names: set[str] = set()
            for pid, product in data_products.items():
                if not _public_storefront_grid_accepts(pid, product):
                    continue

                state = (product.get("state") or "").upper()
                spec_inner = _spec_inner_for_storefront(pid, product)
                _, mq_ev = _marketplace_quality_allowed(pid, product)
                is_landing = _is_marketing_landing_listing(product, spec_inner)

                # Load marketing (now done early in pipeline, has market research + monetization)
                marketing = _load_marketing(pid)
                product_category = _canonical_marketplace_category(marketing, product)

                # Shelf split: landings only under ``landings``; verticals are apps / full builds only.
                if category == LANDINGS_LISTING_SLUG:
                    if not is_landing:
                        continue
                elif category == "uncategorized":
                    if is_landing:
                        continue
                    if product_category != "uncategorized":
                        continue
                elif category:
                    if is_landing:
                        continue
                    if product_category != category:
                        continue

                # Load sales config
                sales_config = _load_sales(pid)
                product_name, is_template = resolve_product_name(
                    product_id=pid,
                    product=product,
                    spec=spec_inner,
                    marketing=marketing,
                    used_names=used_names,
                )

                # Derive description
                description = ""
                if marketing:
                    description = marketing.get("selling_description") or marketing.get("short_description", "")
                if not description:
                    description = product.get("idea", "")[:100]

                # Features
                features = []
                spec_path = specs_dir(pid) / "specification.json"
                if spec_path.exists():
                    try:
                        with open(spec_path, "r") as f:
                            spec_data = json.load(f)
                        spec = spec_data.get("specification", {})
                        if spec.get("core_features"):
                            features = [f.get("name", f.get("description", "")) for f in spec["core_features"]]
                    except Exception:
                        pass
                if not features and marketing:
                    features = marketing.get("key_benefits", [])

                # Tags
                tags = marketing.get("tags", []) or product.get("tags", [])

                # Price: admin override in sales_config → sales agent → marketing → default
                price_usdt, price_tier = resolve_storefront_price_usdt(
                    marketing=marketing or {},
                    sales_config_inner=sales_config or {},
                    default_usdt=DEFAULT_STOREFRONT_PRICE_USDT,
                )
                monetization_scheme = marketing.get("monetization_scheme", {}) or {}

                # Tech stack summary for storefront cards (from architect file)
                implementation_summary: dict[str, Any] = {}
                arch_disk = _load_architecture_from_disk(pid)
                if arch_disk and isinstance(arch_disk.get("tech_stack"), dict):
                    implementation_summary = arch_disk["tech_stack"]

                dprof = _resolved_delivery_profile(product, spec_inner)
                stack_label = _storefront_stack_label(implementation_summary)

                card = {
                    "id": pid,
                    "name": product_name,
                    "is_template": is_template,
                    "category": product_category,
                    "tags": tags,
                    "tagline": marketing.get("tagline", f"{state.replace('_', ' ').title()} — {product_name}"),
                    "description": description,
                    "selling_description": marketing.get("selling_description", ""),
                    "long_description": marketing.get("long_description", description),
                    "idea": product.get("idea", ""),
                    "delivery_profile": dprof,
                    "storefront_stack_label": stack_label,
                    "price_usdt": price_usdt,
                    "price_tier": price_tier,
                    "monetization_scheme": monetization_scheme,
                    "supported_chains": (sales_config.get("pricing") or {}).get("supported_chains", ["base", "ethereum"]),
                    "state": product.get("state"),
                    "created_at": product.get("created_at", 0),
                    "features": features,
                    "rating": 4.5,
                    "implementation_summary": implementation_summary,
                }
                card.update(marketplace_listing_card_fields(mq_ev))
                products.append(card)
        except Exception as e:
            logger.error(f"Failed to list products: {e}")

    return {"products": products, "count": len(products), "category": category or "all"}


@router.get("/{product_id}")
async def get_product(product_id: str):
    """Get detailed information about a specific product."""
    try:
        product = _get_product_entry(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        if public_storefront_blocked(product_id):
            raise HTTPException(status_code=404, detail="Product not found")

        # Load all related data
        marketing = _load_marketing(product_id)
        sales_config = _load_sales(product_id)

        spec_inner = _spec_inner_for_storefront(product_id, product)
        product_name, is_template = resolve_product_name(
            product_id=product_id,
            product=product,
            spec=spec_inner,
            marketing=marketing,
        )

        category = _canonical_marketplace_category(marketing, product)
        tags = marketing.get("tags", []) or product.get("tags", [])
        selling_description = marketing.get("selling_description", "")
        monetization_scheme = marketing.get("monetization_scheme", {}) or {}

        # Price: admin override → sales → marketing → default
        price_usdt, price_tier = resolve_storefront_price_usdt(
            marketing=marketing or {},
            sales_config_inner=sales_config or {},
            default_usdt=DEFAULT_STOREFRONT_PRICE_USDT,
        )

        # Load evolution history
        evolution_history = []
        telemetry_dir_path = telemetry_dir(product_id)
        if telemetry_dir_path.exists():
            for evo_file in sorted(telemetry_dir_path.glob("evolution_*.json")):
                with open(evo_file, "r") as f:
                    evolution_history.append(json.load(f))

        architecture_data = product.get("architecture")
        if architecture_data is None:
            architecture_data = _load_architecture_from_disk(product_id)

        impl_summary: dict[str, Any] = {}
        if isinstance(architecture_data, dict) and isinstance(architecture_data.get("tech_stack"), dict):
            impl_summary = architecture_data["tech_stack"]

        demo_quality = assess_product_demo(product_id, spec_inner)
        dprof = _resolved_delivery_profile(product, spec_inner)
        mq_eval = evaluate_marketplace_quality(
            product_id, specification=spec_inner, delivery_profile=dprof
        )
        stack_lbl = ""
        if isinstance(architecture_data, dict) and isinstance(architecture_data.get("tech_stack"), dict):
            stack_lbl = _storefront_stack_label(architecture_data["tech_stack"])
        stakeholder_brief = build_stakeholder_brief(
            product_id,
            product.get("idea", "") or "",
            spec_inner,
            marketing,
        )

        browser_preview_e2e = None
        qa_gates_all_passed = None
        gate_file = telemetry_dir(product_id) / "demo_quality_gate.json"
        if gate_file.exists():
            try:
                with open(gate_file) as gf:
                    gate_data = json.load(gf)
                browser_preview_e2e = gate_data.get("browser_preview_e2e")
                qa_gates_all_passed = gate_data.get("gates_all_passed")
            except Exception:
                pass

        return {
            "id": product_id,
            "name": product_name,
            "is_template": is_template,
            "delivery_profile": dprof,
            "storefront_stack_label": stack_lbl,
            "idea": product.get("idea", ""),
            "category": category,
            "tags": tags,
            "selling_description": selling_description,
            "price_usdt": price_usdt,
            "price_tier": price_tier,
            "monetization_scheme": monetization_scheme,
            "state": product.get("state"),
            "created_at": product.get("created_at"),
            "updated_at": product.get("updated_at"),
            "spec": spec_inner,
            "architecture": architecture_data,
            "implementation_summary": impl_summary,
            "code": product.get("code"),
            "marketing": marketing,
            "pricing": sales_config.get("pricing", {}),
            "license_terms": sales_config.get("license_terms", {}),
            "evolution_history": evolution_history[-10:],  # Last 10 evolutions
            "tasks": product.get("tasks", []),
            "demo_quality": demo_quality,
            "browser_preview_e2e": browser_preview_e2e,
            "qa_gates_all_passed": qa_gates_all_passed,
            "marketplace_quality": {
                "eligible": mq_eval.get("eligible"),
                "reasons": mq_eval.get("reasons"),
                "rules": mq_eval.get("marketplace_rules"),
            },
            "marketplace_listing_fields": marketplace_listing_card_fields(mq_eval),
            "stakeholder_brief": stakeholder_brief,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get product {product_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{product_id}/security-report")
async def get_product_security_report(product_id: str):
    """Get the security report for a product (public, no auth required)."""
    from web.backend.services.security_report_loader import load_security_report

    report = load_security_report(product_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No security report found for this product")

    return {"product_id": product_id, "report": report}
