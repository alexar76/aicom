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
# Factory Pages tree strips courses/ (aimarket-courses satellite) — keep a slim
# mirror so /learn/ still builds on alexar76.github.io/aicom.
SEO_COURSES = SEO_ROOT / "data" / "courses.yaml"
ENCYCLOPEDIA_SRC = ROOT / "docs" / "encyclopedia"
I18N_PATH = SEO_ROOT / "data" / "i18n.yaml"

# Supported languages. English is served at the site root (x-default); every other
# language is served under a "/{lang}" path prefix. English is always the fallback.
LANGS = ["en", "ru", "es", "fr", "zh"]

# English source-of-truth for the fixed chrome strings. i18n.yaml supplies the
# ru/es/fr/zh renderings; anything missing there falls back to this table so the
# build never breaks on a partial translation.
_EN_UI: dict[str, str] = {
    "nav_home": "Home",
    "nav_learn": "Learn",
    "nav_school": "School",
    "nav_oracles": "Oracles",
    "nav_guides": "Guides",
    "nav_encyclopedia": "Encyclopedia",
    "foot_ecosystem": "AICOM ecosystem",
    "foot_knowledge_base": "Knowledge base",
    "foot_courses_portal": "Courses portal",
    "foot_oracles_live": "Live oracles",
    "oracle_eyebrow": "Verifiable oracle",
    "oracle_tests": "tests",
    "oracle_ppc": "pay-per-call",
    "oracle_live_demo": "Live demo ↗",
    "oracle_how_to_call": "How to call ↗",
    "oracle_umbral": "UMBRAL cockpit ↗",
    "oracle_mathematics": "Mathematics",
    "oracle_capabilities": "Capabilities",
    "oracle_related": "Related",
    "th_id": "ID",
    "th_price": "Price",
    "th_output": "Output",
    "oracle_hub_eyebrow": "×17 · signed · verify offline",
    "oracle_hub_h1": "The oracle constellation",
    "oracle_hub_lede": (
        "Seventeen math oracles sell verifiable computation — not trust-me APIs. "
        "Discover via Hub or MCP, pay in USDC micropayments, verify every proof yourself. "
        "Physical IoT (GAIA live relays) is a separate third class on the same Hub."
    ),
    "oracle_hub_live_portal": "Live portal ↗",
    "oracle_hub_quickstart": "Quick-start guide",
    "oracle_hub_all": "All oracles",
    "oracle_hub_gaia_title": "Also on the Hub — GAIA physical oracles",
    "oracle_hub_gaia_lede": (
        "Live attested relays: Open-Meteo weather/AQ, UK grid carbon, USGS quakes, "
        "NOAA tides (+ sim fleet). Same discover → channel → invoke loop as the math family."
    ),
    "oracle_hub_gaia_cta": "GAIA live ↗",
    "course_academy": "AIMarket Academy",
    "course_open_full": "Open full course ↗",
    "course_source_github": "Source on GitHub",
    "course_what_you_build": "What you build",
    "course_labs_para": (
        "Hands-on Python labs wired to the live AIMarket ecosystem — oracles, Hub, WARDEN, "
        "or factory APIs. Includes graded exercises, Colab notebooks, and a certificate."
    ),
    "course_also_explore": "Also explore",
    "course_dev_guides": "Developer guides",
    "course_verifiable_oracles": "Verifiable oracles",
    "chip_modules": "modules",
    "chip_labs": "labs",
    "course_hub_eyebrow": "10 academies · EN / RU / ES / FR / ZH · Colab",
    "course_hub_h1": "Learn the agent economy hands-on",
    "course_hub_lede": (
        "Python courses with live labs on real AIMarket infrastructure — oracles, MCP "
        "security, USDC channels, factory pipeline, and 3D visualization."
    ),
    "course_hub_full_portal": "Full course portal ↗",
    "course_hub_all": "All courses",
    "langs_chip": "EN / RU / ES / FR / ZH",
    "guide_eyebrow": "Developer guide",
    "guide_related": "Related",
    "guide_hub_eyebrow": "Specs · quickstarts · checklists",
    "guide_hub_h1": "Developer guides",
    "guide_hub_lede": (
        "Answer pages for the queries agents and integrators actually search — discover, "
        "call, verify, and monetize capabilities on the open protocol."
    ),
}

_I18N_CACHE: dict[str, Any] | None = None


