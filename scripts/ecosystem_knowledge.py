"""One renderer for the component facts every agent's knowledge base needs.

**Why this exists.** Nine different agent knowledge bases each carried their own hand-typed list of
ecosystem components. Adding a satellite meant remembering nine files in four languages and three
file formats — so in practice they drifted, and MOMUS, Treasury, ATLAS and the bridges were missing
from every one of them.

**The source of truth is `scripts/satellite-map.yaml`** — the same file the mirror scripts and the
Alien Monitor's own prompt context already read. This module renders it into a block that can be
injected into a knowledge base, and `sync_knowledge_base.py` does the injecting. Add a satellite to
the map, run the sync, and every agent learns about it.

**Rendering constraints** (they are not stylistic — they keep the block safe to embed):

* no backticks and no `${` — the block goes inside a TypeScript template literal;
* no triple quotes — it also goes inside Python triple-quoted strings;
* no trailing whitespace, stable ordering — so `--check` diffs mean drift, not noise.

Runtime facts (a live URL, a port) are not in the satellite map, which is about repositories. They
live in the small overlay `scripts/ecosystem-runtime.yaml`. Only PUBLIC hostnames belong there —
never a bare server IP, per the infra-scrub rule.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "scripts" / "satellite-map.yaml"
RUNTIME_PATH = ROOT / "scripts" / "ecosystem-runtime.yaml"

BEGIN = "BEGIN GENERATED ecosystem-components"
END = "END GENERATED ecosystem-components"

# Bare IPs must never reach a committed knowledge base: the bases are published (docs, landings, the
# public mirror), and infra addresses have leaked that way before.
# A prefix tuple ("0."…"9.") only ever matched a single-digit first octet: it caught 5.129.x.x but
# waved through 78.17.x.x and 31.77.x.x — two of the three hosts from that leak. Match the octet.
_BARE_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_BARE_IPV6 = re.compile(r"^\[?[0-9A-Fa-f]*:[0-9A-Fa-f:.]*\]?$")


def _is_bare_ip(url: str) -> bool:
    """True when the URL's host is a literal address rather than a hostname."""
    host = urlsplit(url if "//" in url else f"//{url}").hostname or ""
    host = host.strip().rstrip(".")
    if not host:
        return False
    return bool(_BARE_IPV4.match(host)) or (":" in host and bool(_BARE_IPV6.match(host)))


def load_satellites(path: Path | None = None) -> list[dict[str, Any]]:
    """Every satellite in the map, including the ones not yet published."""
    data = yaml.safe_load((path or MAP_PATH).read_text(encoding="utf-8")) or {}
    sats = data.get("satellites") or []
    return [s for s in sats if isinstance(s, dict) and s.get("id")]


def is_github_published(sat: dict[str, Any]) -> bool:
    """Whether this satellite exists on GitHub, i.e. whether an agent can be told about it.

    The map is the mirror's INTENT list — a satellite is added to it before it is ever pushed.
    The knowledge bases must follow PUBLICATION instead: telling an agent about a component whose
    repository 404s, and whose landing page does not exist, is worse than silence, because the
    agent then confidently offers a stranger a link that goes nowhere.

    Default TRUE, because 47 of 49 entries are published and demanding the key on all of them
    would rot. `scripts/verify_knowledge_base_publication.py` closes the gap that default leaves:
    it asks GitHub whether every component the knowledge bases name actually exists, which a unit
    test cannot do.
    """
    return sat.get("github_published") is not False


