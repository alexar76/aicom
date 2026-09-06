#!/usr/bin/env python3
"""Does every GitHub link an agent knowledge base hands out actually exist?

The rule these bases follow is: **what is not on GitHub is outside the knowledge base.** A
component an agent cannot open is worse than one it never heard of, because the agent then
confidently hands a stranger a dead link.

Half of that rule is enforced by a unit test (`tests/test_knowledge_sync.py`): a satellite marked
`github_published: false` in `scripts/satellite-map.yaml` reaches no base. The other half cannot be
a unit test, because it is a question only GitHub can answer — and the default is permissive, so a
satellite in the map with no key at all is assumed published. This script asks.

Two ways the rule breaks, both seen:

* **A satellite in the map that was never pushed.** `attested-memory-hub` and
  `attested-saas-gateway` were added with `homepage: https://github.com/alexar76/<name>`, both
  404, and the sync then demanded they appear in every base.
* **A document written but not yet mirrored.** The public mirror is a trimmed copy; a new file
  under `docs/` is a 404 until the next publish, so a link added to the knowledge base in the same
  session that created the file is dead on arrival.

The second kind is temporary and expected right after authoring. The point is that it is VISIBLE
instead of being discovered by whoever follows the link.

Usage:
    python3 scripts/verify_knowledge_base_publication.py           # check everything
    python3 scripts/verify_knowledge_base_publication.py --json
    python3 scripts/verify_knowledge_base_publication.py --links   # documents only
    python3 scripts/verify_knowledge_base_publication.py --repos   # satellite repos only

Exit status is 1 when anything a base names is missing, so CI and the release path can gate on it.
No credential is used or accepted: these are public URLs, and a token on this path would follow a
redirect off github.com (`urllib` re-sends every header except content-length/content-type).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

#: The mirrored base carries ABSOLUTISED links; the canonical one keeps them relative, so this is
#: the copy that shows what a reader outside the monorepo actually receives.
MIRRORED_BASE = ROOT / "alien-monitor" / "docs" / "ecosystem" / "knowledge-base.md"

_GH = re.compile(r"https://github\.com/alexar76/[^)\s\"'<>]+")
_ONLY_HTTPS_GITHUB = "github.com"
TIMEOUT = 20


def _check(url: str) -> int | str:
    """HTTP status for a public GitHub URL, or a reason string. Never raises."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != _ONLY_HTTPS_GITHUB:
        return f"refused: {url[:60]}"

    class _SameHostOnly(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            new = urllib.parse.urlsplit(newurl)
            if new.scheme != "https" or new.hostname != _ONLY_HTTPS_GITHUB:
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(_SameHostOnly)
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"user-agent": "aicom-kb-publication-check"})
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, OSError) as exc:
        return f"unreachable ({type(exc).__name__})"


def unpublished_repos() -> list[dict[str, object]]:
    """Satellites the map names that GitHub does not have.

    DELEGATED to `ecosystem_knowledge.refresh_from_github`, which already answers this and already
    knows that a wiki lives at `<repo>.wiki.git` and never appears in `/repos`. A second existence
    check here would be a second place the same question can be answered differently — the reason
    this ecosystem reads BASANOS's distilled intel instead of standing up its own advisory fetcher.

    The gap this script closes was never "nobody could tell". `refresh_from_github` reported both
    `attested-*` satellites as NOT PUBLISHED all along; nothing ran it, and nothing failed on it.
    """
    import ecosystem_knowledge as ek

    result = ek.refresh_from_github()
    if result.get("error"):
        return [{"kind": "repo", "name": "(gh unavailable)", "url": "",
                 "status": f"could not ask GitHub: {str(result['error'])[:80]}"}]

    absent = {str(d["id"]) for d in (result.get("drift") or []) if d.get("field") == "existence"}
    marked = {str(sat["id"]) for sat in ek.load_satellites() if not ek.is_github_published(sat)}

    rows: list[dict[str, object]] = []
    # The FINDING is the discrepancy, not the absence. A satellite that is absent from GitHub AND
    # marked `github_published: false` is the rule working — reporting it would train people to
    # ignore this output, which is how the existing `refresh_from_github` came to be run by nobody.
    for cid in sorted(absent - marked):
        rows.append({"kind": "repo", "name": cid, "url": f"https://github.com/alexar76/{cid}",
                     "status": "absent on GitHub and NOT marked github_published: false"})
    for cid in sorted(marked - absent):
        # The other direction: hidden from every knowledge base for no reason any more.
        rows.append({"kind": "repo", "name": cid, "url": f"https://github.com/alexar76/{cid}",
                     "status": "published now — drop github_published: false to surface it"})
    return rows


def document_urls() -> list[str]:
    """Every alexar76 GitHub URL the mirrored knowledge base hands a reader."""
    if not MIRRORED_BASE.is_file():
        return []
    text = MIRRORED_BASE.read_text(encoding="utf-8")
    seen: list[str] = []
    for match in _GH.finditer(text):
        url = match.group(0).rstrip(".,;")
        if url not in seen:
            seen.append(url)
    return seen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--links", action="store_true", help="only the document links")
    ap.add_argument("--repos", action="store_true", help="only the satellite repositories")
    args = ap.parse_args(argv)

    do_repos = args.repos or not args.links
    do_links = args.links or not args.repos

    rows: list[dict[str, object]] = []
    if do_repos:
        rows.extend(unpublished_repos())
    if do_links:
        for url in document_urls():
            name = url.split("/blob/main/", 1)[-1] if "/blob/main/" in url else url
            rows.append({"kind": "link", "name": name, "url": url, "status": _check(url)})

    missing = [r for r in rows if r["status"] != 200]
    if args.json:
        print(json.dumps({"checked": len(rows), "missing": missing, "rows": rows},
                         indent=2, sort_keys=True))
    else:
        for r in rows:
            mark = "  " if r["status"] == 200 else "!!"
            print(f"{mark} {str(r['kind']):5} {str(r['status']):<14} {str(r['name'])[:78]}")
        print()
        checked_links = sum(1 for r in rows if r["kind"] == "link")
        print(f"{checked_links} link(s) checked, {len(missing)} problem(s) "
              f"(repo existence delegated to ecosystem_knowledge.refresh_from_github).")
        if missing:
            print("A knowledge base must not name what a reader cannot open. Either publish it, "
                  "or mark the satellite `github_published: false` and re-run "
                  "scripts/sync_knowledge_base.py --write.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