def _load_i18n() -> dict[str, Any]:
    """Load seo-landings/data/i18n.yaml (optional). English fallback if absent/broken."""
    global _I18N_CACHE
    if _I18N_CACHE is not None:
        return _I18N_CACHE
    data: dict[str, Any] = {}
    if I18N_PATH.is_file():
        try:
            loaded = _load_yaml(I18N_PATH)
            if isinstance(loaded, dict):
                data = loaded
        except SystemExit:
            raise
        except Exception:
            data = {}
    _I18N_CACHE = data
    return data


def _lang_prefix(lang: str) -> str:
    """URL/path prefix for a language ('' for en, '/ru' for ru, …)."""
    return "" if lang == "en" else f"/{lang}"


def _out_dir(lang: str) -> Path:
    """Output root for a language (OUT_ROOT for en, OUT_ROOT/ru for ru, …)."""
    return OUT_ROOT if lang == "en" else OUT_ROOT / lang


def _link(base: str, lang: str, path: str) -> str:
    """Internal absolute link that stays within the current language."""
    return f"{base}{_lang_prefix(lang)}{path}"


def _ui(lang: str):
    """Return a getter U(key) → localized chrome string with English fallback."""
    table = _load_i18n().get("ui", {})
    loc = table.get(lang, {}) if isinstance(table, dict) else {}
    if not isinstance(loc, dict):
        loc = {}

    def U(key: str) -> str:
        val = loc.get(key)
        if val:
            return str(val)
        return _EN_UI.get(key, "")

    return U


def _tr(section: str, key: str, lang: str, field: str, default: str) -> str:
    """Translate a data field (oracle/course/guide). English → return default."""
    if lang == "en":
        return default
    sect = _load_i18n().get(section, {})
    if not isinstance(sect, dict):
        return default
    entry = sect.get(key, {})
    if not isinstance(entry, dict):
        return default
    loc = entry.get(lang, {})
    if not isinstance(loc, dict):
        return default
    val = loc.get(field)
    return str(val) if val else default


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


# Satellite folders are published as their own GitHub repos; a guide sourced from one
# must link into that repo, not into a monorepo path that the mirror strips.
# Longest prefix wins (plugins/aimarket-oracle-gateway/ before plugins/).
_SATELLITE_BLOB: list[tuple[str, str]] = [
    ("plugins/aimarket-oracle-gateway/", "aimarket-oracle-gateway/blob/main/"),
    ("plugins/", "aimarket-plugins/blob/main/plugins/"),
    ("apps/pulse-terminal/", "pulse-terminal/blob/main/"),
    ("desktop-integrations/", "aimarket-desktop/blob/main/"),
    ("aimarket-sdks/", "aimarket-sdks/blob/main/"),
    ("aimarket-agent/", "aimarket-agent/blob/main/"),
    ("aimarket-bridges/", "aimarket-bridges/blob/main/"),
    ("aimarket-hub/", "aimarket-hub/blob/main/"),
    ("aimarket-protocol/", "aimarket-protocol/blob/main/"),
    ("aimarket-widget/", "aimarket-widget/blob/main/"),
    ("ai-service-mesh/", "ai-service-mesh/blob/main/"),
    ("alien-monitor/", "alien-monitor/blob/main/"),
    ("oracles/", "oracles/blob/main/"),
    ("lottery/", "lottery/blob/main/"),
    ("argus/", "argus/blob/main/"),
    ("acex/", "acex/blob/main/"),
]


def _source_link(src_rel: str, target: str) -> str | None:
    """Repo-relative link in a guide source → absolute GitHub URL, or None to keep as-is.

    Guides are rendered into a static site, where the source markdown's relative links
    (../onchain-journal.md, ./whitepaper/en.md) point at nothing. Resolve them against
    the source file and send them to the repo that actually publishes that path.
    """
    path, _, anchor = target.partition("#")
    if not path:
        return None
    resolved = (ROOT / src_rel).parent / path
    try:
        rel = resolved.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None
    if not resolved.exists():
        return None
    for prefix, blob in _SATELLITE_BLOB:
        if rel.startswith(prefix):
            rel_in_repo = rel[len(prefix):] if not blob.endswith(prefix) else rel
            url = f"https://github.com/alexar76/{blob}{rel_in_repo}"
            break
    else:
        url = f"https://github.com/alexar76/aicom/blob/main/{rel}"
    return f"{url}#{anchor}" if anchor else url


