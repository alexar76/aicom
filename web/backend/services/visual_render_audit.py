"""
Visual / structural render audits for generated product previews.

Layered gates (highest level → optional extras):

1. **Static HTML** (``demo_quality`` / CI): parse ``points=`` / ``d=`` for absurd numeric literals — catches broken SVG authoring without a browser.

2. **Headless DOM** (Playwright, ``browser_preview_e2e``): ``getBBox`` / ``getBoundingClientRect`` on rendered SVG geometry — catches scaling/marker/layout explosions visible only after layout.

3. **Screenshot probe** (optional): crude viewport luminance — off by default; enable when Pillow is available and false positives are acceptable.

Env:

  ``AIFACTORY_VISUAL_DOM_AUDIT`` — ``1`` (default) run DOM audit inside browser E2E; ``0`` skip.
  ``AIFACTORY_VISUAL_SCREENSHOT_PROBE`` — ``1`` to enable dark-mass heuristic on viewport PNG (needs Pillow); default ``0``.
  ``AIFACTORY_VISUAL_HOG_ALLOW_DECORATIVE`` — ``1`` (default): ``svg_painted_viewport_hog`` on
  ``aria-hidden`` SVG is warning-only (hero backgrounds); ``0`` restores strict fail for all hog hits.
"""

from __future__ import annotations

import io
import os
import re
from typing import Any

# Same order of magnitude as demo_quality static spike — diagram UI rarely needs larger literals.
SVG_COORD_LITERAL_THRESHOLD = 12_000.0

# User-space bbox extremes (getBBox) — pathological connectors / exploded transforms.
SVG_BBOX_USER_SPACE_THRESHOLD = 12_000.0

# Fail if a single non-root SVG shape paints over most of the viewport (classic “black slab”).
SVG_VIEWPORT_AREA_HOG_RATIO = 0.48

# Warn-only path count (diagram generators rarely need hundreds of paths for a flowchart card).
SVG_PATH_COUNT_WARN = 80

VISUAL_DOM_AUDIT_JS = """() => {
  const vw = Math.max(1, window.innerWidth);
  const vh = Math.max(1, window.innerHeight);
  const vArea = vw * vh;
  const COORD = __COORD__;
  const AREA_HOG = __AREA_HOG__;
  const PATH_WARN = __PATH_WARN__;
  const findings = [];

  document.querySelectorAll('svg').forEach((svg, svgIdx) => {
    const svgDecorative =
      svg.getAttribute('aria-hidden') === 'true' ||
      !!svg.closest('[aria-hidden="true"]');
    const shapes = svg.querySelectorAll(
      'path, polygon, polyline, line, circle, ellipse, rect'
    );
    shapes.forEach((el) => {
      let b = null;
      try {
        b = el.getBBox();
      } catch (e) {
        return;
      }
      if (!b || !(typeof b.width === 'number')) return;
      const m = Math.max(
        Math.abs(b.width),
        Math.abs(b.height),
        Math.abs(b.x),
        Math.abs(b.y)
      );
      if (m > COORD) {
        findings.push({
          code: 'svg_geometry_spike',
          tag: el.tagName,
          svgIndex: svgIdx,
          w: b.width,
          h: b.height,
          x: b.x,
          y: b.y,
        });
      }
      try {
        const cr = el.getBoundingClientRect();
        const painted = Math.abs(cr.width * cr.height);
        const wide = cr.width > vw * 0.82;
        const tall = cr.height > vh * 0.82;
        if (painted > vArea * AREA_HOG && (wide || tall)) {
          findings.push({
            code: 'svg_painted_viewport_hog',
            tag: el.tagName,
            svgIndex: svgIdx,
            cw: Math.round(cr.width),
            ch: Math.round(cr.height),
            decorative: svgDecorative,
          });
        }
      } catch (e2) { /* ignore */ }
    });

    const paths = svg.querySelectorAll('path');
    if (paths.length > PATH_WARN) {
      findings.push({
        code: 'svg_excessive_path_count',
        svgIndex: svgIdx,
        n: paths.length,
      });
    }
  });

  document.querySelectorAll('canvas').forEach((c, i) => {
    if (c.width > vw * 12 || c.height > vh * 12) {
      findings.push({
        code: 'canvas_dimension_absurd',
        index: i,
        w: c.width,
        h: c.height,
      });
    }
  });

  return { viewport: { w: vw, h: vh }, findings: findings.slice(0, 64) };
}"""


def visual_dom_audit_js_payload() -> str:
    """Inject numeric thresholds into the audited script."""
    return (
        VISUAL_DOM_AUDIT_JS.replace("__COORD__", str(int(SVG_BBOX_USER_SPACE_THRESHOLD)))
        .replace("__AREA_HOG__", str(SVG_VIEWPORT_AREA_HOG_RATIO))
        .replace("__PATH_WARN__", str(SVG_PATH_COUNT_WARN))
    )


