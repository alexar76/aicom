"""
Heuristic quality checks for generated demo / sandbox HTML vs product specification.
Used to flag placeholder CTAs, broken previews, and weak spec alignment.

Pipeline integration:
  - ``quality_gates_pass()`` decides whether QA lets the product advance to security.
  - Primary: ``quality.*`` in platform YAML (Admin → Settings). Env overrides:
    ``AIFACTORY_DEMO_QUALITY_MIN_SCORE``, ``AIFACTORY_STRICT_DEMO_GATES``.
  - Visual heuristics: ``visual_quality_heuristics.py`` — ``quality.visual_quality_*`` or env
    ``AIFACTORY_VISUAL_QUALITY_GATE``, ``AIFACTORY_VISUAL_QUALITY_STRICT``, ``AIFACTORY_VISUAL_QUALITY_APP_CHECKS``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from web.backend.services.visual_render_audit import svg_coordinate_spike_in_html
from web.backend.services.visual_quality_heuristics import (
    VISUAL_STRICT_GATE_CODES,
    analyze_visual_quality,
    visual_issues_penalty,
    visual_quality_gate_enabled,
)

from core.paths import resolve_data_root
from core.quality_settings import demo_quality_min_score, strict_demo_gates, visual_quality_strict

# Shipped with the default code template; also match legacy generated files.
BANNED_PLACEHOLDER_MARKERS = (
    "Full application deployed",
    "Check the admin panel for details",
)

BANNED_SNIPPETS = (
    "onclick=\"alert('Full application deployed",
    "alert('Full application deployed",
)


def resolve_main_html_path(code_dir: Path) -> Optional[Path]:
    """Find the primary HTML entrypoint (aligned with sandbox Live Preview resolution)."""
    from web.backend.services.sandbox_static_entry import static_preview_file

    return static_preview_file(code_dir)


def _read_index_html(code_dir: Path) -> Optional[str]:
    p = resolve_main_html_path(code_dir)
    if p is None:
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_stylesheet(code_dir: Path) -> str:
    p = code_dir / "style.css"
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _hex_to_srgb(color: str) -> tuple[float, float, float] | None:
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return None
    try:
        r = int(c[0:2], 16)
        g = int(c[2:4], 16)
        b = int(c[4:6], 16)
    except ValueError:
        return None
    return (r / 255.0, g / 255.0, b / 255.0)


def _rgb_from_css_rgb_fragment(fragment: str) -> tuple[float, float, float] | None:
    m = re.search(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", fragment, flags=re.IGNORECASE)
    if not m:
        return None
    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return (max(0.0, min(1.0, r / 255.0)), max(0.0, min(1.0, g / 255.0)), max(0.0, min(1.0, b / 255.0)))


def _first_color_in_css_value(val: str) -> tuple[float, float, float] | None:
    val = val.strip()
    m = re.search(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", val)
    if m:
        rgb = _hex_to_srgb(m.group(0))
        if rgb:
            return rgb
    return _rgb_from_css_rgb_fragment(val)


def _srgb_channel_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (_srgb_channel_to_linear(rgb[0]), _srgb_channel_to_linear(rgb[1]), _srgb_channel_to_linear(rgb[2]))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(rgb1: tuple[float, float, float], rgb2: tuple[float, float, float]) -> float:
    l1 = _relative_luminance(rgb1)
    l2 = _relative_luminance(rgb2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _extract_background_rgb(decl_body: str) -> tuple[float, float, float] | None:
    decl_body_low = decl_body.lower()
    for prop in ("background-color", "background"):
        m = re.search(rf"\b{prop}\s*:\s*([^;]+)", decl_body_low)
        if not m:
            continue
        raw = m.group(1).strip()
        if raw in ("transparent", "none", "inherit", "initial"):
            continue
        # Include gradients: first #hex / rgb() stop is usually the dominant fill hue (same-line scan).
        rgb = _first_color_in_css_value(raw)
        if rgb:
            return rgb
    return None


def _extract_foreground_rgb(decl_body: str) -> tuple[float, float, float] | None:
    m = re.search(r"\bcolor\s*:\s*([^;]+)", decl_body, flags=re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).strip().lower()
    if raw in ("transparent", "inherit", "initial"):
        return None
    return _first_color_in_css_value(raw)


def _theme_body_text_fallback_for_button_var(color_decl: str) -> tuple[float, float, float] | None:
    """When `color: var(--*)` sits on a filled CTA, computed style is often dark body ink — unsafe on colored fills."""
    if "var(" not in color_decl.lower():
        return None
    return (0.29, 0.34, 0.42)


def _selector_is_button_like(selector: str) -> bool:
    s = selector.lower()
    return any(k in s for k in ("button", ".btn", ".cta", "a.cta", "a.btn"))


def _selector_is_nav_interactive(selector: str) -> bool:
    s = selector.lower().strip()
    if re.search(r"\bnav\s+a\b", s):
        return True
    if re.search(r"\bheader\s+nav\s+a\b", s):
        return True
    if re.search(r"\.nav-links?\s+a\b", s):
        return True
    if re.search(r"\.navbar\s+a\b", s):
        return True
    if re.search(r"\.nav-link\b", s):
        return True
    return False


def _darkest_header_nav_background(css_rules: str) -> tuple[float, float, float] | None:
    """Pick the darkest solid bar background from header/nav blocks (for link-only rules)."""
    darkest_l = 1.0
    darkest_rgb: tuple[float, float, float] | None = None
    for rule in re.finditer(r"([^{}]+)\{([^{}]+)\}", css_rules, flags=re.DOTALL):
        selector = (rule.group(1) or "").lower()
        if not re.search(r"\b(header|nav)\b|\.header\b|\.navbar\b|\.site-header\b", selector):
            continue
        body = rule.group(2) or ""
        bg = _extract_background_rgb(body)
        if not bg:
            continue
        lum = _relative_luminance(bg)
        if lum < darkest_l:
            darkest_l = lum
            darkest_rgb = bg
    if darkest_rgb is not None and darkest_l < 0.18:
        return darkest_rgb
    return None


def _collect_css_rules(index_html: str, css_text: str) -> str:
    chunks = [css_text or ""]
    for m in re.finditer(r"<style[^>]*>(.*?)</style>", index_html, flags=re.IGNORECASE | re.DOTALL):
        chunks.append(m.group(1) or "")
    return "\n".join(chunks)


def _read_app_js(code_dir: Path) -> str:
    p = code_dir / "app.js"
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _inline_scripts_from_html(index_html: str) -> str:
    parts: list[str] = []
    for m in re.finditer(r"<script([^>]*)>([\s\S]*?)</script>", index_html, re.I):
        attrs = m.group(1) or ""
        if re.search(r"\bsrc\s*=", attrs, re.I):
            continue
        parts.append(m.group(2) or "")
    return "\n".join(parts)


_TEXT_ARTIFACT_SUFFIXES = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".env",
    ".yml",
    ".yaml",
    ".toml",
}
_SKIP_ARTIFACT_PARTS = {
    ".git",
    "node_modules",
    "dist-info",
    "__pycache__",
    ".venv",
    "venv",
}
_LOOPBACK_URL_RE = re.compile(
    r"(?:https?:)?//(?:localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(?::\d+)?",
    re.IGNORECASE,
)
_HTML_LINK_ATTR_RE = re.compile(
    r"\b(href|src|action|data-src|poster)\s*=\s*([\"'])([^\"']+)\2",
    re.IGNORECASE,
)
_HTML_ID_RE = re.compile(r"\bid\s*=\s*([\"'])([^\"']+)\1", re.IGNORECASE)
_FILELIKE_LINK_SUFFIXES = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".mjs",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".pdf",
}


def _iter_text_artifacts(code_dir: Path):
    if not code_dir.is_dir():
        return
    for p in sorted(code_dir.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _SKIP_ARTIFACT_PARTS for part in p.parts):
            continue
        if p.suffix.lower() not in _TEXT_ARTIFACT_SUFFIXES and p.name != ".env":
            continue
        try:
            rel = p.relative_to(code_dir).as_posix()
        except ValueError:
            rel = p.name
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        yield rel, p, text


def _detect_loopback_artifact_urls(code_dir: Path) -> list[str]:
    offenders: list[str] = []
    for rel, _p, text in _iter_text_artifacts(code_dir) or []:
        if _LOOPBACK_URL_RE.search(text):
            offenders.append(rel)
            if len(offenders) >= 5:
                break
    return offenders


def _link_target_path(html_file: Path, raw_url: str) -> Path | None:
    url = (raw_url or "").strip()
    if not url:
        return None
    low = url.lower()
    if low.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "blob:", "http://", "https://", "//")):
        return None
    if url.startswith("/"):
        return None

    path_part = url.split("#", 1)[0].split("?", 1)[0]
    if not path_part or path_part.endswith("/"):
        return None
    suffix = Path(path_part).suffix.lower()
    if suffix not in _FILELIKE_LINK_SUFFIXES:
        return None
    return (html_file.parent / path_part).resolve()


def _detect_broken_internal_links(code_dir: Path) -> list[str]:
    broken: list[str] = []
    code_root = code_dir.resolve()
    for rel, html_file, text in _iter_text_artifacts(code_dir) or []:
        if html_file.suffix.lower() not in (".html", ".htm"):
            continue
        ids = {m.group(2) for m in _HTML_ID_RE.finditer(text)}
        for m in _HTML_LINK_ATTR_RE.finditer(text):
            attr = (m.group(1) or "").lower()
            url = (m.group(3) or "").strip()
            if url.startswith("#") and len(url) > 1:
                anchor = url[1:].split("?", 1)[0]
                if anchor and anchor not in ids:
                    broken.append(f"{rel}: {attr}={url!r} points to missing in-page anchor")
                    if len(broken) >= 8:
                        return broken
                continue
            target = _link_target_path(html_file, url)
            if target is None:
                continue
            try:
                target.relative_to(code_root)
            except ValueError:
                broken.append(f"{rel}: {attr}={url!r} escapes code directory")
                if len(broken) >= 8:
                    return broken
                continue
            if not target.is_file():
                broken.append(f"{rel}: {attr}={url!r} target file is missing")
                if len(broken) >= 8:
                    return broken
    return broken


def _has_low_contrast_cta(index_html: str, css_rules: str) -> bool:
    """
    WCAG-style contrast heuristics on extracted CSS (hex + rgb).

    Previously we only flagged «dark fill + dark text» on .btn/button — that missed
    pale-on-bright CTAs and muted nav links on dark headers (fixed separately via bar bg).
    """
    bar_bg = _darkest_header_nav_background(css_rules)

    for rule in re.finditer(r"([^{}]+)\{([^{}]+)\}", css_rules, flags=re.DOTALL):
        selector = rule.group(1) or ""
        body = rule.group(2) or ""

        if not (_selector_is_button_like(selector) or _selector_is_nav_interactive(selector)):
            continue

        bg = _extract_background_rgb(body)
        fg = _extract_foreground_rgb(body)
        if fg is None and _selector_is_button_like(selector):
            m_col = re.search(r"\bcolor\s*:\s*([^;]+)", body, flags=re.IGNORECASE)
            if m_col:
                fg = _theme_body_text_fallback_for_button_var(m_col.group(1) or "")

        if bg and fg:
            ratio = _contrast_ratio(fg, bg)
            if _selector_is_button_like(selector) and ratio < 3.0:
                return True
            if _selector_is_nav_interactive(selector) and ratio < 4.5:
                return True
            continue

        # Nav/header links often set only `color`; compare against the darkest header/nav bar.
        if bar_bg and fg and not bg and _selector_is_nav_interactive(selector):
            if _contrast_ratio(fg, bar_bg) < 4.5:
                return True

    # Inline style fallback for explicit CTA copy.
    cta_inline = re.finditer(
        r"<(?:a|button)[^>]*?(?:start free|try free|get started|book demo)[^>]*?>",
        index_html,
        flags=re.IGNORECASE,
    )
    for node in cta_inline:
        tag = node.group(0) or ""
        bg = _extract_background_rgb(tag)
        fg = _extract_foreground_rgb(tag)
        if bg and fg and _contrast_ratio(fg, bg) < 3.0:
            return True

    return False


def _cta_dead_hash_link(index_html: str) -> bool:
    """
    Flag links that look like primary conversion CTAs but use href='#' (no destination).
    Users expect mailto:, https:, tel:, or a same-page section id.
    """
    if not index_html.strip():
        return False
    trial_pat = r"(?:trial|free\s+trial|try\s+free|start\s+free|get\s+started|sign\s*up|book\s+demo|contact)"

    def _link_body_is_suspicious(body: str) -> bool:
        b = (body or "").lower()
        return bool(re.search(trial_pat, b, re.I))

    for m in re.finditer(
        r'<a\s+[^>]*href\s*=\s*["\']([^"\']*)["\'][^>]*>([\s\S]*?)</a>',
        index_html,
        re.I,
    ):
        href = (m.group(1) or "").strip()
        inner = m.group(2) or ""
        if href in ("#", "/#", ""):
            if _link_body_is_suspicious(re.sub(r"<[^>]+>", " ", inner)):
                return True
    return False


def _spec_keywords(spec: Optional[dict]) -> list[str]:
    if not spec or not isinstance(spec, dict):
        return []
    out: list[str] = []
    for f in spec.get("core_features") or []:
        if isinstance(f, dict):
            for k in ("name", "description"):
                v = f.get(k)
                if isinstance(v, str) and len(v) > 2:
                    out.append(v.lower())
    for fr in spec.get("functional_requirements") or []:
        if isinstance(fr, dict):
            for k in ("id", "title", "description", "acceptance_criteria"):
                v = fr.get(k)
                if isinstance(v, str) and len(v) > 2:
                    out.append(v.lower())
    for p in spec.get("personas") or []:
        if isinstance(p, dict):
            for k in ("name", "context"):
                v = p.get(k)
                if isinstance(v, str) and len(v) > 2:
                    out.append(v.lower())
            for job in p.get("jobs_to_be_done") or []:
                if isinstance(job, str) and len(job) > 3:
                    out.append(job.lower())
    for us in spec.get("user_stories") or []:
        if isinstance(us, dict):
            s = us.get("story")
            if isinstance(s, str) and len(s) > 3:
                out.append(s.lower())
    desc = spec.get("description")
    if isinstance(desc, str) and len(desc) > 5:
        out.append(desc.lower())
    # de-dup short tokens
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        t = t.strip()
        if len(t) < 4 or t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    return uniq[:24]


def _coverage_score(index_lower: str, keywords: list[str]) -> int:
    if not keywords:
        return 0
    hits = 0
    for kw in keywords:
        if len(kw) < 5:
            continue
        if kw in index_lower:
            hits += 1
    return int(min(100, round(100 * hits / max(1, len(keywords)))))


def assess_product_demo(
    product_id: str,
    spec: Optional[dict] = None,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """
    Return a small report: score 0–100, human-readable issues, spec coverage heuristic.
    """
    from core.delivery_profile import DESKTOP_APP, normalize_delivery_profile
    from web.backend.services.desktop_product import assess_desktop_product_demo

    dp = normalize_delivery_profile(str((spec or {}).get("delivery_profile") or "")) if isinstance(spec, dict) else None
    if dp == DESKTOP_APP:
        return assess_desktop_product_demo(product_id, spec=spec, data_root=data_root)

    code_dir = resolve_data_root(data_root) / "code" / product_id
    issues: list[dict[str, str]] = []
    index_html = _read_index_html(code_dir)
    css_text = _read_stylesheet(code_dir)

    if not code_dir.is_dir():
        return {
            "score": 0,
            "grade": "F",
            "sandbox_ready": False,
            "has_index_html": False,
            "issues": [{"code": "no_code_dir", "detail": "No generated code directory"}],
            "spec_coverage_pct": None,
            "has_code_dir": False,
        }

    if not index_html:
        return {
            "score": 10,
            "grade": "F",
            "sandbox_ready": False,
            "has_index_html": False,
            "has_code_dir": True,
            "issues": [{"code": "no_index_html", "detail": "Missing index.html — preview cannot load a main page"}],
            "spec_coverage_pct": None,
        }

    lower = index_html.lower()
    for snippet in BANNED_SNIPPETS:
        if snippet.lower() in lower:
            issues.append(
                {
                    "code": "placeholder_cta",
                    "detail": "Template «fake launch» / alert remains in index.html — replace with real UI",
                }
            )
            break

    for marker in BANNED_PLACEHOLDER_MARKERS[:2]:
        if marker in index_html:
            issues.append(
                {
                    "code": "marketing_stub",
                    "detail": f"Stub phrase present: «{marker}»",
                }
            )

    # Root-absolute asset paths often break inside sandbox iframe
    if re.search(r'(?:src|href)\s*=\s*["\']/(?!/)', index_html):
        issues.append(
            {
                "code": "root_absolute_paths",
                "detail": "Uses absolute /… asset URLs — may render blank in sandbox; prefer relative paths or same-folder assets",
            }
        )

    # localhost / protocol-relative loopback escapes the iframe (browser opens the viewer's machine).
    _lh = r"(?:127\.0\.0\.1|localhost|\[::1\])"
    localhost_offenders = _detect_loopback_artifact_urls(code_dir)
    if localhost_offenders or re.search(
        rf'(?:src|href)\s*=\s*["\'](?:https?://{_lh}(?::\d+)?|//{_lh}(?::\d+)?)',
        index_html,
        re.I,
    ) or re.search(rf"\burl\s*\(\s*[\"']?//{_lh}(?::\d+)?", index_html, re.I):
        detail = (
            "Links, scripts, styles, or config target loopback hosts — preview leaves our origin "
            "and hits the viewer's PC; use relative paths, same-origin /api calls, or sandbox proxy paths."
        )
        if localhost_offenders:
            detail += " Offending artifacts: " + ", ".join(localhost_offenders)
        issues.append(
            {
                "code": "sandbox_localhost_urls",
                "detail": detail,
            }
        )

    broken_internal_links = _detect_broken_internal_links(code_dir)
    if broken_internal_links:
        issues.append(
            {
                "code": "broken_internal_link",
                "detail": "Broken internal sandbox links detected: " + "; ".join(broken_internal_links),
            }
        )

    from core.public_site_url import audit_watermark_links_in_tree

    issues.extend(audit_watermark_links_in_tree(code_dir))

    if svg_coordinate_spike_in_html(index_html):
        issues.append(
            {
                "code": "svg_coordinate_spike",
                "detail": "SVG paths/points contain extreme coordinates — diagram connectors may render as garbage in-browser",
            }
        )

    if len(index_html.strip()) < 200:
        issues.append({"code": "tiny_html", "detail": "index.html is very short — likely incomplete"})

    # UX baseline: avoid bare template pages with no meaningful product surface.
    section_count = len(re.findall(r"<section\b", lower))
    has_cta = bool(re.search(r"<button\b|cta|start free|try free|get started|book demo|sign up", lower))
    has_form = "<form" in lower
    if section_count < 1:
        issues.append(
            {
                "code": "ux_structure_thin",
                "detail": "UI has too few sections; looks like a thin template instead of a sellable product page.",
            }
        )
    if not has_cta:
        issues.append(
            {
                "code": "ux_missing_cta",
                "detail": "No clear CTA/button detected; conversion path is unclear.",
            }
        )
    if not has_form and "login" in lower and "register" in lower:
        issues.append(
            {
                "code": "ux_auth_flow_thin",
                "detail": "Auth intent is visible but no actual form flow detected in HTML.",
            }
        )
    css_rules = _collect_css_rules(index_html, css_text)
    if _has_low_contrast_cta(index_html, css_rules):
        issues.append(
            {
                "code": "ux_low_contrast_cta",
                "detail": "Text/fill contrast is too low on buttons or header/nav (WCAG-style ratio check on static CSS).",
            }
        )

    if _cta_dead_hash_link(index_html):
        issues.append(
            {
                "code": "cta_dead_hash_link",
                "detail": "Primary CTA uses href=\"#\" — use mailto:, tel:, https://, or an in-page anchor (#pricing) that exists; dead links fail users.",
            }
        )

    spec_keywords = _spec_keywords(spec)
    coverage = _coverage_score(lower, spec_keywords) if spec_keywords else None
    if spec_keywords and coverage is not None and coverage < 25:
        issues.append(
            {
                "code": "low_spec_alignment",
                "detail": "Demo page mentions few concepts from the written specification — review PM vs dev output",
            }
        )

    if visual_quality_gate_enabled():
        css_bundle = _collect_css_rules(index_html, css_text)
        js_bundle = (_read_app_js(code_dir) + "\n" + _inline_scripts_from_html(index_html)).strip()
        issues.extend(
            analyze_visual_quality(
                index_html=index_html,
                css_bundle=css_bundle,
                js_bundle=js_bundle,
                spec=spec,
            )
        )

    # Score
    score = 100
    score -= 25 * sum(1 for i in issues if i["code"] in ("placeholder_cta", "marketing_stub"))
    score -= 10 * sum(
        1 for i in issues if i["code"] in ("root_absolute_paths", "sandbox_localhost_urls")
    )
    score -= 12 if any(i["code"] == "svg_coordinate_spike" for i in issues) else 0
    score -= 15 if any(i["code"] == "tiny_html" for i in issues) else 0
    score -= 10 if any(i["code"] == "low_spec_alignment" for i in issues) else 0
    score -= 12 * sum(1 for i in issues if i["code"] in ("ux_structure_thin", "ux_missing_cta"))
    score -= 14 if any(i["code"] == "ux_low_contrast_cta" for i in issues) else 0
    score -= 12 if any(i["code"] == "cta_dead_hash_link" for i in issues) else 0
    score -= 18 if any(i["code"] == "broken_internal_link" for i in issues) else 0
    score -= 20 if any(i["code"] == "watermark_wrong_public_url" for i in issues) else 0
    score -= 8 if any(i["code"] == "ux_auth_flow_thin" for i in issues) else 0
    score = max(0, min(100, score))
    score -= visual_issues_penalty(issues)
    score = max(0, min(100, score))

    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "sandbox_ready": len(index_html.strip()) > 0 and not any(
            i["code"] in ("placeholder_cta", "marketing_stub") for i in issues
        ),
        "has_index_html": True,
        "has_code_dir": True,
        "issues": issues,
        "spec_coverage_pct": coverage,
    }


# Fail the pipeline QA stage if any of these issue codes appear (demo not shippable).
CRITICAL_ISSUE_CODES = frozenset(
    {
        "placeholder_cta",
        "marketing_stub",
        "no_index_html",
        "no_code_dir",
        "sandbox_localhost_urls",
        "broken_internal_link",
        "watermark_wrong_public_url",
        "ux_low_contrast_cta",
        "cta_dead_hash_link",
    }
)

# Brochure / marketing_landing: hash CTAs and soft alignment hints are common; do not block ship.
LANDING_NON_BLOCKING_ISSUE_CODES = frozenset(
    {
        "cta_dead_hash_link",
        "low_spec_alignment",
        "visual_weak_focus_styles",
    }
)


def quality_gates_pass(report: dict[str, Any], *, delivery_profile: str | None = None) -> bool:
    """Return True if demo/TZ gates allow advancing past QA (to security)."""
    from core.delivery_profile import DESKTOP_APP, MARKETING_LANDING, normalize_delivery_profile

    strict = strict_demo_gates()
    visual_strict = visual_quality_strict()
    min_score = demo_quality_min_score()
    profile = normalize_delivery_profile(delivery_profile)
    landing = profile == MARKETING_LANDING
    desktop = profile == DESKTOP_APP
    if landing:
        min_score = min(min_score, max(0, int(os.environ.get("AIFACTORY_LANDING_DEMO_MIN_SCORE", "45") or 45)))
    if desktop:
        min_score = min(min_score, max(0, int(os.environ.get("AIFACTORY_DESKTOP_DEMO_MIN_SCORE", "50") or 50)))

    if report.get("score", 0) < min_score:
        return False

    codes = {i.get("code") for i in report.get("issues", []) if isinstance(i, dict)}
    critical = CRITICAL_ISSUE_CODES
    if landing:
        critical = critical - LANDING_NON_BLOCKING_ISSUE_CODES
    if desktop:
        critical = critical - frozenset({"no_index_html", "sandbox_localhost_urls", "broken_internal_link", "tiny_html"})
    if codes & critical:
        return False

    if visual_strict and codes & VISUAL_STRICT_GATE_CODES:
        return False

    if strict:
        if any(
            i.get("code") in ("root_absolute_paths", "sandbox_localhost_urls", "broken_internal_link")
            for i in report.get("issues", [])
            if isinstance(i, dict)
        ):
            return False
        if any(i.get("code") == "tiny_html" for i in report.get("issues", []) if isinstance(i, dict)):
            return False
        if any(i.get("code") == "ux_structure_thin" for i in report.get("issues", []) if isinstance(i, dict)):
            return False

    if not report.get("has_index_html", True) and not desktop:
        return False

    if desktop and not report.get("desktop_ready", True):
        return False

    return True
