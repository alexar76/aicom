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

# Everything above is an explicit override (a satellite whose export layout keeps a
# subfolder, e.g. plugins/). Every OTHER registered satellite is appended from
# satellite-map.yaml with the default layout — the folder becomes the repo root.
# Without this, the audit flagged 22 docs (gaia, logos, metis, atlas, momus, skopos,
# signal-hunt, …) that this fixer had no entry for and therefore silently skipped.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from aicom_publish_config import satellite_path_to_repo  # noqa: E402

    _explicit = {p.rstrip("/") for p, _ in PREFIX_TO_BLOB_BASE}
    for _path, _repo in sorted(satellite_path_to_repo().items()):
        if _path in _explicit or _path.endswith(".md"):
            continue
        PREFIX_TO_BLOB_BASE.append((f"{_path}/", f"https://github.com/{ORG}/{_repo}/blob/{BRANCH}/"))
except Exception as exc:  # pragma: no cover - map unreadable → keep the static list
    print(f"warning: satellite map unavailable ({exc}); using the static prefix list", file=sys.stderr)

# Longest prefix first, so plugins/aimarket-oracle-gateway/ never loses to plugins/.
PREFIX_TO_BLOB_BASE.sort(key=lambda kv: -len(kv[0]))

SATELLITE_DIRS = sorted({p.rstrip("/") for p, _ in PREFIX_TO_BLOB_BASE}, key=len, reverse=True)

# Built from the same prefix table, so a satellite is matched here the moment it is
# registered — the old hand-written alternation is what let gaia/, logos/, metis/ and
# friends slip past the rewrite while the audit kept failing on them.
SATellite_PATH = (
    r"(?!aimarket-whitepaper(?:\.md)?(?:#|$))"
    r"(?:aimarket-(?!whitepaper)[^)\s#]+|"
    + "|".join(rf"{re.escape(d)}(?:/[^)\s#]*)?" for d in SATELLITE_DIRS)
    + r")"
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


def owning_satellite(path: Path) -> str | None:
    """The satellite folder a file lives in, if any."""
    try:
        rel = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None
    for d in SATELLITE_DIRS:
        if rel.startswith(d + "/"):
            return d
    return None


_REL = re.compile(r"(!?\[[^\]]*\]\()(?!https?://|mailto:|#|/)([^)\s]+?)(#[^)]*)?\)")


def rewrite_escapes(text: str, doc: Path, home: str) -> tuple[str, int]:
    """Absolutise links that resolve OUTSIDE the satellite the document is published in.

    Each satellite folder is rsynced to its repo ROOT, so `../scripts/satellite-map.yaml`
    in acex/README.md has no target on alexar76/acex — it 404s for every reader of the
    published repo while resolving perfectly in the monorepo, which is why it survived.
    Cross-satellite targets go to the repo that owns them; everything else to aicom.
    """
    changes = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal changes
        head, target, anchor = m.group(1), m.group(2), m.group(3) or ""
        resolved = (doc.parent / target).resolve()
        try:
            rel = resolved.relative_to(ROOT).as_posix()
        except ValueError:
            return m.group(0)
        if rel == home or rel.startswith(home + "/"):
            return m.group(0)          # stays inside the published repo — leave relative
        if not resolved.exists():
            return m.group(0)          # a genuinely dead link; do not launder it into a 404
        url = satellite_path_to_url(rel) or f"https://github.com/{ORG}/aicom/blob/{BRANCH}/{rel}"
        changes += 1
        return f"{head}{url.split('#', 1)[0]}{anchor})"

    return _REL.sub(repl, text), changes


def rewrite_content(text: str, lang: str, home: str | None = None) -> tuple[str, int]:
    """`home` is the satellite the file itself lives in — its own links stay relative.

    oracles/docs/crypto-maturity.en.md links `../oracles/chronos/SECURITY.md`, which
    resolves correctly both in the monorepo and inside alexar76/oracles. Absolutising
    it would point at a path the satellite does not have.
    """
    changes = 0

    def sub_link(m: re.Match[str]) -> str:
        nonlocal changes
        inner = m.group(1)
        full = m.group(0)
        if home and (inner == home or inner.startswith(home + "/")):
            return full
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
        # Every registered satellite folder, so a doc published to its own repo is
        # checked for links that escape that repo. The hand-written list above named
        # 8 of 30+ folders, which is how 157 escaping links accumulated unseen.
        seen = set(paths)
        for sat in SATELLITE_DIRS:
            base = ROOT / sat
            if not base.is_dir():
                continue
            for md in sorted(base.rglob("*.md")):
                if any(part in {"node_modules", ".venv", "dist", "build"} for part in md.parts):
                    continue
                if md not in seen:
                    seen.add(md)
                    paths.append(md)
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
        home = owning_satellite(path)
        updated, n = rewrite_content(original, infer_lang(path), home=home)
        if home:
            updated, esc = rewrite_escapes(updated, path, home)
            n += esc
        if n and updated != original:
            total += n
            print(f"{path.relative_to(ROOT)}: {n} link(s) rewritten")
            if not dry:
                path.write_text(updated, encoding="utf-8")
    print(f"Done — {total} total rewrites" + (" (dry run)" if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
