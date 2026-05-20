"""
Build storefront sandbox previews from PM specification when on-disk code is the
factory placeholder bundle (LLM fallback / stub developer output).

Materializes differentiated HTML to disk so sandboxes and git show real product pages.
"""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from core.delivery_profile import MARKETING_LANDING, normalize_delivery_profile
from core.logging_utils import log_suppressed
from core.paths import code_dir, specs_dir

logger = logging.getLogger(__name__)

_BOILERPLATE_MARKERS = (
    "shipped preview bundle",
    "illustrative capability cards",
    "explore capability cards",
    "a modern web application built by the ai-factory pipeline",
)

_HEX_RE = re.compile(r"#([0-9a-fA-F]{3,8})\b")

_NAMED_PALETTES: dict[str, tuple[str, str]] = {
    "terracotta": ("#c4725a", "#3d4f2f"),
    "olive": ("#3d4f2f", "#c4725a"),
    "cyan": ("#0a2540", "#00d4aa"),
    "navy": ("#0a2540", "#00d4aa"),
    "emerald": ("#064e3b", "#34d399"),
    "gold": ("#1a1208", "#d4a853"),
    "coral": ("#2d1b1b", "#ff6b6b"),
    "lavender": ("#1e1b2e", "#a78bfa"),
    "rose": ("#2a1520", "#fb7185"),
    "slate": ("#0f172a", "#38bdf8"),
}


def is_factory_boilerplate_index(html_text: str) -> bool:
    if not html_text or len(html_text) < 200:
        return False
    low = html_text.lower()
    hits = sum(1 for m in _BOILERPLATE_MARKERS if m in low)
    return hits >= 2


def _inner_from_spec_blob(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    inner = raw.get("specification")
    if isinstance(inner, dict) and inner:
        return inner
    if raw.get("product_name") or raw.get("description"):
        return raw
    return None


def _load_spec_from_sqlite(product_id: str) -> Optional[dict[str, Any]]:
    """PM spec or pipeline idea when specs/ dir is missing (SQLite-only products)."""
    try:
        import sqlite3

        from core.paths import pipeline_db_path

        db_path = pipeline_db_path()
        if not db_path.is_file():
            return None
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT idea, spec FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        if not row:
            return None
        idea, spec_raw = row[0], row[1]
        if spec_raw:
            try:
                parsed = json.loads(spec_raw) if isinstance(spec_raw, str) else spec_raw
                inner = _inner_from_spec_blob(parsed)
                if inner:
                    return inner
            except (TypeError, json.JSONDecodeError) as exc:
                log_suppressed(logger, "sandbox_spec_landing sqlite spec", exc_info=exc)
        idea_text = (idea or "").strip()
        if not idea_text:
            return None
        from web.backend.services.product_naming import _derive_from_idea

        return {
            "product_name": _derive_from_idea(idea_text),
            "description": idea_text,
            "core_features": [
                {"name": "Overview", "description": idea_text[:800]},
            ],
        }
    except Exception as exc:
        log_suppressed(logger, "sandbox_spec_landing sqlite", exc_info=exc)
        return None


def _minimal_spec_from_index_html(product_id: str) -> Optional[dict[str, Any]]:
    """Use title/h1 from on-disk index when spec artifacts are missing."""
    idx = code_dir(product_id) / "index.html"
    if not idx.is_file():
        return None
    try:
        text = idx.read_text(encoding="utf-8")
    except OSError:
        return None
    title = ""
    m = re.search(r"<title[^>]*>([^<]+)</title>", text, re.I)
    if m:
        title = html.unescape(m.group(1).strip())
    if not title or title.lower().startswith("product "):
        m = re.search(r"<h1[^>]*>([^<]+)</h1>", text, re.I)
        if m:
            title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip())
    if not title:
        return None
    return {
        "product_name": title,
        "description": f"Preview for {title}.",
        "core_features": [{"name": "Product", "description": title}],
    }


def _load_spec_inner(product_id: str) -> Optional[dict[str, Any]]:
    spec_path = specs_dir(product_id) / "specification.json"
    if spec_path.is_file():
        try:
            raw = json.loads(spec_path.read_text(encoding="utf-8"))
            inner = _inner_from_spec_blob(raw)
            if inner:
                return inner
        except (OSError, json.JSONDecodeError) as exc:
            log_suppressed(logger, "sandbox_spec_landing read spec", exc_info=exc)
    inner = _load_spec_from_sqlite(product_id)
    if inner:
        return inner
    return _minimal_spec_from_index_html(product_id)