def _md_to_html(md: str, src_rel: str | None = None) -> str:
    """Lightweight markdown → HTML (no external deps).

    `src_rel` is the repo-relative path of the markdown source; when given, relative
    links are absolutised against the repo that publishes them (see `_source_link`).
    """
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

    def _raw(url: str) -> str:
        """A GitHub /blob/ URL serves an HTML page — an <img> needs the raw bytes."""
        return url.replace("https://github.com/", "https://raw.githubusercontent.com/", 1).replace(
            "/blob/", "/", 1
        ) if url.startswith("https://github.com/") and "/blob/" in url else url

    def _href(target: str) -> str:
        if src_rel and not re.match(r"^(?:https?:|mailto:|#|/)", target):
            rewritten = _source_link(src_rel, target)
            if rewritten:
                target = rewritten
        return html.escape(target, quote=True)

    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        # Images before links — otherwise ![alt](src) leaves a stray "!" before an <a>.
        # alt is already escaped by the html.escape() above; escaping it again yields &amp;amp;.
        s = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            lambda m: f'<img src="{_raw(_href(m.group(2)))}" alt="{m.group(1).replace(chr(34), "&quot;")}" loading="lazy">',
            s,
        )
        s = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: f'<a href="{_href(m.group(2))}">{m.group(1)}</a>',
            s,
        )
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


def _nav_html(base: str, current: str, lang: str = "en") -> str:
    U = _ui(lang)
    prefix = _lang_prefix(lang)
    links = [
        ("/", U("nav_home")),
        ("/school/", U("nav_school")),
        ("/learn/", U("nav_learn")),
        ("/oracles/", U("nav_oracles")),
        ("/guides/", U("nav_guides")),
        ("/encyclopedia/", U("nav_encyclopedia")),
    ]
    items = []
    for href, label in links:
        # The encyclopedia keeps its own per-language mirror (en/ru/es/fr/zh
        # subdirs) rather than the "/{lang}" prefix scheme, so link to its
        # language subpath directly; everything else stays within-language.
        if href == "/encyclopedia/":
            full_href = f"{base}/encyclopedia/{lang}/" if lang != "en" else f"{base}/encyclopedia/"
        else:
            full_href = f"{base}{prefix}{href}"
        cur = ' aria-current="page"' if current == href.rstrip("/") or current == href else ""
        items.append(f'<a href="{html.escape(full_href)}"{cur}>{html.escape(label)}</a>')
    return (
        f'<nav class="topnav"><div class="wrap row">'
        f'<a class="brand" href="{html.escape(base + prefix + "/")}"><span>AICOM</span> · {html.escape(U("nav_learn"))}</a>'
        f'<div class="nav-links">{"".join(items)}'
        f'<a class="nav-cta" href="https://github.com/alexar76/aicom" rel="noopener">GitHub</a>'
        f"</div></div></nav>"
    )


def _meta_head(
    *,
    base: str,
    path: str,
    lang: str = "en",
    title: str,
    description: str,
    keywords: list[str] | None = None,
    og_type: str = "website",
    json_ld: dict[str, Any] | None = None,
    cfg: dict[str, Any],
    include_seo_css: bool = True,
    hreflang: bool = True,
) -> str:
    # For hreflang pages, `path` is the canonical (en) path and the current lang's
    # URL carries the "/{lang}" prefix. For non-hreflang pages (encyclopedia) the
    # `path` already encodes its language, so it is used verbatim.
    url = f"{base}{_lang_prefix(lang)}{path}" if hreflang else f"{base}{path}"
    kw = ", ".join(keywords) if keywords else ""
    og_image = cfg.get("brand", {}).get("og_image", "")
    ld = ""
    if json_ld:
        ld = f'<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>'
    kw_meta = f'<meta name="keywords" content="{html.escape(kw)}" />' if kw else ""
    alt_links = ""
    if hreflang:
        rows = [
            f'<link rel="alternate" hreflang="{l}" href="{html.escape(base + _lang_prefix(l) + path)}" />'
            for l in LANGS
        ]
        rows.append(
            f'<link rel="alternate" hreflang="x-default" href="{html.escape(base + path)}" />'
        )
        alt_links = "\n".join(rows)
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
        {alt_links}
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
    lang: str = "en",
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
        lang=lang,
        title=title,
        description=description,
        keywords=keywords,
        og_type=og_type,
        json_ld=json_ld,
        cfg=cfg,
        include_seo_css=True,
        hreflang=True,
    )


