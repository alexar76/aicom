#!/usr/bin/env python3
"""Which recorded MCP tool-definition changes a client-side tool fingerprint cannot see.

Input: three files of a HISTOR snapshot (servers, changes, extras_changes .jsonl.gz).
Rules (read from source on 2026-11-19, not run against the libraries):

AI SDK  = `fingerprintTools` in ai@7.0.177 over tools built by @ai-sdk/mcp@2.0.101
          (`tools()` in automatic mode). Per tool it hashes
            description (string), title ?? annotations.title,
            {...inputSchema, properties: inputSchema.properties ?? {}, additionalProperties: false}
          so it does NOT cover: outputSchema, annotations other than title, _meta, icons,
          execution, vendor members, and the top-level inputSchema.additionalProperties.
FastMCP = the base payload of the "Tool fingerprinting" page (New in 3.0.0): tool key + inputSchema.
          Everything else (description included) is left to the author to add.

Conservative choices (each lowers the "not seen" counts):
  - any move of annotations.title counts as seen by the AI SDK (it is hashed only when the
    tool has no top-level title; the summaries do not say which case applies);
  - a summary marked `truncated`, and a `names-only` change, count as seen;
  - a tool that was added or removed in the same read counts as seen.
"""
import collections
import gzip
import json
import sys
from urllib.parse import urlsplit

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
TOP_ADDITIONAL = '$."additionalProperties"'


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            s = r["summaryJson"]
            r["summary"] = json.loads(s) if isinstance(s, str) else s
            yield r


