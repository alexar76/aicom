#!/usr/bin/env python3
"""Build SEO landing pages into ecosystem-landing/ for modeldev + GitHub Pages.

Outputs:
  ecosystem-landing/learn/          — course hub + 10 course landings
  ecosystem-landing/oracles/        — oracle hub + 17 oracle landings
  ecosystem-landing/guides/         — guides hub + answer pages from specs
  ecosystem-landing/encyclopedia/   — encyclopedia mirror with injected meta
  ecosystem-landing/shared/seo.css  — copied stylesheet
  ecosystem-landing/sitemap.xml
  ecosystem-landing/robots.txt

Usage:
  python3 scripts/build_seo_landings.py
  SEO_BASE_URL=https://alexar76.github.io/aicom python3 scripts/build_seo_landings.py
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import textwrap
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any
from xml.dom import minidom

ROOT = Path(__file__).resolve().parents[1]
SEO_ROOT = ROOT / "seo-landings"
OUT_ROOT = ROOT / "ecosystem-landing"
ORACLES_TS = ROOT / "oracles" / "frontend" / "src" / "oracles.ts"
CATALOG = ROOT / "courses" / "catalog.yaml"
ENCYCLOPEDIA_SRC = ROOT / "docs" / "encyclopedia"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit("PyYAML required: pip install pyyaml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _load_config() -> dict[str, Any]:
    return _load_yaml(SEO_ROOT / "seo.config.yaml")


def _base_url(cfg: dict[str, Any], override: str | None) -> str:
    raw = override or __import__("os").environ.get("SEO_BASE_URL") or cfg.get("default_base_url")
    return str(raw).rstrip("/")


def _parse_oracles_ts() -> list[dict[str, Any]]:
    if not ORACLES_TS.is_file():
        return []
    text = ORACLES_TS.read_text(encoding="utf-8")
    block = text.split("export const ORACLES", 1)[-1]
    block = block.split("export const oracleBySlug", 1)[0]
    oracles: list[dict[str, Any]] = []
    for chunk in re.split(r"\n  \{", block):
        if 'slug: "' not in chunk:
            continue
        slug = re.search(r'slug:\s*"([^"]+)"', chunk)
        name = re.search(r'name:\s*"([^"]+)"', chunk)
        accent = re.search(r'accent:\s*"([^"]+)"', chunk)
        skill = re.search(r'skill:\s*"([^"]+)"', chunk)
        if not slug or not name:
            continue
        blurb_m = re.search(r"blurb:\s*\n\s*\"([^\"]+)\"", chunk, re.DOTALL)
        if not blurb_m:
            blurb_m = re.search(r'blurb:\s*"([^"]+)"', chunk)
        math_m = re.search(r"math:\s*\n\s*\"([^\"]+)\"", chunk, re.DOTALL)
        if not math_m:
            math_m = re.search(r'math:\s*"([^"]+)"', chunk)
        caps: list[dict[str, str]] = []
        for cap in re.finditer(
            r'\{\s*id:\s*"([^"]+)"\s*,\s*price:\s*"([^"]+)"\s*,\s*what:\s*"([^"]+)"\s*\}',
            chunk,
        ):
            caps.append({"id": cap.group(1), "price": cap.group(2), "what": cap.group(3)})
        tests_m = re.search(r"tests:\s*(\d+)", chunk)
        cockpit_m = re.search(r'cockpitUrl:\s*"([^"]+)"', chunk)
        oracles.append(
            {
                "slug": slug.group(1),
                "name": name.group(1),
                "accent": accent.group(1) if accent else "#38e0ff",
                "skill": skill.group(1) if skill else "",
                "blurb": (blurb_m.group(1) if blurb_m else "").replace("\n      ", " "),
                "math": (math_m.group(1) if math_m else "").replace("\n      ", " "),
                "caps": caps,
                "tests": int(tests_m.group(1)) if tests_m else 0,
                "cockpit_url": cockpit_m.group(1) if cockpit_m else None,
            }
        )
    if not oracles:
        return []
    if len(oracles) < 17 and ORACLES_TS.is_file():
        # Trimmed mirrors may ship a partial oracles tree — still publish what we parsed.
        pass
    return oracles


def _oracle_keywords(o: dict[str, Any]) -> list[str]:
    base = [o["name"].lower(), o["slug"], "verifiable oracle", "AIMarket", "agent oracle"]
    skill = o.get("skill", "")
    for token in re.split(r"[\s—–-]+", skill):
        t = token.strip().lower()
        if len(t) > 3 and t not in base:
            base.append(t)
    return base[:12]


def _md_to_html(md: str) -> str:
    """Lightweight markdown → HTML (no external deps)."""
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_code = False
    code_buf: list[str] = []
    list_buf: list[str] = []
    list_type: str | None = None

    def flush_list() -> None:
        nonlocal list_buf, list_type
        if not list_buf:
            return
        tag = "ol" if list_type == "ol" else "ul"
        out.append(f"<{tag}>")
        for item in list_buf:
            out.append(f"<li>{item}</li>")
        out.append(f"</{tag}>")
        list_buf = []
        list_type = None

    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush_list()
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue
        if not line.strip():
            flush_list()
            i += 1
            continue
        if line.startswith("# "):
            flush_list()
            out.append(f"<h2>{inline(line[2:].strip())}</h2>")
        elif line.startswith("## "):
            flush_list()
            out.append(f"<h2>{inline(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            flush_list()
            out.append(f"<h3>{inline(line[4:].strip())}</h3>")
        elif re.match(r"^[-*] ", line):
            if list_type not in (None, "ul"):
                flush_list()
            list_type = "ul"
            list_buf.append(inline(line[2:].strip()))
        elif re.match(r"^\d+\.\s", line):
            if list_type not in (None, "ol"):
                flush_list()
            list_type = "ol"
            list_buf.append(inline(re.sub(r"^\d+\.\s*", "", line).strip()))
        elif line.startswith("|") and "|" in line[1:]:
            flush_list()
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.match(r"^[-:]+$", c.replace(" ", "")) for c in row):
                    rows.append(row)
                i += 1
            if rows:
                out.append("<table>")
                out.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead>")
                out.append("<tbody>")
                for row in rows[1:]:
                    out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
                out.append("</tbody></table>")
            continue
        elif line.startswith(">"):
            flush_list()
            out.append(f"<blockquote><p>{inline(line.lstrip('> ').strip())}</p></blockquote>")
        else:
            flush_list()
            out.append(f"<p>{inline(line.strip())}</p>")
        i += 1
    flush_list()
    if in_code and code_buf:
        out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
    return "\n".join(out)


def _nav_html(base: str, current: str) -> str:
    links = [
        ("/", "Home"),
        ("/learn/", "Learn"),
        ("/oracles/", "Oracles"),
        ("/guides/", "Guides"),
        ("/encyclopedia/", "Encyclopedia"),
    ]
    items = []
    for href, label in links:
        full = href if href == "/" else href.rstrip("/")
        cur = ' aria-current="page"' if current == full or current == href.rstrip("/") else ""
        items.append(f'<a href="{html.escape(base + href)}"{cur}>{label}</a>')
    return (
        f'<nav class="topnav"><div class="wrap row">'
        f'<a class="brand" href="{html.escape(base + "/")}"><span>AICOM</span> · Learn</a>'
        f'<div class="nav-links">{"".join(items)}'
        f'<a class="nav-cta" href="https://github.com/alexar76/aicom" rel="noopener">GitHub</a>'
        f"</div></div></nav>"
    )


def _meta_head(
    *,
    base: str,
    path: str,
    title: str,
    description: str,
    keywords: list[str] | None = None,
    og_type: str = "website",
    json_ld: dict[str, Any] | None = None,
    cfg: dict[str, Any],
    include_seo_css: bool = True,
) -> str:
    url = f"{base}{path}"
    kw = ", ".join(keywords) if keywords else ""
    og_image = cfg.get("brand", {}).get("og_image", "")
    ld = ""
    if json_ld:
        ld = f'<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>'
    kw_meta = f'<meta name="keywords" content="{html.escape(kw)}" />' if kw else ""
    css_link = (
        f'<link rel="stylesheet" href="{html.escape(base)}/shared/seo.css" />'
        if include_seo_css
        else ""
    )
    return textwrap.dedent(
        f"""\
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{html.escape(title)}</title>
        <meta name="description" content="{html.escape(description)}" />
        {kw_meta}
        <link rel="canonical" href="{html.escape(url)}" />
        <meta property="og:type" content="{html.escape(og_type)}" />
        <meta property="og:title" content="{html.escape(title)}" />
        <meta property="og:description" content="{html.escape(description)}" />
        <meta property="og:url" content="{html.escape(url)}" />
        <meta property="og:image" content="{html.escape(og_image)}" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="{html.escape(title)}" />
        <meta name="twitter:description" content="{html.escape(description)}" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
        {css_link}
        {ld}
        """
    )


def _head(
    *,
    base: str,
    path: str,
    title: str,
    description: str,
    keywords: list[str] | None = None,
    og_type: str = "website",
    json_ld: dict[str, Any] | None = None,
    cfg: dict[str, Any],
) -> str:
    return _meta_head(
        base=base,
        path=path,
        title=title,
        description=description,
        keywords=keywords,
        og_type=og_type,
        json_ld=json_ld,
        cfg=cfg,
        include_seo_css=True,
    )


def _page_shell(
    *,
    base: str,
    path: str,
    title: str,
    description: str,
    body: str,
    nav_current: str,
    keywords: list[str] | None = None,
    og_type: str = "website",
    json_ld: dict[str, Any] | None = None,
    cfg: dict[str, Any],
) -> str:
    foot = cfg.get("external", {})
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        + _head(
            base=base,
            path=path,
            title=title,
            description=description,
            keywords=keywords,
            og_type=og_type,
            json_ld=json_ld,
            cfg=cfg,
        )
        + "\n</head>\n<body>\n<div class=\"bg-glow\"></div>\n"
        + _nav_html(base, nav_current)
        + body
        + f'\n<footer class="site-foot wrap"><p>AICOM ecosystem · '
        f'<a href="{html.escape(foot.get("knowledge_base", ""))}">Knowledge base</a> · '
        f'<a href="{html.escape(foot.get("courses_portal", ""))}">Courses portal</a> · '
        f'<a href="{html.escape(foot.get("oracles_live", ""))}">Live oracles</a></p></footer>\n'
        "</body>\n</html>\n"
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _load_courses() -> list[dict[str, Any]]:
    catalog_by_folder: dict[str, dict[str, Any]] = {}
    if CATALOG.is_file():
        data = _load_yaml(CATALOG)
        for c in data.get("courses") or []:
            folder = c.get("folder")
            if folder:
                catalog_by_folder[str(folder)] = c

    courses_root = ROOT / "courses"
    if not courses_root.is_dir():
        return []

    out: list[dict[str, Any]] = []
    for course_dir in sorted(courses_root.iterdir()):
        if not course_dir.is_dir() or not course_dir.name.endswith("-course"):
            continue
        folder = course_dir.name
        base_meta = dict(catalog_by_folder.get(folder) or {})
        base_meta.setdefault("folder", folder)
        cfg_path = course_dir / "course.config.json"
        if cfg_path.is_file():
            base_meta.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        if not base_meta.get("title"):
            base_meta["title"] = folder.replace("-", " ").title()
        out.append(base_meta)
    return out


def _build_learn(base: str, cfg: dict[str, Any]) -> list[tuple[str, str]]:
    courses = _load_courses()
    if not courses:
        return []
    ext = cfg.get("external", {})
    urls: list[tuple[str, str]] = [("/learn/", "weekly")]

    cards = []
    for c in courses:
        folder = c["folder"]
        title = c.get("title") or folder
        tagline = c.get("tagline") or c.get("description") or ""
        labs = len(c.get("labs") or [])
        modules = len(c.get("modules") or {})
        cards.append(
            f'<article class="card"><h3><a href="{html.escape(folder)}/">{html.escape(title)}</a></h3>'
            f"<p>{html.escape(tagline)}</p>"
            f'<div class="chips"><span class="chip hot">{modules} modules</span>'
            f'<span class="chip">{labs} labs</span><span class="chip">EN / RU / ES</span></div></article>'
        )
        urls.append((f"/learn/{folder}/", "weekly"))

        course_url = f"{ext.get('courses_portal', '').rstrip('/')}/{folder}/"
        desc = c.get("description") or tagline
        body = (
            '<div class="wrap article"><p class="eyebrow">AIMarket Academy</p>'
            f"<h1>{html.escape(title)}</h1>"
            f'<p class="lede">{html.escape(desc)}</p>'
            f'<div class="hero-cta">'
            f'<a class="btn primary" href="{html.escape(course_url)}">Open full course ↗</a>'
            f'<a class="btn" href="https://github.com/alexar76/aimarket-courses/tree/main/{html.escape(folder)}">Source on GitHub</a>'
            f"</div>"
            f"<section class=\"section\"><h2>What you build</h2><p>{html.escape(tagline)}</p>"
            f"<p>Hands-on Python labs wired to the live AIMarket ecosystem — oracles, Hub, WARDEN, "
            f"or factory APIs. Includes graded exercises, Colab notebooks, and a certificate.</p></section>"
            f'<section class="section related"><h2>Also explore</h2><ul>'
            f'<li><a href="{html.escape(base)}/guides/">Developer guides</a></li>'
            f'<li><a href="{html.escape(base)}/oracles/">Verifiable oracles</a></li>'
            f"</ul></section></div>"
        )
        ld = {
            "@context": "https://schema.org",
            "@type": "Course",
            "name": title,
            "description": desc,
            "provider": {"@type": "Organization", "name": "AIMarket", "url": base},
            "url": f"{base}/learn/{folder}/",
            "isAccessibleForFree": True,
            "inLanguage": ["en", "ru", "es"],
        }
        html_out = _page_shell(
            base=base,
            path=f"/learn/{folder}/",
            title=f"{title} — AIMarket Course",
            description=desc[:300],
            body=body,
            nav_current="/learn",
            keywords=[title.lower(), "python course", "AI agents", "AIMarket"],
            og_type="article",
            json_ld=ld,
            cfg=cfg,
        )
        _write(OUT_ROOT / "learn" / folder / "index.html", html_out)

    hub_body = (
        '<div class="wrap hero"><p class="eyebrow">10 academies · EN / RU / ES · Colab</p>'
        "<h1>Learn the agent economy hands-on</h1>"
        "<p class=\"lede\">Python courses with live labs on real AIMarket infrastructure — "
        "oracles, MCP security, USDC channels, factory pipeline, and 3D visualization.</p>"
        f'<div class="hero-cta"><a class="btn primary" href="{html.escape(ext.get("courses_portal", ""))}">'
        f"Full course portal ↗</a></div></div>"
        f'<div class="wrap section"><h2>All courses</h2><div class="grid">{"".join(cards)}</div></div>'
    )
    hub = _page_shell(
        base=base,
        path="/learn/",
        title="AIMarket Courses — Learn Agent Orchestration, Oracles & MCP Security",
        description="Ten hands-on Python academies on the live AIMarket ecosystem. "
        "Verifiable randomness, agent economy, MCP security, trust math, and more.",
        body=hub_body,
        nav_current="/learn",
        keywords=["AI agent course", "MCP security tutorial", "verifiable randomness course"],
        json_ld={
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "AIMarket Courses",
            "url": f"{base}/learn/",
        },
        cfg=cfg,
    )
    _write(OUT_ROOT / "learn" / "index.html", hub)
    return urls


def _build_oracles(base: str, cfg: dict[str, Any]) -> list[tuple[str, str]]:
    oracles = _parse_oracles_ts()
    if not oracles:
        return []
    ext = cfg.get("external", {})
    live = ext.get("oracles_live", "https://oracles.modelmarket.dev").rstrip("/")
    urls: list[tuple[str, str]] = [("/oracles/", "weekly")]

    cards = []
    for o in oracles:
        slug = o["slug"]
        cards.append(
            f'<article class="card oracle"><span class="oracle-accent" style="background:{html.escape(o["accent"])}"></span>'
            f'<h3><a href="{html.escape(slug)}/">{html.escape(o["name"])}</a></h3>'
            f'<p>{html.escape(o["skill"])}</p></article>'
        )
        urls.append((f"/oracles/{slug}/", "weekly"))

        cap_rows = "".join(
            f"<tr><td>{html.escape(c['id'])}</td><td>{html.escape(c['price'])}</td>"
            f"<td>{html.escape(c['what'])}</td></tr>"
            for c in o["caps"]
        )
        live_link = f"{live}/?o={slug}"
        umbral = ""
        if o.get("cockpit_url"):
            umbral = f'<a class="btn" href="{html.escape(live + o["cockpit_url"])}">UMBRAL cockpit ↗</a>'
        desc = f"{o['name']}: {o['skill']}. {o['blurb']}"
        body = (
            '<div class="wrap article">'
            f'<p class="eyebrow" style="color:{html.escape(o["accent"])}">Verifiable oracle</p>'
            f"<h1>{html.escape(o['name'])}</h1>"
            f'<p class="meta">{html.escape(o["skill"])} · {o["tests"]} tests · pay-per-call</p>'
            f'<p class="lede">{html.escape(o["blurb"])}</p>'
            f'<div class="hero-cta">'
            f'<a class="btn primary" href="{html.escape(live_link)}">Live demo ↗</a>'
            f"{umbral}"
            f'<a class="btn" href="{html.escape(base)}/guides/call-verifiable-oracle/">How to call ↗</a>'
            f"</div>"
            f'<section class="section prose"><h2>Mathematics</h2><p>{html.escape(o["math"])}</p></section>'
            f'<section class="section"><h2>Capabilities</h2>'
            f'<table class="cap-table"><thead><tr><th>ID</th><th>Price</th><th>Output</th></tr></thead>'
            f"<tbody>{cap_rows}</tbody></table></section>"
            f'<section class="section related"><h2>Related</h2><ul>'
            f'<li><a href="{html.escape(base)}/learn/verifiable-randomness-course/">Verifiable Randomness course</a></li>'
            f'<li><a href="{html.escape(ext.get("oracle_gateway_glama", ""))}">MCP oracle gateway (Glama)</a></li>'
            f"</ul></section></div>"
        )
        ld = {
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": f"{o['name']} Oracle",
            "applicationCategory": "DeveloperApplication",
            "description": o["blurb"],
            "url": f"{base}/oracles/{slug}/",
            "offers": {"@type": "Offer", "price": "0.001", "priceCurrency": "USD"},
        }
        html_out = _page_shell(
            base=base,
            path=f"/oracles/{slug}/",
            title=f"{o['name']} — Verifiable Oracle for AI Agents",
            description=desc[:300],
            body=body,
            nav_current="/oracles",
            keywords=_oracle_keywords(o),
            og_type="article",
            json_ld=ld,
            cfg=cfg,
        )
        _write(OUT_ROOT / "oracles" / slug / "index.html", html_out)

    hub = _page_shell(
        base=base,
        path="/oracles/",
        title="17 Verifiable Math Oracles for Autonomous AI Agents",
        description="Pay-per-call oracles with independently verifiable outputs — "
        "VRF, VDF, reputation, optimization, topology, and more. AIMarket Protocol v2.",
        body=(
            '<div class="wrap hero"><p class="eyebrow">×17 · signed · verify offline</p>'
            "<h1>The oracle constellation</h1>"
            "<p class=\"lede\">Each oracle sells a specific verifiable computation — "
            "not trust-me APIs. Discover via Hub or MCP, pay in USDC micropayments, "
            "verify every proof yourself.</p>"
            f'<div class="hero-cta"><a class="btn primary" href="{html.escape(live)}">Live portal ↗</a>'
            f'<a class="btn" href="{html.escape(base)}/guides/call-verifiable-oracle/">Quick-start guide</a></div></div>'
            f'<div class="wrap section"><h2>All oracles</h2><div class="grid">{"".join(cards)}</div></div>'
        ),
        nav_current="/oracles",
        keywords=["verifiable oracle", "VRF", "VDF", "agent randomness", "LUMEN reputation"],
        cfg=cfg,
    )
    _write(OUT_ROOT / "oracles" / "index.html", hub)
    return urls


def _build_guides(base: str, cfg: dict[str, Any]) -> list[tuple[str, str]]:
    guides_path = SEO_ROOT / "data" / "guides.yaml"
    if not guides_path.is_file():
        return []
    guides_cfg = _load_yaml(guides_path).get("guides") or []
    if not guides_cfg:
        return []
    urls: list[tuple[str, str]] = [("/guides/", "weekly")]
    cards = []

    for g in guides_cfg:
        slug = g["slug"]
        title = g["title"]
        desc = g["description"]
        source = ROOT / g["source"]
        if not source.is_file():
            continue
        md = source.read_text(encoding="utf-8")
        if g.get("excerpt_chars"):
            md = md[: int(g["excerpt_chars"])]
        # Skip YAML front-matter style title dup
        md_body = re.sub(r"^#\s+.+\n+", "", md, count=1)
        prose = _md_to_html(md_body)

        related_oracles = g.get("related_oracles") or []
        related_courses = g.get("related_courses") or []
        rel = ""
        if related_oracles or related_courses:
            items = []
            for o in related_oracles:
                items.append(f'<li><a href="{html.escape(base)}/oracles/{html.escape(o)}/">{html.escape(o.title())}</a></li>')
            for c in related_courses:
                items.append(f'<li><a href="{html.escape(base)}/learn/{html.escape(c)}/">{html.escape(c.replace("-", " "))}</a></li>')
            rel = f'<section class="section related"><h2>Related</h2><ul>{"".join(items)}</ul></section>'

        cards.append(
            f'<article class="card"><h3><a href="{html.escape(slug)}/">{html.escape(title)}</a></h3>'
            f"<p>{html.escape(desc[:160])}…</p></article>"
        )
        urls.append((f"/guides/{slug}/", "monthly"))

        body = (
            '<div class="wrap article"><p class="eyebrow">Developer guide</p>'
            f"<h1>{html.escape(title)}</h1>"
            f'<p class="meta">{html.escape(desc)}</p>'
            f'<div class="prose">{prose}</div>{rel}</div>'
        )
        ld = {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": title,
            "description": desc,
            "url": f"{base}/guides/{slug}/",
            "author": {"@type": "Organization", "name": "AICOM"},
        }
        html_out = _page_shell(
            base=base,
            path=f"/guides/{slug}/",
            title=f"{title} — AICOM Guide",
            description=desc,
            body=body,
            nav_current="/guides",
            keywords=g.get("keywords") or [],
            og_type="article",
            json_ld=ld,
            cfg=cfg,
        )
        _write(OUT_ROOT / "guides" / slug / "index.html", html_out)

    if not cards:
        return []

    hub = _page_shell(
        base=base,
        path="/guides/",
        title="AICOM Developer Guides — Oracles, MCP Security & Agent Economy",
        description="Step-by-step guides for calling verifiable oracles, securing MCP agents, "
        "and joining the AIMarket economy as a consumer or supplier.",
        body=(
            '<div class="wrap hero"><p class="eyebrow">Specs · quickstarts · checklists</p>'
            "<h1>Developer guides</h1>"
            "<p class=\"lede\">Answer pages for the queries agents and integrators actually search — "
            "discover, call, verify, and monetize capabilities on the open protocol.</p></div>"
            f'<div class="wrap section"><div class="grid">{"".join(cards)}</div></div>'
        ),
        nav_current="/guides",
        keywords=["MCP guide", "verifiable oracle tutorial", "agent economy"],
        cfg=cfg,
    )
    _write(OUT_ROOT / "guides" / "index.html", hub)
    return urls


def _inject_encyclopedia_head(html_text: str, *, base: str, rel_path: str, title: str, desc: str, cfg: dict[str, Any]) -> str:
    extra = _meta_head(
        base=base,
        path=rel_path,
        title=title,
        description=desc,
        keywords=["AICOM encyclopedia", "agent economy", "autonomous agents"],
        cfg=cfg,
        include_seo_css=False,
    )
    if "<head>" in html_text:
        # Replace existing minimal head tags without duplicating charset/title from source
        html_text = re.sub(r"<meta charset[^>]*>\s*", "", html_text)
        html_text = re.sub(r"<meta name=\"viewport\"[^>]*>\s*", "", html_text)
        html_text = re.sub(r"<title>[^<]*</title>\s*", "", html_text)
        return html_text.replace("<head>", f"<head>\n{extra}", 1)
    return html_text


def _build_encyclopedia(base: str, cfg: dict[str, Any]) -> list[tuple[str, str]]:
    dest = OUT_ROOT / "encyclopedia"
    if not ENCYCLOPEDIA_SRC.is_dir():
        return []
    if dest.exists():
        shutil.rmtree(dest)

    ignore = shutil.ignore_patterns("scripts", "*.mjs", "content")
    shutil.copytree(ENCYCLOPEDIA_SRC, dest, ignore=ignore)

    urls: list[tuple[str, str]] = [("/encyclopedia/", "monthly")]
    desc = "Premium storybook guide to the AICOM federated autonomous-agent economy — ideology, oracles, ARGUS, deploy."
    titles = {
        "index.html": "AICOM Cosmic Encyclopedia — Choose Your Language",
        "en/index.html": "AICOM Cosmic Encyclopedia — English",
        "ru/index.html": "AICOM Cosmic Encyclopedia — Русский",
        "es/index.html": "AICOM Cosmic Encyclopedia — Español",
    }
    for rel, title in titles.items():
        fp = dest / rel
        if not fp.is_file():
            continue
        rel_url = "/encyclopedia/" + ("" if rel == "index.html" else rel.replace("index.html", ""))
        text = fp.read_text(encoding="utf-8")
        text = _inject_encyclopedia_head(text, base=base, rel_path=rel_url, title=title, desc=desc, cfg=cfg)
        # Fix relative css paths when served from subpaths
        if rel != "index.html":
            text = text.replace('href="shared/', 'href="../shared/')
            text = text.replace('href="pdf/', 'href="../pdf/')
            text = text.replace('href="en/', 'href="../en/')
            text = text.replace('href="ru/', 'href="../ru/')
            text = text.replace('href="es/', 'href="../es/')
        fp.write_text(text, encoding="utf-8")
        urls.append((rel_url, "monthly"))

    return urls


def _build_sitemap(base: str, urls: list[tuple[str, str]]) -> None:
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    today = date.today().isoformat()
    seen: set[str] = set()
    all_urls = [("/", "daily")] + urls
    for path, freq in all_urls:
        if path in seen:
            continue
        seen.add(path)
        u = ET.SubElement(urlset, "url")
        ET.SubElement(u, "loc").text = f"{base}{path}"
        ET.SubElement(u, "lastmod").text = today
        ET.SubElement(u, "changefreq").text = freq
        pri = "1.0" if path == "/" else "0.8" if path.count("/") <= 2 else "0.6"
        ET.SubElement(u, "priority").text = pri
    rough = ET.tostring(urlset, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ")
    lines = [ln for ln in pretty.splitlines() if ln.strip()]
    _write(OUT_ROOT / "sitemap.xml", "\n".join(lines) + "\n")


def _build_robots(base: str) -> None:
    content = textwrap.dedent(
        f"""\
        User-agent: *
        Allow: /

        Sitemap: {base}/sitemap.xml
        """
    )
    _write(OUT_ROOT / "robots.txt", content)


def _copy_shared_css() -> None:
    dest = OUT_ROOT / "shared"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SEO_ROOT / "shared" / "seo.css", dest / "seo.css")


def build(*, base_url: str | None = None) -> dict[str, Any]:
    cfg = _load_config()
    base = _base_url(cfg, base_url)
    _copy_shared_css()
    urls: list[tuple[str, str]] = []
    urls.extend(_build_learn(base, cfg))
    urls.extend(_build_oracles(base, cfg))
    urls.extend(_build_guides(base, cfg))
    urls.extend(_build_encyclopedia(base, cfg))
    _build_sitemap(base, urls)
    _build_robots(base)
    return {
        "base_url": base,
        "pages": len(urls) + 1,
        "out": str(OUT_ROOT),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SEO landings into ecosystem-landing/")
    parser.add_argument(
        "--base-url",
        help="Canonical site origin (default: seo.config.yaml or SEO_BASE_URL env)",
    )
    args = parser.parse_args()
    result = build(base_url=args.base_url)
    print(f"OK: {result['pages']} URLs → {result['out']} (base={result['base_url']})")


if __name__ == "__main__":
    main()