def svg_coordinate_spike_in_html(html: str, *, threshold: float = SVG_COORD_LITERAL_THRESHOLD) -> bool:
    """True if any numeric literal inside SVG ``points`` or path ``d`` blows past ``threshold``."""
    if "<svg" not in html.lower():
        return False
    num_re = re.compile(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", re.IGNORECASE)
    for svg_chunk in re.finditer(r"<svg\b[^>]*>.*?</svg>", html, flags=re.IGNORECASE | re.DOTALL):
        block = svg_chunk.group(0) or ""
        for attr in ("points", "d"):
            for m in re.finditer(rf"{attr}\s*=\s*[\"']([^\"']+)[\"']", block, flags=re.IGNORECASE):
                blob = m.group(1) or ""
                for num_m in num_re.finditer(blob):
                    try:
                        if abs(float(num_m.group(0))) > threshold:
                            return True
                    except ValueError:
                        continue
    return False


def _viewport_hog_allow_decorative() -> bool:
    return os.environ.get("AIFACTORY_VISUAL_HOG_ALLOW_DECORATIVE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def classify_visual_findings(
    findings: list[dict[str, Any]],
    *,
    delivery_profile: str | None = None,
) -> tuple[list[str], list[str], bool]:
    """
    Map structured findings to human-readable lines.

    Returns ``(fatal_issues, warnings, gate_should_fail)``.
    ``svg_excessive_path_count`` is warning-only (does not fail the gate).
    ``svg_painted_viewport_hog`` on ``aria-hidden`` decorative SVG is warning-only when
    ``AIFACTORY_VISUAL_HOG_ALLOW_DECORATIVE=1`` (default) so full-bleed hero backgrounds pass.
    """
    fatal_issues: list[str] = []
    warnings: list[str] = []
    fatal = False
    allow_decorative_hog = _viewport_hog_allow_decorative()
    for f in findings:
        code = f.get("code")
        if code == "svg_geometry_spike":
            fatal = True
            fatal_issues.append(
                "visual_svg_geometry_spike:"
                f" tag={f.get('tag')} svg#{f.get('svgIndex')} w={f.get('w')} h={f.get('h')} x={f.get('x')} y={f.get('y')}"
                f" phase={f.get('phase', '?')}"
            )
        elif code == "svg_painted_viewport_hog":
            hog_line = (
                "visual_svg_viewport_hog:"
                f" tag={f.get('tag')} svg#{f.get('svgIndex')} clientPx={f.get('cw')}x{f.get('ch')}"
                f" phase={f.get('phase', '?')}"
            )
            if allow_decorative_hog and bool(f.get("decorative")):
                warnings.append(f"{hog_line} (decorative aria-hidden SVG; review only)")
            else:
                fatal = True
                fatal_issues.append(hog_line)
        elif code == "svg_excessive_path_count":
            warnings.append(
                f"visual_svg_many_paths: svg#{f.get('svgIndex')} n={f.get('n')} (review diagram complexity)"
            )
        elif code == "canvas_dimension_absurd":
            fatal = True
            fatal_issues.append(
                f"visual_canvas_huge: canvas#{f.get('index')} {f.get('w')}x{f.get('h')} phase={f.get('phase', '?')}"
            )

    def _dedupe(lines: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for line in lines:
            if line not in seen:
                seen.add(line)
                out.append(line)
        return out

    return _dedupe(fatal_issues), _dedupe(warnings), fatal


def merge_visual_phases(
    initial: dict[str, Any],
    after_interaction: dict[str, Any],
) -> dict[str, Any]:
    """Tag and concatenate DOM audit results from load vs post-click states."""
    out_findings: list[dict[str, Any]] = []
    for f in initial.get("findings") or []:
        if isinstance(f, dict):
            ff = dict(f)
            ff["phase"] = "initial"
            out_findings.append(ff)
    for f in after_interaction.get("findings") or []:
        if isinstance(f, dict):
            ff = dict(f)
            ff["phase"] = "after_ui_clicks"
            out_findings.append(ff)
    vw = (initial.get("viewport") or {}).get("w")
    vh = (initial.get("viewport") or {}).get("h")
    return {"viewport": {"w": vw, "h": vh}, "findings": out_findings[:96]}


def screenshot_viewport_dark_mass_ratio(page: Any, *, dark_threshold: int = 80) -> float | None:
    """
    Fraction of pixels in central viewport crop that are near-black (R+G+B < dark_threshold).
    Needs Pillow; returns None if unavailable or screenshot fails.
    """
    try:
        from PIL import Image  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        png: bytes = page.screenshot(full_page=False)
        im = Image.open(io.BytesIO(png)).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    if w < 16 or h < 16:
        return None
    crop = im.crop((w // 4, h // 4, (3 * w) // 4, (3 * h) // 4))
    pixels = list(crop.getdata())
    if not pixels:
        return None
    dark = sum(1 for p in pixels if p[0] + p[1] + p[2] < dark_threshold)
    return dark / len(pixels)


def run_playwright_visual_audit(page: Any, *, phase_label: str) -> dict[str, Any]:
    """Execute DOM audit script; ``phase_label`` is informational for logging only."""
    js = visual_dom_audit_js_payload()
    raw = page.evaluate(js)
    if not isinstance(raw, dict):
        return {"phase": phase_label, "error": "audit_returned_non_object", "findings": []}
    raw["phase"] = phase_label
    return raw
