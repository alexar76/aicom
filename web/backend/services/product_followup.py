"""
Pipeline product storefront annotations (follow-up labels, admin score, force-list).

Single JSON per product: ``{data_root}/state/product_followup/{product_id}.json``.
Merging updates preserve unrelated keys (e.g. admin_force_list when editing followup).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

STOREFRONT_ESTABLISHED_LISTING_KEY = "storefront_established_listing"


def _data_root() -> Path:
    from core.paths import data_root

    return data_root()


def followup_dir() -> Path:
    return _data_root() / "state" / "product_followup"


def followup_path(product_id: str) -> Path:
    return followup_dir() / f"{product_id}.json"


def read_followup(product_id: str) -> Optional[dict[str, Any]]:
    p = followup_path(product_id)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("read_followup %s: %s", product_id, e)
        return None


def write_followup(product_id: str, payload: dict[str, Any]) -> None:
    d = followup_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = followup_path(product_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_followup(product_id: str) -> None:
    p = followup_path(product_id)
    try:
        if p.is_file():
            p.unlink()
    except OSError as e:
        logger.warning("delete_followup %s: %s", product_id, e)


def normalize_pipeline_followup(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Full shape for API / pipeline product JSON."""
    if not raw:
        return {
            "followup": None,
            "planned_notes": None,
            "not_pursuing_reason": None,
            "followup_updated_at": None,
            "quality_score": None,
            "admin_force_list": False,
            "admin_force_list_note": None,
            "admin_force_list_at": None,
            "admin_hide_from_storefront": False,
            "admin_decisions_updated_at": None,
            "storefront_established_listing": False,
            "storefront_established_listing_at": None,
        }
    return {
        "followup": raw.get("followup"),
        "planned_notes": raw.get("planned_notes"),
        "not_pursuing_reason": raw.get("not_pursuing_reason"),
        "followup_updated_at": raw.get("followup_updated_at") or raw.get("updated_at"),
        "quality_score": raw.get("quality_score"),
        "admin_force_list": bool(raw.get("admin_force_list")),
        "admin_force_list_note": raw.get("admin_force_list_note"),
        "admin_force_list_at": raw.get("admin_force_list_at"),
        "admin_hide_from_storefront": bool(raw.get("admin_hide_from_storefront")),
        "admin_decisions_updated_at": raw.get("admin_decisions_updated_at"),
        "storefront_established_listing": bool(raw.get(STOREFRONT_ESTABLISHED_LISTING_KEY)),
        "storefront_established_listing_at": raw.get("storefront_established_listing_at"),
    }