def _short_tagline(description: str, *, max_len: int = 200) -> str:
    text = (description or "").strip()
    if not text:
        return ""
    for sep in (". ", ".\n", "! ", "? "):
        idx = text.find(sep)
        if 0 < idx < max_len:
            return text[: idx + 1].strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return (cut or text[:max_len]).strip() + "…"


def _extract_palette(description: str) -> tuple[str, str, str]:
    """primary, accent, background tint."""
    found = _HEX_RE.findall(description or "")
    if len(found) >= 2:
        return f"#{found[0]}", f"#{found[1]}", f"#{found[0]}"
    low = (description or "").lower()
    for name, pair in _NAMED_PALETTES.items():
        if name in low:
            return pair[0], pair[1], pair[0]
    if "dark blue" in low or "navy" in low:
        return "#0a2540", "#00d4aa", "#0a2540"
    if "warm" in low and "terracotta" in low:
        return "#c4725a", "#3d4f2f", "#2a1810"
    return "#0f172a", "#6366f1", "#0f172a"


def _heading_font(description: str) -> str:
    low = (description or "").lower()
    if "serif" in low or "hand-drawn" in low:
        return "'Playfair Display', Georgia, serif"
    if "mono" in low:
        return "'JetBrains Mono', monospace"
    return "'Inter', system-ui, sans-serif"


def _hero_headline(spec: dict[str, Any]) -> str:
    for feat in spec.get("core_features") or []:
        if not isinstance(feat, dict):
            continue
        desc = str(feat.get("description") or "")
        m = re.search(r"headline\s+['\"]([^'\"]+)['\"]", desc, re.I)
        if m:
            return m.group(1).strip()
        m = re.search(r"['\"]([^'\"]{8,60})['\"]", desc)
        if m and "pass" in m.group(1).lower():
            return m.group(1).strip()
    name = str(spec.get("product_name") or "").strip()
    if name:
        return name
    return "Welcome"


def _feature_cards(spec: dict[str, Any]) -> list[tuple[str, str, str]]:
    """title, body, icon emoji."""
    icons = ("✦", "◆", "●", "▲", "★", "◎", "◇", "○")
    out: list[tuple[str, str, str]] = []
    for i, item in enumerate(spec.get("core_features") or []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("name") or "").strip()
        desc = str(item.get("description") or "").strip()
        if not title:
            continue
        low = title.lower()
        if "pricing" in low:
            continue
        icon = icons[i % len(icons)]
        body = _short_tagline(desc, max_len=140) if desc else ""
        out.append((title, body, icon))
    return out[:6]


def _pricing_cards(spec: dict[str, Any]) -> list[tuple[str, str, str, bool]]:
    """name, price, blurb, is_featured."""
    cards: list[tuple[str, str, str, bool]] = []
    for item in spec.get("core_features") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("name") or "")
        if "pricing" not in title.lower():
            continue
        desc = str(item.get("description") or "")
        for m in re.finditer(
            r"['\"]?([A-Za-z][\w\s]{2,30} Pass)['\"]?\s*\(([^)]+)\)", desc
        ):
            tier, meta = m.group(1).strip(), m.group(2).strip()
            price_m = re.search(r"\$[\d,]+", meta)
            price = price_m.group(0) if price_m else meta
            featured = "premium" in tier.lower() or "best value" in desc.lower()
            cards.append((tier, price, meta, featured))
        if not cards:
            cards.append(("Starter", "$199", _short_tagline(desc, max_len=80), False))
            cards.append(("Premium", "$349", "Best value · more perks", True))
        break
    return cards[:3]


