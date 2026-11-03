"""HISTOR -> ScraperWatch: changes HISTOR recorded on ScraperWatch's panel that its daily diffs do not list.

ScraperWatch read its panel at 2026-10-30 10:49:43-10:59:39Z (baseline), then daily from 02:50Z (about ten minutes
per run). For every panel endpoint and day where HISTOR recorded a change between two ScraperWatch reads and
ScraperWatch lists no tool change, this compares HISTOR's definitions at the two read times and says why the daily
diff would not show it.

usage: python3 -I xcheck_reverse.py changes.json panel.txt phase1.jsonl obs.jsonl blobs.jsonl robots.json > reverse.json

robots.json maps a host to its robots.txt text (null when it could not be read); rules apply as RFC 9309 says
(longest match, Allow on a tie), for ScraperWatch's user agent and for *.
"""
import collections
import json
import re
import sys

SW_FIELDS = ("name", "description", "inputSchema", "outputSchema", "title", "annotations")
# Read windows: (run start, run end) of the earlier read and of the later read.
RUNS = {"2026-10-31": (("2026-10-30T10:49:43Z", "2026-10-30T10:59:39Z"), ("2026-10-31T02:50:00Z", "2026-10-31T03:00:00Z")),
        "2026-11-01": (("2026-10-31T02:50:00Z", "2026-10-31T03:00:00Z"), ("2026-11-01T02:50:00Z", "2026-11-01T03:00:00Z"))}

sw = json.load(open(sys.argv[1]))
panel = [l.strip() for l in open(sys.argv[2]) if l.strip() and not l.startswith("#")]
rows = [json.loads(l) for l in open(sys.argv[3]) if l.startswith("{")]
obs = collections.defaultdict(list)
for l in open(sys.argv[4]):
    if l.startswith("{"):
        r = json.loads(l)
        obs[r["target_id"]].append(r)
for v in obs.values():
    v.sort(key=lambda r: r["observed_at"])
blobs = {}
for l in open(sys.argv[5]):
    if l.startswith("{"):
        r = json.loads(l)
        blobs[r["digest"]] = json.loads(r["body"])

robots = json.load(open(sys.argv[6])) if len(sys.argv) > 6 else {}


def robots_allows(url):
    from urllib.parse import urlsplit
    u = urlsplit(url)
    text = robots.get(u.hostname)
    if not text:
        return True
    path = (u.path or "/") + ("?" + u.query if u.query else "")
    groups, current, seen_rule = {}, [], False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, val = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if seen_rule:
                current, seen_rule = [], False
            current.append(val.lower())
            groups.setdefault(val.lower(), [])
        elif key in ("allow", "disallow") and current:
            seen_rule = True
            for agent in current:
                groups[agent].append((key, val))
    rules = groups.get("scraperwatch-mcp-observatory") or groups.get("*") or []

    def match(rule):
        if not rule:
            return -1
        pattern = re.escape(rule).replace(r"\*", ".*")
        if pattern.endswith(r"\$"):
            pattern = pattern[:-2] + "$"
        return len(rule) if re.match(pattern, path) else -1
    best = max(((match(v), k == "allow") for k, v in rules), default=(-1, True))
    return best[0] < 0 or best[1]


targets = {r["id"]: r for r in rows if r["k"] == "target"}
listed = collections.defaultdict(set)
for d in sw["days"]:
    for c in d["changes"]:
        if c["op"] == "tools_changed":
            listed[c["endpoint"].rstrip("/")].add(d["day"])
reported = {(c["endpoint"].rstrip("/"), d["day"]) for d in sw["days"] for c in d["changes"] if c["op"] == "tools_changed"}
events = collections.defaultdict(list)
for r in rows:
    if r["k"] in ("change", "xchange"):
        for day, (prev, cur) in RUNS.items():
            if prev[1] < r["observed_at"] <= cur[0]:
                events[(r["target_id"], day)].append(r)


def inline_refs(schema, root=None, depth=0):
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
        return {k: inline_refs(v, root, depth + 1) for k, v in schema.items() if k not in ("$defs", "definitions")}
    if isinstance(schema, list):
        return [inline_refs(v, root, depth + 1) for v in schema]
    return schema