def _page_shell(
    *,
    base: str,
    path: str,
    lang: str = "en",
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
    U = _ui(lang)
    return (
        f'<!DOCTYPE html>\n<html lang="{html.escape(lang)}">\n<head>\n'
        + _head(
            base=base,
            path=path,
            lang=lang,
            title=title,
            description=description,
            keywords=keywords,
            og_type=og_type,
            json_ld=json_ld,
            cfg=cfg,
        )
        + "\n</head>\n<body>\n<div class=\"bg-glow\"></div>\n"
        + _nav_html(base, nav_current, lang)
        + body
        + f'\n<footer class="site-foot wrap"><p>{html.escape(U("foot_ecosystem"))} · '
        f'<a href="{html.escape(foot.get("knowledge_base", ""))}">{html.escape(U("foot_knowledge_base"))}</a> · '
        f'<a href="{html.escape(foot.get("courses_portal", ""))}">{html.escape(U("foot_courses_portal"))}</a> · '
        f'<a href="{html.escape(foot.get("oracles_live", ""))}">{html.escape(U("foot_oracles_live"))}</a></p></footer>\n'
        "</body>\n</html>\n"
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _load_courses() -> list[dict[str, Any]]:
    catalog_by_folder: dict[str, dict[str, Any]] = {}
    for path in (CATALOG, SEO_COURSES):
        if not path.is_file():
            continue
        data = _load_yaml(path)
        for c in data.get("courses") or []:
            folder = c.get("folder")
            if folder:
                # Prefer monorepo catalog / course.config over SEO mirror when both exist.
                catalog_by_folder.setdefault(str(folder), dict(c))

    courses_root = ROOT / "courses"
    out: list[dict[str, Any]] = []
    if courses_root.is_dir():
        for course_dir in sorted(courses_root.iterdir()):
            if not course_dir.is_dir() or not course_dir.name.endswith("-course"):
                continue
            folder = course_dir.name
            base_meta = dict(catalog_by_folder.pop(folder, {}) or {})
            base_meta.setdefault("folder", folder)
            cfg_path = course_dir / "course.config.json"
            if cfg_path.is_file():
                base_meta.update(json.loads(cfg_path.read_text(encoding="utf-8")))
            if not base_meta.get("title"):
                base_meta["title"] = folder.replace("-", " ").title()
            out.append(base_meta)

    # Factory Pages: no courses/ tree — emit SEO mirror entries.
    for folder in sorted(catalog_by_folder):
        base_meta = dict(catalog_by_folder[folder])
        base_meta.setdefault("folder", folder)
        if not base_meta.get("title"):
            base_meta["title"] = folder.replace("-", " ").title()
        out.append(base_meta)
    return out


def _build_learn(base: str, cfg: dict[str, Any]) -> list[tuple[str, str]]:
    courses = _load_courses()
    if not courses:
        return []
    ext = cfg.get("external", {})
    # Canonical (en) sitemap paths, emitted once with hreflang alternates.
    urls: list[tuple[str, str]] = [("/learn/", "weekly")]
    for c in courses:
        urls.append((f"/learn/{c['folder']}/", "weekly"))

    for lang in LANGS:
        U = _ui(lang)
        out_root = _out_dir(lang)
        cards = []
        for c in courses:
            folder = c["folder"]
            en_title = c.get("title") or folder
            en_tagline = c.get("tagline") or c.get("description") or ""
            en_desc = c.get("description") or en_tagline
            title = _tr("courses", folder, lang, "title", en_title)
            tagline = _tr("courses", folder, lang, "tagline", en_tagline)
            desc = _tr("courses", folder, lang, "description", en_desc)
            labs = len(c.get("labs") or [])
            modules = len(c.get("modules") or {})
            cards.append(
                f'<article class="card"><h3><a href="{html.escape(folder)}/">{html.escape(title)}</a></h3>'
                f"<p>{html.escape(tagline)}</p>"
                f'<div class="chips"><span class="chip hot">{modules} {html.escape(U("chip_modules"))}</span>'
                f'<span class="chip">{labs} {html.escape(U("chip_labs"))}</span>'
                f'<span class="chip">{html.escape(U("langs_chip"))}</span></div></article>'
            )

            course_url = f"{ext.get('courses_portal', '').rstrip('/')}/{folder}/"
            body = (
                f'<div class="wrap article"><p class="eyebrow">{html.escape(U("course_academy"))}</p>'
                f"<h1>{html.escape(title)}</h1>"
                f'<p class="lede">{html.escape(desc)}</p>'
                f'<div class="hero-cta">'
                f'<a class="btn primary" href="{html.escape(course_url)}">{html.escape(U("course_open_full"))}</a>'
                f'<a class="btn" href="https://github.com/alexar76/aimarket-courses/tree/main/{html.escape(folder)}">{html.escape(U("course_source_github"))}</a>'
                f"</div>"
                f'<section class="section"><h2>{html.escape(U("course_what_you_build"))}</h2><p>{html.escape(tagline)}</p>'
                f"<p>{html.escape(U('course_labs_para'))}</p></section>"
                f'<section class="section related"><h2>{html.escape(U("course_also_explore"))}</h2><ul>'
                f'<li><a href="{html.escape(_link(base, lang, "/guides/"))}">{html.escape(U("course_dev_guides"))}</a></li>'
                f'<li><a href="{html.escape(_link(base, lang, "/oracles/"))}">{html.escape(U("course_verifiable_oracles"))}</a></li>'
                f"</ul></section></div>"
            )
            ld = {
                "@context": "https://schema.org",
                "@type": "Course",
                "name": title,
                "description": desc,
                "provider": {"@type": "Organization", "name": "AIMarket", "url": base},
                "url": _link(base, lang, f"/learn/{folder}/"),
                "isAccessibleForFree": True,
                "inLanguage": LANGS,
            }
            html_out = _page_shell(
                base=base,
                path=f"/learn/{folder}/",
                lang=lang,
                title=f"{title} — AIMarket Course",
                description=desc[:300],
                body=body,
                nav_current="/learn",
                keywords=[title.lower(), "python course", "AI agents", "AIMarket"],
                og_type="article",
                json_ld=ld,
                cfg=cfg,
            )
            _write(out_root / "learn" / folder / "index.html", html_out)

        hub_body = (
            f'<div class="wrap hero"><p class="eyebrow">{html.escape(U("course_hub_eyebrow"))}</p>'
            f'<h1>{html.escape(U("course_hub_h1"))}</h1>'
            f'<p class="lede">{html.escape(U("course_hub_lede"))}</p>'
            f'<div class="hero-cta"><a class="btn primary" href="{html.escape(ext.get("courses_portal", ""))}">'
            f'{html.escape(U("course_hub_full_portal"))}</a>'
            f'<a class="btn" href="{html.escape(_link(base, lang, "/school/"))}">'
            f'{html.escape(U("nav_school"))} · 5-min clips</a></div></div>'
            f'<div class="wrap section"><h2>{html.escape(U("course_hub_all"))}</h2>'
            f'<div class="grid">{"".join(cards)}</div></div>'
        )
        hub = _page_shell(
            base=base,
            path="/learn/",
            lang=lang,
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
                "url": _link(base, lang, "/learn/"),
                "inLanguage": LANGS,
            },
            cfg=cfg,
        )
        _write(out_root / "learn" / "index.html", hub)
    return urls


def _build_oracles(base: str, cfg: dict[str, Any]) -> list[tuple[str, str]]:
    oracles = _parse_oracles_ts()
    if not oracles:
        return []
    ext = cfg.get("external", {})
    live = ext.get("oracles_live", "https://oracles.modelmarket.dev").rstrip("/")
    # Canonical (en) sitemap paths, emitted once with hreflang alternates.
    urls: list[tuple[str, str]] = [("/oracles/", "weekly")]
    for o in oracles:
        urls.append((f"/oracles/{o['slug']}/", "weekly"))

    for lang in LANGS:
        U = _ui(lang)
        out_root = _out_dir(lang)
        cards = []
        for o in oracles:
            slug = o["slug"]
            skill = _tr("oracles", slug, lang, "skill", o["skill"])
            blurb = _tr("oracles", slug, lang, "blurb", o["blurb"])
            # `math` is math-with-symbols → kept in English (glossary rule).
            math = _tr("oracles", slug, lang, "math", o["math"])
            cards.append(
                f'<article class="card oracle"><span class="oracle-accent" style="background:{html.escape(o["accent"])}"></span>'
                f'<h3><a href="{html.escape(slug)}/">{html.escape(o["name"])}</a></h3>'
                f'<p class="skill">{html.escape(skill)}</p>'
                f'<p class="blurb">{html.escape(blurb)}</p></article>'
            )

            cap_rows = "".join(
                f"<tr><td>{html.escape(c['id'])}</td><td>{html.escape(c['price'])}</td>"
                f"<td>{html.escape(c['what'])}</td></tr>"
                for c in o["caps"]
            )
            live_link = f"{live}/?o={slug}"
            umbral = ""
            if o.get("cockpit_url"):
                umbral = f'<a class="btn" href="{html.escape(live + o["cockpit_url"])}">{html.escape(U("oracle_umbral"))}</a>'
            desc = f"{o['name']}: {skill}. {blurb}"
            body = (
                '<div class="wrap article">'
                f'<p class="eyebrow" style="color:{html.escape(o["accent"])}">{html.escape(U("oracle_eyebrow"))}</p>'
                f"<h1>{html.escape(o['name'])}</h1>"
                f'<p class="meta">{html.escape(skill)} · {o["tests"]} {html.escape(U("oracle_tests"))} · {html.escape(U("oracle_ppc"))}</p>'
                f'<p class="lede">{html.escape(blurb)}</p>'
                f'<div class="hero-cta">'
                f'<a class="btn primary" href="{html.escape(live_link)}">{html.escape(U("oracle_live_demo"))}</a>'
                f"{umbral}"
                f'<a class="btn" href="{html.escape(_link(base, lang, "/guides/call-verifiable-oracle/"))}">{html.escape(U("oracle_how_to_call"))}</a>'
                f"</div>"
                f'<section class="section prose"><h2>{html.escape(U("oracle_mathematics"))}</h2><p>{html.escape(math)}</p></section>'
                f'<section class="section"><h2>{html.escape(U("oracle_capabilities"))}</h2>'
                f'<table class="cap-table"><thead><tr><th>{html.escape(U("th_id"))}</th>'
                f'<th>{html.escape(U("th_price"))}</th><th>{html.escape(U("th_output"))}</th></tr></thead>'
                f"<tbody>{cap_rows}</tbody></table></section>"
                f'<section class="section related"><h2>{html.escape(U("oracle_related"))}</h2><ul>'
                f'<li><a href="{html.escape(_link(base, lang, "/learn/verifiable-randomness-course/"))}">'
                f'{html.escape(_tr("courses", "verifiable-randomness-course", lang, "title", "Verifiable Randomness & Cryptographic Time"))}</a></li>'
                f'<li><a href="{html.escape(ext.get("oracle_gateway_glama", ""))}">MCP oracle gateway (Glama)</a></li>'
                f"</ul></section></div>"
            )
            ld = {
                "@context": "https://schema.org",
                "@type": "SoftwareApplication",
                "name": f"{o['name']} Oracle",
                "applicationCategory": "DeveloperApplication",
                "description": blurb,
                "url": _link(base, lang, f"/oracles/{slug}/"),
                "inLanguage": lang,
                "offers": {"@type": "Offer", "price": "0.001", "priceCurrency": "USD"},
            }
            html_out = _page_shell(
                base=base,
                path=f"/oracles/{slug}/",
                lang=lang,
                title=f"{o['name']} — Verifiable Oracle for AI Agents",
                description=desc[:300],
                body=body,
                nav_current="/oracles",
                keywords=_oracle_keywords(o),
                og_type="article",
                json_ld=ld,
                cfg=cfg,
            )
            _write(out_root / "oracles" / slug / "index.html", html_out)

        gaia = ext.get("gaia_live", "https://iot.modelmarket.dev").rstrip("/")
        hub = _page_shell(
            base=base,
            path="/oracles/",
            lang=lang,
            title="17 Verifiable Math Oracles for Autonomous AI Agents",
            description="Pay-per-call oracles with independently verifiable outputs — "
            "VRF, VDF, reputation, optimization, topology, and more. Plus GAIA physical "
            "IoT relays on the same Hub. AIMarket Protocol v2.",
            body=(
                f'<div class="wrap hero"><p class="eyebrow">{html.escape(U("oracle_hub_eyebrow"))}</p>'
                f'<h1>{html.escape(U("oracle_hub_h1"))}</h1>'
                f'<p class="lede">{html.escape(U("oracle_hub_lede"))}</p>'
                f'<div class="hero-cta"><a class="btn primary" href="{html.escape(live)}">{html.escape(U("oracle_hub_live_portal"))}</a>'
                f'<a class="btn" href="{html.escape(_link(base, lang, "/guides/call-verifiable-oracle/"))}">{html.escape(U("oracle_hub_quickstart"))}</a></div></div>'
                f'<div class="wrap section"><h2>{html.escape(U("oracle_hub_gaia_title"))}</h2>'
                f'<p class="lede">{html.escape(U("oracle_hub_gaia_lede"))}</p>'
                f'<div class="hero-cta"><a class="btn" href="{html.escape(gaia)}">{html.escape(U("oracle_hub_gaia_cta"))}</a>'
                f'<a class="btn" href="{html.escape(ext.get("hub", "https://modelmarket.dev").rstrip("/"))}">Hub search ↗</a></div></div>'
                f'<div class="wrap section"><h2>{html.escape(U("oracle_hub_all"))}</h2>'
                f'<div class="grid">{"".join(cards)}</div></div>'
            ),
            nav_current="/oracles",
            keywords=["verifiable oracle", "VRF", "VDF", "agent randomness", "LUMEN reputation", "GAIA IoT"],
            cfg=cfg,
        )
        _write(out_root / "oracles" / "index.html", hub)
    return urls


def _build_guides(base: str, cfg: dict[str, Any]) -> list[tuple[str, str]]:
    guides_path = SEO_ROOT / "data" / "guides.yaml"
    if not guides_path.is_file():
        return []
    guides_cfg = _load_yaml(guides_path).get("guides") or []
    if not guides_cfg:
        return []

    # Pre-render each guide's English prose body once (guide BODY stays English;
    # only title/description/chrome are localized).
    prepared: list[dict[str, Any]] = []
    for g in guides_cfg:
        source = ROOT / g["source"]
        if not source.is_file():
            continue
        md = source.read_text(encoding="utf-8")
        if g.get("excerpt_chars"):
            md = md[: int(g["excerpt_chars"])]
        md_body = re.sub(r"^#\s+.+\n+", "", md, count=1)  # drop dup H1
        prepared.append({"g": g, "prose": _md_to_html(md_body, src_rel=g["source"])})

    if not prepared:
        return []

    # Canonical (en) sitemap paths, emitted once with hreflang alternates.
    urls: list[tuple[str, str]] = [("/guides/", "weekly")]
    for item in prepared:
        urls.append((f"/guides/{item['g']['slug']}/", "monthly"))

    for lang in LANGS:
        U = _ui(lang)
        out_root = _out_dir(lang)
        cards = []
        for item in prepared:
            g = item["g"]
            prose = item["prose"]
            slug = g["slug"]
            title = _tr("guides", slug, lang, "title", g["title"])
            desc = _tr("guides", slug, lang, "description", g["description"])

            related_oracles = g.get("related_oracles") or []
            related_courses = g.get("related_courses") or []
            rel = ""
            if related_oracles or related_courses:
                lis = []
                for o in related_oracles:
                    lis.append(
                        f'<li><a href="{html.escape(_link(base, lang, f"/oracles/{o}/"))}">{html.escape(o.title())}</a></li>'
                    )
                for c in related_courses:
                    label = _tr("courses", c, lang, "title", c.replace("-", " "))
                    lis.append(
                        f'<li><a href="{html.escape(_link(base, lang, f"/learn/{c}/"))}">{html.escape(label)}</a></li>'
                    )
                rel = (
                    f'<section class="section related"><h2>{html.escape(U("guide_related"))}</h2>'
                    f'<ul>{"".join(lis)}</ul></section>'
                )

            cards.append(
                f'<article class="card"><h3><a href="{html.escape(slug)}/">{html.escape(title)}</a></h3>'
                f"<p>{html.escape(desc[:160])}…</p></article>"
            )

            body = (
                f'<div class="wrap article"><p class="eyebrow">{html.escape(U("guide_eyebrow"))}</p>'
                f"<h1>{html.escape(title)}</h1>"
                f'<p class="meta">{html.escape(desc)}</p>'
                f'<div class="prose">{prose}</div>{rel}</div>'
            )
            ld = {
                "@context": "https://schema.org",
                "@type": "TechArticle",
                "headline": title,
                "description": desc,
                "url": _link(base, lang, f"/guides/{slug}/"),
                "inLanguage": lang,
                "author": {"@type": "Organization", "name": "AICOM"},
            }
            html_out = _page_shell(
                base=base,
                path=f"/guides/{slug}/",
                lang=lang,
                title=f"{title} — AICOM Guide",
                description=desc,
                body=body,
                nav_current="/guides",
                keywords=g.get("keywords") or [],
                og_type="article",
                json_ld=ld,
                cfg=cfg,
            )
            _write(out_root / "guides" / slug / "index.html", html_out)

        hub = _page_shell(
            base=base,
            path="/guides/",
            lang=lang,
            title="AICOM Developer Guides — Oracles, MCP Security & Agent Economy",
            description="Step-by-step guides for calling verifiable oracles, securing MCP agents, "
            "and joining the AIMarket economy as a consumer or supplier.",
            body=(
                f'<div class="wrap hero"><p class="eyebrow">{html.escape(U("guide_hub_eyebrow"))}</p>'
                f'<h1>{html.escape(U("guide_hub_h1"))}</h1>'
                f'<p class="lede">{html.escape(U("guide_hub_lede"))}</p></div>'
                f'<div class="wrap section"><div class="grid">{"".join(cards)}</div></div>'
            ),
            nav_current="/guides",
            keywords=["MCP guide", "verifiable oracle tutorial", "agent economy"],
            cfg=cfg,
        )
        _write(out_root / "guides" / "index.html", hub)
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
        hreflang=False,  # encyclopedia has its own per-language mirror
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
        "fr/index.html": "AICOM Cosmic Encyclopedia — Français",
        "zh/index.html": "AICOM Cosmic Encyclopedia — 中文",
    }
    lang_dirs = ("en", "ru", "es", "fr", "zh")
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
            for d in lang_dirs:
                text = text.replace(f'href="{d}/', f'href="../{d}/')
        fp.write_text(text, encoding="utf-8")
        urls.append((rel_url, "monthly"))

    return urls


