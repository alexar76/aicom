"""ScraperWatch MCP tool-change log vs HISTOR, same endpoints, same days (2026-10-31 and 2026-11-01).

ScraperWatch reads a fixed panel of 3,000 remote endpoints once a day (about 02:50Z) and publishes, per endpoint,
the tools added and removed and, per changed tool, field-level diffs with JSON paths and old/new values. HISTOR
reads the same endpoints about every 30 minutes and stores every definition it was served.

For every ScraperWatch tool change this checks, path by path, whether HISTOR saw the old value and then the new one
between the two ScraperWatch reads (with 7 h of slack on each side: some endpoints HISTOR reads every 6 h). For the endpoints known to be in their panel it
also lists the HISTOR changes that the daily diff did not report and why (reverted within the day, or a difference
of a kind ScraperWatch filters out).

usage: python3 -I xcheck.py changes.json histor-export.jsonl.gz > results.json
"""
import collections
import datetime as dt
import gzip
import json
import re
import sys

# ScraperWatch's first (baseline) run was 2026-10-30 10:49:43-10:59:39Z (ops@scraperwatch.com, 2026-11-01); later
# runs start at 02:50Z. A day's diff compares the read before with the read of that day.
PREV_READ = {"2026-10-31": "2026-10-30T10:49:43Z"}
SLACK = dt.timedelta(hours=7)  # HISTOR reads most of these endpoints every 30 min, some every 6 h
READ_AT = dt.time(2, 50)
MISSING = object()


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def at_path(doc, path):
    cur = doc
    for key, idx in re.findall(r"\.([^.\[]+)|\[(\d+)\]", path[1:]):
        if key:
            if not isinstance(cur, dict) or key not in cur:
                return MISSING
            cur = cur[key]
        else:
            i = int(idx)
            if not isinstance(cur, list) or i >= len(cur):
                return MISSING
            cur = cur[i]
    return cur


