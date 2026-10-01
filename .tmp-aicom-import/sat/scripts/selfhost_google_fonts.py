#!/usr/bin/env python3
"""Mirror a Google Fonts stylesheet into a site's own origin.

Why this exists: a `<link>` to fonts.googleapis.com sends every visitor's IP address to
Google before the page has done anything, with no consent asked and no way to refuse. That
is the one thing in this estate with live European case law against it (LG München I,
2022-01-20, 3 O 17493/20). Self-hosting removes the transfer instead of asking permission
for it, and it is faster: one origin, no extra DNS + TLS handshake on the critical path.

What it does NOT do: re-subset or re-encode anything. It fetches the exact stylesheet
Google would serve a current browser, keeps the `@font-face` blocks and their
`unicode-range` declarations verbatim, and only rewrites `src: url(...)` to point at a
local copy. So a page still downloads the latin file and not the cyrillic one, exactly as
before — the only thing that changes is who serves it.

Downloaded files are pooled in a gitignored cache so 50-odd stylesheets that all want IBM
Plex Mono 400 fetch it once. The cache is not committed: it is regenerable from Google, and
what the sites actually serve is their own copy of only the faces they asked for — they
deploy independently, and a shared font host would just be a third party we happen to own.

    # one site
    scripts/selfhost_google_fonts.py --dest pantheon/public --from-html pantheon/index.html \\
        --rewrite pantheon/index.html --href /fonts/fonts.css

    # every live page in this tree
    scripts/selfhost_google_fonts.py --all
"""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Gitignored: a download cache, not a source of truth. Lives under scripts/ rather than at
# the repo root so it does not create a top-level directory the publish guard has to
# classify as public or excluded.
POOL = ROOT / "scripts" / ".webfont-cache"
PROMO = ROOT.parent / "PromoMaterials"

# Google serves woff2 only to browsers it believes support it. With a stale or absent
# User-Agent it falls back to ttf, which is roughly twice the bytes for the same glyphs.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

CSS2 = re.compile(r"https://fonts\.googleapis\.com/css2\?[^\"'\s)>]+")
SRC_URL = re.compile(r"url\([\"']?(https://fonts\.gstatic\.com/[^)\"'\s]+)[\"']?\)")
PRECONNECT = re.compile(
    r"[ \t]*<link[^>]*rel=[\"']preconnect[\"'][^>]*fonts\.(?:googleapis|gstatic)\.com[^>]*>"
    r"[ \t]*\r?\n?",
    re.I,
)
STYLESHEET = re.compile(
    r"[ \t]*<link\b[^>]*fonts\.googleapis\.com/css2[^>]*>\s*",
    re.I | re.S,
)
IMPORT = re.compile(
    r"""@import\s+url\(\s*['"]https://fonts\.googleapis\.com/css2\?[^'"]+['"]\s*\)\s*;""",
    re.I,
)

SKIP_DIR_NAMES = {
    "node_modules", ".git", ".next", ".venv", "venv", ".venv-test",
    "__pycache__", "dist", "coverage", ".turbo", ".claude", ".upstreams",
}
SKIP_SUFFIXES = {".woff2", ".woff", ".ttf", ".png", ".jpg", ".jpeg", ".webp", ".svg",
                 ".pdf", ".lock"}
# Tests that mention Google Fonts as sample customer HTML, not a live page.
SKIP_PATH_PARTS = {
    "test_code_entrypoint.py",
    "test_developer_agent_prompts.py",
    "test_preview_stylesheet_heal.py",
    "selfhost_google_fonts.py",
}

# Longest-prefix wins. dest is relative to the scan root (aicom or PromoMaterials).
# Vite apps put static files in public/, so dest is public/ even when index.html sits
# next to it — the browser then sees /fonts/fonts.css.
PREFIX_DEST = (
    ("ecosystem-landing/", "ecosystem-landing"),
    ("edu-landing/", "edu-landing"),
    ("pantheon/", "pantheon/public"),
    ("lottery/frontend/", "lottery/frontend"),
    ("alien-monitor/frontend/", "alien-monitor/frontend/public"),
    ("use-cases-portal/", "use-cases-portal"),
    ("cite-desks/kernel/web/", "cite-desks/kernel/web"),
    ("cite-desks/emberline/frontend/", "cite-desks/emberline/frontend/public"),
    ("independent/daily-card/apps/web/", "independent/daily-card/apps/web/public"),
    ("web/frontend/", "web/frontend/public"),
    ("web/backend/", "web/frontend/public"),
    ("docs/encyclopedia/", "docs/encyclopedia/shared"),
    ("skopos/docs/landing/", "skopos/docs/landing"),
    ("skopos/skopos/", "skopos/docs/landing"),
    ("aicom-landing/public/", "aicom-landing/public"),
    ("aicom-landing/docs/", "aicom-landing/docs"),
    ("atlas/frontend/public/", "atlas/frontend/public"),
    ("atlas/atlas/_static/", "atlas/atlas/_static"),
    ("art-portal/", "art-portal"),
    ("portal/", "portal"),
    ("x-radar/app/static/", "x-radar/app/static"),
    ("reddit-radar/app/static/", "reddit-radar/app/static"),
    ("video-generator/app/static/", "video-generator/app/static"),
)

