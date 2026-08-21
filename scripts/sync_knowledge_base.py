#!/usr/bin/env python3
"""Propagate the ecosystem fact table into every agent knowledge base — from ONE source.

    python3 scripts/sync_knowledge_base.py --check        # CI: report drift, change nothing
    python3 scripts/sync_knowledge_base.py --write        # regenerate the blocks
    python3 scripts/sync_knowledge_base.py --from-github  # compare the map against GitHub
    python3 scripts/sync_knowledge_base.py --list         # where every knowledge base lives

**The problem this solves.** Nine agent knowledge bases each carried a hand-typed component list, in
four languages and three file formats. Adding a satellite meant editing nine files, so nobody did:
MOMUS, Treasury, ATLAS and the bridges were missing from every single one.

**How it works.** Each target file gets TWO generated blocks, fenced by markers in that file's own
comment syntax: the component roster (from satellite-map.yaml) and the physical/map SKU table
(from ATLAS STATION_CATALOG + LAYER_META + PRODUCT_CAPS). Everything outside the markers is
hand-written prose and is never touched — the careful wording in these prompts (ARGUS's
"WARDEN does NOT orchestrate", MOMUS's "cannot pay itself") is load-bearing and must stay
human-authored. The generator only owns the roster and the SKU table.

**Who is responsible for keeping it current.** Nobody, by design — a human owner is exactly what
decays. Three mechanical layers instead:

1. `tests/test_knowledge_sync.py` fails when a satellite is in the map but missing from a knowledge
   base, so a drifted base cannot pass CI;
2. `--check` runs in CI on every change to the map or a target;
3. `--from-github` re-reads what the public repos actually say, so the map cannot silently rot
   against the published truth. It is READ-ONLY and never pushes: this repo's push target is Gitea,
   and the GitHub repos are a mirror.

A file with no markers is reported as `no-markers`, not silently skipped — an unmarked target is the
failure mode that let the drift happen in the first place.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ecosystem_knowledge import (  # noqa: E402
    BEGIN,
    END,
    components,
    fill_blanks_from_github,
    refresh_from_github,
    render_block,
)
from physical_capabilities import (  # noqa: E402
    BEGIN as PHYS_BEGIN,
    END as PHYS_END,
    render_block as render_physical_block,
)

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Target:
    """One knowledge base and how the generated block is fenced inside it.

    `comment` describes WHERE the block lands, not the file's extension. A block injected into prompt
    prose — a Markdown doc, a Python triple-quoted brief, a TypeScript template literal — uses the
    `md` fence, because an HTML comment is inert in all three and invisible when the prose is
    rendered. The `py` / `ts` fences are for blocks that land in actual code."""

    path: str
    comment: str          # "md" (prose, incl. inside py/ts strings) | "py" | "ts"
    consumer: str         # which agent reads it
    lang: str = "en"
    heading: str = "### Component registry"

    @property
    def full(self) -> Path:
        return ROOT / self.path


# Every knowledge base in the monorepo, and which agent eats it. Keep this list in step with
# docs/ecosystem/knowledge-sources.md — the test asserts they agree.
TARGETS: tuple[Target, ...] = (
    Target("docs/ecosystem/knowledge-base.md", "md", "shared ecosystem knowledge base"),
    Target("docs/ecosystem/knowledge-base-ru.md", "md", "shared ecosystem knowledge base", "ru"),
    Target("docs/ecosystem/knowledge-base-es.md", "md", "shared ecosystem knowledge base", "es"),
    Target("docs/ecosystem/knowledge-base-fr.md", "md", "shared ecosystem knowledge base", "fr"),
    Target("docs/ecosystem/knowledge-base-zh.md", "md", "shared ecosystem knowledge base", "zh"),
    Target("atlas/atlas/ecosystem_context.py", "md", "ATLAS Analyst"),
    Target("argus/src/ecosystem/knowledge.ts", "md", "ARGUS (demand-side client)"),
    Target("web/backend/services/support_rag_baseline.md", "md", "web support agent (RAG baseline)"),
)

# Consumers that already read satellite-map.yaml at RUNTIME and therefore need no injected block.
# They are the pattern this script generalises, and they are listed so the registry doc stays honest.
RUNTIME_CONSUMERS = (
    ("alien-monitor/backend/ecosystem_registry.py", "Alien Monitor AI bot"),
    ("scripts/mirror_satellites.sh", "mirror / publish tooling"),
    ("atlas/atlas/capability_awareness.py",
     "ATLAS Analyst surfaces — live from STATION_CATALOG at request time"),
    ("logos/logos/app.py",
     "LOGOS assistant — live Hub GET /api/v1/federation/capabilities, not a static SKU list"),
)

# Whole-file mirrors: the EN knowledge base is also the Alien Monitor fallback copy.
# The copy lands in a DIFFERENT repo (alexar76/alien-monitor), where the source's
# relative links (../onchain-journal.md, ./whitepaper/en.md, …) have no targets — so the
# copy is not byte-identical: relative links are absolutised against the aicom blob URL
# first. --write copies the rewritten text, --check fails on drift against it.
FILE_MIRRORS = (
    ("docs/ecosystem/knowledge-base.md", "alien-monitor/docs/ecosystem/knowledge-base.md"),
)

MIRROR_BLOB_BASE = "https://github.com/alexar76/aicom/blob/main/"

# [text](path) and ![alt](path) where path is repo-relative (not http/mailto/#/absolute).
_REL_LINK = re.compile(r"(!?\[[^\]]*\]\()(?!https?://|mailto:|#|/)([^)\s]+?)(#[^)]*)?\)")


def mirror_text(src_rel: str, text: str) -> str:
    """Rewrite the source's repo-relative links to absolute aicom blob URLs.

    The mirror destination is a different repository, so every relative link in the
    source resolves to nothing there. Anchors are preserved; links that do not resolve
    to a real file in the monorepo are left untouched so they stay visible as breakage
    at the source instead of being laundered into a plausible-looking 404.
    """
    src_dir = (ROOT / src_rel).parent

    def repl(m: re.Match[str]) -> str:
        head, target, anchor = m.group(1), m.group(2), m.group(3) or ""
        resolved = (src_dir / target).resolve()
        try:
            rel = resolved.relative_to(ROOT)
        except ValueError:
            return m.group(0)
        if not resolved.exists():
            return m.group(0)
        return f"{head}{MIRROR_BLOB_BASE}{rel.as_posix()}{anchor})"

    return _REL_LINK.sub(repl, text)

# Knowledge stores that deliberately take NO component roster, with the reason. Listed because
# "why isn't X in the sync?" is the question that ends with a roster pasted into the wrong prompt.
NOT_TARGETS = (
    ("skopos/skopos/agent/ecosystem_briefing.py",
     "an on-call SRE prompt capped at 180 words — it reads LIVE host data, and a 35-line roster "
     "would crowd out the health signal it exists to summarise"),
    ("web/backend/services/methodology_knowledge.py",
     "the Methodology Agent's lesson/case store, not ecosystem knowledge — it learns from review "
     "outcomes and must not be seeded with static facts"),
    ("metis/scripts/seed_ecosystem_knowledge.py",
     "curated Q&A pairs about METIS ITSELF for grounded RAG; the component roster belongs in the "
     "shared knowledge base its answers point to"),
    ("helios/helios/knowledge/mnemosyne.py",
     "a read-only BM25 reader over DIOSCURI's mnemosyne.json — that corpus is built by DIOSCURI "
     "from live sources, so it picks up new satellites without a roster injection"),
    ("momus/momus/config.py",
     "MOMUS learns what exists from its TARGET ALLOWLIST, not from prose. A component it may probe "
     "must be registered there deliberately; a roster in a prompt would invite it to probe things "
     "nobody authorised"),
)

_FENCE = {
    "md": ("<!-- {} -->", "<!-- {} -->"),
    "py": ("# {}", "# {}"),
    "ts": ("// {}", "// {}"),
}


def _markers(kind: str, begin_token: str = BEGIN, end_token: str = END) -> tuple[str, str]:
    open_fmt, close_fmt = _FENCE[kind]
    return open_fmt.format(begin_token), close_fmt.format(end_token)


def _block_for(t: Target, begin_token: str, end_token: str, body: str) -> str:
    begin, end = _markers(t.comment, begin_token, end_token)
    return f"{begin}\n{body}{end}"


def _replace_fence(
    text: str,
    t: Target,
    begin_token: str,
    end_token: str,
    body: str,
) -> tuple[str, str]:
    """Return (new_text, status) for one named fence."""
    begin, end = _markers(t.comment, begin_token, end_token)
    if begin not in text or end not in text:
        return text, "no-markers"
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    desired = _block_for(t, begin_token, end_token, body)
    current = pattern.search(text)
    if current and current.group(0) == desired:
        return text, "ok"
    return pattern.sub(lambda _: desired, text, count=1), "updated"


def _apply_target(text: str, t: Target) -> tuple[str, list[str]]:
    """Apply both generated fences. Status tags: ok / updated / no-markers / no-markers-physical."""
    notes: list[str] = []
    text, st = _replace_fence(
        text,
        t,
        BEGIN,
        END,
        render_block(heading=t.heading, lang=t.lang),
    )
    notes.append("components:" + st)
    phys_body = render_physical_block(lang=t.lang, heading="### Physical and map SKUs")
    text, st_p = _replace_fence(text, t, PHYS_BEGIN, PHYS_END, phys_body)
    tag = {"no-markers": "no-markers-physical"}.get(st_p, st_p)
    notes.append("physical:" + tag)
    return text, notes


def _target_status(notes: list[str]) -> str:
    joined = " ".join(notes)
    if "no-markers" in joined:
        return "no-markers"
    if "updated" in joined:
        return "updated"
    return "ok"


def run(mode: str) -> int:
    rows = components()
    print(f"fact table: {len(rows)} components "
          f"(source: scripts/satellite-map.yaml + scripts/ecosystem-runtime.yaml)\n")
    worst = 0
    for t in TARGETS:
        if not t.full.is_file():
            print(f"  MISSING   {t.path}")
            worst = max(worst, 2)
            continue
        text = t.full.read_text(encoding="utf-8")
        new, notes = _apply_target(text, t)
        status = _target_status(notes)
        detail = ", ".join(notes)
        if status == "no-markers":
            print(f"  NO-MARKERS {t.path}  → add the fence, see --list  ({detail})")
            worst = max(worst, 1)
        elif status == "updated":
            if mode == "write":
                t.full.write_text(new, encoding="utf-8")
                print(f"  written   {t.path}  ({t.consumer}; {detail})")
            else:
                print(f"  DRIFT     {t.path}  ({t.consumer}; {detail})")
                worst = max(worst, 1)
        else:
            print(f"  ok        {t.path}")
    print()
    for src, dst in FILE_MIRRORS:
        src_p, dst_p = ROOT / src, ROOT / dst
        if not src_p.is_file() or not dst_p.is_file():
            print(f"  MIRROR-MISSING  {src} → {dst}")
            worst = max(worst, 2)
            continue
        want = mirror_text(src, src_p.read_text(encoding="utf-8"))
        if dst_p.read_text(encoding="utf-8") == want:
            print(f"  mirror ok {dst}")
            continue
        if mode == "write":
            dst_p.write_text(want, encoding="utf-8")
            print(f"  mirrored  {src} → {dst}  (relative links absolutised)")
        else:
            print(f"  MIRROR-DRIFT {src} → {dst}")
            worst = max(worst, 1)
    print()
    for path, consumer in RUNTIME_CONSUMERS:
        print(f"  runtime   {path}  ({consumer}) — reads live sources, nothing to inject")
    return worst


def show_list() -> int:
    print("Agent knowledge bases (source of truth: scripts/satellite-map.yaml "
          "+ ATLAS STATION_CATALOG)\n")
    print(f"{'file':52s} {'fmt':4s} {'lang':5s} consumer")
    for t in TARGETS:
        mark = "" if t.full.is_file() else "  [MISSING]"
        print(f"{t.path:52s} {t.comment:4s} {t.lang:5s} {t.consumer}{mark}")
    print("\nRuntime consumers (no injection needed):")
    for path, consumer in RUNTIME_CONSUMERS:
        print(f"{path:52s} {'—':4s} {'—':5s} {consumer}")
    print("\nWhole-file mirrors:")
    for src, dst in FILE_MIRRORS:
        print(f"  {src}  →  {dst}")
    print("\nFences to add to a new target (comment syntax of that file):")
    for kind in ("md", "py", "ts"):
        b, e = _markers(kind)
        bp, ep = _markers(kind, PHYS_BEGIN, PHYS_END)
        print(f"  {kind} components: {b}\n     {e}")
        print(f"  {kind} physical:    {bp}\n     {ep}")
    return 0


def show_github(apply: bool = False) -> int:
    out = refresh_from_github()
    if not out.get("ok"):
        print(f"github read failed: {out.get('error')}\n"
              "(needs the gh CLI authenticated; READ-ONLY — this never pushes)")
        return 2
    drift = out["drift"]
    print(f"org {out['org']}: {out['repos_seen']} repos seen, "
          f"{out['satellites']} satellites in the map\n")
    if not drift:
        print("  the map agrees with GitHub on every description and homepage")
        return 0
    unpublished = [d for d in drift if d["field"] == "existence"]
    fillable = [d for d in drift if d.get("fillable")]
    conflicts = [d for d in drift if d["field"] != "existence" and not d.get("fillable")]

    for d in drift:
        tag = "fill" if d.get("fillable") else ("absent" if d["field"] == "existence" else "CONFLICT")
        print(f"  [{tag}] {d['id']} · {d['field']}")
        print(f"      map:    {d['local'][:110] or '(empty)'}")
        print(f"      github: {d['github'][:110]}")
    print()
    if apply and fillable:
        applied = fill_blanks_from_github(drift)
        print(f"  filled {len(applied)} blank field(s) in scripts/satellite-map.yaml: "
              f"{', '.join(applied)}")
        print("  now run --write to propagate into the knowledge bases")
    elif fillable:
        print(f"  {len(fillable)} blank field(s) can be filled automatically: "
              "re-run with --from-github --apply")
    if conflicts:
        print(f"  {len(conflicts)} conflict(s) need a human: both sides have a value, and the map "
              "may be deliberately different from the repo blurb")
    if unpublished:
        ids = ", ".join(d["id"] for d in unpublished)
        print(f"  {len(unpublished)} satellite(s) in the map are NOT on GitHub yet: {ids}\n"
              "      (expected for a satellite whose mirror has not been pushed — the map is the "
              "plan, GitHub is the published state)")
    return 0 if (apply and not conflicts and not unpublished) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="report drift, change nothing (CI)")
    g.add_argument("--write", action="store_true", help="regenerate every block")
    g.add_argument("--from-github", action="store_true", help="compare the map against GitHub")
    g.add_argument("--list", action="store_true", help="where every knowledge base lives")
    ap.add_argument("--apply", action="store_true",
                    help="with --from-github: fill BLANK map fields from GitHub (never overwrites "
                         "a value that differs — that needs a human)")
    a = ap.parse_args()
    if a.list:
        return show_list()
    if a.from_github:
        return show_github(apply=a.apply)
    return run("write" if a.write else "check")


if __name__ == "__main__":
    raise SystemExit(main())
