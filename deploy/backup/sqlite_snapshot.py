#!/usr/bin/env python3
"""Consistent copies of every SQLite database under the backup roots.

Copying a live SQLite file byte by byte can catch it mid-transaction, and the -wal file next
to it holds commits the main file does not have yet. The backup API reads the database the
way a reader does — one consistent snapshot, WAL included — while writers carry on.

For each database found, a snapshot is written to <stage>/<absolute path> and the original
(plus its -wal/-shm/-journal) is listed in <exclude file> as a borg `pp:` pattern, so the
archive carries the snapshot instead of a torn copy. A database that cannot be snapshotted
is left in the archive as it is and reported, never dropped.

    sqlite_snapshot.py --stage DIR --exclude-out FILE [--exclude-from FILE] ROOT...

Prints one JSON line: {"snapshots": n, "bytes": n, "failed": [[path, error], ...]}.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sqlite3
import sys

SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db3")
MAGIC = b"SQLite format 3\x00"


def load_patterns(paths: list[str]) -> tuple[list[str], list[str]]:
    """borg `sh:` / `pp:` patterns -> (globs, prefixes). `**` and `*` both cross `/` here,
    which is close enough for skipping the same trees borg will skip."""
    globs: list[str] = []
    prefixes: list[str] = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("pp:"):
                    prefixes.append(line[3:].rstrip("/"))
                else:
                    if line[:3] in ("sh:", "fm:"):
                        line = line[3:]
                    globs.append(line.replace("**", "*"))
    return globs, prefixes


def excluded(path: str, globs: list[str], prefixes: list[str]) -> bool:
    if any(path == p or path.startswith(p + "/") for p in prefixes):
        return True
    return any(fnmatch.fnmatchcase(path, g) for g in globs)


def is_sqlite(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == MAGIC
    except OSError:
        return False


def snapshot(src: str, dst: str) -> int:
    os.makedirs(os.path.dirname(dst), mode=0o700, exist_ok=True)
    tmp = dst + ".part"
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=60)
    try:
        target = sqlite3.connect(tmp)
        try:
            source.backup(target)  # one step: a single consistent read transaction
        finally:
            target.close()
    finally:
        source.close()
    check = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    try:
        verdict = check.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        check.close()
    if verdict != "ok":
        os.unlink(tmp)
        raise RuntimeError(f"snapshot failed quick_check: {verdict}")
    os.replace(tmp, dst)
    return os.path.getsize(dst)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--exclude-out", required=True)
    ap.add_argument("--exclude-from", action="append", default=[])
    ap.add_argument("roots", nargs="+")
    args = ap.parse_args()

    globs, prefixes = load_patterns(args.exclude_from)
    stage = os.path.abspath(args.stage)
    prefixes.append(stage)
    done, total, failed = 0, 0, []
    with open(args.exclude_out, "a", encoding="utf-8") as out:
        for root in args.roots:
            if not os.path.isdir(root):
                continue
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = [d for d in dirnames
                               if not excluded(os.path.join(dirpath, d), globs, prefixes)]
                for name in filenames:
                    if not name.lower().endswith(SUFFIXES):
                        continue
                    path = os.path.join(dirpath, name)
                    if os.path.islink(path) or excluded(path, globs, prefixes):
                        continue
                    try:
                        if os.path.getsize(path) == 0 or not is_sqlite(path):
                            continue
                    except OSError:
                        continue
                    try:
                        total += snapshot(path, stage + path)
                        done += 1
                    except Exception as exc:  # keep the raw file in the archive instead
                        failed.append([path, f"{type(exc).__name__}: {exc}"[:200]])
                        continue
                    for suffix in ("", "-wal", "-shm", "-journal"):
                        out.write(f"pp:{path}{suffix}\n")
    print(json.dumps({"snapshots": done, "bytes": total, "failed": failed}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