XHTML_NS = "http://www.w3.org/1999/xhtml"


def _build_sitemap(
    base: str,
    alt_urls: list[tuple[str, str]],
    plain_urls: list[tuple[str, str]] | None = None,
) -> None:
    """Emit sitemap.xml.

    `alt_urls` are canonical (en) paths that get one <url> each with the en loc
    plus <xhtml:link rel="alternate"> entries for every language + x-default.
    `plain_urls` (home, encyclopedia language mirror) are emitted as bare <url>.
    """
    ET.register_namespace("xhtml", XHTML_NS)
    urlset = ET.Element(
        "urlset",
        {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"},
    )
    today = date.today().isoformat()
    seen: set[str] = set()

    def _add(path: str, freq: str, alternates: bool) -> None:
        if path in seen:
            return
        seen.add(path)
        u = ET.SubElement(urlset, "url")
        ET.SubElement(u, "loc").text = f"{base}{path}"
        ET.SubElement(u, "lastmod").text = today
        ET.SubElement(u, "changefreq").text = freq
        pri = "1.0" if path == "/" else "0.8" if path.count("/") <= 2 else "0.6"
        ET.SubElement(u, "priority").text = pri
        if alternates:
            for l in LANGS:
                ET.SubElement(
                    u,
                    f"{{{XHTML_NS}}}link",
                    {"rel": "alternate", "hreflang": l, "href": f"{base}{_lang_prefix(l)}{path}"},
                )
            ET.SubElement(
                u,
                f"{{{XHTML_NS}}}link",
                {"rel": "alternate", "hreflang": "x-default", "href": f"{base}{path}"},
            )

    _add("/", "daily", alternates=False)
    for path, freq in plain_urls or []:
        _add(path, freq, alternates=False)
    for path, freq in alt_urls:
        _add(path, freq, alternates=True)

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
    # Localized sections: each canonical (en) path is emitted in all LANGS.
    alt_urls: list[tuple[str, str]] = []
    alt_urls.extend(_build_learn(base, cfg))
    alt_urls.extend(_build_oracles(base, cfg))
    alt_urls.extend(_build_guides(base, cfg))
    # Encyclopedia keeps its own per-language mirror (not the "/{lang}" scheme).
    enc_urls = _build_encyclopedia(base, cfg)
    _build_sitemap(base, alt_urls, enc_urls)
    _build_robots(base)
    # Localized HTML pages actually written = canonical paths × languages,
    # plus the encyclopedia mirror pages and the home entry.
    generated = len(alt_urls) * len(LANGS) + len(enc_urls) + 1
    return {
        "base_url": base,
        "canonical_urls": len(alt_urls) + len(enc_urls) + 1,
        "pages": generated,
        "languages": len(LANGS),
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
    print(
        f"OK: {result['pages']} pages across {result['languages']} languages "
        f"({result['canonical_urls']} canonical URLs) → {result['out']} "
        f"(base={result['base_url']})"
    )


if __name__ == "__main__":
    main()
