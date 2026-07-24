#!/usr/bin/env python3
"""Rewrite monorepo satellite relative links to GitHub satellite blob URLs.

Factory mirror (alexar76/aicom) excludes satellites — ../aimarket-sdks/… 404s on GitHub.
Also fixes stale https://github.com/alexar76/aicom/blob/main/<satellite>/… URLs.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORG = "alexar76"
BRANCH = "main"

# Longest prefixes first (plugins/aimarket-oracle-gateway before plugins/)
PREFIX_TO_BLOB_BASE: list[tuple[str, str]] = [
    ("plugins/aimarket-oracle-gateway/", f"https://github.com/{ORG}/aimarket-oracle-gateway/blob/{BRANCH}/"),
    ("plugins/", f"https://github.com/{ORG}/aimarket-plugins/blob/{BRANCH}/plugins/"),
    ("apps/pulse-terminal/", f"https://github.com/{ORG}/pulse-terminal/blob/{BRANCH}/"),
    ("desktop-integrations/", f"https://github.com/{ORG}/aimarket-desktop/blob/{BRANCH}/"),
    ("aimarket-sdks/", f"https://github.com/{ORG}/aimarket-sdks/blob/{BRANCH}/"),
    ("aimarket-agent/", f"https://github.com/{ORG}/aimarket-agent/blob/{BRANCH}/"),
    ("aimarket-hub/", f"https://github.com/{ORG}/aimarket-hub/blob/{BRANCH}/"),
    ("aimarket-protocol/", f"https://github.com/{ORG}/aimarket-protocol/blob/{BRANCH}/"),
    ("aimarket-widget/", f"https://github.com/{ORG}/aimarket-widget/blob/{BRANCH}/"),
    ("ai-service-mesh/", f"https://github.com/{ORG}/ai-service-mesh/blob/{BRANCH}/"),
    ("alien-monitor/", f"https://github.com/{ORG}/alien-monitor/blob/{BRANCH}/"),
    ("oracles/", f"https://github.com/{ORG}/oracles/blob/{BRANCH}/"),
    ("lottery/", f"https://github.com/{ORG}/lottery/blob/{BRANCH}/"),
    ("argus/", f"https://github.com/{ORG}/argus/blob/{BRANCH}/"),
    ("acex/", f"https://github.com/{ORG}/acex/blob/{BRANCH}/"),
]

SATellite_PATH = (
    r"(?!aimarket-whitepaper(?:\.md)?(?:#|$))"
    r"(?:aimarket-(?!whitepaper)[^)\s#]+|"
    r"plugins(?:/[^)\s#]*)?|oracles(?:/[^)\s#]*)?|argus(?:/[^)\s#]*)?|"
    r"lottery(?:/[^)\s#]*)?|acex(?:/[^)\s#]*)?|ai-service-mesh(?:/[^)\s#]*)?|"
    r"alien-monitor(?:/[^)\s#]*)?|desktop-integrations(?:/[^)\s#]*)?|"
    r"apps/pulse-terminal(?:/[^)\s#]*)?)"
)

ANCHOR = r"(?:#[^)]*)?"

REL_PATTERNS = [
    re.compile(rf"\(\.\./\.\./\.\./({SATellite_PATH}){ANCHOR}\)"),
    re.compile(rf"\(\.\./\.\./({SATellite_PATH}){ANCHOR}\)"),
    re.compile(rf"\(\.\./({SATellite_PATH}){ANCHOR}\)"),
]

AICOM_STALE = re.compile(
    rf"https://github\.com/{ORG}/aicom/blob/{BRANCH}/({SATellite_PATH})"
)

SDK_DOC = {
    "en": f"https://github.com/{ORG}/aimarket-sdks/blob/{BRANCH}/docs/en.md",
    "ru": f"https://github.com/{ORG}/aimarket-sdks/blob/{BRANCH}/docs/ru.md",
    "es": f"https://github.com/{ORG}/aimarket-sdks/blob/{BRANCH}/docs/es.md",
}


def satellite_path_to_url(path: str) -> str | None:
    path = path.split("#", 1)[0].rstrip("/")
    anchor = ""
    if "#" in path:
        path, anchor = path.split("#", 1)
    had_trailing = path.endswith("/") or ("/" in path and not path.rsplit("/", 1)[-1].count("."))
    for prefix, base in PREFIX_TO_BLOB_BASE:
        pfx = prefix.rstrip("/")
        if path == pfx or path.startswith(prefix):
            rest = path[len(pfx) :].lstrip("/")
            if not rest:
                url = base.replace("/blob/", "/tree/").rstrip("/") + "/"
            else:
                url = base + rest
                if had_trailing and not rest.endswith((".md", ".py", ".json", ".html", ".sol")):
                    url = url.replace("/blob/", "/tree/") + "/"
            return url + (f"#{anchor}" if anchor else "")
    return None


def infer_lang(path: Path) -> str:
    stem = path.stem
    if stem.endswith("-ru") or stem == "ru":
        return "ru"
    if stem.endswith("-es") or stem == "es":
        return "es"
    if stem in SDK_DOC:
        return stem
    return "en"


def rewrite_content(text: str, lang: str) -> tuple[str, int]:
    changes = 0

    def sub_link(m: re.Match[str]) -> str:
        nonlocal changes
        inner = m.group(1)
        full = m.group(0)
        anchor = ""
        if "#" in full:
            anchor = "#" + full.split("#", 1)[1].rstrip(")")
        url = satellite_path_to_url(inner)
        if url:
            changes += 1
            base = url.split("#", 1)[0]
            return f"({base}{anchor})"
        return m.group(0)

    for pat in REL_PATTERNS:
        text = pat.sub(sub_link, text)

    def sub_stale(m: re.Match[str]) -> str:
        nonlocal changes
        url = satellite_path_to_url(m.group(1))
        if url:
            changes += 1
            return url
        return m.group(0)

    text = AICOM_STALE.sub(sub_stale, text)

    sdk = SDK_DOC.get(lang, SDK_DOC["en"])
    old_same = "| TypeScript | `@aimarket/agent` | Yes | same |\n| Rust | `aimarket-agent` | Yes | same |"
    new_same = (
        f"| TypeScript | `@aimarket/agent` | Yes | [SDK docs]({sdk}) |\n"
        f"| Rust | `aimarket-agent` | Yes | [SDK docs]({sdk}) |"
    )
    if old_same in text:
        text = text.replace(old_same, new_same)
        changes += 2

    return text, changes


def collect_targets(scope: str) -> list[Path]:
    if scope == "docs":
        return sorted((ROOT / "docs").rglob("*.md"))
    if scope == "all":
        paths: list[Path] = []
        for rel in (
            "docs",
            "argus/docs",
            "scripts/wiki-gitea",
            "scripts/wiki-argus",
            "scripts/release-notes",
            "contracts",
            "ecosystem-landing",
            "aimarket-agent/docs",
            "aimarket-sdks/docs",
            "aimarket-hub",
            "aimarket-protocol",
            "plugins",
            "acex",
            "oracles/docs",
            "desktop-integrations",
        ):
            base = ROOT / rel
            if base.is_file() and base.suffix == ".md":
                paths.append(base)
            elif base.is_dir():
                paths.extend(sorted(base.rglob("*.md")))
        return paths
    # default: whitepaper bundle (back-compat)
    wp = ROOT / "docs" / "ecosystem" / "whitepaper"
    eco = ROOT / "docs" / "ecosystem"
    doc = ROOT / "docs"
    out: list[Path] = []
    out.extend(sorted(wp.glob("*.md")))
    out.extend(sorted(eco.glob("knowledge-base*.md")))
    out.extend(sorted(doc.glob("quickstart-ecosystem-deploy*.md")))
    return out


def main() -> int:
    dry = "--dry-run" in sys.argv
    scope = "all" if "--all" in sys.argv else ("docs" if "--docs" in sys.argv else "default")
    if scope == "default" and not any(a.startswith("--") for a in sys.argv[1:]):
        scope = "all"
    targets = collect_targets(scope if scope != "default" else "all")

    seen: set[Path] = set()
    total = 0
    for path in targets:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        original = path.read_text(encoding="utf-8")
        updated, n = rewrite_content(original, infer_lang(path))
        if n and updated != original:
            total += n
            print(f"{path.relative_to(ROOT)}: {n} link(s) rewritten")
            if not dry:
                path.write_text(updated, encoding="utf-8")
    print(f"Done — {total} total rewrites" + (" (dry run)" if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
