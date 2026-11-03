"""Where the old and the RFC 9309 robots.txt rules disagree on MCP endpoints (2026-11-01).

Inputs: panel.txt (ScraperWatch's fixed panel, 2,995 MCP endpoints) and raw/ from fetch.sh.
Every endpoint path is decided for a crawler with no named group of its own ("ExampleBot") by
urllib.robotparser of the interpreter that runs `decide`:

  python3.12 -I analyze.py decide old.json   # old reader: first matching rule wins, '*' and '$' are plain text
                                              # (all of 3.12 and older, 3.13.0-3.13.13, 3.14.0-3.14.4)
  python3.14 -I analyze.py decide new.json   # RFC 9309 reader (3.14.5+, 3.13.14+, 3.15)
  python3 -I analyze.py compare old.json new.json <path to histor/>

`compare` also runs HISTOR's own reader (histor.peer_xcheck.robots_allows) as a third opinion and writes
results.json and disagreements.csv.
"""
import csv, json, re, sys, urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
UA = "ExampleBot"

def robots_bodies():
    for meta in sorted((HERE / "raw").glob("*.meta")):
        host = meta.name[:-5]
        text = meta.read_text().strip()
        code = text.split()[0] if text else "000"
        body = None
        if code in ("200", "206"):
            body = (HERE / "raw" / f"{host}.txt").read_bytes()[:524288].decode("utf-8", "replace")
            if not re.search(r"(?im)^\s*user-agent\s*:", body) or body.lstrip()[:1] == "<":
                body = ""          # an HTML page or no groups: no rules
        yield host, code, body

def endpoints():
    eps = {}
    for line in (HERE / "panel.txt").read_text().splitlines():
        if line.startswith("http"):
            u = urlsplit(line.strip())
            eps.setdefault(u.netloc.lower(), []).append((line.strip(), (u.path or "/") + (f"?{u.query}" if u.query else "")))
    return eps

def decide(out):
    eps, res = endpoints(), {}
    for host, code, body in robots_bodies():
        if not body:
            continue
        p = urllib.robotparser.RobotFileParser(); p.parse(body.splitlines())
        for url, _ in eps.get(host, []):
            res[url] = p.can_fetch(UA, url)
    Path(out).write_text(json.dumps({"python": sys.version.split()[0], "decisions": res}, indent=0, sort_keys=True))
    print(sys.version.split()[0], len(res))

def group_rules(text):
    """Allow/Disallow lines of the group that applies to UA (its named group, else '*')."""
    groups, cur, in_agents = [], None, False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (s.strip() for s in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if not in_agents:
                cur = {"agents": [], "rules": []}; groups.append(cur)
            cur["agents"].append(v.lower()); in_agents = True
        elif k in ("allow", "disallow") and cur is not None:
            cur["rules"].append((k, v)); in_agents = False
        else:
            in_agents = False
    named = [g for g in groups if UA.lower() in g["agents"]]
    return [r for g in (named or [g for g in groups if "*" in g["agents"]]) for r in g["rules"]]

def rule_matches(rule, path):
    pat = re.escape(rule).replace(r"\*", ".*")
    if pat.endswith(r"\$"):
        pat = pat[:-2] + "$"
    return re.match(pat, path) is not None

def compare(old_f, new_f, histor_dir):
    sys.path.insert(0, histor_dir)
    from histor.peer_xcheck import robots_allows
    old, new = json.loads(Path(old_f).read_text()), json.loads(Path(new_f).read_text())
    eps = endpoints()
    s = {"python_old": old["python"], "python_new": new["python"], "hosts": 0, "fetched": {},
         "hosts_with_robots": 0, "hosts_html_or_no_groups": 0, "endpoints_on_hosts_with_robots": 0,
         "agree": 0, "old_allows_rfc_disallows": 0, "old_disallows_rfc_allows": 0, "hosts_disagreeing": 0,
         "reasons": {}, "deciding_disallow": {}, "rfc_vs_histor_disagree": 0,
         "hosts_allow_root_then_disallow": 0, "hosts_with_star_or_dollar": 0}
    rows = []
    for host, code, body in robots_bodies():
        s["hosts"] += 1
        s["fetched"][code] = s["fetched"].get(code, 0) + 1
        if body is None:
            continue
        if not body:
            s["hosts_html_or_no_groups"] += 1; continue
        s["hosts_with_robots"] += 1
        rules = group_rules(body)
        s["hosts_with_star_or_dollar"] += any("*" in v.rstrip("*") or v.endswith("$") for _, v in rules)
        s["hosts_allow_root_then_disallow"] += any(k == "allow" and v == "/" and any(kk == "disallow" and vv for kk, vv in rules[i + 1:])
                                                   for i, (k, v) in enumerate(rules))
        bad = False
        for url, path in eps.get(host, []):
            s["endpoints_on_hosts_with_robots"] += 1
            a_old, a_new = old["decisions"][url], new["decisions"][url]
            s["rfc_vs_histor_disagree"] += a_new != robots_allows(body, path, UA)
            if a_old == a_new:
                s["agree"] += 1; continue
            bad = True
            s["old_allows_rfc_disallows" if a_old else "old_disallows_rfc_allows"] += 1
            hits = [v for _, v in rules if v and path.startswith(re.split(r"[*$]", v)[0])]
            reason = "'*' or '$' in a rule that matches" if any(re.search(r"[*$]", v) for v in hits) else "rule order (first match vs longest)"
            s["reasons"][reason] = s["reasons"].get(reason, 0) + 1
            if a_old:  # the rule RFC 9309 applies: the longest Disallow that matches
                dis = [v for k, v in rules if k == "disallow" and v and rule_matches(v, path)]
                top = max(dis, key=len) if dis else "?"
                s["deciding_disallow"][top] = s["deciding_disallow"].get(top, 0) + 1
            rows.append({"host": host, "endpoint": url, "old": a_old, "rfc9309": a_new, "reason": reason,
                         "rules": " | ".join(f"{k}: {v}" for k, v in rules)[:500]})
        s["hosts_disagreeing"] += bad
    (HERE / "results.json").write_text(json.dumps(s, indent=1, sort_keys=True) + "\n")
    with open(HERE / "disagreements.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["host"]); w.writeheader(); w.writerows(rows)
    print(json.dumps(s, indent=1, sort_keys=True))

if __name__ == "__main__":
    {"decide": decide, "compare": compare}[sys.argv[1]](*sys.argv[2:])