# Back-compat alias
def normalize_followup_record(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    r = normalize_pipeline_followup(raw)
    return {
        "followup": r["followup"],
        "planned_notes": r["planned_notes"],
        "not_pursuing_reason": r["not_pursuing_reason"],
        "updated_at": r["followup_updated_at"],
    }


def admin_force_list_enabled(product_id: str) -> bool:
    raw = read_followup(product_id)
    return bool(raw and raw.get("admin_force_list"))


def storefront_established_listing_enabled(product_id: str) -> bool:
    """True once this product met storefront quality while shipped — keeps card visible during repair."""
    raw = read_followup(product_id)
    return bool(raw and raw.get(STOREFRONT_ESTABLISHED_LISTING_KEY))


def merge_mark_storefront_established_listing(product_id: str) -> bool:
    """Set storefront_established_listing in follow-up JSON. Returns True if newly set."""
    cur = read_followup(product_id) or {}
    if cur.get(STOREFRONT_ESTABLISHED_LISTING_KEY):
        return False
    merged = dict(cur)
    merged[STOREFRONT_ESTABLISHED_LISTING_KEY] = True
    merged["storefront_established_listing_at"] = time.time()
    write_followup(product_id, merged)
    return True


def storefront_followup_not_pursuing(product_id: str) -> bool:
    raw = read_followup(product_id)
    return bool(raw and raw.get("followup") == "not_pursuing")


def public_storefront_blocked(product_id: str) -> bool:
    """True → exclude from public marketplace listing and product detail (404)."""
    raw = read_followup(product_id)
    if not raw:
        return False
    if raw.get("followup") == "not_pursuing":
        return True
    if bool(raw.get("admin_hide_from_storefront")):
        return True
    return False


def annotate_automated_storefront_backlog(product_id: str, reasons: list[str]) -> None:
    """
    When the worker schedules storefront remediation, mirror intent in follow-up JSON so the admin
    Pipeline UI shows «planned» without clobbering operator «not pursuing».
    """
    cur = read_followup(product_id) or {}
    if cur.get("followup") == "not_pursuing":
        return

    snippet = "; ".join(str(r) for r in reasons[:10])
    auto_line = f"[factory storefront backlog] {snippet}"
    cur["followup"] = "planned"

    prev = (cur.get("planned_notes") or "").strip()
    if prev:
        if auto_line not in prev:
            merged = (prev + "\n" + auto_line).strip()
            cur["planned_notes"] = merged[:8000]
    else:
        cur["planned_notes"] = auto_line[:8000]

    now = time.time()
    cur["followup_updated_at"] = now
    cur["last_factory_storefront_probe_at"] = now
    write_followup(product_id, cur)


def patch_followup_only(
    product_id: str,
    *,
    followup: Optional[str],
    planned_notes: Optional[str],
    not_pursuing_reason: Optional[str],
) -> dict[str, Any]:
    """Merge follow-up fields; marking ``not_pursuing`` clears admin force-list (cannot list publicly)."""
    cur = read_followup(product_id) or {}

    if followup is None:
        cur.pop("followup", None)
        cur.pop("planned_notes", None)
        cur.pop("not_pursuing_reason", None)
    else:
        fu = followup.strip().lower()
        if fu not in ("planned", "not_pursuing"):
            raise ValueError("followup must be null, 'planned', or 'not_pursuing'")

        notes = (planned_notes or "").strip() or None
        reason = (not_pursuing_reason or "").strip() or None

        if fu == "not_pursuing":
            if not reason or len(reason) < 5:
                raise ValueError(
                    "not_pursuing_reason is required (min 5 characters) when followup is not_pursuing"
                )
            cur["admin_force_list"] = False
            cur.pop("admin_force_list_note", None)
            cur.pop("admin_force_list_at", None)
            cur.pop(STOREFRONT_ESTABLISHED_LISTING_KEY, None)
            cur.pop("storefront_established_listing_at", None)

        cur["followup"] = fu
        cur["planned_notes"] = notes if fu == "planned" else None
        cur["not_pursuing_reason"] = reason if fu == "not_pursuing" else None

    now = time.time()
    cur["followup_updated_at"] = now

    if not cur.get("followup") and not cur.get("admin_force_list") and cur.get("quality_score") is None:
        # nothing meaningful besides timestamps — still save if we had keys cleared from partial
        pass

    write_followup(product_id, cur)
    return normalize_pipeline_followup(cur)


def patch_admin_decisions(
    product_id: str,
    *,
    quality_score: Optional[int] = None,
    admin_force_list: Optional[bool] = None,
    admin_force_list_note: Optional[str] = None,
    clear_force_list: bool = False,
    admin_hide_from_storefront: Optional[bool] = None,
    clear_hide_from_storefront: bool = False,
) -> dict[str, Any]:
    """Human rating 1–5 and/or forced storefront listing (bypasses marketplace quality gates, not code checks)."""
    cur = read_followup(product_id) or {}
    now = time.time()

    if quality_score is not None:
        if quality_score < 1 or quality_score > 5:
            raise ValueError("quality_score must be between 1 and 5")
        cur["quality_score"] = int(quality_score)

    if clear_hide_from_storefront:
        cur.pop("admin_hide_from_storefront", None)
    elif admin_hide_from_storefront is not None:
        cur["admin_hide_from_storefront"] = bool(admin_hide_from_storefront)
        if cur["admin_hide_from_storefront"]:
            cur["admin_force_list"] = False
            cur.pop("admin_force_list_note", None)
            cur.pop("admin_force_list_at", None)

    if clear_force_list:
        cur["admin_force_list"] = False
        cur.pop("admin_force_list_note", None)
        cur.pop("admin_force_list_at", None)
    elif admin_force_list is not None:
        if cur.get("admin_hide_from_storefront"):
            raise ValueError("cannot enable admin_force_list while admin_hide_from_storefront is set")
        cur["admin_force_list"] = bool(admin_force_list)
        if admin_force_list:
            note = (admin_force_list_note or "").strip()
            if len(note) < 5:
                raise ValueError("admin_force_list_note is required (min 5 chars) when forcing storefront")
            cur["admin_force_list_note"] = note
            cur["admin_force_list_at"] = now
        else:
            cur.pop("admin_force_list_note", None)
            cur.pop("admin_force_list_at", None)

    cur["admin_decisions_updated_at"] = now
    write_followup(product_id, cur)
    return normalize_pipeline_followup(cur)


# Legacy name used by dashboard PATCH — now merges
def validate_and_save(
    product_id: str,
    *,
    followup: Optional[str],
    planned_notes: Optional[str],
    not_pursuing_reason: Optional[str],
) -> dict[str, Any]:
    return patch_followup_only(
        product_id,
        followup=followup,
        planned_notes=planned_notes,
        not_pursuing_reason=not_pursuing_reason,
    )
