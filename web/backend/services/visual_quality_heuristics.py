"""
Static visual-quality heuristics for generated web demos (HTML/CSS/JS on disk).

Used by ``demo_quality.assess_product_demo``. Env:
- ``AIFACTORY_VISUAL_QUALITY_GATE`` — run checks (default 1).
- ``AIFACTORY_VISUAL_QUALITY_STRICT`` — fail ``quality_gates_pass`` on strict codes (default 0).
- ``AIFACTORY_VISUAL_QUALITY_APP_CHECKS`` — apply skeleton/empty/error checks only for app-like specs (default 1).

Strict failure codes when STRICT=1 are listed in ``VISUAL_STRICT_GATE_CODES``.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

# Issues that fail pipeline when AIFACTORY_VISUAL_QUALITY_STRICT=1
VISUAL_STRICT_GATE_CODES = frozenset(
    {
        "visual_missing_html_lang",
        "visual_missing_viewport_meta",
        "visual_insufficient_design_tokens",
        "visual_app_missing_skeleton",
        "visual_app_missing_empty_state",
        "visual_app_missing_error_ui",
        "visual_app_missing_toast_or_alert",
        "visual_form_without_labels",
        "visual_no_responsive_nav_mobile",
    }
)


def visual_quality_gate_enabled() -> bool:
    return os.environ.get("AIFACTORY_VISUAL_QUALITY_GATE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def visual_app_checks_enabled() -> bool:
    return os.environ.get("AIFACTORY_VISUAL_QUALITY_APP_CHECKS", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_app_like_surface(spec: Optional[dict]) -> bool:
    """Heuristic: SPA/dashboard/full_software-style UI expectations."""
    if not spec or not isinstance(spec, dict):
        return False
    if str(spec.get("delivery_profile") or "").strip().lower() == "full_software":
        return True
    blob = json.dumps(spec, ensure_ascii=False).lower()
    needles = (
        "dashboard",
        "authentication",
        "login",
        "task list",
        "settings page",
        "admin",
        "spa",
        "single-page app",
        "crud",
        "database",
        "api ",
    )
    return any(n in blob for n in needles)


def _count_css_custom_properties(css: str) -> int:
    """Distinct custom property names under :root / html { ... }."""
    css_lower = css.lower()
    # Strip comments
    css_clean = re.sub(r"/\*[^*]*\*+(?:[^/*][^*]*\*+)*/", " ", css)
    blocks = []
    for m in re.finditer(
        r"(?:^|\})\s*:root\s*\{([^}]*)\}|(?:^|\})\s*html\s*\{([^}]*)\}",
        css_clean,
        re.DOTALL | re.IGNORECASE,
    ):
        blocks.append(m.group(1) or m.group(2) or "")
    blob = "\n".join(blocks)
    names = set(re.findall(r"--([a-zA-Z0-9_-]+)\s*:", blob))
    return len(names)


def _hex_literal_count(css: str) -> int:
    return len(re.findall(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", css))


def _var_usage_count(css: str) -> int:
    return len(re.findall(r"var\s*\(\s*--", css))


def analyze_visual_quality(
    *,
    index_html: str,
    css_bundle: str,
    js_bundle: str,
    spec: Optional[dict],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not visual_quality_gate_enabled():
        return issues

    combined = f"{index_html}\n{css_bundle}\n{js_bundle}"
    lower = combined.lower()
    html_lower = index_html.lower()
    app_like = is_app_like_surface(spec) and visual_app_checks_enabled()

    # ── Universal: document baseline ─────────────────────────────────────
    if not re.search(r"<html[^>]*\blang\s*=", index_html, re.I):
        issues.append(
            {
                "code": "visual_missing_html_lang",
                "detail": "Add <html lang=\"...\"> for accessibility and predictable typography.",
            }
        )

    if 'name="viewport"' not in html_lower and "name='viewport'" not in html_lower:
        issues.append(
            {
                "code": "visual_missing_viewport_meta",
                "detail": "Missing responsive viewport meta tag (width=device-width).",
            }
        )

    n_vars = _count_css_custom_properties(css_bundle)
    if n_vars < 3:
        issues.append(
            {
                "code": "visual_insufficient_design_tokens",
                "detail": f"Expected at least 3 CSS custom properties on :root/html; found ~{n_vars}. Prefer design tokens over scattered hex colors.",
            }
        )

    hex_c = _hex_literal_count(css_bundle)
    var_c = _var_usage_count(css_bundle)
    if hex_c > 24 and var_c < 4 and n_vars < 5:
        issues.append(
            {
                "code": "visual_magic_hex_heavy",
                "detail": "CSS relies on many raw hex colors with few var(--token) usages — consolidate into tokens.",
            }
        )

    # Focus visibility (keyboard UX)
    if ":focus-visible" not in css_bundle and "focus-visible" not in css_bundle.lower():
        issues.append(
            {
                "code": "visual_weak_focus_styles",
                "detail": "No :focus-visible (or focus-visible) styles detected — add visible keyboard focus rings.",
            }
        )

    # Landmarks
    if "<main" not in html_lower and 'role="main"' not in html_lower:
        issues.append(
            {
                "code": "visual_weak_main_landmark",
                "detail": "Use a <main> landmark (or role=main) for primary content.",
            }
        )

    # Responsive media queries
    if "@media" not in css_bundle:
        issues.append(
            {
                "code": "visual_no_media_queries",
                "detail": "No @media rules — layout may break on mobile; add breakpoints.",
            }
        )

    # Mobile nav pattern
    has_nav_toggle = bool(
        re.search(
            r"(aria-expanded|menu-toggle|nav-toggle|hamburger|burger|drawer-open)",
            lower,
        )
    )
    has_mobile_mq = bool(re.search(r"@media\s*\([^)]*max-width", css_bundle, re.I))
    if app_like and has_mobile_mq and not has_nav_toggle:
        issues.append(
            {
                "code": "visual_no_responsive_nav_mobile",
                "detail": "App-like UI: add a mobile nav toggle (button with aria-expanded / hamburger) alongside breakpoints.",
            }
        )

    # Forms: inputs should have labels or aria
    input_tags = list(re.finditer(r"<input\b[^>]*>", index_html, re.I))
    bad_inputs = 0
    for m in input_tags:
        tag = m.group(0).lower()
        if "type=\"hidden\"" in tag or "type='hidden'" in tag:
            continue
        if "aria-label=" in tag or "aria-labelledby=" in tag:
            continue
        id_m = re.search(r"\bid\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        if id_m:
            iid = id_m.group(1)
            if re.search(rf"<label[^>]*\bfor\s*=\s*[\"']{re.escape(iid)}[\"']", index_html, re.I):
                continue
        # wrapped in label?
        bad_inputs += 1
        if bad_inputs >= 3:
            break
    if (app_like and bad_inputs >= 1) or (not app_like and bad_inputs >= 3):
        issues.append(
            {
                "code": "visual_form_without_labels",
                "detail": "Visible <input> elements should use <label for>, wrapping <label>, or aria-label / aria-labelledby.",
            }
        )

    # ── App-like surfaces ────────────────────────────────────────────────
    if app_like:
        skel = bool(
            re.search(
                r"(skeleton|shimmer|animate-pulse|aria-busy|data-loading|loading-state|\.pulse\b)",
                lower,
            )
        )
        if not skel:
            issues.append(
                {
                    "code": "visual_app_missing_skeleton",
                    "detail": "App-like spec: add a loading/skeleton state (aria-busy, skeleton classes, or pulse animation).",
                }
            )

        empty_ok = bool(
            re.search(
                r"(empty-state|empty_state|data-empty|no items|nothing here|nothing yet)",
                lower,
            )
        )
        if not empty_ok:
            issues.append(
                {
                    "code": "visual_app_missing_empty_state",
                    "detail": "App-like spec: add an empty state (copy + secondary action when a list has no data).",
                }
            )

        err_ok = bool(
            re.search(
                r"(role=[\"']alert[\"']|toast|snackbar|error-state|data-toast|validation-error|\.toast\b)",
                lower,
            )
        )
        if not err_ok:
            issues.append(
                {
                    "code": "visual_app_missing_error_ui",
                    "detail": "App-like spec: add error feedback (role=alert, toast container, or inline validation).",
                }
            )

        toast_ok = bool(re.search(r"(toast|snackbar|role=[\"']status[\"']|aria-live)", lower))
        if not toast_ok:
            issues.append(
                {
                    "code": "visual_app_missing_toast_or_alert",
                    "detail": "App-like spec: add non-blocking status/toast (aria-live / role=status) or snackbar pattern.",
                }
            )

    return issues


def visual_issues_penalty(issues: list[dict[str, str]]) -> int:
    """Score penalty bucket for visual codes (soft)."""
    visual_codes = {
        i["code"]
        for i in issues
        if isinstance(i, dict) and str(i.get("code", "")).startswith("visual_")
    }
    # Soft issues: fixed deduction per hit, capped
    soft = visual_codes - VISUAL_STRICT_GATE_CODES
    penalty = min(35, 3 * len(soft))
    strict_hits = visual_codes & VISUAL_STRICT_GATE_CODES
    penalty += min(40, 5 * len(strict_hits))
    return penalty
