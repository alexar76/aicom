#!/usr/bin/env python3
"""Static launch checks for the Attested Memory marketing surface.

The script is network-free and does not create trials, invoices or API keys.
"""

from __future__ import annotations

import json
import re
import struct
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "saas-landing"
LOCALES = ("en", "ru", "es", "pt-BR", "de", "fr", "ja", "ko", "zh-CN", "tr")


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.json_ld: list[str] = []
        self._json_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        self.tags.append((tag, values))
        if tag == "script" and values.get("type") == "application/ld+json":
            self._json_parts = []

    def handle_data(self, data: str) -> None:
        if self._json_parts is not None:
            self._json_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_parts is not None:
            self.json_ld.append("".join(self._json_parts))
            self._json_parts = None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def parse_page(name: str) -> tuple[str, Page]:
    source = (LANDING / name).read_text(encoding="utf-8")
    page = Page()
    page.feed(source)
    return source, page


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    require(data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name}: invalid PNG")
    return struct.unpack(">II", data[16:24])


def main() -> int:
    index_source, index = parse_page("index.html")
    market_source, market = parse_page("market.html")
    guide_source, guide = parse_page("market-guide.html")
    cases_source, cases = parse_page("market-use-cases.html")
    developer_source, developer = parse_page("developers.html")
    use_case_source, use_case = parse_page("use-cases.html")

    require(index_source.count('class="card product-card') == 6, "main landing must expose six products")
    require("numberOfItems\":6" in index_source.replace(" ", ""), "main product JSON-LD must contain six products")
    for page_name, page in (("index", index), ("market", market), ("guide", guide), ("market use cases", cases), ("developers", developer), ("use cases", use_case)):
        tags = page.tags
        require(any(tag == "link" and attrs.get("rel") == "canonical" for tag, attrs in tags), f"{page_name}: missing canonical")
        require(any(tag == "meta" and attrs.get("property") == "og:image" for tag, attrs in tags), f"{page_name}: missing social image")
        alternates = {attrs.get("hreflang") for tag, attrs in tags if tag == "link" and attrs.get("rel") == "alternate"}
        require(set(LOCALES).issubset(alternates) and "x-default" in alternates, f"{page_name}: incomplete hreflang set")
        for block in page.json_ld:
            json.loads(block)

    keys = set(re.findall(r'data-market-i18n(?:-placeholder)?="([A-Za-z0-9_-]+)"', market_source + guide_source + cases_source))
    market_js = (LANDING / "market.js").read_text(encoding="utf-8")
    locale_markers = {
        "en": "en", "ru": "ru", "es": "es", "pt-BR": '"pt-BR"', "de": "de",
        "fr": "fr", "ja": "ja", "ko": "ko", "zh-CN": '"zh-CN"', "tr": "tr",
    }
    for locale, marker in locale_markers.items():
        match = re.search(rf"^    {re.escape(marker)}:\s*\{{(.*?)^    \}}[,\n]", market_js, re.MULTILINE | re.DOTALL)
        require(match is not None, f"market.js: dictionary missing for {locale}")
        available = set(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*:", match.group(1)))
        missing = sorted(keys - available)
        require(not missing, f"market.js: {locale} missing {', '.join(missing)}")

    for locale in LOCALES:
        for filename in ("MARKET_GUIDE.md", "MARKET_USE_CASES.md"):
            path = ROOT / "docs" / "i18n" / locale / filename
            require(path.exists(), f"missing {locale}/{filename}")
            content = path.read_text(encoding="utf-8")
            require(len(content) >= 900 and "## " in content, f"{locale}/{filename}: content is incomplete")

    dev_keys = set(re.findall(r'data-dev-i18n(?:-aria)?="([A-Za-z0-9_-]+)"', developer_source))
    developer_js = (LANDING / "developer.js").read_text(encoding="utf-8")
    for key in dev_keys:
        occurrences = len(re.findall(rf"\b{re.escape(key)}\s*:", developer_js))
        require(occurrences == len(LOCALES), f"developer.js: {key} has {occurrences}/{len(LOCALES)} translations")
    for locale in LOCALES:
        path = ROOT / "docs" / "i18n" / locale / "DEVELOPER_GUIDE.md"
        require(path.exists(), f"missing {locale}/DEVELOPER_GUIDE.md")
        content = path.read_text(encoding="utf-8")
        require(len(content) >= 1000 and "/ai-market/v2/supply/register" in content, f"{locale}/DEVELOPER_GUIDE.md: content is incomplete")

    use_case_js = (LANDING / "use-cases.js").read_text(encoding="utf-8")
    case_keys_match = re.search(r"var CASE_KEYS = (\[.*?\]);", use_case_js, re.DOTALL)
    case_rows_match = re.search(r"var CASE_ROWS = (\{.*?\});\n  var CASE_CATEGORIES", use_case_js, re.DOTALL)
    case_categories_match = re.search(r"var CASE_CATEGORIES = (\{.*?\});\n  var CASE_TONES", use_case_js, re.DOTALL)
    case_matrix_match = re.search(r"var CASE_MATRIX_COPY = (\{.*?\});\n  var CASE_LAYER_COPY", use_case_js, re.DOTALL)
    case_layers_match = re.search(r"var CASE_LAYER_COPY = (\{.*?\});\n  var CASE_REQUIREMENTS", use_case_js, re.DOTALL)
    case_requirements_match = re.search(r"var CASE_REQUIREMENTS = (\[.*?\]);", use_case_js, re.DOTALL)
    require(
        all(match is not None for match in (case_keys_match, case_rows_match, case_categories_match, case_matrix_match, case_layers_match, case_requirements_match)),
        "use-cases.js: localization or visualization tables missing",
    )
    case_keys = json.loads(case_keys_match.group(1))
    case_rows = json.loads(case_rows_match.group(1))
    case_categories = json.loads(case_categories_match.group(1))
    case_matrix = json.loads(case_matrix_match.group(1))
    case_layers = json.loads(case_layers_match.group(1))
    case_requirements = json.loads(case_requirements_match.group(1))
    require(set(case_rows) == set(LOCALES), "use-cases.js: locale rows are incomplete")
    require(set(case_categories) == set(LOCALES), "use-cases.js: category locales are incomplete")
    require(set(case_matrix) == set(LOCALES), "use-cases.js: matrix locales are incomplete")
    require(set(case_layers) == set(LOCALES), "use-cases.js: layer-label locales are incomplete")
    require(all(len(row) == len(case_keys) for row in case_rows.values()), "use-cases.js: localized UI row length mismatch")
    require(all(len(row) == 7 for row in case_categories.values()), "use-cases.js: each locale needs seven scenario categories")
    require(all(len(row) == 8 for row in case_matrix.values()), "use-cases.js: each locale needs eight matrix labels")
    require(all(len(row) == 5 for row in case_layers.values()), "use-cases.js: each locale needs five trust-layer labels")
    require(len(case_requirements) == 7 and all(len(row) == 5 for row in case_requirements), "use-cases.js: trust-layer matrix must be 7 by 5")
    require(all(value in (0, 1) for row in case_requirements for value in row), "use-cases.js: trust-layer matrix must use boolean values")
    require('data-guide-file="USE_CASES.md"' in use_case_source, "use-cases.html: localized guide source missing")

    memory_source, _memory = parse_page("memory.html")
    teams_source, _teams = parse_page("teams.html")
    require('id="studio"' in memory_source, "memory.html: activation studio missing")
    require('id="open-trial"' in memory_source, "memory.html: trial CTA missing")
    require('data-product-scene="personal"' in memory_source, "memory.html: Personal 3D scene missing")
    require('data-product-scene="team"' in teams_source, "teams.html: Team 3D scene missing")
    require((LANDING / "product-scenes.js").exists(), "shared Personal/Team 3D renderer missing")
    require('id="team-studio"' in teams_source, "teams.html: activation studio missing")
    require('id="open-team-trial"' in teams_source, "teams.html: Team trial CTA missing")
    require((LANDING / "team.js").exists(), "teams.html: Team workspace controller missing")
    require("/memory/api/memories" in (LANDING / "memory.js").read_text(encoding="utf-8"), "memory.js: write path missing")
    team_javascript = (LANDING / "team.js").read_text(encoding="utf-8")
    for route in ("/api/teams", "/api/team-memories", "/api/team-search", "/members"):
        require(route in team_javascript, f"team.js: {route} route missing")
    actor_javascript = (LANDING / "actor.js").read_text(encoding="utf-8")
    require('generateKey({ name: "Ed25519" }, false' in actor_javascript, "actor.js: private signing key must be non-exportable")
    require("identityPromise" in actor_javascript, "actor.js: concurrent identity initialization must be deduplicated")
    require("https://prove.attestedmemory.net" in memory_source, "memory.html: Prove footer missing")
    require("https://deal.attestedmemory.net" in memory_source, "memory.html: Deal footer missing")
    require("https://meter.attestedmemory.net" in memory_source, "memory.html: Meter footer missing")
    lowered = memory_source.lower() + (LANDING / "memory.js").read_text(encoding="utf-8").lower()
    for banned in ("modelmarket", "aimarket", "alexar76/aicom", "factory"):
        require(banned not in lowered, f"memory surface leaked {banned}")

    require(png_size(LANDING / "attested-social.png") == (1200, 630), "invalid main social image size")
    require(png_size(LANDING / "market-social.png") == (1200, 630), "invalid market social image size")
    ET.parse(LANDING / "sitemap.xml")
    robots = (LANDING / "robots.txt").read_text(encoding="utf-8")
    require("Sitemap: https://attestedmemory.net/sitemap.xml" in robots, "robots.txt: sitemap missing")
    require("Disallow: /market/v1/" in robots and "Disallow: /market\n" not in robots, "robots.txt: market crawl policy is wrong")

    caddy = (ROOT / "saas-edge" / "Caddyfile").read_text(encoding="utf-8")
    require("handle /market/guide" in caddy and "handle /market/use-cases" in caddy, "Caddy routes missing")
    require("MARKET_GUIDE.md" in (LANDING / "app.js").read_text(encoding="utf-8"), "guide link routing missing")

    print(
        "Attested marketing checks passed: "
        f"6 products, {len(keys)} localized Market UI keys, "
        f"{len(case_keys)} localized use-case UI keys and a 7x5 trust-layer map, "
        f"{len(LOCALES) * 3} localized Market/developer documents, SEO assets and routes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
