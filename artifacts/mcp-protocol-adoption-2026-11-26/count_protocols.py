"""Count which MCP protocol revision registry servers answered HISTOR with.

Inputs (paths as arguments, see README):
  remote   data/remote_protocols.csv       one row per remote server with an ok read, 2-26 Nov 2026 (remote_protocols.sql)
  packages package_observations.jsonl.gz   public HISTOR snapshot 2026-11-23 (every sandbox run of an npm/PyPI package)
  servers  servers.jsonl.gz                same snapshot (entry id -> endpoint), used to tell npm from PyPI
  psl      public_suffix_list.dat          publicsuffix.org, to group hosts by registrable domain

Usage: python3 -B count_protocols.py data/remote_protocols.csv package_observations.jsonl.gz servers.jsonl.gz public_suffix_list.dat
"""
import collections, csv, gzip, json, sys

import psl

MODERN = "2026-07-28"
WINDOW_FROM = "2026-11-19T16:00:00Z"   # "current" = last ok read in the seven days to 2026-11-26T16:00Z
OBSERVER_WITH_MODERN_PROBE = 5         # package sandbox: server/discover first since observer 5 (15-16 Nov)


def share(counter):
    n = sum(counter.values())
    return {k: {"n": v, "pct": round(100 * v / n, 2)} for k, v in counter.most_common()} | {"_total": n}


def remote(path, registrable):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    cur = [r for r in rows if r["last_ok"] >= WINDOW_FROM]
    by_version = collections.Counter(r["last_protocol"] or "(not recorded)" for r in cur)

    by_domain = collections.defaultdict(list)
    for r in cur:
        by_domain[registrable(r["host"])].append(r)
    dom = collections.Counter()
    for rs in by_domain.values():
        kinds = {r["last_protocol"] == MODERN for r in rs}
        dom["modern" if kinds == {True} else "legacy" if kinds == {False} else "mixed"] += 1
    biggest = sorted(by_domain.items(), key=lambda kv: -len(kv[1]))[:12]
    modern_by_domain = collections.Counter(registrable(r["host"]) for r in cur if r["last_protocol"] == MODERN)
    top_modern, top_n = modern_by_domain.most_common(1)[0]
    without_top = [r for r in cur if registrable(r["host"]) != top_modern]

    # Switches inside 2-26 Nov: every legacy answer precedes every modern one, and the server ends modern.
    switched = [r for r in rows if r["first_modern"] and r["first_legacy"] and r["last_legacy"] < r["first_modern"]]
    back = [r for r in rows if r["first_modern"] and r["first_legacy"] and r["last_modern"] < r["first_legacy"]]
    interleaved = [r for r in rows if r["first_modern"] and r["first_legacy"]
                   and not (r["last_legacy"] < r["first_modern"] or r["last_modern"] < r["first_legacy"])]
    sw_dom = collections.Counter(registrable(r["host"]) for r in switched)
    sw_other = [r for r in switched if registrable(r["host"]) != top_modern]
    by_suffix = collections.defaultdict(collections.Counter)
    for r in cur:
        for sfx in ("workers.dev", "vercel.app", "onrender.com", "run.app", "railway.app", "pages.dev", "supabase.co"):
            if r["host"].split(":")[0].endswith("." + sfx):
                by_suffix[sfx][r["last_protocol"]] += 1
    return {
        "rowsInExport": len(rows),
        "serversReadOkInWindow": len(cur),
        "byVersion": share(by_version),
        "registrableDomains": {"total": len(by_domain), **{k: {"n": v, "pct": round(100 * v / len(by_domain), 2)} for k, v in dom.items()}},
        "biggestDomains": [{"domain": d, "entries": len(rs), "versions": dict(collections.Counter(r["last_protocol"] for r in rs).most_common(4))} for d, rs in biggest],
        "largestModernPublisher": {"domain": top_modern, "modernEntries": top_n,
                                   "shareOfModernPct": round(100 * top_n / by_version[MODERN], 2)},
        "withoutLargestModernPublisher": share(collections.Counter(r["last_protocol"] or "(not recorded)" for r in without_top)),
        "switchedLegacyToModern": {"servers": len(switched), "domains": len(sw_dom), "top": sw_dom.most_common(5),
                                   "byDay": dict(sorted(collections.Counter(r["first_modern"][:10] for r in switched).items()))},
        "switchedWithoutLargest": {"servers": len(sw_other), "domains": len({registrable(r["host"]) for r in sw_other}),
                                   "byDay": dict(sorted(collections.Counter(r["first_modern"][:10] for r in sw_other).items()))},
        "wentBackToLegacy": len(back), "interleaved": len(interleaved),
        "sharedPlatforms": {k: dict(v.most_common()) | {"_total": sum(v.values())} for k, v in by_suffix.items()},
    }


def packages(obs_path, servers_path):
    kind = {}
    with gzip.open(servers_path, "rt", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            kind[s["id"]] = (s.get("endpoint") or "").split(":", 1)[0]
    latest, runs = {}, collections.Counter()
    first, last = None, None
    with gzip.open(obs_path, "rt", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            if o["status"] != "ok" or not o.get("protocolVersion") or o["protocolVersion"] == "None":
                continue
            try:
                launch = json.loads(o["launchJson"]) if o.get("launchJson") not in (None, "None") else {}
            except ValueError:
                launch = {}
            if str(launch.get("observer")) != str(OBSERVER_WITH_MODERN_PROBE):
                continue
            runs[o["protocolVersion"]] += 1
            first = first or o["observedAt"]
            last = o["observedAt"]
            latest[o["serverId"]] = o["protocolVersion"]      # file is oldest first
    by_kind = collections.defaultdict(collections.Counter)
    for sid, v in latest.items():
        by_kind[kind.get(sid, "?")][v] += 1
    return {"window": [first, last], "okRuns": sum(runs.values()), "entries": len(latest),
            "byVersion": share(collections.Counter(latest.values())),
            "byRegistryType": {k: share(v) for k, v in by_kind.items()}}


if __name__ == "__main__":
    remote_csv, obs, servers, suffixes = sys.argv[1:5]
    out = {"modern": MODERN, "remoteWindow": [WINDOW_FROM, "2026-11-26T16:00:00Z"],
           "remote": remote(remote_csv, psl.make(suffixes)), "packages": packages(obs, servers)}
    json.dump(out, sys.stdout, indent=1)
    print()