def main(folder, since, until):
    servers = {}
    with gzip.open(f"{folder}/servers.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            ep = r.get("endpoint") or ""
            remote = ep.startswith("http")
            host = (urlsplit(ep).hostname or ep) if remote else ep
            servers[r["id"]] = (remote, host)

    events = collections.defaultdict(lambda: {"c": None, "x": None})
    for r in rows(f"{folder}/changes.jsonl.gz"):
        if since <= r["observedAt"] <= until:
            events[(r["serverId"], r["observedAt"])]["c"] = r["summary"]
    for r in rows(f"{folder}/extras_changes.jsonl.gz"):
        if since <= r["observedAt"] <= until:
            events[(r["serverId"], r["observedAt"])]["x"] = r["summary"]

    out = collections.OrderedDict()
    out["window"] = [since, until]
    out["events"] = len(events)
    out["servers_with_events"] = len({k[0] for k in events})

    n = collections.Counter()
    srv = collections.defaultdict(set)
    hosts = collections.defaultdict(set)
    kind_events = collections.Counter()
    host_blind = collections.Counter()
    # per (server, tool): ordered moves of the two hints, with whether the AI SDK saw that tool move
    hint_moves = collections.defaultdict(list)

    for (sid, at) in sorted(events, key=lambda k: k[1]):
        ev = events[(sid, at)]
        c, x = ev["c"], ev["x"]
        remote, host = servers.get(sid, (False, "?"))
        unknown = bool((c and c.get("detail") != "full") or (x and x.get("truncated")))
        tools = collections.defaultdict(lambda: {"ai": False, "fm": False, "cats": set()})
        if c:
            for name in list(c.get("added", [])) + list(c.get("removed", [])):
                t = tools[name]
                t["ai"] = t["fm"] = True
            for m in c.get("modified", []):
                t = tools[m["tool"]]
                f = m.get("fields") or {}
                if "description" in f:
                    t["ai"] = True
                    t["cats"].add("description")
                if "inputSchema" in f:
                    t["fm"] = True
                    paths = [p.get("path") for p in (f["inputSchema"] or [])]
                    if paths and all(p == TOP_ADDITIONAL for p in paths):
                        t["cats"].add("inputSchema.additionalProperties(top)")
                    else:
                        t["ai"] = True
                        t["cats"].add("inputSchema")
                if "outputSchema" in f:
                    t["cats"].add("outputSchema")
        if x:
            for name, d in (x.get("tools") or {}).items():
                t = tools[name]
                ann = d.get("annotations") or {}
                mem = d.get("members") or {}
                if "title" in ann or "title" in mem:
                    t["ai"] = True
                    t["cats"].add("title")
                for k, v in ann.items():
                    if k in HINTS:
                        t["cats"].add("hint")
                        t.setdefault("hints", {})[k] = v
                    elif k != "title":
                        t["cats"].add("annotation-other")
                for k in mem:
                    if k == "version":
                        t["cats"].add("member:version")
                    elif k in HINTS:
                        t["cats"].add("member:hint-outside-annotations")
                    elif k != "title":
                        t["cats"].add("member:" + (k if k in ("_meta", "execution", "securitySchemes", "icons") else "other"))
        if not tools:
            n["events_without_tool_moves"] += 1
            continue
        ai_any = any(t["ai"] for t in tools.values())
        fm_any = any(t["fm"] for t in tools.values())
        for name, t in tools.items():
            for k, v in (t.get("hints") or {}).items():
                hint_moves[(sid, name, k)].append((at, v[0], v[1], t["ai"], ai_any or unknown))
        allcats = set().union(*(t["cats"] for t in tools.values()))
        version_only = allcats == {"member:version"}
        n["events_with_tool_moves"] += 1
        if not version_only:
            n["events_excl_version_only"] += 1
            srv["moved"].add(sid)
        kind_events["remote" if remote else "package"] += 1
        if unknown:
            n["events_unknown_detail"] += 1
            continue
        for label, seen in (("ai", ai_any), ("fm", fm_any)):
            if seen:
                continue
            n[f"{label}_blind_events"] += 1
            if version_only:
                n[f"{label}_blind_events_vendor_version_only"] += 1
                continue
            n[f"{label}_blind_events_excl_version_only"] += 1
            srv[f"{label}_blind"].add(sid)
            hosts[f"{label}_blind"].add(host)
            n[f"{label}_blind_events_{'remote' if remote else 'package'}"] += 1
            if label == "ai":
                host_blind[host] += 1
                for cat in allcats:
                    n[f"ai_blind_events_touching::{cat}"] += 1
            else:
                if allcats <= {"description"}:
                    n["fm_blind_events_description_only"] += 1
                    srv["fm_desc_only"].add(sid)
                    hosts["fm_desc_only"].add(host)
        # tool-level: tools that moved while the AI SDK digest of that very tool stayed the same
        for name, t in tools.items():
            if not t["ai"] and t["cats"] - {"member:version"}:
                n["ai_blind_tool_moves"] += 1
                if ai_any:
                    n["ai_blind_tool_moves_in_events_where_another_tool_was_seen"] += 1

    out["counts"] = dict(sorted(n.items()))
    out["events_by_kind"] = dict(kind_events)
    out["servers_with_events_excl_version_only"] = len(srv["moved"])
    out["ai_blind_servers"] = len(srv["ai_blind"])
    out["ai_blind_hosts"] = len(hosts["ai_blind"])
    out["fm_blind_servers"] = len(srv["fm_blind"])
    out["fm_blind_hosts"] = len(hosts["fm_blind"])
    out["fm_description_only_servers"] = len(srv["fm_desc_only"])
    out["fm_description_only_hosts"] = len(hosts["fm_desc_only"])
    out["ai_blind_events_top_hosts"] = host_blind.most_common(10)

    def hint_report(hint, bad):
        """bad(before, after) -> True for the move that widens what the tool says it does."""
        res = collections.OrderedDict()
        for strict_name, pred in bad.items():
            pairs_all, pairs_blind, pairs_blind_net, pairs_read_blind = set(), set(), set(), set()
            for (sid, name, k), moves in hint_moves.items():
                if k != hint:
                    continue
                hit_blind = False
                for (at, b, a, ai, read_seen) in moves:
                    if pred(b, a):
                        pairs_all.add((sid, name))
                        if not ai:
                            pairs_blind.add((sid, name))
                            hit_blind = True
                        if not read_seen:
                            pairs_read_blind.add((sid, name))
                if hit_blind:
                    last = moves[-1]
                    # Not moved back: the last recorded value is not the one the counted move left.
                    if pred(last[1], last[2]) or last[2] != next(b for (_, b, a, ai, _) in moves if pred(b, a) and not ai):
                        pairs_blind_net.add((sid, name))
            def agg(pairs):
                s = {p[0] for p in pairs}
                return {
                    "tools": len(pairs),
                    "servers": len(s),
                    "hosts": len({servers.get(i, (0, "?"))[1] for i in s}),
                    "remote_servers": sum(1 for i in s if servers.get(i, (False,))[0]),
                    "package_servers": sum(1 for i in s if not servers.get(i, (False,))[0]),
                }
            res[strict_name] = {
                "all": agg(pairs_all),
                "tool_fingerprint_unchanged_in_that_read": agg(pairs_blind),
                "of_those_still_so_at_last_recorded_move": agg(pairs_blind_net),
                "no_tool_fingerprint_changed_in_that_read": agg(pairs_read_blind),
            }
        return res

    out["readOnlyHint"] = hint_report("readOnlyHint", {
        "true_to_false": lambda b, a: b is True and a is False,
        "true_to_absent": lambda b, a: b is True and a is None,
        # The other direction (added 2026-11-20, asked on DEV): a tool that now claims read-only. A host that
        # skips the prompt for read-only tools stops asking about it.
        "false_to_true": lambda b, a: b is False and a is True,
        "absent_to_true": lambda b, a: b is None and a is True,
    })
    out["destructiveHint"] = hint_report("destructiveHint", {
        "false_to_true": lambda b, a: b is False and a is True,
        "false_to_absent": lambda b, a: b is False and a is None,
        "true_to_false": lambda b, a: b is True and a is False,
    })
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
