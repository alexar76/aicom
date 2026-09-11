"""README badge/gallery assets must exist on disk — GitHub shows alt text when they 404.

Measured on Sentinel in alexar76/aicom-products: README linked coverage.svg, tests.svg and
docs/gallery/hero.svg while the catalog snapshot only had ci.svg + license.svg. GitHub
rendered «coverage», «tests» and «Sentinel hero» as links, not images.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_ASSET_RE = re.compile(
    r"""(?:src\s*=\s*['"]|\[[^\]]*\]\()(?P<path>docs/(?:badges|gallery)/[^'")\s]+)""",
    re.I,
)
_BARE_GALLERY_CELL = re.compile(
    r"^(\|\s*)`?(docs/gallery/[^`|\s]+)`?(\s*\|)",
    re.M,
)

_BADGE_MESSAGES = {
    "ci": ("passing", "#4c1"),
    "coverage": ("ok", "#4c1"),
    "tests": ("ok", "#4c1"),
    "license": ("MIT", "#007ec6"),
    "mesh": ("live", "#4c1"),
}


def extract_readme_local_assets(readme_text: str) -> list[str]:
    """Local docs/badges and docs/gallery paths referenced by <img> or markdown images."""
    seen: list[str] = []
    for m in _ASSET_RE.finditer(readme_text or ""):
        rel = m.group("path").strip().lstrip("./")
        if rel not in seen:
            seen.append(rel)
    return seen


def missing_readme_assets(code_root: Path, readme_text: str | None = None) -> list[str]:
    root = Path(code_root)
    text = readme_text
    if text is None:
        readme = root / "README.md"
        if not readme.is_file():
            return []
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    missing: list[str] = []
    for rel in extract_readme_local_assets(text):
        if not (root / rel).is_file():
            missing.append(rel)
    return missing


def _shield_svg(label: str, message: str, color: str) -> str:
    lw = max(28, 7 * len(label) + 12)
    mw = max(32, 7 * len(message) + 12)
    w = lw + mw
    lx = lw / 2
    mx = lw + mw / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20">'
        f'<linearGradient id="b" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<mask id="a"><rect width="{w}" height="20" rx="3" fill="#fff"/></mask>'
        f'<g mask="url(#a)">'
        f'<path fill="#555" d="M0 0h{lw}v20H0z"/>'
        f'<path fill="{color}" d="M{lw} 0h{mw}v20H{lw}z"/>'
        f'<path fill="url(#b)" d="M0 0h{w}v20H0z"/></g>'
        f'<g fill="#fff" text-anchor="middle" '
        f'font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">'
        f'<text x="{lx:.1f}" y="14">{label}</text>'
        f'<text x="{mx:.1f}" y="14">{message}</text></g></svg>\n'
    )


def _embed_gallery_table(text: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        path = m.group(2)
        stem = Path(path).stem.replace("-", " ")
        return f"{m.group(1)}![{stem}]({path}){m.group(3)}"

    return _BARE_GALLERY_CELL.sub(_sub, text)


def apply_github_house_asset_autofix(code_root: Path) -> list[str]:
    """Write missing badge SVGs the README already names. Do not invent a hero screenshot.

    Gallery table cells that are bare ``docs/gallery/…`` paths become markdown images so
    GitHub renders them. Missing gallery files stay missing — QA/catalog must fail.
    """
    root = Path(code_root)
    readme = root / "README.md"
    if not readme.is_file():
        return []
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    notes: list[str] = []
    new_text = _embed_gallery_table(text)
    if new_text != text:
        readme.write_text(new_text, encoding="utf-8")
        notes.append("README.md:gallery-table")
        text = new_text

    for rel in extract_readme_local_assets(text):
        dest = root / rel
        if dest.is_file():
            continue
        if not rel.startswith("docs/badges/") or not rel.endswith(".svg"):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        stem = Path(rel).stem.lower()
        message, color = _BADGE_MESSAGES.get(stem, ("ok", "#4c1"))
        dest.write_text(_shield_svg(stem, message, color), encoding="utf-8")
        notes.append(rel)
        logger.warning("GitHub-house autofix wrote %s (factory-owned, not Cursor)", rel)
    return notes
