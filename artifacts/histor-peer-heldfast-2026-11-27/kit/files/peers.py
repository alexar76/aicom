"""Cross-checks with other public observers of MCP tool lists, configured as one list.

Every observer HISTOR compares itself with is one entry in a JSON list (deploy/peers.json, installed as
/etc/histor/peers.json). Adding an observer is adding an entry; nothing else changes. An entry:

    slug       short lower-case name; the results go to /datasets/peers/<slug>/<YYYY-MM-DD>/
    name       display name;  operator, contact, page, since: optional, shown in the index
    method     "digest"     — compare the observer's tool-set digests with HISTOR's timeline
                              (histor/digest_xcheck.py), run by this module every day
               "fingerprints" — compare the observer's per-tool fingerprints, one file per server in a public
                              GitHub folder, with the ones HISTOR computes in that format
                              (histor/fingerprint_xcheck.py, heldfast), run by this module every day
               "field-diff" — compare the observer's field-level change log with HISTOR's records, both ways
                              (histor/peer_xcheck.py, ScraperWatch); it reads HISTOR's database
    sources    for "digest": [{"name": "feed", "url": "https://…"}, …], each a file the observer publishes in a
               format digest_xcheck reads (rows in JSON, JSON Lines or CSV, or CrawlCheck's change feed)
    window_hours  for "digest": how far from the observer's read HISTOR may have seen the same digest (24)
    max_rows   for "digest" and "fingerprints", optional: compare at most this many rows of a source per day. A larger
               source (a census of the whole registry rather than a change feed) is split into
               parts = ceil(1.1 * rows / max_rows) by sha256(name + "\\n" + endpoint) (for "fingerprints": by
               sha256 of the file name), and each day compares the part numbered (day's ordinal mod parts), so every
               row comes round every `parts` days and anyone can recompute which rows a day compared. Each compared
               row costs one HISTOR request, which is why the share is bounded.
    format, github  for "fingerprints": the fingerprint format (heldfast) and where the files are:
               {"repo": "owner/name", "ref": "main", "folder": "state", "prefix": "remote__"}; the run reads the
               folder at the commit `ref` names at that moment, and keeps the commit
    changes, panel, agent, run_start, run_minutes, first_run, days
               for "field-diff": the observer's change log and endpoint panel (https), the user agent its robots.txt
               rules name, when its daily run starts (HH:MM:SS UTC) and how long it takes, its first run (two RFC 3339
               times, the baseline of its first diff) and how many of its newest days each run compares (1)
    aliases    older folder names under /datasets/ that should keep pointing at /datasets/peers/<slug>/

    python -m histor.peers --config peers.json --out DIR [--published DIR] [--histor URL] [--day YYYY-MM-DD]
                           [--peer SLUG] [--method digest|fingerprints|field-diff]

writes DIR/<slug>/ for every peer run (a "digest" peer: per source <name>.input.*, <name>.report.json,
<name>.report.md and SHA256SUMS; a "fingerprints" peer the same for its folder; a "field-diff" peer: README.md,
results.json, inputs/ and SHA256SUMS) and
DIR/index.json, which lists every peer; for those not run now it reads the newest day and its results from
--published (the live /datasets/peers/). deploy/peers_check.sh runs each method in its own container (the "digest"
and "fingerprints" ones have no database, the "field-diff" one has no host network) and moves the results into
place. Exit
status: 0, or 1 when a source could not be fetched or read or a peer failed (the others are still written);
disagreements are a result, not a failure. "digest" and "fingerprints" need the standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:  # inside the package, and when mounted next to it into an older image
    from histor import digest_xcheck as dx
    from histor import fingerprint_xcheck as fx
except ImportError:  # pragma: no cover - a copy of the files run by path
    import digest_xcheck as dx  # type: ignore[no-redef]
    import fingerprint_xcheck as fx  # type: ignore[no-redef]

METHODS = ("digest", "fingerprints", "field-diff")
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
PATH_PART = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MAX_SOURCE = 16 * 1024 * 1024
UA = "histor-peers/1 (+https://histor.modelmarket.dev/)"
SHOWN = ("name", "operator", "contact", "page", "since", "method", "schedule")


class ConfigError(ValueError):
    pass


def load_config(text: str) -> list[dict]:
    """The peer list, checked: a JSON list of entries with unique slugs, a known method and, for "digest", https
    sources with unique names."""
    try:
        peers = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"not JSON: {exc}") from exc
    if not isinstance(peers, list) or not peers:
        raise ConfigError("the config must be a non-empty JSON list")
    seen: set[str] = set()
    for i, p in enumerate(peers):
        where = f"entry {i}"
        if not isinstance(p, dict):
            raise ConfigError(f"{where} is not an object")
        slug = p.get("slug")
        if not isinstance(slug, str) or not SLUG.match(slug):
            raise ConfigError(f"{where}: slug must match {SLUG.pattern}")
        where = f"peer {slug}"
        if slug in seen:
            raise ConfigError(f"{where}: slug used twice")
        seen.add(slug)
        if not isinstance(p.get("name"), str) or not p["name"].strip():
            raise ConfigError(f"{where}: name is required")
        if p.get("method") not in METHODS:
            raise ConfigError(f"{where}: method must be one of {', '.join(METHODS)}")
        for alias in p.get("aliases", []):
            if not isinstance(alias, str) or not SLUG.match(alias) or alias in ("peers", "latest"):
                raise ConfigError(f"{where}: bad alias {alias!r}")
        if p["method"] == "digest":
            sources = p.get("sources")
            if not isinstance(sources, list) or not sources:
                raise ConfigError(f"{where}: a digest peer needs sources")
            names: set[str] = set()
            for s in sources:
                if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not SLUG.match(s["name"]):
                    raise ConfigError(f"{where}: every source needs a name matching {SLUG.pattern}")
                if s["name"] in names:
                    raise ConfigError(f"{where}: source {s['name']} named twice")
                names.add(s["name"])
                if not isinstance(s.get("url"), str) or not s["url"].startswith("https://"):
                    raise ConfigError(f"{where}: source {s['name']} needs an https url")
            w = p.get("window_hours", 24)
            if not isinstance(w, (int, float)) or not 0 < w <= 24 * 14:
                raise ConfigError(f"{where}: window_hours must be between 0 and 336")
            _check_max_rows(p, where)
        elif p["method"] == "fingerprints":
            if p.get("format") not in fx.FORMATS:
                raise ConfigError(f"{where}: format must be one of {', '.join(fx.FORMATS)}")
            g = p.get("github")
            if not isinstance(g, dict) or not isinstance(g.get("repo"), str) or not REPO.match(g["repo"]):
                raise ConfigError(f"{where}: a fingerprints peer needs github.repo as owner/name")
            for key in ("ref", "folder"):
                if not isinstance(g.get(key), str) or not PATH_PART.match(g[key]):
                    raise ConfigError(f"{where}: github.{key} must be one plain path part")
            if not isinstance(g.get("prefix", ""), str) or not re.fullmatch(r"[A-Za-z0-9._-]{0,100}", g.get("prefix", "")):
                raise ConfigError(f"{where}: github.prefix must be letters, digits, '.', '_' or '-'")
            _check_max_rows(p, where)
        else:
            for key in ("changes", "panel"):
                if not isinstance(p.get(key), str) or not p[key].startswith("https://"):
                    raise ConfigError(f"{where}: a field-diff peer needs an https {key} url")
            if not isinstance(p.get("agent"), str) or not p["agent"].strip():
                raise ConfigError(f"{where}: a field-diff peer needs the agent its robots.txt rules name")
            if not isinstance(p.get("run_start"), str) or not re.fullmatch(r"[0-2]\d:[0-5]\d:[0-5]\d", p["run_start"]):
                raise ConfigError(f"{where}: run_start must be HH:MM:SS")
            if not isinstance(p.get("run_minutes"), int) or not 0 < p["run_minutes"] <= 24 * 60:
                raise ConfigError(f"{where}: run_minutes must be a positive number of minutes")
            first = p.get("first_run")
            if not isinstance(first, list) or len(first) != 2 or not all(isinstance(x, str) for x in first):
                raise ConfigError(f"{where}: first_run must be two RFC 3339 times (the observer's first read)")
            for x in first:
                try:
                    dt.datetime.fromisoformat(x.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ConfigError(f"{where}: first_run must be two RFC 3339 times (the observer's first read)") from exc
            d = p.get("days", 1)
            if not isinstance(d, int) or not 1 <= d <= 31:
                raise ConfigError(f"{where}: days must be between 1 and 31")
    return peers


def _check_max_rows(p: dict, where: str) -> None:
    m = p.get("max_rows")
    if m is not None and (isinstance(m, bool) or not isinstance(m, int) or not 1 <= m <= 100_000):
        raise ConfigError(f"{where}: max_rows must be a whole number between 1 and 100000")


def fetch_text(url: str, timeout: float = 120) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(MAX_SOURCE + 1)
    if len(body) > MAX_SOURCE:
        raise ValueError(f"larger than {MAX_SOURCE} bytes")
    return body.decode("utf-8")


def _input_name(source: dict) -> str:
    path = source["url"].split("?", 1)[0]
    ext = ".jsonl" if path.endswith(".jsonl") else ".csv" if path.endswith(".csv") else ".json"
    return f"{source['name']}.input{ext}"


def _name_endpoint(row: dict) -> str:
    return f"{row.get('name') or ''}\n{row.get('endpoint') or ''}"


def daily_share(rows: list[dict], max_rows: int | None, day: str, key: Callable[[dict], str] = _name_endpoint,
                key_rule: str = 'sha256(name + "\\n" + endpoint)') -> tuple[list[dict], dict | None]:
    """The rows of a source to compare on `day`, and how they were chosen (None when all of them are).

    Split by a hash of the row's name and endpoint (or of `key`), so a row stays in its part from day to day while the
    file keeps its size, and every row comes round once every `parts` days. The part is capped at max_rows in key
    order, for the rare part a little larger than the rest."""
    if not max_rows or len(rows) <= max_rows:
        return rows, None
    # 10% more parts than rows / max_rows: parts are only roughly equal, and one larger than max_rows is cut.
    parts = -(-len(rows) * 11 // (max_rows * 10))
    part = dt.date.fromisoformat(day).toordinal() % parts

    def bucket(row: dict) -> int:
        return int.from_bytes(hashlib.sha256(key(row).encode("utf-8")).digest()[:8], "big") % parts

    chosen = sorted((r for r in rows if bucket(r) == part), key=key)
    capped = len(chosen) > max_rows
    chosen = chosen[:max_rows]
    return chosen, {
        "rows_in_source": len(rows), "max_rows": max_rows, "parts": parts, "part": part,
        "rule": f"parts = ceil(1.1 * rows / max_rows); a row is compared when the first 8 bytes of "
                f"{key_rule}, as a big-endian integer, mod parts equal the day's proleptic Gregorian ordinal mod parts",
        **({"capped": True} if capped else {}),
    }


def run_peer(peer: dict, out: Path, *, histor: str, get_text: Callable[[str], str] = fetch_text,
             get_json: Callable[[str], Any] = dx.fetch_json, pause: float = 0.2, day: str | None = None) -> dict:
    """Run one "digest" peer into OUT: each source fetched, kept as read, and compared. Returns the index entry's
    result part: per source the counts, or the error that stopped it."""
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    for source in peer["sources"]:
        name = source["name"]
        try:
            text = get_text(source["url"])
            (out / _input_name(source)).write_text(text, encoding="utf-8")
            rows, sample = daily_share(dx.read_rows(text), peer.get("max_rows"),
                                       day or dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"))
            report = dx.xcheck(rows, get_json, histor, float(peer.get("window_hours", 24)), pause)
            if sample:
                report["sample"] = sample
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the others
            results[name] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            continue
        report["peer"] = peer["slug"]
        report["source"] = {"name": name, "url": source["url"]}
        (out / f"{name}.report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (out / f"{name}.report.md").write_text(dx.markdown(report), encoding="utf-8")
        results[name] = {"rows": report["rows_in"], "counts": report["counts"],
                         **({"rows_in_source": sample["rows_in_source"], "part": f"{sample['part'] + 1}/{sample['parts']}"}
                            if sample else {})}
    files = sorted(p for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    sums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files)
    (out / "SHA256SUMS").write_text(sums, encoding="utf-8")
    return results


def run_fingerprints(peer: dict, out: Path, *, histor: str, get_text: Callable[[str], str] = fetch_text,
                     get_json: Callable[[str], Any] = fx.fetch_json, pause: float = 0.2, day: str | None = None) -> dict:
    """Run one "fingerprints" peer into OUT: the folder listed at one commit, today's share of its files read and kept
    as read (<name>.input.jsonl, one {"file", "url", "body"} per line), and compared. Returns the index entry's result
    part under the source name "state"."""
    out.mkdir(parents=True, exist_ok=True)
    g = peer["github"]
    name = g["folder"]
    try:
        listing = fx.github_listing(g["repo"], g["ref"], g["folder"], g.get("prefix", ""), get_json)
        files, sample = daily_share([{"file": f} for f in listing["files"]], peer.get("max_rows"),
                                    day or dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
                                    key=lambda r: r["file"], key_rule="sha256(file name)")
        rows, kept = [], []
        for f in files:
            url = fx.raw_url(g["repo"], listing["commit"], g["folder"], f["file"])
            try:
                text = get_text(url)
            except Exception as exc:  # noqa: BLE001 - one file failing is a bad row, not a failed run
                rows.append({"file": f["file"], "name": None, "endpoint": None, "read_at": None, "tools": None,
                             "fetch_error": f"{type(exc).__name__}: {str(exc)[:120]}"})
                continue
            kept.append(json.dumps({"file": f["file"], "url": url, "body": text}, ensure_ascii=False))
            rows.append({"file": f["file"], **fx.read_state(text)})
            if pause:
                time.sleep(pause)
        (out / f"{name}.input.jsonl").write_text("".join(line + "\n" for line in kept), encoding="utf-8")
        report = fx.xcheck(rows, get_json, histor, peer["format"], pause)
        if sample:
            report["sample"] = sample
    except Exception as exc:  # noqa: BLE001 - reported in the index like a digest source that failed
        return {name: {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}}
    report["peer"] = peer["slug"]
    report["source"] = {"name": name, "repo": g["repo"], "ref": g["ref"], "folder": g["folder"],
                        "prefix": g.get("prefix", ""), "commit": listing["commit"],
                        "committed_at": listing["committed_at"], "files_in_folder": listing["files_in_folder"],
                        "files_with_prefix": len(listing["files"])}
    (out / f"{name}.report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out / f"{name}.report.md").write_text(fx.markdown(report), encoding="utf-8")
    files_ = sorted(p for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (out / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files_),
                                    encoding="utf-8")
    return {name: {"rows": report["rows_in"], "counts": report["counts"], "commit": listing["commit"],
                   **({"rows_in_source": sample["rows_in_source"], "part": f"{sample['part'] + 1}/{sample['parts']}"}
                      if sample else {})}}


def field_diff_summary(result: dict) -> dict:
    """The part of a field-diff result (histor/peer_xcheck.py) the index shows."""
    return {"days": result.get("days"), "forward": (result.get("forward") or {}).get("verdicts"),
            "reverse": (result.get("reverse") or {}).get("why"),
            "likelyMisses": len((result.get("reverse") or {}).get("likelyMisses") or [])}


def run_field_diff(peer: dict, out: Path) -> dict:
    """Run one "field-diff" peer into OUT (which must not exist) against HISTOR's database, read-only."""
    from histor import peer_xcheck as px
    from histor.config import load_settings
    from histor.dataset import open_readonly

    spec = {"name": peer["name"], "slug": peer["slug"], "page": peer.get("page", ""), "changes": peer["changes"],
            "panel": peer["panel"], "agent": peer["agent"], "run_start": peer["run_start"],
            "run_minutes": peer["run_minutes"], "first_run": tuple(peer["first_run"])}
    store, _key, backend = open_readonly(load_settings())
    try:
        result = px.run(store, out, days=int(peer.get("days", 1)), peer=spec)
    finally:
        backend.close()
    return field_diff_summary(result)


