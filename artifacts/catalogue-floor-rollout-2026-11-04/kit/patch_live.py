#!/usr/bin/env python3
"""Port aicom 28004ff8a (catalogue floor, discovery draft -04 §5) onto a LIVE hub variant.

    patch_live.py SRC_DIR LIVE_DIR OUT_DIR

SRC_DIR holds the committed crawler.py, database.py and migrations.py (28004ff8a). LIVE_DIR holds the
same three files copied out of a running hub. OUT_DIR receives the patched three. Every new block is
cut out of the committed source by its markers, never retyped, and inserted at anchors that must occur
exactly once in the live file; any missing or repeated anchor stops the script.
"""
from __future__ import annotations

import sys
from pathlib import Path


def cut(text: str, start: str, end: str) -> str:
    """The text from `start` (inclusive) to `end` (exclusive), each found exactly once."""
    assert text.count(start) == 1, f"source marker not unique: {start[:60]!r}"
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def insert(text: str, anchor: str, block: str, *, before: bool) -> str:
    n = text.count(anchor)
    if n != 1:
        sys.exit(f"anchor found {n} times, need 1: {anchor[:70]!r}")
    return text.replace(anchor, block + anchor if before else anchor + block)


def main() -> None:
    src, live, out = (Path(p) for p in sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=True)

    # ── crawler.py ───────────────────────────────────────────────────────────────────────────
    s = (src / "crawler.py").read_text()
    parse_fn = cut(s, "def _parse_generated_at(raw: Any):", "def _safe_tool_endpoint(")
    methods = cut(s, "    def _catalogue_rolled_back(", "    def _extract_peer_urls(")
    crawl_check = cut(s, "            # Rollback: older than a catalogue already verified from this peer.",
                      "            # Index capabilities\n")
    c = (live / "crawler.py").read_text()
    if "_catalogue_rolled_back" in c:
        sys.exit("live crawler.py already has the check")
    c = insert(c, "\nclass Crawler:\n", "\n" + parse_fn.rstrip("\n") + "\n\n", before=True)
    c = insert(c, "            # Index capabilities\n", crawl_check, before=True)
    c = insert(c, "            self._prune_unlisted(base_url)\n",
               "            self._record_catalogue_time(base_url, pinned_key, manifest)\n", before=False)
    c = insert(c, "            if self._manifest_too_stale(manifest):\n                return 0\n",
               "            if self._catalogue_rolled_back(base_url, pinned_key, manifest):\n"
               "                return 0\n", before=False)
    old_ret = "            return self.db.replace_preview_capabilities(base_url, rows)\n"
    new_ret = cut(s, "            written = self.db.replace_preview_capabilities(base_url, rows)\n",
                  "        except Exception as exc:  # pragma: no cover - defensive\n"
                  "            # WARNING, not INFO.")
    assert c.count(old_ret) == 1, "preview return anchor"
    c = c.replace(old_ret, new_ret)
    c = insert(c, "    def _extract_peer_urls(\n", methods, before=True)
    (out / "crawler.py").write_text(c)

    # ── database.py ──────────────────────────────────────────────────────────────────────────
    s = (src / "database.py").read_text()
    db_methods = cut(s, "    # ── Catalogue watermarks (migration 066", "    def promote_pending_peer(")
    d = (live / "database.py").read_text()
    if "peer_catalogue_watermarks" in d:
        sys.exit("live database.py already has the table")
    d = insert(d, '        cur = self._conn.execute("DELETE FROM peers WHERE url=?", (url,))\n',
               '        self._conn.execute("DELETE FROM peer_catalogue_watermarks WHERE url=?", (url,))\n',
               before=True)
    d = insert(d, "    def promote_pending_peer(", db_methods, before=True)
    (out / "database.py").write_text(d)

    # ── migrations.py ────────────────────────────────────────────────────────────────────────
    s = (src / "migrations.py").read_text()
    mig = cut(s, "# 066: the newest `generated_at`", "\n\ndef channel_ledger_versions()")
    m = (live / "migrations.py").read_text()
    if "_register(66," in m:
        sys.exit("live migrations.py already registers 066")
    m = insert(m, "\n\ndef channel_ledger_versions()", "\n" + mig.rstrip("\n") + "\n", before=True)
    (out / "migrations.py").write_text(m)
    print("patched", out)


if __name__ == "__main__":
    main()
