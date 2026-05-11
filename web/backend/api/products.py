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

from fastapi import APIRouter, HTTPException, Query

from web.backend.services.demo_quality import assess_product_demo
from web.backend.services.marketplace_quality import (
    evaluate_marketplace_quality,
    marketplace_listing_card_fields,
)
from web.backend.services.product_followup import public_storefront_blocked
from web.backend.services.product_naming import resolve_product_name
from web.backend.services.product_brief import build_stakeholder_brief
from marketplace_taxonomy import MARKETPLACE_CATEGORY_IDS, canonical_marketplace_category

logger = logging.getLogger(__name__)

# Storefront-only: marketing landings tab (not a Director / LLM vertical topic).
LANDINGS_LISTING_SLUG = "landings"
LISTING_CATEGORY_IDS = tuple(MARKETPLACE_CATEGORY_IDS) + (LANDINGS_LISTING_SLUG,)

# Default storefront / checkout amount when marketing & sales artifacts omit price (one-shot landing SKU).
DEFAULT_STOREFRONT_PRICE_USDT = 4.99


def _use_sqlite_pipeline() -> bool:
    return os.environ.get("USE_SQLITE", "").strip().lower() in ("1", "true", "yes")


def _sqlite_db_path() -> Path:
    return Path(os.environ.get("SQLITE_PATH", "/app/data/state/pipeline.db"))


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
    if _use_sqlite_pipeline() and _sqlite_db_path().exists():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_sqlite_db_path()))
            sm.connect()
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
    if _use_sqlite_pipeline() and _sqlite_db_path().exists():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_sqlite_db_path()))
            sm.connect()
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
    pipeline_file = Path("/app/data/state/pipeline.json")
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
    spec_path = Path(f"/app/data/specs/{pid}/specification.json")
    if spec_path.exists():
        try:
            with open(spec_path, "r") as f:
                spec_data = json.load(f)
            spec = spec_data.get("specification", {})
            name = str(spec.get("product_name", "")).strip()
        except Exception:
            pass
    return name or f"Product {pid[:8]}"


def _load_specification_from_disk(pid: str) -> Optional[dict]:
    """Return inner `specification` object from specs file (PM output)."""
    spec_path = Path(f"/app/data/specs/{pid}/specification.json")
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
    arch_path = Path(f"/app/data/arch/{pid}/architecture.json")
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
    mkt_file = Path(f"/app/data/state/{pid}/marketing_content.json")
    if mkt_file.exists():
        try:
            with open(mkt_file, "r") as f:
                return json.load(f).get("marketing", {})
        except Exception:
            pass
    return {}


def _load_sales(pid: str) -> dict:
    """Load sales config for a product."""
    sales_file = Path(f"/app/data/state/{pid}/sales_config.json")
    if sales_file.exists():
        try:
            with open(sales_file, "r") as f:
                return json.load(f).get("sales_data", {})
        except Exception:
            pass
    return {}


@router.get("/categories")
async def list_categories():
    """List all product categories with counts — only counting products that are
    actually visible on the storefront (COMPLETED/DEPLOYED_PRODUCTION state with code files).

    This must stay in sync with the filters in list_products().
    """
    products = _get_products_map()

    # Count only products that would appear in the marketplace listing
    # (same filters as list_products()). Landings are counted only under ``landings``;
    # vertical tabs (SaaS, IoT, …) count runnable/full builds only — not marketing landings.
    category_counts: dict[str, int] = {}
    landings_count = 0
    for pid, product in products.items():
        state = (product.get("state") or "").upper()
        if state not in ("COMPLETED", "DEPLOYED_PRODUCTION"):
            continue

        # Skip products with no actual generated code (incomplete sandbox)
        if not _product_has_code(pid):
            continue

        if public_storefront_blocked(pid):
            continue

        ok_mq, _mq_ev = _marketplace_quality_allowed(pid, product)
        if not ok_mq and not _admin_force_list(pid):
            continue

        spec_inner = _spec_inner_for_storefront(pid, product)
        if _is_marketing_landing_listing(product, spec_inner):
            landings_count += 1
            continue

        marketing = _load_marketing(pid)
        category = _canonical_marketplace_category(marketing, product)
        category_counts[category] = category_counts.get(category, 0) + 1

    # Build response with category info
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


def _marketplace_quality_allowed(pid: str, product: Optional[dict[str, Any]] = None) -> tuple[bool, dict[str, Any]]:
    """Whether this build meets storefront quality rules (demo + optional QA telemetry)."""
    if product is None:
        product = _get_product_entry(pid) or {}
    spec_inner = _spec_inner_for_storefront(pid, product)
    ev = evaluate_marketplace_quality(pid, specification=spec_inner)
    return bool(ev.get("eligible")), ev