def published_results(published: Path | None, peer: dict, day: str | None) -> dict | None:
    """The results of a peer's published day, read back for the index."""
    if published is None or not day:
        return None
    folder = published / peer["slug"] / day
    try:
        if peer["method"] in ("digest", "fingerprints"):
            out = {}
            for f in sorted(folder.glob("*.report.json")):
                r = json.loads(f.read_text(encoding="utf-8"))
                out[f.name[: -len(".report.json")]] = {"rows": r.get("rows_in"), "counts": r.get("counts")}
            return out or None
        return field_diff_summary(json.loads((folder / "results.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def newest_day(published: Path | None, slug: str) -> str | None:
    """The newest dated folder of a peer already published (its `latest` link, else the highest date)."""
    if published is None:
        return None
    root = published / slug
    latest = root / "latest"
    if latest.is_symlink():
        return Path(latest.readlink()).name
    days = sorted(p.name for p in root.glob("20[0-9][0-9]-[0-1][0-9]-[0-3][0-9]") if p.is_dir()) if root.is_dir() else []
    return days[-1] if days else None


def build_index(peers: list[dict], ran: dict[str, dict], day: str, published: Path | None, now: str) -> dict:
    entries = []
    for p in peers:
        e: dict[str, Any] = {"slug": p["slug"], **{k: p[k] for k in SHOWN if k in p}}
        e["path"] = f"/datasets/peers/{p['slug']}/"
        if p["method"] == "digest":
            e["sources"] = [{"name": s["name"], "url": s["url"]} for s in p["sources"]]
            e["window_hours"] = p.get("window_hours", 24)
            if p.get("max_rows"):
                e["max_rows"] = p["max_rows"]
        elif p["method"] == "fingerprints":
            g = p["github"]
            e["sources"] = [{"name": g["folder"],
                             "url": f"https://github.com/{g['repo']}/tree/{g['ref']}/{g['folder']}"}]
            e["format"] = p["format"]
            if p.get("max_rows"):
                e["max_rows"] = p["max_rows"]
        if p.get("aliases"):
            e["aliases"] = [f"/datasets/{a}/" for a in p["aliases"]]
        if p["slug"] in ran:
            e["last_day"] = day
            e["last_results"] = ran[p["slug"]]
        else:
            e["last_day"] = newest_day(published, p["slug"])
            e["last_results"] = published_results(published, p, e["last_day"])
        entries.append(e)
    return {"kind": "histor-peer-cross-checks", "v": 1, "generated_at": now,
            "about": "Observers HISTOR compares its records with, and where each comparison is published. "
                     "Method and verdicts: https://github.com/alexar76/histor/blob/main/docs/cross-check.md",
            "peers": entries}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True, help="directory for this run's results and index.json")
    ap.add_argument("--published", help="the live peers directory, to list the newest day of peers not run now")
    ap.add_argument("--histor", default="https://histor.modelmarket.dev")
    ap.add_argument("--day", default=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"))
    ap.add_argument("--peer", action="append", help="run only this slug (repeatable); the index still lists all")
    ap.add_argument("--method", choices=METHODS, action="append", help="run only peers with this method (repeatable)")
    ap.add_argument("--pause", type=float, default=0.2)
    a = ap.parse_args(argv)
    try:
        peers = load_config(Path(a.config).read_text(encoding="utf-8"))
    except (OSError, ConfigError) as exc:
        print(f"peers config: {exc}", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ran: dict[str, dict] = {}
    failed = False
    for p in peers:
        if (a.peer and p["slug"] not in a.peer) or (a.method and p["method"] not in a.method):
            continue
        if p["method"] == "field-diff":
            try:
                ran[p["slug"]] = run_field_diff(p, out / p["slug"])
            except Exception as exc:  # noqa: BLE001 - one peer failing must not stop the others
                failed = True
                print(f"{p['slug']}: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
                continue
            r = ran[p["slug"]]
            print(f"{p['slug']}: days {r['days']}, forward {r['forward']}, reverse {r['reverse']}, "
                  f"likely misses {r['likelyMisses']}")
            continue
        if p["method"] == "fingerprints":
            ran[p["slug"]] = run_fingerprints(p, out / p["slug"], histor=a.histor, pause=a.pause, day=a.day)
        else:
            ran[p["slug"]] = run_peer(p, out / p["slug"], histor=a.histor, pause=a.pause, day=a.day)
        for src, res in ran[p["slug"]].items():
            if "error" in res:
                failed = True
                print(f"{p['slug']}/{src}: {res['error']}", file=sys.stderr)
            else:
                c = res["counts"]
                share = f" (part {res['part']} of {res['rows_in_source']})" if "part" in res else ""
                nearby = f"{c['agree_nearby']} nearby, " if "agree_nearby" in c else ""
                print(f"{p['slug']}/{src}: {res['rows']} rows{share}, {c['agree']} agree, {nearby}"
                      f"{c['disagree']} disagree")
    now = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    index = build_index(peers, ran, a.day, Path(a.published) if a.published else None, now)
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
