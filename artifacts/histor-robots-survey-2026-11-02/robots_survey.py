"""How many of HISTOR's remote MCP endpoints does their own robots.txt disallow? (2026-11-02)

    python3 -I robots_survey.py fetch endpoints.tsv hosts.jsonl.gz      # once per host, on the server
    python3 -I robots_survey.py match endpoints.tsv hosts.jsonl.gz      # the counts

endpoints.tsv: id, endpoint, lastStatus, changes, observations (from the public /datasets/ servers snapshot).
`fetch` asks every host once for https://<host>/robots.txt (10 s, at most 512 KiB, redirects followed), from
HISTOR's address, as `histor-robots-survey`. A host whose name resolves to a non-public address is not
asked. It appends one line per host, so a rerun continues where it stopped. Stdlib only.

`match` reads each endpoint's path against its host's robots.txt as RFC 9309 says: the group naming
`histor` (HISTOR's product token), else `*`; the longest matching rule wins, Allow on a tie; `*` and a
trailing `$` are wildcards. A 4xx means no robots.txt (everything allowed, RFC 9309 2.3.1.3); a 5xx or no
answer means "assume complete disallow" (2.3.1.4) and is counted on its own line, not as a disallow.
"""
import concurrent.futures as cf
import gzip
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from urllib.parse import urlsplit

AGENT = "histor"
UA = "histor-robots-survey/1 (+https://histor.modelmarket.dev/#crawler; one GET of /robots.txt per host)"
MAX = 512 * 1024


def read_endpoints(path):
    rows = []
    with open(path) as f:
        for line in f:
            tid, endpoint, status, changes, observations = line.rstrip("\n").split("\t")
            rows.append({"id": tid, "endpoint": endpoint, "status": status, "changes": int(changes or 0),
                         "observations": int(observations or 0)})
    return rows