def _admin_force_list(pid: str) -> bool:
    """Human override: list on storefront even when marketplace quality gates fail."""
    try:
        from web.backend.services.product_followup import admin_force_list_enabled

        return admin_force_list_enabled(pid)
    except Exception:
        return False


def is_shipped_pipeline_product_state(state: Any) -> bool:
    """True when the product row is a finished pipeline build (same family as storefront ship states)."""
    s = str(state or "").strip().upper()
    return s in ("COMPLETED", "DEPLOYED_PRODUCTION")


def public_storefront_listing_eligible(pid: str, product: dict[str, Any]) -> tuple[bool, list[str]]:
    """Same gates as ``list_products`` / admin pipeline hints — shipped, code on disk, not hidden, quality or force."""
    state = (product.get("state") or "").upper()
    if state not in ("COMPLETED", "DEPLOYED_PRODUCTION"):
        return False, ["pipeline_state_not_shipped"]
    if not _product_has_code(pid):
        return False, ["no_generated_code_on_disk_or_empty_manifest"]
    if public_storefront_blocked(pid):
        return False, ["hidden_from_public_storefront"]
    mq_ok, mq_ev = _marketplace_quality_allowed(pid, product)
    force = _admin_force_list(pid)
    if not mq_ok and not force:
        rs = mq_ev.get("reasons") if isinstance(mq_ev, dict) else None
        if isinstance(rs, list) and rs:
            return False, [str(x) for x in rs[:15]]
        return False, ["marketplace_quality_not_eligible"]
    if force and not mq_ok:
        return True, ["listed_via_admin_force_list"]
    return True, []


def _product_has_code(pid: str) -> bool:
    """Check if a product has actual generated code files on disk."""
    manifest_path = Path(f"/app/data/code/{pid}/code_manifest.json")
    if not manifest_path.exists():
        return False
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        files = manifest.get("files", [])
        if not files:
            return False
        code_dir = Path(f"/app/data/code/{pid}")
        for f_entry in files:
            fpath = f_entry.get("path") or f_entry.get("file_path", "")
            if fpath and (code_dir / fpath).exists():
                return True
        return False
    except Exception:
        return False


def count_showcase_listable_products() -> int:
    """Products listed on the public storefront if ``category`` is unset — same gates as ``list_products``.

    Counts COMPLETED/DEPLOYED_PRODUCTION rows with generated code on disk that pass
    ``evaluate_marketplace_quality`` (must stay aligned with ``list_products`` / ``list_categories``).
    """
    n = 0
    for pid, product in _get_products_map().items():
        state = (product.get("state") or "").upper()
        if state not in ("COMPLETED", "DEPLOYED_PRODUCTION"):
            continue
        if not _product_has_code(pid):
            continue
        if public_storefront_blocked(pid):
            continue
        mq_ok, _ = _marketplace_quality_allowed(pid, product)
        if not mq_ok and not _admin_force_list(pid):
            continue
        n += 1
    return n


