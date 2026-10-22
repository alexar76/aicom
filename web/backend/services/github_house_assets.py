"""README badge/gallery assets must exist on disk — GitHub shows alt text when they 404.

Measured on Sentinel in alexar76/aicom-products: README linked coverage.svg, tests.svg and
docs/gallery/hero.svg while the catalog snapshot only had ci.svg + license.svg. GitHub
rendered «coverage», «tests» and «Sentinel hero» as links, not images.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The factory's own record of running a product's tests. ``docs/badges/ci.svg`` is drawn
#: from it and from nothing else: an agent-written or placeholder "ci: passing" said a CI
#: had run when none had (2026-10-21 audit), so the badge is factory-owned and says which run.
FACTORY_TESTS_RECORD = "docs/badges/factory-tests.json"
CI_BADGE = "docs/badges/ci.svg"
_GREY = "#9f9f9f"
_STATUS_COLORS = {"passed": "#4c1", "failed": "#e05d44", "not run": _GREY, "not re-run": _GREY}
# What the tests exercise: source and config files, outside the directories the catalog
# publish drops or rewrites. Docs, READMEs and workflow files are edited after the run (badge
# markers, CONTRIBUTING.md) and caches, databases and keys never reach the catalog, so none of
# them may make a published tree look different from the one that was tested.
_DIGEST_SKIP_DIRS = {"docs", ".github", ".git", "node_modules", "__pycache__", ".venv", "venv",
                     ".pytest_cache", ".mypy_cache", ".ruff_cache", ".aicom_sandbox", "dist",
                     "build", ".next", "coverage", "htmlcov"}
_DIGEST_SUFFIXES = {".py", ".pyi", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
                    ".json", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".txt", ".html", ".css",
                    ".scss", ".sql", ".sh", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".dart"}

_ASSET_RE = re.compile(
    r"""(?:src\s*=\s*['"]|\[[^\]]*\]\()(?P<path>docs/(?:badges|gallery)/[^'")\s]+)""",
    re.I,
)
_BARE_GALLERY_CELL = re.compile(
    r"^(\|\s*)`?(docs/gallery/[^`|\s]+)`?(\s*\|)",
    re.M,
)

# A missing badge is drawn as what is known, never as a result: nobody measured coverage or
# counted tests for these, so they say so. ``ci`` is handled by refresh_factory_test_badge.
_BADGE_MESSAGES = {
    "coverage": ("not measured", _GREY),
    "tests": ("not counted", _GREY),
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


def product_tree_digest(code_root: Path) -> str:
    """SHA-256 over the source and config files a product's tests exercise (see _DIGEST_*)."""
    root = Path(code_root)
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if any(part in _DIGEST_SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if path.suffix.lower() not in _DIGEST_SUFFIXES or rel.name.lower().startswith(".env"):
            continue
        h.update(rel.as_posix().encode("utf-8") + b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def _status_of(result: dict[str, Any]) -> str:
    if result.get("skipped") or not result.get("commands"):
        return "not run"
    return "passed" if result.get("passed") else "failed"


def record_factory_test_run(code_root: Path, result: dict[str, Any], *, now: float | None = None) -> dict:
    """Write the factory's test run into the product tree and draw ``ci.svg`` from it.

    ``result`` is what the pipeline's runtime-test stage returns: ``passed``, ``skipped``,
    ``commands`` and per-command ``results`` with ``exit_code``.
    """
    root = Path(code_root)
    record = {
        "status": _status_of(result),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time())),
        "commands": [str(c) for c in result.get("commands") or []],
        "exit_codes": [r.get("exit_code") for r in result.get("results") or [] if isinstance(r, dict)],
        "tree_sha256": product_tree_digest(root),
        "what": (
            "The AI-Factory ran these test commands on this tree before publishing it. "
            "This is not a GitHub Actions status."
        ),
    }
    dest = root / FACTORY_TESTS_RECORD
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    refresh_factory_test_badge(root)
    return record


def refresh_factory_test_badge(code_root: Path) -> str:
    """Redraw ``ci.svg`` from the factory's record; return the status it shows.

    No record → "not run". A record for a different tree (code changed after the run) →
    "not re-run". Whatever ``ci.svg`` said before is replaced: the file is factory-owned.
    """
    root = Path(code_root)
    status = "not run"
    when = ""
    try:
        record = json.loads((root / FACTORY_TESTS_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = None
    if isinstance(record, dict) and record.get("status") in _STATUS_COLORS:
        if record.get("tree_sha256") == product_tree_digest(root):
            status = str(record["status"])
            when = str(record.get("checked_at") or "")[:10]
        else:
            status = "not re-run"
    message = f"{status} {when}".strip() if status in ("passed", "failed") else status
    dest = root / CI_BADGE
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_shield_svg("factory tests", message, _STATUS_COLORS[status]), encoding="utf-8")
    return status


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
        if rel == CI_BADGE:
            # Always redrawn, present or not: an existing ci.svg may be an agent's "passing".
            status = refresh_factory_test_badge(root)
            notes.append(f"{rel}:{status}")
            continue
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
