"""
Marketplace listing quality — generated programs must offer real user value before
they appear on the public storefront (aligned with pipeline QA demo gates).

Primary source: ``quality.*`` in layered platform YAML (Admin → Settings → Pipeline & product quality).
Env vars override YAML when set (non-empty). Legacy env names:

  AIFACTORY_MARKETPLACE_QUALITY_GATE — default 1; set 0 to disable storefront filter (debug).
  AIFACTORY_MARKETPLACE_REQUIRE_FULL_QA — default 0; set 1 to require telemetry
    demo_quality_gate.json with gates_all_passed true (includes browser E2E when QA ran).
  AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE — default 15; min spec keyword coverage %% when
    the spec defines measurable keywords (0 disables).
  AIFACTORY_MARKETPLACE_REQUIRE_NON_PLACEHOLDER_NAME — default 1; block spam/placeholder titles.
  AIFACTORY_MARKETPLACE_REQUIRE_DESIGN_NOVELTY — default 1; when an architecture
    novelty score is available, require it to meet minimum.
  AIFACTORY_MARKETPLACE_MIN_DESIGN_NOVELTY — default 0.18; minimum novelty score
    from arch/*/architecture.json for marketplace eligibility.
  AIFACTORY_MARKETPLACE_REQUIRE_QA_REALISM — default 1; blocks listing when
    high-severity backend realism findings are present in QA report.
  AIFACTORY_MARKETPLACE_REQUIRE_RELEASE_SCORE — default 1; if QA report has a
    release_score field, require minimum threshold.
  AIFACTORY_MARKETPLACE_MIN_RELEASE_SCORE — default 70.
  AIFACTORY_LANDING_STOREFRONT_RELAXED — default 0; set 1 to relax methodology +
    design-novelty storefront requirements for ``marketing_landing`` only.
  AIFACTORY_LANDING_MIN_RELEASE_SCORE — optional; caps / lowers release score threshold for
    relaxed landing storefront checks (0–100).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass
from web.backend.services.domain_methodology import get_domain_pack, select_domain_pack
from core.logging_utils import log_suppressed
from web.backend.services.methodology_review import (
    review_implementation as _methodology_review_implementation,
)
from web.backend.services.product_naming import is_placeholder_product_name
from web.backend.services.quality_constitution import evaluate_quality_constitution
from web.backend.services.release_cockpit import evaluate_release_cockpit

from core.paths import resolve_data_root

logger = logging.getLogger(__name__)
from core.quality_settings import (
    marketplace_min_design_novelty,
    marketplace_min_release_score,
    marketplace_min_spec_coverage,
    marketplace_quality_gate,
    marketplace_require_design_novelty,
    marketplace_require_full_qa,
    marketplace_require_methodology,
    marketplace_require_non_placeholder_name,
    marketplace_require_qa_realism,
    marketplace_require_quality_constitution,
    marketplace_require_release_cockpit,
    marketplace_require_release_score,
)


def _env_int_optional(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _resolve_delivery_profile_for_marketplace(
    product_id: str,
    specification: Optional[dict[str, Any]],
    delivery_profile: Optional[str],
    data_root: Path,
) -> str:
    from core.delivery_profile import FULL_SOFTWARE, normalize_delivery_profile

    if delivery_profile:
        return normalize_delivery_profile(str(delivery_profile))
    if isinstance(specification, dict) and specification.get("delivery_profile"):
        return normalize_delivery_profile(str(specification.get("delivery_profile")))
    spec_path = data_root / "specs" / product_id / "specification.json"
    if spec_path.is_file():
        try:
            raw = json.loads(spec_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                if raw.get("delivery_profile"):
                    return normalize_delivery_profile(str(raw.get("delivery_profile")))
                inner = raw.get("specification")
                if isinstance(inner, dict) and inner.get("delivery_profile"):
                    return normalize_delivery_profile(str(inner.get("delivery_profile")))
        except (OSError, json.JSONDecodeError, TypeError) as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/services/marketplace_quality.py)", exc_info=_suppressed_exc)
    return FULL_SOFTWARE


def _load_gate_telemetry(product_id: str, data_root: Path) -> Optional[dict[str, Any]]:
    p = data_root / "telemetry" / product_id / "demo_quality_gate.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_qa_report(product_id: str, data_root: Path) -> Optional[dict[str, Any]]:
    p = data_root / "bugs" / product_id / "qa_report.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_architecture_artifact(product_id: str, data_root: Path) -> Optional[dict[str, Any]]:
    p = data_root / "arch" / product_id / "architecture.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _has_blocking_realism_findings(qa_report: Optional[dict[str, Any]]) -> bool:
    if not isinstance(qa_report, dict):
        return False
    qa_result = qa_report.get("qa_result")
    if not isinstance(qa_result, dict):
        return False

    for item in qa_result.get("bugs_found") or []:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity", "")).lower()
        title = str(item.get("title", "")).lower()
        if sev == "high" and title.startswith("backend realism:"):
            return True

    for item in qa_result.get("security_issues") or []:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity", "")).lower()
        issue = str(item.get("issue", "")).lower()
        if sev == "high" and "backend realism" in issue:
            return True
    return False


def _evaluate_methodology(
    product_id: str,
    data_root: Path,
    specification: Optional[dict[str, Any]],
    qa_report: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """
    Prefer the cached methodology snapshot QA wrote out; otherwise run a fresh
    heuristic scan against the code directory so the storefront gate stays self-sufficient.
    """
    snapshot_path = data_root / "telemetry" / product_id / "methodology_implementation.json"
    if snapshot_path.is_file():
        try:
            return json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/services/marketplace_quality.py)", exc_info=_suppressed_exc)

    if isinstance(qa_report, dict):
        qa_result = qa_report.get("qa_result")
        if isinstance(qa_result, dict):
            mr = qa_result.get("methodology_review")
            if isinstance(mr, dict) and mr:
                return mr

    spec_inner = specification
    if isinstance(specification, dict) and isinstance(specification.get("specification"), dict):
        spec_inner = specification["specification"]
    if not isinstance(spec_inner, dict):
        spec_inner = {}

    forced = str(spec_inner.get("domain") or "").strip()
    pack = get_domain_pack(forced) if forced else None
    if pack is None:
        idea_blob = " ".join(
            str(spec_inner.get(k) or "")
            for k in ("product_name", "description")
        )
        category = str(spec_inner.get("category") or "")
        pack = select_domain_pack(idea_blob, category=category, spec=spec_inner)
    if pack is None:
        return None

    code_dir = data_root / "code" / product_id
    return _methodology_review_implementation(
        code_dir,
        pack=pack,
        spec=spec_inner,
        stage="post_implementation_marketplace",
    )


def _qa_release_score(qa_report: Optional[dict[str, Any]]) -> Optional[int]:
    if not isinstance(qa_report, dict):
        return None
    qa_result = qa_report.get("qa_result")
    if not isinstance(qa_result, dict):
        return None
    score = qa_result.get("release_score")
    if isinstance(score, (int, float)):
        return int(score)
    return None


def evaluate_marketplace_quality(
    product_id: str,
    *,
    specification: Optional[dict] = None,
    data_root: str | Path | None = None,
    delivery_profile: Optional[str] = None,
) -> dict[str, Any]:
    """
    Decide whether a product may appear on the public marketplace grid.

    Returns keys: eligible (bool), demo_quality (report), reasons (list[str]),
    telemetry_gates_all_passed (optional bool), marketplace_rules (dict summary).
    """
    from core.delivery_profile import MARKETING_LANDING

    root = resolve_data_root(data_root)
    reasons: list[str] = []

    gate_enabled = marketplace_quality_gate()
    require_full_qa = marketplace_require_full_qa()
    require_design_novelty = marketplace_require_design_novelty()
    require_qa_realism = marketplace_require_qa_realism()
    require_release_score = marketplace_require_release_score()
    require_quality_constitution = marketplace_require_quality_constitution()
    require_release_cockpit = marketplace_require_release_cockpit()
    require_non_placeholder_name = marketplace_require_non_placeholder_name()
    require_methodology = marketplace_require_methodology()
    min_cov = marketplace_min_spec_coverage()
    min_design_novelty = marketplace_min_design_novelty()
    min_release_score = marketplace_min_release_score()

    from core.delivery_profile import DESKTOP_APP, FULL_SOFTWARE, MARKETING_LANDING

    resolved_profile = _resolve_delivery_profile_for_marketplace(
        product_id, specification, delivery_profile, root
    )
    landing_relaxed = resolved_profile == MARKETING_LANDING and os.environ.get(
        "AIFACTORY_LANDING_STOREFRONT_RELAXED", "0"
    ).strip().lower() in ("1", "true", "yes", "on")
    if landing_relaxed:
        require_methodology = False
        require_design_novelty = False
        env_landing_min = _env_int_optional("AIFACTORY_LANDING_MIN_RELEASE_SCORE")
        if env_landing_min is not None:
            min_release_score = min(min_release_score, max(0, min(100, env_landing_min)))
        else:
            min_release_score = min(min_release_score, 55)

    demo = assess_product_demo(product_id, specification, data_root=data_root)
    static_ok = quality_gates_pass(demo, delivery_profile=resolved_profile)

    tel = _load_gate_telemetry(product_id, root)
    qa_report = _load_qa_report(product_id, root)
    telemetry_all_ok: Optional[bool] = None
    if tel is not None:
        telemetry_all_ok = bool(tel.get("gates_all_passed"))
    arch_art = _load_architecture_artifact(product_id, root)
    novelty_score: Optional[float] = None
    if isinstance(arch_art, dict):
        raw = arch_art.get("novelty_score")
        if isinstance(raw, (int, float)):
            novelty_score = float(raw)
    release_score = _qa_release_score(qa_report)

    rules = {
        "quality_gate_enabled": gate_enabled,
        "require_full_pipeline_qa": require_full_qa,
        "require_design_novelty": require_design_novelty,
        "require_qa_realism": require_qa_realism,
        "require_release_score": require_release_score,
        "require_quality_constitution": require_quality_constitution,
        "require_release_cockpit_go": require_release_cockpit,
        "require_non_placeholder_name": require_non_placeholder_name,
        "require_methodology": require_methodology,
        "min_spec_coverage_pct": min_cov,
        "min_design_novelty": min_design_novelty,
        "min_release_score": min_release_score,
        "delivery_profile_resolved": resolved_profile,
        "landing_storefront_relaxed": landing_relaxed,
    }

    from web.backend.services.sandbox_static_entry import storefront_front_page_ready
    from web.backend.services.desktop_product import desktop_storefront_ready, is_desktop_product

    desktop_product = resolved_profile == DESKTOP_APP or is_desktop_product(
        delivery_profile=resolved_profile,
        specification=specification,
    )
    if desktop_product:
        fp_ok, fp_reasons = desktop_storefront_ready(product_id, code_root=root / "code" / product_id)
    else:
        fp_ok, _fp_rel, fp_reasons = storefront_front_page_ready(
            product_id,
            code_root=root / "code" / product_id,
        )
    if not fp_ok:
        reasons.append("storefront_front_page_required" if not desktop_product else "desktop_storefront_not_ready")
        reasons.extend(fp_reasons[:8])
        return {
            "eligible": False,
            "demo_quality": demo,
            "reasons": reasons,
            "telemetry_gates_all_passed": telemetry_all_ok,
            "marketplace_rules": rules,
        }

    if not gate_enabled:
        return {
            "eligible": True,
            "demo_quality": demo,
            "reasons": [],
            "telemetry_gates_all_passed": telemetry_all_ok,
            "marketplace_rules": rules,
        }

    if not static_ok:
        reasons.append("demo_quality_gates_failed")
        for issue in demo.get("issues", []):
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "").strip()
            if code in ("sandbox_localhost_urls", "broken_internal_link"):
                reasons.append(f"broken_link:{code}")
        return {
            "eligible": False,
            "demo_quality": demo,
            "reasons": reasons,
            "telemetry_gates_all_passed": telemetry_all_ok,
            "marketplace_rules": rules,
        }

    from core.delivery_profile import FULL_SOFTWARE

    if resolved_profile == FULL_SOFTWARE:
        from web.backend.services.sandbox_static_entry import (
            full_software_storefront_preview_capable,
        )

        fs_ok, fs_reasons = full_software_storefront_preview_capable(
            product_id,
            code_root=root / "code" / product_id,
        )
        if not fs_ok:
            reasons.append("full_software_preview_not_ready")
            reasons.extend(fs_reasons[:8])
            return {
                "eligible": False,
                "demo_quality": demo,
                "reasons": reasons,
                "telemetry_gates_all_passed": telemetry_all_ok,
                "marketplace_rules": rules,
            }

    # desktop_app skips full_software browser preview gate (download-first SKU)

    if require_quality_constitution:
        constitution = evaluate_quality_constitution(product_id, data_root=data_root)
        if not constitution.get("passed"):
            reasons.append("quality_constitution_failed")
            return {
                "eligible": False,
                "demo_quality": demo,
                "reasons": reasons,
                "telemetry_gates_all_passed": telemetry_all_ok,
                "marketplace_rules": rules,
            }

    if require_release_cockpit:
        cockpit = evaluate_release_cockpit(product_id, data_root=data_root)
        if cockpit.get("go_no_go") != "go":
            reasons.append("release_cockpit_no_go")
            return {
                "eligible": False,
                "demo_quality": demo,
                "reasons": reasons,
                "telemetry_gates_all_passed": telemetry_all_ok,
                "marketplace_rules": rules,
                "release_cockpit": {
                    "go_no_go": cockpit.get("go_no_go"),
                    "issues": cockpit.get("issues"),
                },
            }

    methodology = _evaluate_methodology(product_id, root, specification, qa_report)
    if require_methodology and methodology is not None and not methodology.get("passed", True):
        reasons.append("methodology_review_failed")
        for finding in methodology.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            if finding.get("severity") != "high":
                continue
            code = str(finding.get("code") or "domain_methodology_finding")[:80]
            reasons.append(f"methodology:{code}")
        return {
            "eligible": False,
            "demo_quality": demo,
            "methodology": methodology,
            "reasons": reasons,
            "telemetry_gates_all_passed": telemetry_all_ok,
            "marketplace_rules": rules,
        }

    # Hard naming quality check: no placeholder catalog titles.
    spec_name = ""
    mkt_name = ""
    if isinstance(specification, dict):
        spec_name = str(specification.get("product_name") or "").strip()
    marketing_path = root / "state" / product_id / "marketing_content.json"
    if marketing_path.is_file():
        try:
            mkt = json.loads(marketing_path.read_text(encoding="utf-8"))
            mkt_name = str(((mkt.get("marketing") or {}).get("product_name")) or "").strip()
        except Exception:
            mkt_name = ""
    candidate_name = mkt_name or spec_name
    if require_non_placeholder_name and candidate_name and is_placeholder_product_name(candidate_name):
        reasons.append("placeholder_product_name")
        return {
            "eligible": False,
            "demo_quality": demo,
            "reasons": reasons,
            "telemetry_gates_all_passed": telemetry_all_ok,
            "marketplace_rules": rules,
        }

    if require_full_qa:
        if telemetry_all_ok is not True:
            reasons.append("pipeline_qa_gates_not_passed_or_missing_telemetry")
            return {
                "eligible": False,
                "demo_quality": demo,
                "reasons": reasons,
                "telemetry_gates_all_passed": telemetry_all_ok,
                "marketplace_rules": rules,
            }

    if require_qa_realism and _has_blocking_realism_findings(qa_report):
        reasons.append("qa_realism_high_severity_failed")
        return {
            "eligible": False,
            "demo_quality": demo,
            "reasons": reasons,
            "telemetry_gates_all_passed": telemetry_all_ok,
            "design_novelty_score": novelty_score,
            "marketplace_rules": rules,
        }

    if require_release_score and release_score is not None and release_score < min_release_score:
        reasons.append("release_score_below_marketplace_minimum")
        return {
            "eligible": False,
            "demo_quality": demo,
            "reasons": reasons,
            "telemetry_gates_all_passed": telemetry_all_ok,
            "design_novelty_score": novelty_score,
            "release_score": release_score,
            "marketplace_rules": rules,
        }

    cov = demo.get("spec_coverage_pct")
    if min_cov > 0 and cov is not None and cov < min_cov:
        reasons.append("spec_coverage_below_marketplace_minimum")
        return {
            "eligible": False,
            "demo_quality": demo,
            "reasons": reasons,
            "telemetry_gates_all_passed": telemetry_all_ok,
            "marketplace_rules": rules,
        }

    if require_design_novelty and novelty_score is not None and novelty_score < min_design_novelty:
        reasons.append("design_novelty_below_marketplace_minimum")
        return {
            "eligible": False,
            "demo_quality": demo,
            "reasons": reasons,
            "telemetry_gates_all_passed": telemetry_all_ok,
            "design_novelty_score": novelty_score,
            "marketplace_rules": rules,
        }

    return {
        "eligible": True,
        "demo_quality": demo,
        "methodology": methodology,
        "reasons": [],
        "telemetry_gates_all_passed": telemetry_all_ok,
        "design_novelty_score": novelty_score,
        "release_score": release_score,
        "marketplace_rules": rules,
    }


def marketplace_listing_card_fields(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Subset safe for public JSON (scores, grade, verification flags)."""
    demo = evaluation.get("demo_quality") or {}
    return {
        "quality_score": demo.get("score"),
        "quality_grade": demo.get("grade"),
        "marketplace_verified": bool(evaluation.get("eligible")),
        "spec_coverage_pct": demo.get("spec_coverage_pct"),
        "telemetry_qa_gates_passed": evaluation.get("telemetry_gates_all_passed"),
        "release_score": evaluation.get("release_score"),
    }