def canon(v, noise=False):
    """ScraperWatch's view: lists unordered, whitespace collapsed; with noise=True also dates, versions, numbers."""
    if isinstance(v, dict):
        return {k: canon(x, noise) for k, x in v.items()}
    if isinstance(v, list):
        return sorted((canon(x, noise) for x in v), key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(v, str):
        s = " ".join(v.split())
        if noise:
            s = re.sub(r"\d{4}-\d{2}-\d{2}([T ][\d:.]+Z?)?", "<date>", s)
            s = re.sub(r"\bv?\d+(\.\d+)+([-+][\w.]+)?\b", "<ver>", s)
            s = re.sub(r"\d+", "<n>", s)
        return s
    if noise and isinstance(v, (int, float)) and not isinstance(v, bool):
        return "<n>"
    return v


def full_view(o):
    tools = {t["name"]: dict(t) for t in blobs.get(o["toolset"], [])} if o and o["toolset"] else {}
    ex = blobs.get(o["extras"]) if o and o["extras"] else None
    for name, e in ((ex or {}).get("tools") or {}).items():
        if name in tools:
            tools[name].update({k: v for k, v in e.items() if k != "members"})
    return tools


def sw_view(tools, noise=False):
    out = {}
    for name, t in tools.items():
        v = {k: t[k] for k in SW_FIELDS if k in t}
        for k in ("inputSchema", "outputSchema"):
            if isinstance(v.get(k), dict):
                v[k] = inline_refs(v[k])
        out[name] = canon(v, noise)
    return out


def last_ok(tid, at):
    before = [o for o in obs.get(tid, []) if o["observed_at"] <= at]
    return before[-1] if before else None


def describe(a, b):
    added, removed = sorted(set(b) - set(a)), sorted(set(a) - set(b))
    fields = collections.Counter()
    for n in set(a) & set(b):
        for k in set(a[n]) | set(b[n]):
            if a[n].get(k) != b[n].get(k):
                fields[k] += 1
    return {"added": added[:8], "removed": removed[:8], "changedFields": dict(fields)}


out = []
for (tid, day), evs in sorted(events.items()):
    t = targets[tid]
    if (t["endpoint"].rstrip("/"), day) in reported:
        continue
    (p0, p1), (c0, c1) = RUNS[day]
    oa, ob = last_ok(tid, p1), last_ok(tid, c1)
    row = {"day": day, "endpoint": t["endpoint"], "server": t["name"],
           "histor": [{"at": e["observed_at"], "kind": "tools" if e["k"] == "change" else "extras"} for e in evs]}
    if not oa or not ob:
        row["why"] = "HISTOR has no successful read before one of the two ScraperWatch reads"
        out.append(row)
        continue
    row["protocol"] = sorted({oa["protocol"], ob["protocol"]})
    row["robotsAllowsScraperWatch"] = robots_allows(t["endpoint"])
    if not oa["toolset"] or not ob["toolset"]:
        # No four-field copy on one side (a fraction in a schema, before 31 Oct 16:42Z); members kept beside the
        # digest (title, annotations, _meta, ...) are still comparable.
        xa = (blobs.get(oa["extras"]) or {}).get("tools") or {} if oa["extras"] else {}
        xb = (blobs.get(ob["extras"]) or {}).get("tools") or {} if ob["extras"] else {}
        va = {n: canon({k: v for k, v in e.items() if k in SW_FIELDS}) for n, e in xa.items()}
        vb = {n: canon({k: v for k, v in e.items() if k in SW_FIELDS}) for n, e in xb.items()}
        if not xa or not xb:
            row["why"] = "HISTOR held no copy at one of the two reads to compare"
        elif va == vb:
            extra = sorted({k for n in set(xa) & set(xb) for k in set(xa[n]) | set(xb[n])
                            if xa[n].get(k) != xb[n].get(k) and k != "members"} - set(SW_FIELDS))
            row["why"] = "only members ScraperWatch does not hash changed" if extra else \
                "back to the same definitions by the second read (changed and reverted between the two reads)"
            row["members"] = extra
        else:
            row["why"] = ("a change in the fields ScraperWatch hashes" if row["robotsAllowsScraperWatch"] else
                          "robots.txt disallows the endpoint, so ScraperWatch skips it")
            row["detail"] = {"titleOrAnnotations": sorted(n for n in set(va) | set(vb) if va.get(n) != vb.get(n))[:8],
                             "note": "name/description/schemas not comparable: no digest on one side"}
        out.append(row)
        continue
    # HISTOR reads some endpoints only every 6 h: when its read before the change is older than ScraperWatch's earlier
    # read, the change may have happened before that read and belongs to the previous day's diff.
    first = min(e["observed_at"] for e in evs)
    before = [o["observed_at"] for o in obs.get(tid, []) if o["observed_at"] < first]
    early = not before or before[-1] <= p1
    fa, fb = full_view(oa), full_view(ob)
    a, b = sw_view(fa), sw_view(fb)
    in_run = [e["at"] for e in row["histor"] if p0 < e["at"] <= p1 or c0 < e["at"] <= c1]
    if fa == fb:
        row["why"] = "back to the same definitions by the second read (changed and reverted between the two reads)"
    elif a == b:
        extra = sorted({k for n in set(fa) & set(fb) for k in set(fa[n]) | set(fb[n])
                        if fa[n].get(k) != fb[n].get(k)} - set(SW_FIELDS))
        row["why"] = "only members ScraperWatch does not hash changed"
        row["members"] = extra
    elif sw_view(fa, True) == sw_view(fb, True):
        row["why"] = "only dates, version strings, numbers or whitespace changed (ScraperWatch leaves these out)"
        row["detail"] = describe(a, b)
    elif not row["robotsAllowsScraperWatch"]:
        row["why"] = "robots.txt disallows the endpoint, so ScraperWatch skips it"
        row["detail"] = describe(a, b)
    elif early and day == "2026-10-31":
        row["why"] = "may predate ScraperWatch's first read (HISTOR's reads around 30 Oct 10:49Z were hours apart)"
        row["detail"] = describe(a, b)
    elif early:
        row["why"] = ("listed by ScraperWatch the day before (HISTOR's reads were hours apart)" if "2026-10-31" in
                      listed[t["endpoint"].rstrip("/")] else
                      "may have happened before ScraperWatch's earlier read (HISTOR's reads were hours apart)")
        row["detail"] = describe(a, b)
    elif in_run:
        row["why"] = "changed during a ScraperWatch run; which side its read saw depends on when it reached this endpoint"
        row["detail"] = describe(a, b)
    else:
        row["why"] = "a change in the fields ScraperWatch hashes"
        row["detail"] = describe(a, b)
    out.append(row)

summary = collections.Counter(r["why"] for r in out)
missed = [r for r in out if r["why"] == "a change in the fields ScraperWatch hashes"]
json.dump({"panel": len(panel), "pairsWithHistorChange": len(events), "alsoInScraperWatch": len(events) - len(out),
           "notInScraperWatch": len(out), "why": dict(summary.most_common()),
           "membersNotHashed": dict(collections.Counter(m for r in out for m in r.get("members", [])).most_common()),
           "candidates": missed, "all": out}, sys.stdout, indent=1, ensure_ascii=False)
