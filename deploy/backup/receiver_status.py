#!/usr/bin/env python3
"""Write what the alerter needs to know about received backups, and nothing it does not.

The receiver cannot open a repository (no key), but it can see when each client last
committed: in append-only mode borg logs every transaction with its UTC time in
<repo>/transactions. `borg compact` (run here) does not write there, so a weekly compact
cannot make a dead client look alive.

Also carries this host's OWN outgoing backup (its last-run.json), because the alerter only
reads one URL: on PingBlip that is PingBlip's own backup to attested.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time

TX = re.compile(r"transaction (\d+), UTC time (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)")


def last_commit(repo: str) -> str | None:
    path = os.path.join(repo, "transactions")
    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, os.path.getsize(path) - 4096))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    hits = TX.findall(tail)
    return hits[-1][1] + "Z" if hits else None


def size_mb(repo: str) -> float:
    total = 0
    for dirpath, _dirs, files in os.walk(repo):
        for name in files:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return round(total / 1e6, 1)


def _load_peaks(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {k: [(float(t), float(s)) for t, s in v] for k, v in data.items()}
    except (OSError, ValueError, TypeError):
        return {}


def _save_peaks(path: str, peaks: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(peaks, fh)
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--own-run", default="")
    args = ap.parse_args()

    repos = {}
    # Kept out of the published directory: the status file is what the web server serves.
    state_dir = "/var/lib/aicom-backup"
    peaks_path = (os.path.join(state_dir, "status-peaks.json") if os.path.isdir(state_dir)
                  else args.out + ".peaks.json")
    peaks = _load_peaks(peaks_path)
    now = time.time()
    for name in sorted(os.listdir(args.root)):
        repo = os.path.join(args.root, name)
        if os.path.isfile(os.path.join(repo, "config")) and os.path.isdir(os.path.join(repo, "data")):
            size = size_mb(repo)
            # A repo only shrinks when segments are compacted away; after a client's
            # "delete everything" that is the moment the loss becomes final. The peak over a
            # week lets the alerter see a drop without any key.
            seen = [(t, s) for t, s in peaks.get(name, []) if now - t <= 7 * 86400] + [(now, size)]
            peaks[name] = seen[-2016:]
            repos[name] = {"last_commit": last_commit(repo), "size_mb": size,
                           "size_mb_peak_7d": max(s for _t, s in seen)}
    _save_peaks(peaks_path, peaks)
    doc = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "free_gb": round(shutil.disk_usage(args.root).free / 1e9, 1),
        "repos": repos,
    }
    if args.own_run:
        try:
            with open(args.own_run, encoding="utf-8") as fh:
                own = json.load(fh)
            doc["own"] = {k: own.get(k) for k in ("label", "finished_at", "ok", "errors")}
        except (OSError, ValueError):
            doc["own"] = None
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