def public(host):
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return False, "dns: " + type(exc).__name__
    addrs = {i[4][0] for i in infos}
    if not addrs or not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs):
        return False, "non-public address"
    return True, ""


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Follow at most 5 redirects, and only to http(s) hosts that resolve to public addresses."""
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlsplit(newurl)
        if u.scheme not in ("http", "https") or not u.hostname or not public(u.hostname)[0]:
            raise urllib.error.URLError("redirect to a non-public or non-http address")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(PublicRedirects)


def fetch_one(host):
    row = {"host": host, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ok, why = public(host)
    if not ok:
        return row | {"kind": "not-asked", "detail": why}
    req = urllib.request.Request(f"https://{host}/robots.txt", headers={"User-Agent": UA})
    try:
        with OPENER.open(req, timeout=10) as resp:
            body = resp.read(MAX + 1)
            row |= {"http": resp.status, "final": resp.geturl()}
            if len(body) > MAX:
                return row | {"kind": "too-large"}
            text = body.decode("utf-8", "replace")
            return row | {"kind": "ok", "sha256": hashlib.sha256(body).hexdigest(), "text": text}
    except urllib.error.HTTPError as exc:
        return row | {"kind": "4xx" if 400 <= exc.code < 500 else "5xx", "http": exc.code}
    except Exception as exc:  # timeouts, TLS, refused, reset: "unreachable" in RFC 9309 terms
        return row | {"kind": "unreachable", "detail": type(exc).__name__}


def fetch(endpoints, out):
    hosts = sorted({urlsplit(r["endpoint"]).hostname for r in read_endpoints(endpoints)})
    done = set()
    if os.path.exists(out):
        with gzip.open(out, "rt") as f:
            done = {json.loads(line)["host"] for line in f if line.strip()}
    todo = [h for h in hosts if h not in done]
    print(f"{len(hosts)} hosts, {len(done)} done, {len(todo)} to ask", flush=True)
    lock = threading.Lock()
    with gzip.open(out, "at") as f, cf.ThreadPoolExecutor(32) as pool:
        for n, row in enumerate(pool.map(fetch_one, todo), 1):
            with lock:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if n % 1000 == 0:
                f.flush()
                print(f"{n}/{len(todo)}", flush=True)
    print("fetch done", flush=True)


def robots_allows(text, url, agent):
    """Same rule as histor/peer_xcheck.py robots_allows."""
    if not text:
        return True
    u = urlsplit(url)
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
            for a in current:
                groups[a].append((key, val))
    rules = groups.get(agent.lower()) or groups.get("*") or []

    def length(rule):
        if not rule:
            return -1
        pattern = re.escape(rule).replace(r"\*", ".*")
        if pattern.endswith(r"\$"):
            pattern = pattern[:-2] + "$"
        return len(rule) if re.match(pattern, path) else -1

    best = max(((length(v), k == "allow") for k, v in rules), default=(-1, True))
    return best[0] < 0 or best[1]


def names_histor(text):
    return any(re.match(r"\s*user-agent\s*:\s*histor\b", l, re.I) for l in (text or "").splitlines())


def match(endpoints, hosts_file):
    rows = read_endpoints(endpoints)
    hosts = {}
    with gzip.open(hosts_file, "rt") as f:
        for line in f:
            if line.strip():
                h = json.loads(line)
                hosts[h["host"]] = h
    verdict = Counter()
    by = {}
    for r in rows:
        h = hosts.get(urlsplit(r["endpoint"]).hostname) or {"kind": "missing"}
        kind = h["kind"]
        if kind == "ok":
            v = "allowed" if robots_allows(h.get("text"), r["endpoint"], AGENT) else "disallowed"
            if v == "disallowed" and robots_allows(h.get("text"), "https://x/", AGENT) is False:
                v = "disallowed (whole site)"
        elif kind == "4xx":
            v = "no robots.txt (4xx): allowed"
        elif kind in ("5xx", "unreachable"):
            v = "robots.txt 5xx or no answer: RFC 9309 says assume disallow"
        else:
            v = "not asked / other: " + kind
        r["verdict"] = v
        verdict[v] += 1
        by.setdefault(v, []).append(r)
    total = len(rows)
    out = {"endpoints": total, "hosts": len({urlsplit(r["endpoint"]).hostname for r in rows}),
           "hostKinds": dict(Counter(h["kind"] for h in hosts.values())),
           "verdicts": dict(verdict.most_common())}
    dis = [r for r in rows if r["verdict"].startswith("disallowed")]
    out["disallowed"] = {
        "endpoints": len(dis),
        "hosts": len({urlsplit(r["endpoint"]).hostname for r in dis}),
        "readOkByHistor": sum(1 for r in dis if r["status"] == "ok"),
        "withRecordedChanges": sum(1 for r in dis if r["changes"] > 0),
        "recordedChanges": sum(r["changes"] for r in dis),
        "topHosts": Counter(urlsplit(r["endpoint"]).hostname for r in dis).most_common(15),
    }
    out["allRemote"] = {"readOkByHistor": sum(1 for r in rows if r["status"] == "ok"),
                        "withRecordedChanges": sum(1 for r in rows if r["changes"] > 0),
                        "recordedChanges": sum(r["changes"] for r in rows)}
    out["namesHistor"] = sorted(h for h, v in hosts.items() if v.get("kind") == "ok" and names_histor(v.get("text")))
    rules = Counter()
    for r in dis:
        text = hosts[urlsplit(r["endpoint"]).hostname].get("text") or ""
        path = urlsplit(r["endpoint"]).path or "/"
        best = ""
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if line.lower().startswith("disallow:"):
                rule = line.split(":", 1)[1].strip()
                pat = re.escape(rule).replace(r"\*", ".*")
                if rule and re.match(pat[:-2] + "$" if pat.endswith(r"\$") else pat, path) and len(rule) > len(best):
                    best = rule
        rules[best] += 1
    out["disallowingRules"] = rules.most_common(15)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    {"fetch": fetch, "match": match}[sys.argv[1]](*sys.argv[2:])