def unordered(v):
    """ScraperWatch leaves reordered lists out and publishes lists sorted, at any depth (an enum comes alphabetical)."""
    if isinstance(v, dict):
        return {k: unordered(x) for k, x in v.items()}
    if isinstance(v, list):
        return sorted((unordered(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True))
    return v


def inline_refs(schema, root=None, depth=0):
    """ScraperWatch walks schemas with local $ref resolved (its paths go through them); HISTOR keeps them as served."""
    root = schema if root is None else root
    if depth > 30:
        return schema
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/") and len(schema) == 1:
            target = root
            for part in ref[2:].split("/"):
                target = target.get(part) if isinstance(target, dict) else None
            if target is not None:
                return inline_refs(target, root, depth + 1)
        return {k: inline_refs(v, root, depth + 1) for k, v in schema.items()}
    if isinstance(schema, list):
        return [inline_refs(v, root, depth + 1) for v in schema]
    return schema


def same(a, b):
    return a == b or unordered(a) == unordered(b)


sw = json.load(open(sys.argv[1]))
opener = gzip.open if sys.argv[2].endswith(".gz") else open
rows = [json.loads(l) for l in opener(sys.argv[2], "rt") if l.startswith("{")]
blobs = {r["digest"]: json.loads(r["body"]) for r in rows if r["k"] == "blob"}
targets = {r["endpoint"].rstrip("/"): r for r in rows if r["k"] == "target"}
obs = collections.defaultdict(list)
for r in rows:
    if r["k"] == "obs":
        obs[r["target_id"]].append(r)
for v in obs.values():
    v.sort(key=lambda r: r["observed_at"])
hchanges = collections.defaultdict(list)
for r in rows:
    if r["k"] in ("change", "xchange"):
        hchanges[r["target_id"]].append(r)


def tools_of(o):
    """HISTOR's full view of one observation: the four digested fields plus title/annotations from extras."""
    if o["status"] != "ok" or not o["toolset"]:
        return None
    tools = {t["name"]: dict(t) for t in blobs[o["toolset"]]}
    extras = blobs.get(o["extras"]) if o["extras"] else None
    for name, ex in ((extras or {}).get("tools") or {}).items():
        if name in tools:
            for k in ("title", "annotations"):
                if k in ex:
                    tools[name][k] = ex[k]
    return tools


def views(tid, start, end):
    return [(ts(o["observed_at"]), tools_of(o)) for o in obs.get(tid, [])
            if start <= ts(o["observed_at"]) <= end and tools_of(o) is not None]


def first_transition(seq, is_old, is_new):
    """Time of the first observation in the new state that follows one in the old state, else None."""
    seen_old = False
    for t, v in seq:
        if is_old(v):
            seen_old = True
        elif seen_old and is_new(v):
            return t
    return None


def check_record(day, rec):
    d = dt.date.fromisoformat(day)
    t_cur = dt.datetime.combine(d, READ_AT, dt.timezone.utc)
    t_prev = ts(PREV_READ[day]) if day in PREV_READ else t_cur - dt.timedelta(days=1)
    tgt = targets.get(rec["endpoint"].rstrip("/"))
    out = {"day": day, "endpoint": rec["endpoint"], "server": rec["servers"][0], "op": rec["op"]}
    if not tgt:
        return out | {"verdict": "not in HISTOR"}
    seq = views(tgt["id"], t_prev - SLACK, t_cur + SLACK)
    out["histor_reads_in_window"] = len(seq)
    if not seq:
        statuses = collections.Counter(o["status"] if o["toolset"] or o["status"] != "ok" else "ok-undigested"
                                       for o in obs.get(tgt["id"], [])
                                       if t_prev - SLACK <= ts(o["observed_at"]) <= t_cur + SLACK)
        return out | {"verdict": "HISTOR has no definitions in the window", "histor_statuses": dict(statuses)}
    items = []
    for name in rec.get("added") or []:
        items.append(("tool added", name, lambda v, n=name: n not in v, lambda v, n=name: n in v))
    for name in rec.get("removed") or []:
        items.append(("tool removed", name, lambda v, n=name: n in v, lambda v, n=name: n not in v))
    for ch in rec.get("changed") or []:
        for field, diffs in ch["fields"].items():
            for x in diffs:
                # ScraperWatch writes a member that is not there as null ("annotations": old {...}, new null)
                old = x.get("old") if x["op"] != "added" else None
                new = x.get("new") if x["op"] != "removed" else None
                old = MISSING if old is None else old
                new = MISSING if new is None else new

                def val(v, n=ch["name"], p=x["path"], f=field):
                    if n not in v:
                        return None
                    if f in ("inputSchema", "outputSchema") and isinstance(v[n].get(f), dict):
                        # ScraperWatch's paths index the schema after $ref is resolved and lists are sorted
                        return at_path({f: unordered(inline_refs(v[n][f]))}, p)
                    return at_path(v[n], p)

                def is_old(v, o=old, val=val):
                    got = val(v)
                    return got is not None and ((got is MISSING) if o is MISSING else (got is not MISSING and same(got, o)))

                def is_new(v, nw=new, val=val):
                    got = val(v)
                    return got is not None and ((got is MISSING) if nw is MISSING else (got is not MISSING and same(got, nw)))
                items.append((f"{field} {x['op']}", f"{ch['name']} {x['path']}", is_old, is_new))
    seen, details = 0, []
    for kind, what, is_old, is_new in items:
        when = first_transition(seq, is_old, is_new)
        if when:
            seen += 1
            details.append({"item": f"{kind}: {what}", "histor_first_new": when.strftime("%Y-%m-%dT%H:%M:%SZ")})
        else:
            # O = HISTOR read the old value, N = the new one, x = something else, - = the tool was not in that read
            states = "".join("O" if is_old(v) else "N" if is_new(v) else "x" for _, v in seq)
            details.append({"item": f"{kind}: {what}", "histor_states": states})
    out["items"] = len(items)
    out["items_seen_by_histor"] = seen
    out["verdict"] = ("server instructions only (HISTOR does not record them)" if not items else
                      "same change in HISTOR" if seen == len(items) else
                      "partly in HISTOR" if seen else "not seen as a change in HISTOR")
    out["details"] = details
    return out


results = []
for day in sw["days"]:
    for rec in day["changes"]:
        if rec["op"] == "tools_changed":
            results.append(check_record(day["day"], rec))

# Status transitions: what HISTOR's own reads around the two ScraperWatch reads said.
status_rows = []
for day in sw["days"]:
    d = dt.date.fromisoformat(day["day"])
    t_cur = dt.datetime.combine(d, READ_AT, dt.timezone.utc)
    for rec in day["changes"]:
        if rec["op"] != "status_changed":
            continue
        tgt = targets.get(rec["endpoint"].rstrip("/"))
        near = lambda t: collections.Counter(o["status"] for o in obs.get(tgt["id"], [])
                                             if abs(ts(o["observed_at"]) - t) <= dt.timedelta(hours=2)) if tgt else None
        status_rows.append({"day": day["day"], "endpoint": rec["endpoint"], "scraperwatch": f"{rec['old_status']} -> {rec['new_status']}",
                            "transient": rec.get("transient"), "histor_near_prev": dict(near(t_cur - dt.timedelta(days=1)) or {}),
                            "histor_near_cur": dict(near(t_cur) or {})})

# The other direction, on endpoints known to be in their panel: HISTOR changes between two ScraperWatch reads that
# the daily diff did not list for that endpoint and day.
reported = {(c["endpoint"].rstrip("/"), day["day"]) for day in sw["days"] for c in day["changes"] if c["op"] == "tools_changed"}
unreported = []
for ep, tgt in targets.items():
    for day in sw["days"]:
        d = dt.date.fromisoformat(day["day"])
        t_cur = dt.datetime.combine(d, READ_AT, dt.timezone.utc)
        t_prev = t_cur - dt.timedelta(days=1)
        evs = [c for c in hchanges.get(tgt["id"], []) if t_prev < ts(c["observed_at"]) <= t_cur]
        if not evs or (ep, day["day"]) in reported:
            continue
        before = [v for t, v in views(tgt["id"], t_prev - SLACK, t_prev)][-1:]
        after = [v for t, v in views(tgt["id"], t_prev, t_cur)][-1:]
        if before and after and before[0] == after[0]:
            why = "reverted within the day: the state at both ScraperWatch reads is the same"
        elif before and after:
            diff = sorted({f"{n}.{k}" for n in set(before[0]) | set(after[0])
                           for k in set(before[0].get(n, {})) | set(after[0].get(n, {}))
                           if before[0].get(n, {}).get(k) != after[0].get(n, {}).get(k)} |
                          {f"tool {n} {'added' if n in after[0] else 'removed'}" for n in set(before[0]) ^ set(after[0])})
            why = "net difference: " + ", ".join(diff[:6]) + (" …" if len(diff) > 6 else "")
        else:
            why = "HISTOR lacks a definition at one of the two read times"
        unreported.append({"day": day["day"], "endpoint": tgt["endpoint"], "server": tgt["name"],
                           "histor_changes": len(evs), "why": why})

summary = {
    "scraperwatch_tool_change_records": len(results),
    "verdicts": dict(collections.Counter(r["verdict"] for r in results)),
    "items": sum(r.get("items", 0) for r in results),
    "items_seen_by_histor": sum(r.get("items_seen_by_histor", 0) for r in results),
    "status_transitions": len(status_rows),
    "histor_changes_not_in_daily_diff": len(unreported),
    "not_in_daily_diff_reasons": dict(collections.Counter(u["why"].split(":")[0] for u in unreported)),
}
json.dump({"summary": summary, "tool_changes": results, "status_transitions": status_rows,
           "histor_not_in_daily_diff": unreported}, sys.stdout, indent=1, ensure_ascii=False)