def build_spec_landing_html_from_spec(
    product_id: str,
    spec: dict[str, Any],
    *,
    subtle_banner: bool = True,
) -> str:
    profile = normalize_delivery_profile(str(spec.get("delivery_profile") or MARKETING_LANDING))
    product_name = html.escape(str(spec.get("product_name") or product_id))
    description = str(spec.get("description") or "").strip()
    tagline = html.escape(_short_tagline(description))
    audience = html.escape(str(spec.get("target_audience") or ""))
    primary, accent, bg_tint = _extract_palette(description)
    head_font = _heading_font(description)
    hero_title = html.escape(_hero_headline(spec))

    features = _feature_cards(spec)
    feature_html = ""
    for title, body, icon in features:
        body_p = f'<p class="feat-p">{html.escape(body)}</p>' if body else ""
        feature_html += f"""
        <article class="feat">
          <span class="feat-icon" aria-hidden="true">{icon}</span>
          <h3>{html.escape(title)}</h3>
          {body_p}
        </article>"""

    pricing = _pricing_cards(spec)
    pricing_html = ""
    if pricing:
        tier_cards = ""
        for name, price, blurb, featured in pricing:
            cls = "price-card featured" if featured else "price-card"
            badge = '<span class="price-badge">Best value</span>' if featured else ""
            tier_cards += f"""
            <article class="{cls}">
              {badge}
              <h3>{html.escape(name)}</h3>
              <p class="price-amt">{html.escape(price)}</p>
              <p class="price-blurb">{html.escape(blurb)}</p>
              <a class="price-cta" href="#book">Choose plan</a>
            </article>"""
        pricing_html = f"""
    <section id="pricing" class="section pricing-section">
      <h2>Plans</h2>
      <div class="price-grid">{tier_cards}</div>
    </section>"""

    cta_label = "Book a demo" if "demo" in description.lower() else "Get started"
    if "pass" in description.lower() or "book" in description.lower():
        cta_label = "Get your pass"

    banner = ""
    if subtle_banner:
        banner = (
            '<p class="preview-note">AI-Factory product preview · built from your PM specification</p>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{product_name}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --primary: {primary};
      --accent: {accent};
      --bg-deep: color-mix(in srgb, {bg_tint} 88%, #000);
      --card: rgba(255,255,255,0.07);
      --text: #f8fafc;
      --muted: color-mix(in srgb, var(--text) 65%, transparent);
      --head-font: {head_font};
      --body-font: 'Inter', system-ui, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--body-font);
      background: var(--bg-deep);
      background-image:
        radial-gradient(ellipse 80% 50% at 50% -10%, color-mix(in srgb, var(--accent) 35%, transparent), transparent),
        radial-gradient(circle at 100% 100%, color-mix(in srgb, var(--primary) 40%, transparent), transparent 50%);
      color: var(--text);
      line-height: 1.55;
      min-height: 100vh;
    }}
    .preview-note {{
      text-align: center;
      font-size: 0.7rem;
      color: var(--muted);
      padding: 0.4rem 1rem;
      opacity: 0.85;
    }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 0 1.25rem 5rem; }}
    .hero {{
      text-align: center;
      padding: 3.5rem 1rem 3rem;
      position: relative;
    }}
    .hero::before {{
      content: '';
      position: absolute;
      inset: 10% 5% auto;
      height: 55%;
      background: repeating-linear-gradient(
        45deg,
        color-mix(in srgb, var(--accent) 12%, transparent) 0 12px,
        transparent 12px 24px
      );
      border-radius: 24px;
      opacity: 0.5;
      z-index: 0;
    }}
    .hero > * {{ position: relative; z-index: 1; }}
    .badge {{
      display: inline-block;
      padding: 0.35rem 0.9rem;
      border-radius: 999px;
      background: color-mix(in srgb, var(--accent) 22%, transparent);
      border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
      font-size: 0.7rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 1.25rem;
      font-weight: 600;
    }}
    h1 {{
      font-family: var(--head-font);
      font-size: clamp(2.25rem, 6vw, 3.5rem);
      font-weight: 700;
      line-height: 1.08;
      margin-bottom: 1rem;
      color: var(--text);
    }}
    .lead {{ color: var(--muted); font-size: 1.125rem; max-width: 640px; margin: 0 auto 1rem; }}
    .audience {{ color: var(--muted); font-size: 0.875rem; margin-bottom: 2rem; }}
    .cta {{
      display: inline-block;
      padding: 1rem 2rem;
      border-radius: 999px;
      background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--primary) 60%, var(--accent)));
      color: #fff;
      font-weight: 700;
      text-decoration: none;
      box-shadow: 0 12px 40px color-mix(in srgb, var(--accent) 45%, transparent);
      transition: transform 0.2s ease;
    }}
    .cta:hover {{ transform: translateY(-2px); }}
    .section {{ margin-top: 3.5rem; }}
    h2 {{
      font-family: var(--head-font);
      font-size: 1.75rem;
      margin-bottom: 1.25rem;
      text-align: center;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1.25rem;
    }}
    .feat {{
      background: var(--card);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 16px;
      padding: 1.5rem;
      backdrop-filter: blur(8px);
    }}
    .feat-icon {{
      display: block;
      font-size: 1.5rem;
      color: var(--accent);
      margin-bottom: 0.75rem;
    }}
    .feat h3 {{
      font-family: var(--head-font);
      font-size: 1.1rem;
      margin-bottom: 0.5rem;
      color: var(--text);
    }}
    .feat-p {{ color: var(--muted); font-size: 0.875rem; }}
    .price-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1.25rem;
      max-width: 720px;
      margin: 0 auto;
    }}
    .price-card {{
      background: var(--card);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 20px;
      padding: 1.75rem;
      text-align: center;
      position: relative;
    }}
    .price-card.featured {{
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent), 0 16px 48px color-mix(in srgb, var(--accent) 25%, transparent);
    }}
    .price-badge {{
      position: absolute;
      top: -10px;
      left: 50%;
      transform: translateX(-50%);
      background: var(--accent);
      color: #111;
      font-size: 0.65rem;
      font-weight: 700;
      padding: 0.25rem 0.65rem;
      border-radius: 999px;
      text-transform: uppercase;
    }}
    .price-amt {{ font-size: 2rem; font-weight: 800; margin: 0.75rem 0; color: var(--accent); }}
    .price-blurb {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 1rem; }}
    .price-cta {{
      display: inline-block;
      padding: 0.6rem 1.25rem;
      border-radius: 10px;
      border: 1px solid var(--accent);
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
      font-size: 0.875rem;
    }}
    .sticky-cta {{
      display: none;
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      padding: 0.75rem 1rem;
      background: color-mix(in srgb, var(--bg-deep) 92%, #000);
      border-top: 1px solid rgba(255,255,255,0.12);
      z-index: 100;
      text-align: center;
    }}
    .sticky-cta a {{
      display: block;
      padding: 0.85rem;
      background: var(--accent);
      color: #111;
      font-weight: 700;
      border-radius: 12px;
      text-decoration: none;
    }}
    @media (max-width: 768px) {{
      .sticky-cta {{ display: block; }}
      body {{ padding-bottom: 4.5rem; }}
    }}
    footer {{
      margin-top: 4rem;
      text-align: center;
      color: var(--muted);
      font-size: 0.75rem;
    }}
  </style>
</head>
<body>
  {banner}
  <main class="wrap">
    <section class="hero">
      <span class="badge">{html.escape(profile.replace('_', ' '))}</span>
      <h1>{hero_title}</h1>
      <p class="lead">{tagline}</p>
      {f'<p class="audience">For {audience}</p>' if audience else ''}
      <a class="cta" href="#pricing">{html.escape(cta_label)}</a>
    </section>
    <section id="features" class="section">
      <h2>What you get</h2>
      <div class="grid">{feature_html}</div>
    </section>
    {pricing_html}
    <footer id="book">{html.escape(product_id)} · AI-Factory</footer>
  </main>
  <div class="sticky-cta"><a href="#book">Book your spot</a></div>
</body>
</html>"""


def build_spec_landing_html(product_id: str) -> Optional[str]:
    spec = _load_spec_inner(product_id)
    if not spec:
        return None
    return build_spec_landing_html_from_spec(product_id, spec)


def materialize_spec_landing_on_disk(product_id: str, *, code_root: Path | None = None) -> bool:
    """
    Replace factory boilerplate index.html with a spec-built landing on disk.
    Returns True when a new file was written.
    """
    root = code_root or code_dir(product_id)
    idx = root / "index.html"
    if not idx.is_file():
        return False
    try:
        current = idx.read_text(encoding="utf-8")
    except OSError:
        return False
    if not is_factory_boilerplate_index(current):
        return False
    built = build_spec_landing_html(product_id)
    if not built:
        return False
    try:
        idx.write_text(built, encoding="utf-8")
        logger.info("materialize_spec_landing_on_disk %s (%d bytes)", product_id, len(built))
        return True
    except OSError as exc:
        log_suppressed(logger, "materialize_spec_landing", exc_info=exc)
        return False


def resolve_sandbox_index_html(product_id: str, on_disk_html: str) -> str:
    """Serve spec-built landing when index on disk is still the generic factory stub."""
    from web.backend.services.sandbox_remediation_badge import inject_remediation_badge

    if is_factory_boilerplate_index(on_disk_html):
        built = build_spec_landing_html(product_id)
        html_out = built if built else on_disk_html
    else:
        html_out = on_disk_html
    return inject_remediation_badge(html_out, product_id)
