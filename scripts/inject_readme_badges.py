#!/usr/bin/env python3
"""Inject idempotent CI + coverage badge block into satellite README.md files."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "scripts" / "satellite-readme-badges.yaml"
MARKER_START = "<!-- aicom-readme-badges -->"
MARKER_END = "<!-- /aicom-readme-badges -->"

# Monorepo path → satellite id (for bulk inject)
PATH_TO_ID: dict[str, str] = {
    "school": "aimarket-school",
    "courses": "aimarket-courses",
    "desktop-integrations": "aimarket-desktop",
    "aimarket-sdks": "aimarket-sdks",
    "apps/pulse-terminal": "pulse-terminal",
    "acex": "acex",
    "ai-service-mesh": "ai-service-mesh",
    "aimarket-hub": "aimarket-hub",
    "aimarket-widget": "aimarket-widget",
    "coach": "linkedin-profile-coach",
    "aicom-landing": "aicom-landing",
    "aimarket-protocol": "aimarket-protocol",
    "aimarket-agent": "aimarket-agent",
    "plugins/aimarket-mcp-packager": "aimarket-plugins",
    "plugins/aimarket-oracle-gateway": "aimarket-oracle-gateway",
    "alien-monitor": "alien-monitor",
    "platon": "platon",
    "oracles": "oracles",
    "lottery": "lottery",
    "argus": "argus",
    "dioscuri": "dioscuri",
    "theoros": "theoros",
    "helios": "helios",
    "aimarket-mcp": "aimarket-mcp",
    "metis": "metis",
    "aimarket-playground": "aimarket-playground",
    "create-aimarket-agent": "create-aimarket-agent",
    "skopos": "skopos",
    "gaia": "gaia",
    ".": "aicom",
}


def _load() -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    return yaml.safe_load(MAP_PATH.read_text(encoding="utf-8")) or {}


_EXTRA_MD = re.compile(r"^\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)\s*$")


def _absolutize_src(html: str, raw_base: str) -> str:
    """Rewrite any repo-relative `src="…"` in *html* to an absolute raw URL.

    The `extra_badges` entries in satellite-readme-badges.yaml are hand-written HTML carrying
    `src="docs/badges/release.svg"`. Those render on a GitHub page and nowhere else, which is the
    same defect the main badges had -- and one of these READMEs is a published package
    long_description, where a relative path resolves against pypi.org. Rewritten here rather than
    in the YAML so the config stays readable and every satellite gets it without being edited.
    """
    def repl(m: "re.Match[str]") -> str:
        attr, value = m.group(1), m.group(2)
        if value.startswith(("http://", "https://", "//", "data:")):
            return m.group(0)
        return f'{attr}="{raw_base}/{value.lstrip("/")}"'

    return re.sub(r'\b(src)="([^"]+)"', repl, html)


def _extra_badge_html(extra: str, raw_base: str = "") -> str:
    """Turn [![alt](img)](url) or raw <img> into inline HTML for the badge row."""
    extra = extra.strip()
    m = _EXTRA_MD.match(extra)
    if m:
        alt, img, url = m.group(1), m.group(2), m.group(3)
        html = f'<a href="{url}"><img src="{img}" alt="{alt}" /></a>'
        return _absolutize_src(html, raw_base) if raw_base else html
    if extra.startswith("<"):
        return _absolutize_src(extra, raw_base) if raw_base else extra
    return extra


def badge_block(sat: dict[str, Any], *, use_raw_coverage: bool = False) -> str:
    org = sat.get("_org", "alexar76")
    repo = sat["repo"]
    workflow = sat.get("workflow", "ci.yml")
    license_name = sat.get("license", "MIT")
    ci_url = f"https://github.com/{org}/{repo}/actions/workflows/{workflow}"
    # Every src is an ABSOLUTE raw URL, and every href an absolute repository URL. A relative
    # `docs/badges/ci.svg` renders fine on a GitHub page and is a broken image everywhere else --
    # including a PyPI project page, where a relative path resolves against pypi.org. Any README
    # this script touches can become a package long_description (aimarket-hub's is), and PyPI
    # keeps a release forever, so the broken image would be permanent. `use_raw_coverage` used to
    # be the one switch that produced an absolute URL, for the one badge whose SVG is regenerated
    # by CI; it is now how all of them behave and the flag is kept only so existing callers do
    # not break. Absolute costs nothing on GitHub, where these URLs resolve to the same files.
    raw = f"https://raw.githubusercontent.com/{org}/{repo}/main"
    # New repositories can opt into the authoritative GitHub Actions status.
    # Existing satellites retain their self-hosted badge until migrated so this
    # generator does not silently rewrite established README presentation.
    if sat.get("ci_badge") == "github":
        ci_img = f"{ci_url}/badge.svg"
    else:
        ci_img = f"{raw}/docs/badges/ci.svg"
    ci = f'<a href="{ci_url}"><img src="{ci_img}" alt="CI" /></a>'
    html_parts: list[str] = [ci]
    extras = [_extra_badge_html(e, raw) for e in (sat.get("extra_badges") or []) if e and e.strip()]
    html_parts.extend(extras)
    if sat.get("include_coverage", True):
        cov_src = f"{raw}/docs/badges/coverage.svg"
        html_parts.append(f'<a href="{cov_src}"><img src="{cov_src}" alt="Test coverage" /></a>')
    license_src = f"{raw}/docs/badges/license.svg"
    license_badge = (
        f'<a href="https://github.com/{org}/{repo}/blob/main/LICENSE">'
        f'<img src="{license_src}" alt="License: {license_name}" /></a>'
    )
    html_parts.append(license_badge)
    inner = "\n  ".join(html_parts)
    return f"{MARKER_START}\n<p align=\"center\">\n  {inner}\n</p>\n{MARKER_END}"


def _strip_legacy_duplicate_badges(text: str) -> str:
    """Remove pre-marker CI/Release lines superseded by the injected block."""
    lines = text.splitlines()
    out: list[str] = []
    skip_ci_release = False
    for line in lines:
        if MARKER_END in line:
            skip_ci_release = True
            out.append(line)
            continue
        if skip_ci_release and re.search(
            r"^\[!\[(CI|Release)\]", line.strip()
        ):
            continue
        if skip_ci_release and line.strip() and not line.strip().startswith(">"):
            skip_ci_release = False
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _strip_manual_badge_lines(text: str) -> str:
    """Remove standalone markdown shield badge lines (superseded by injected block)."""
    badge_line = re.compile(
        r"^\[!\[[^\]]*\]\([^)]+\)\](?:\([^)]+\))?\s*$"
    )
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        if badge_line.match(line.strip()):
            continue
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def inject_text(text: str, block: str) -> str:
    pattern = re.compile(
        re.escape(MARKER_START) + r"[\s\S]*?" + re.escape(MARKER_END)
        + r"[ \t]*(?:\r?\n[ \t]*)*",
    )
    if pattern.search(text):
        text = pattern.sub(block + "\n\n", text, count=1)
        return _strip_legacy_duplicate_badges(_strip_manual_badge_lines(text))

    mirror_end = "<!-- aicom-mirror-notice -->"
    if mirror_end in text:
        # Insert after mirror notice block (ends at first blank line after policy line)
        lines = text.splitlines(keepends=True)
        out: list[str] = []
        i = 0
        while i < len(lines):
            out.append(lines[i])
            if lines[i].strip() == mirror_end:
                i += 1
                while i < len(lines) and lines[i].strip().startswith(">"):
                    out.append(lines[i])
                    i += 1
                while i < len(lines) and lines[i].strip() == "":
                    out.append(lines[i])
                    i += 1
                out.append(block + "\n\n")
                out.extend(lines[i:])
                return "".join(out)
            i += 1

    # After first heading
    m = re.search(r"^# .+\n", text, re.MULTILINE)
    if m:
        pos = m.end()
        text = _strip_manual_badge_lines(text)
        return text[:pos] + "\n" + block + "\n\n" + text[pos:]
    return block + "\n\n" + text


def inject_file(readme: Path, sat: dict[str, Any], *, dry_run: bool = False) -> bool:
    if not readme.is_file():
        return False
    badges_dir = readme.parent / "docs" / "badges"
    gen = ROOT / "scripts" / "generate_static_badge.py"
    if not dry_run:
        badges_dir.mkdir(parents=True, exist_ok=True)
        # Generate only badges whose value is genuinely static. Repositories
        # using the GitHub Actions badge must never publish a hard-coded
        # "CI: passing" asset.
        static_badges = [("License", sat.get("license", "MIT"), "license.svg")]
        if sat.get("ci_badge") != "github":
            static_badges.insert(0, ("CI", "passing", "ci.svg"))
        for label, value, name in static_badges:
            out = badges_dir / name
            if not out.is_file():
                subprocess.run(
                    [sys.executable, str(gen), label, value, str(out)],
                    check=False,
                )
    org = _load().get("org", "alexar76")
    sat = {**sat, "_org": org}
    block = badge_block(sat, use_raw_coverage=False)
    new_text = inject_text(readme.read_text(encoding="utf-8"), block)
    if new_text == readme.read_text(encoding="utf-8"):
        return False
    if not dry_run:
        readme.write_text(new_text, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--satellite", help="Satellite id from satellite-readme-badges.yaml")
    parser.add_argument("--readme", type=Path, help="Explicit README path")
    parser.add_argument("--all", action="store_true", help="Inject all mapped monorepo READMEs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    data = _load()
    satellites: dict[str, Any] = data.get("satellites") or {}

    targets: list[tuple[Path, dict[str, Any]]] = []
    if args.readme and args.satellite:
        targets.append((args.readme, satellites[args.satellite]))
    elif args.satellite:
        sat = satellites.get(args.satellite)
        if not sat:
            print(f"unknown satellite: {args.satellite}", file=sys.stderr)
            return 1
        # profile etc. not in PATH_TO_ID values as readme root
        for path, sid in PATH_TO_ID.items():
            if sid == args.satellite:
                targets.append((ROOT / path / "README.md", sat))
                break
        else:
            print(f"no README path for satellite {args.satellite}", file=sys.stderr)
            return 1
    elif args.all:
        for path, sid in PATH_TO_ID.items():
            readme = ROOT / path / "README.md"
            if sid in satellites and readme.is_file():
                targets.append((readme, satellites[sid]))
    else:
        parser.print_help()
        return 1

    changed = 0
    for readme, sat in targets:
        readme = readme.resolve()
        if inject_file(readme, sat, dry_run=args.dry_run):
            try:
                rel = readme.relative_to(ROOT)
            except ValueError:
                rel = readme
            print(f"  ✓ badges → {rel}")
            changed += 1
        else:
            try:
                rel = readme.relative_to(ROOT)
            except ValueError:
                rel = readme
            print(f"  · unchanged {rel}")
    print(f"Done ({changed} updated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