def load_runtime(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p = path or RUNTIME_PATH
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: dict[str, dict[str, Any]] = {}
    for cid, facts in (data.get("components") or {}).items():
        if not isinstance(facts, dict):
            continue
        host = str(facts.get("url") or "")
        if _is_bare_ip(host):
            raise ValueError(f"{p.name}: component '{cid}' uses a bare IP ({host}); "
                             "knowledge bases are published — use a public hostname")
        out[str(cid)] = facts
    return out


def components(*, map_path: Path | None = None,
               runtime_path: Path | None = None) -> list[dict[str, Any]]:
    """The merged fact table: repository metadata from the map, live surface from the overlay."""
    rt = load_runtime(runtime_path)
    rows: list[dict[str, Any]] = []
    for sat in load_satellites(map_path):
        if not is_github_published(sat):
            continue                    # unpublished: outside every knowledge base by rule
        cid = str(sat["id"])
        extra = rt.get(cid, {})
        rows.append({
            "id": cid,
            "repo": str(sat.get("repo") or cid),
            "description": str(sat.get("description") or "").strip(),
            "description_i18n": {
                str(lang): str(text).strip()
                for lang, text in (sat.get("description_i18n") or {}).items()
                if text
            },
            "homepage": str(sat.get("homepage") or "").strip(),
            "optional": sat.get("optional") is True,
            "factory_embedded": sat.get("factory_embedded") is True,
            "role": str(extra.get("role") or "").strip(),      # hand-written, load-bearing
            "url": str(extra.get("url") or "").strip(),        # live public surface
            "port": extra.get("port"),
            "group": str(extra.get("group") or "satellite"),
        })
    rows.sort(key=lambda r: r["id"])
    return rows


def _sanitize(text: str) -> str:
    """Make a line safe inside a TS template literal and a Python triple-quoted string."""
    return (text.replace("`", "'").replace("${", "$ {")
                .replace('"""', "'''").replace("\\", "/").strip())


def render_block(rows: list[dict[str, Any]] | None = None, *, org: str = "alexar76",
                 heading: str = "### Component registry", lang: str = "en") -> str:
    """The generated block: one line per component, longest-lived facts first."""
    rows = rows if rows is not None else components()
    lines = [
        heading,
        "",
        f"Generated from scripts/satellite-map.yaml — do not hand-edit. GitHub org: {org}.",
        f"Run: python3 scripts/sync_knowledge_base.py --write ({len(rows)} components).",
        "",
    ]
    for r in rows:
        bits = [f"- {r['id']}"]
        if r["repo"] != r["id"]:
            bits.append(f"(repo {r['repo']})")
        if r["optional"]:
            bits.append("(profile README)")
        if r.get("factory_embedded"):
            bits.append("(monorepo subrepo — hub studio + forge landing)")
        head = " ".join(bits)
        localized = r.get("description_i18n", {}).get(lang, "")
        desc = _sanitize(r["role"] or localized or r["description"]) or "—"
        line = f"{head}: {desc}"
        tail = [t for t in (r["url"] or r["homepage"],
                            f"port {r['port']}" if r["port"] else "") if t]
        if tail:
            line += " · " + " · ".join(_sanitize(t) for t in tail)
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def refresh_from_github(*, org: str = "alexar76", map_path: Path | None = None) -> dict[str, Any]:
    """Compare the map's description/homepage against what GitHub actually serves.

    READ-ONLY, and deliberately so: it reports drift and (with apply=True in the caller) updates the
    LOCAL map. It never pushes anything anywhere — the public repos are a mirror, and this repo's
    push target is Gitea.
    """
    import json
    import subprocess

    p = map_path or MAP_PATH
    raw = subprocess.run(
        ["gh", "api", f"users/{org}/repos?per_page=100",
         "--jq", '[.[] | {name, description, homepage}]'],
        capture_output=True, text=True, timeout=90)
    if raw.returncode != 0:
        return {"ok": False, "error": (raw.stderr or "").strip()[:300]}
    remote = {r["name"]: r for r in json.loads(raw.stdout or "[]")}
    drift: list[dict[str, Any]] = []
    for sat in load_satellites(p):
        repo = str(sat.get("repo") or sat["id"])
        # A GitHub *wiki* lives at <repo>.wiki.git and never appears in /repos. Reporting it as
        # unpublished would be a false alarm that trains people to ignore this report.
        if repo.endswith(".wiki") or repo.endswith("-wiki"):
            continue
        gh = remote.get(repo)
        if gh is None:
            drift.append({"id": sat["id"], "repo": repo, "field": "existence",
                          "local": "in map", "github": "NOT PUBLISHED"})
            continue
        for field, gh_key in (("description", "description"), ("homepage", "homepage")):
            local = str(sat.get(field) or "").strip()
            upstream = str(gh.get(gh_key) or "").strip()
            if upstream and local != upstream:
                drift.append({"id": sat["id"], "repo": repo, "field": field,
                              "local": local, "github": upstream,
                              # A blank local field is a gap to fill. A DIFFERENT local value may be
                              # a deliberate local edit, so it is reported and never overwritten.
                              "fillable": not local})
    return {"ok": True, "org": org, "repos_seen": len(remote),
            "satellites": len(load_satellites(p)), "drift": drift}


def fill_blanks_from_github(drift: list[dict[str, Any]], *,
                            map_path: Path | None = None) -> list[str]:
    """Write GitHub's value into the map for BLANK local fields only.

    Deliberately narrow. A conflict between two non-empty values is a judgement call — maybe the map
    is right and the repo blurb is stale — so those are left for a human. Blanks carry no judgement.
    Line-level editing preserves the file's comments and ordering, which a yaml round-trip would eat.
    """
    p = map_path or MAP_PATH
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    applied: list[str] = []
    for d in drift:
        if not d.get("fillable") or d["field"] not in ("description", "homepage"):
            continue
        # Find this satellite's block, then its (empty or absent) field line.
        start = next((i for i, ln in enumerate(lines)
                      if ln.strip() in (f"- id: {d['id']}", f"-   id: {d['id']}")), None)
        if start is None:
            continue
        end = next((j for j in range(start + 1, len(lines))
                    if lines[j].lstrip().startswith("- id: ")), len(lines))
        indent = " " * (len(lines[start]) - len(lines[start].lstrip()) + 2)
        value = d["github"].replace('"', '\\"')
        for j in range(start, end):
            if lines[j].lstrip().startswith(f"{d['field']}:"):
                lines[j] = f'{indent}{d["field"]}: "{value}"\n'
                break
        else:
            lines.insert(start + 1, f'{indent}{d["field"]}: "{value}"\n')
        applied.append(f"{d['id']}.{d['field']}")
    if applied:
        p.write_text("".join(lines), encoding="utf-8")
    return applied


if __name__ == "__main__":  # pragma: no cover - manual inspection
    print(render_block())
    print(f"\n{len(components())} components; runtime overlay: "
          f"{'present' if os.path.isfile(RUNTIME_PATH) else 'absent'}")