SCAN_GLOBS = {".html", ".css", ".js", ".py", ".ts", ".tsx", ".jsx"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def css_urls_in(text: str) -> list[str]:
    seen: list[str] = []
    for raw in CSS2.findall(text):
        url = html.unescape(raw)
        if url not in seen:
            seen.append(url)
    return seen


def pool_name(gstatic_url: str) -> str:
    """A stable filename per face, taken from Google's own path.

    Their path already encodes family, style and subset (…/s/inter/v20/<hash>.woff2), and the
    hash changes when the file does — which is exactly the property a cache wants.
    """
    parts = [p for p in gstatic_url.split("/") if p]
    family = parts[parts.index("s") + 1] if "s" in parts else "font"
    return "%s-%s" % (family, parts[-1])


def mirror(css_urls: list[str], dest_fonts: Path) -> tuple[int, int]:
    """Fetch the stylesheets, pool their faces, write one local copy under dest_fonts.

    Several URLs collapse into one `fonts.css` on purpose: a site's pages often ask for the
    same families at slightly different weights, and the file is nothing but `@font-face`
    blocks, so appending them is valid CSS. A face declared twice is the same bytes and the
    same declaration, which costs a duplicate rule and nothing else.
    """
    POOL.mkdir(parents=True, exist_ok=True)
    dest_fonts.mkdir(parents=True, exist_ok=True)

    fetched = reused = 0
    chunks: list[str] = []

    def localise(match: re.Match) -> str:
        nonlocal fetched, reused
        remote = match.group(1)
        name = pool_name(remote)
        pooled = POOL / name
        if not pooled.exists():
            pooled.write_bytes(fetch(remote))
            fetched += 1
        else:
            reused += 1
        local = dest_fonts / name
        if not local.exists() or local.read_bytes() != pooled.read_bytes():
            local.write_bytes(pooled.read_bytes())
        return "url(%s)" % name

    for css_url in css_urls:
        css = fetch(css_url).decode("utf-8")
        localised = SRC_URL.sub(localise, css)
        header = (
            "/* Mirrored from Google Fonts by scripts/selfhost_google_fonts.py — do not\n"
            "   hand-edit. Faces and unicode-range are Google's, verbatim; only the src\n"
            "   URLs are local, so no visitor's address reaches a third party for a font.\n"
            "   Source: %s */\n" % css_url
        )
        chunks.append(header + localised)
        if "fonts.gstatic.com" in localised:
            raise RuntimeError("gstatic URL survived localisation for %s" % css_url)

    (dest_fonts / "fonts.css").write_text("\n".join(chunks), encoding="utf-8")
    return fetched, reused


def href_for(page: Path, dest: Path) -> str:
    css = dest / "fonts" / "fonts.css"
    try:
        page.resolve().relative_to(dest.resolve())
    except ValueError:
        return "/fonts/fonts.css"
    return os.path.relpath(css, page.parent).replace("\\", "/")


def rewrite(path: Path, href: str) -> str:
    """Point one page at the local stylesheet and drop the handshakes it no longer needs.

    The `preconnect` hints go too. Left behind they would still open a TLS connection to
    Google on every page load — announcing the visitor without even fetching a font, which
    is the same disclosure with none of the benefit.
    """
    text = original = path.read_text(encoding="utf-8")
    changed = False

    if STYLESHEET.search(text):
        match = STYLESHEET.search(text)
        indent = re.match(r"[ \t]*", match.group(0)).group(0)
        text = STYLESHEET.sub(
            '%s<link href="%s" rel="stylesheet" />\n' % (indent, href), text, count=1
        )
        text = STYLESHEET.sub("", text)
        text = PRECONNECT.sub("", text)
        changed = True

    if IMPORT.search(text):
        text = IMPORT.sub('@import url("%s");' % href, text)
        changed = True

    if not changed:
        return "no css2 <link>/@import found"
    if text == original:
        return "unchanged"
    path.write_text(text, encoding="utf-8")
    return "rewritten"


def should_skip(path: Path) -> bool:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    if path.name in SKIP_PATH_PARTS:
        return True
    if path.name == "fonts.css":
        return True
    return any(part in SKIP_DIR_NAMES for part in path.parts)


# Pages an app serves, not a directory. Mirroring beside them writes a copy no route serves:
# the hub's landing got aimarket-hub/fonts/ and 404ed on every hub. Link the app's own bundle.
APP_SERVED = {
    "aimarket-hub/": "the hub serves aimarket_hub/assets/fonts at /assets/fonts/ — link "
                     "assets/fonts/fonts.css (relative, so it works under a path prefix) and "
                     "add any new face to that bundle by hand",
}


def dest_for(path: Path, root: Path) -> Path:
    rel = path.relative_to(root).as_posix()
    for prefix, how in APP_SERVED.items():
        if rel.startswith(prefix):
            raise SystemExit(f"{rel} links Google Fonts, but {how}")
    if "site_assets" in path.parts:
        idx = path.parts.index("site_assets")
        return Path(*path.parts[: idx + 1])
    if "/docs/landing/" in rel or rel.endswith("/docs/landing/index.html"):
        return path.parent
    best = None
    for prefix, dest in PREFIX_DEST:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            best = dest
            break
    if best:
        return root / best
    return path.parent


def iter_candidates(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in SCAN_GLOBS:
                continue
            if should_skip(path):
                continue
            yield path


def collect(roots: list[Path]) -> dict[Path, dict[str, object]]:
    """Group files by dest → {urls, files}."""
    groups: dict[Path, dict[str, object]] = defaultdict(lambda: {"urls": [], "files": []})
    for root in roots:
        if not root.is_dir():
            continue
        for path in iter_candidates(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            urls = css_urls_in(text)
            if not urls:
                continue
            dest = dest_for(path, root)
            bucket = groups[dest]
            for url in urls:
                if url not in bucket["urls"]:
                    bucket["urls"].append(url)
            bucket["files"].append(path)
    return groups


def run_all(roots: list[Path]) -> int:
    groups = collect(roots)
    if not groups:
        print("no Google Fonts URL found — nothing to mirror", file=sys.stderr)
        return 1

    total_files = 0
    for dest, bucket in sorted(groups.items(), key=lambda kv: str(kv[0])):
        urls: list[str] = bucket["urls"]
        files: list[Path] = bucket["files"]
        dest_fonts = dest / "fonts"
        fetched, reused = mirror(urls, dest_fonts)
        faces = list(dest_fonts.glob("*.woff2"))
        size = sum(f.stat().st_size for f in faces)
        print("mirrored %d faces (%.0f KB) into %s — %d newly fetched, %d already pooled"
              % (len(faces), size / 1024, dest_fonts, fetched, reused))
        for path in files:
            href = href_for(path, dest)
            status = rewrite(path, href)
            print("  %s %s → %s" % (status, path.relative_to(path.anchor), href))
            if status == "rewritten":
                total_files += 1

    pantheon_public = ROOT / "pantheon" / "public" / "fonts"
    pantheon_dist = ROOT / "pantheon" / "dist"
    if pantheon_public.is_dir() and pantheon_dist.is_dir():
        dest_fonts = pantheon_dist / "fonts"
        if dest_fonts.exists():
            shutil.rmtree(dest_fonts)
        shutil.copytree(pantheon_public, dest_fonts)
        for html_path in (pantheon_dist / "index.html", pantheon_dist / "school.html"):
            if html_path.is_file() and css_urls_in(html_path.read_text(encoding="utf-8", errors="replace")):
                print("  %s %s → /fonts/fonts.css"
                      % (rewrite(html_path, "/fonts/fonts.css"), html_path))
                total_files += 1

    print("rewrote %d files" % total_files)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", help="web root of the site; fonts land in <dest>/fonts/")
    ap.add_argument("--from-html", action="append", default=[],
                    help="file to read Google Fonts URLs out of (repeatable)")
    ap.add_argument("--css-url", action="append", default=[],
                    help="explicit css2 URL (repeatable)")
    ap.add_argument("--rewrite", action="append", default=[],
                    help="page to repoint at the local stylesheet (repeatable)")
    ap.add_argument("--href", default="/fonts/fonts.css",
                    help="href to write into the rewritten pages (default /fonts/fonts.css)")
    ap.add_argument("--all", action="store_true",
                    help="scan aicom + PromoMaterials and self-host every css2 URL")
    args = ap.parse_args()

    if args.all:
        roots = [ROOT]
        if PROMO.is_dir():
            roots.append(PROMO)
        return run_all(roots)

    if not args.dest:
        print("--dest is required unless --all", file=sys.stderr)
        return 2

    urls: list[str] = list(args.css_url)
    for name in args.from_html + args.rewrite:
        path = Path(name)
        if not path.is_file():
            print("no such file: %s" % name, file=sys.stderr)
            return 2
        for url in css_urls_in(path.read_text(encoding="utf-8", errors="replace")):
            if url not in urls:
                urls.append(url)

    if not urls:
        print("no Google Fonts URL found — nothing to mirror", file=sys.stderr)
        return 1

    dest = Path(args.dest)
    fetched, reused = mirror(urls, dest / "fonts")
    faces = list((dest / "fonts").glob("*.woff2"))
    size = sum(f.stat().st_size for f in faces)
    print("mirrored %d faces (%.0f KB) into %s — %d newly fetched, %d already pooled"
          % (len(faces), size / 1024, dest / "fonts", fetched, reused))
    for name in args.rewrite:
        print("  %s" % rewrite(Path(name), args.href))
    if not args.rewrite:
        print("replace the Google <link> tags with:")
        print('  <link href="%s" rel="stylesheet" />' % args.href)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