@router.get("")
async def list_products(category: Optional[str] = Query(None, description="Filter by category")):
    """List all products available on the storefront, optionally filtered by category.

    Products without actual generated code files on disk are excluded
    (incomplete sandbox products should not appear in the marketplace).

    Additionally, listings enforce **marketplace quality** (same demo gates as pipeline QA,
    optional minimum spec coverage — see ``marketplace_quality.evaluate_marketplace_quality``).
    Low-value / stub demos must not appear until the build is revised.
    """
    products_dir = Path("/app/data/state")
    products = []

    if category and category not in LISTING_CATEGORY_IDS and category != "uncategorized":
        return {"products": [], "count": 0, "category": category}

    if products_dir.exists():
        try:
            data_products = _get_products_map()
            used_names: set[str] = set()
            for pid, product in data_products.items():
                state = (product.get("state") or "").upper()
                if state not in ("COMPLETED", "DEPLOYED_PRODUCTION"):
                    continue

                # Skip products with no actual generated code (incomplete sandbox)
                if not _product_has_code(pid):
                    logger.info(f"Skipping product {pid} from marketplace: no code files")
                    continue

                if public_storefront_blocked(pid):
                    logger.info("Skipping product %s from marketplace: hidden by admin / not pursuing", pid)
                    continue

                mq_ok, mq_ev = _marketplace_quality_allowed(pid, product)
                force = _admin_force_list(pid)
                if not mq_ok and not force:
                    logger.info(
                        "Skipping product %s from marketplace: quality gate — %s",
                        pid,
                        mq_ev.get("reasons") or mq_ev.get("demo_quality", {}).get("issues"),
                    )
                    continue
                if not mq_ok and force:
                    logger.info(
                        "Listing product %s on marketplace via admin_force_list override",
                        pid,
                    )

                spec_inner = _spec_inner_for_storefront(pid, product)
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
                spec_path = Path(f"/app/data/specs/{pid}/specification.json")
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

                # Price from monetization scheme (marketing) first — primary source
                price_usdt = DEFAULT_STOREFRONT_PRICE_USDT
                price_tier = "professional"
                monetization_scheme = marketing.get("monetization_scheme", {})

                if monetization_scheme:
                    paid_tiers = monetization_scheme.get("paid_tiers", [])
                    if paid_tiers:
                        price_usdt = paid_tiers[0].get("price_usd_monthly", DEFAULT_STOREFRONT_PRICE_USDT)
                        price_tier = paid_tiers[0].get("name", "professional").lower()

                # Sales config may override with crypto one-time price
                if sales_config:
                    pricing = sales_config.get("pricing", {})
                    # Also check pricing_tiers (some agents use this key instead)
                    if not pricing:
                        pricing = {"tiers": sales_config.get("pricing_tiers", [])}
                    if pricing.get("tiers"):
                        # Find first paid tier (skip free tier with price=0)
                        paid_tier = None
                        for t in pricing["tiers"]:
                            tp = t.get("price_usdt") or t.get("price", 0)
                            if tp and tp > 0:
                                paid_tier = t
                                break
                        if paid_tier:
                            tier_price = paid_tier.get("price_usdt") or paid_tier.get("price", 0)
                            price_usdt = tier_price
                            price_tier = paid_tier.get("name", price_tier).lower()
                    elif pricing.get("usdt_price"):
                        p = pricing["usdt_price"]
                        if p and p > 0:
                            price_usdt = p

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
                    "supported_chains": sales_config.get("pricing", {}).get("supported_chains", ["base", "ethereum"]),
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
        monetization_scheme = marketing.get("monetization_scheme", {})

        # Price from monetization scheme (marketing) first — primary source
        price_usdt = DEFAULT_STOREFRONT_PRICE_USDT
        price_tier = "professional"
        if monetization_scheme:
            paid_tiers = monetization_scheme.get("paid_tiers", [])
            if paid_tiers:
                price_usdt = paid_tiers[0].get("price_usd_monthly", DEFAULT_STOREFRONT_PRICE_USDT)
                price_tier = paid_tiers[0].get("name", "professional").lower()

        # Sales config may override with crypto one-time price
        if sales_config:
            pricing = sales_config.get("pricing", {})
            # Also check pricing_tiers (some agents use this key instead)
            if not pricing:
                pricing = {"tiers": sales_config.get("pricing_tiers", [])}
            if pricing.get("tiers"):
                # Find first paid tier (skip free tier with price=0)
                paid_tier = None
                for t in pricing["tiers"]:
                    tp = t.get("price_usdt") or t.get("price", 0)
                    if tp and tp > 0:
                        paid_tier = t
                        break
                if paid_tier:
                    tier_price = paid_tier.get("price_usdt") or paid_tier.get("price", 0)
                    price_usdt = tier_price
                    price_tier = paid_tier.get("name", price_tier).lower()
            elif pricing.get("usdt_price"):
                p = pricing["usdt_price"]
                if p and p > 0:
                    price_usdt = p

        # Load evolution history
        evolution_history = []
        telemetry_dir = Path(f"/app/data/telemetry/{product_id}")
        if telemetry_dir.exists():
            for evo_file in sorted(telemetry_dir.glob("evolution_*.json")):
                with open(evo_file, "r") as f:
                    evolution_history.append(json.load(f))

        architecture_data = product.get("architecture")
        if architecture_data is None:
            architecture_data = _load_architecture_from_disk(product_id)

        impl_summary: dict[str, Any] = {}
        if isinstance(architecture_data, dict) and isinstance(architecture_data.get("tech_stack"), dict):
            impl_summary = architecture_data["tech_stack"]

        demo_quality = assess_product_demo(product_id, spec_inner)
        mq_eval = evaluate_marketplace_quality(product_id, specification=spec_inner)
        dprof = _resolved_delivery_profile(product, spec_inner)
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
        gate_file = Path(f"/app/data/telemetry/{product_id}/demo_quality_gate.json")
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
