"""Do the sites whose robots.txt keeps HISTOR off their MCP path publish an MCP server card it may read? (2026-11-02)

    python3 -I cards_survey.py ../histor-robots-survey-20261102 cards.jsonl.gz     # on admin-vps

Input: the robots survey of 2026-11-02 (endpoints.tsv, hosts.jsonl.gz, robots_survey.py). For every host with an
endpoint its robots.txt disallows to `histor`, these candidates are asked, each only if that same robots.txt
allows it to `histor` (RFC 9309, the survey's matcher):

  /.well-known/mcp/server-card.json   the MCP server card proposal
  /.well-known/mcp.json, /.well-known/mcp
  <endpoint path>/server-card         (signupsheet.page serves it there and allows it explicitly)
  every literal Allow path in the host's group that names a server card or /.well-known/mcp

One GET each, 10 s, at most 512 KiB, redirects only to public hosts (at most 5), User-Agent naming the survey.
Recorded: status, content type, whether it is JSON, its top-level keys, and what it says about tools (a list:
how many, and whether each has a name and an inputSchema; "dynamic"; or nothing). The tool list itself is kept
for the cards that have one, to compare with what HISTOR last observed. Stdlib only.
"""
import concurrent.futures as cf
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

sys.path.insert(0, sys.argv[1])
import robots_survey as rs  # noqa: E402

UA = "histor-card-survey/1 (+https://histor.modelmarket.dev/#crawler; one GET per allowed server-card path)"
MAX = 512 * 1024
OPENER = urllib.request.build_opener(rs.PublicRedirects)


def candidates(host, text, endpoints):
    paths = ["/.well-known/mcp/server-card.json", "/.well-known/mcp.json", "/.well-known/mcp"]
    for e in endpoints:
        p = (urlsplit(e).path or "/").rstrip("/")
        paths.append(f"{p}/server-card")
    for line in text.splitlines():
        m = re.match(r"\s*allow\s*:\s*(\S+)", line.split("#", 1)[0], re.I)
        if m and ("server-card" in m.group(1) or "/.well-known/mcp" in m.group(1)) and "*" not in m.group(1):
            paths.append(m.group(1).rstrip("$"))
    out = []
    for p in dict.fromkeys(paths):
        url = f"https://{host}{p}"
        if rs.robots_allows(text, url, "histor"):
            out.append(url)
    return out


def tools_of(doc):
    if not isinstance(doc, dict):
        return {"shape": "not-an-object"}
    t = doc.get("tools")
    if t is None and isinstance(doc.get("capabilities"), dict):
        t = doc["capabilities"].get("tools")
    if isinstance(t, list):
        named = [x for x in t if isinstance(x, dict) and isinstance(x.get("name"), str)]
        schemas = [x for x in named if isinstance(x.get("inputSchema"), dict)]
        return {"shape": "list", "count": len(t), "named": len(named), "withSchema": len(schemas),
                "names": [x["name"] for x in named][:200], "tools": t if len(json.dumps(t)) < 400_000 else None}
    if isinstance(t, str):
        return {"shape": "string", "value": t[:40]}
    if isinstance(t, dict):
        return {"shape": "object", "keys": sorted(t)[:20]}
    return {"shape": "absent"}


def fetch(url):
    row = {"url": url, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ok, why = rs.public(urlsplit(url).hostname)
    if not ok:
        return row | {"kind": "not-asked", "detail": why}
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "identity"})
    try:
        with OPENER.open(req, timeout=10) as resp:
            body = resp.read(MAX + 1)
            row |= {"http": resp.status, "final": resp.geturl(), "type": resp.headers.get("content-type", "")}
    except urllib.error.HTTPError as exc:
        return row | {"kind": "http", "http": exc.code}
    except Exception as exc:  # noqa: BLE001
        return row | {"kind": "error", "detail": type(exc).__name__}
    if len(body) > MAX:
        return row | {"kind": "too-large"}
    try:
        doc = json.loads(body)
    except ValueError:
        return row | {"kind": "not-json", "head": body[:80].decode("utf-8", "replace")}
    keys = sorted(doc)[:30] if isinstance(doc, dict) else []
    info = doc.get("serverInfo") if isinstance(doc, dict) else None
    return row | {"kind": "json", "keys": keys, "tools": tools_of(doc),
                  "serverName": info.get("name") if isinstance(info, dict) else None,
                  "transport": doc.get("transport") if isinstance(doc, dict) else None}


def main(survey_dir, out):
    rows = rs.read_endpoints(f"{survey_dir}/endpoints.tsv")
    hosts = {}
    with gzip.open(f"{survey_dir}/hosts.jsonl.gz", "rt") as f:
        for line in f:
            if line.strip():
                h = json.loads(line)
                hosts[h["host"]] = h
    blocked = {}
    for r in rows:
        host = urlsplit(r["endpoint"]).hostname
        h = hosts.get(host) or {}
        if h.get("kind") == "ok" and not rs.robots_allows(h.get("text"), r["endpoint"], "histor"):
            blocked.setdefault(host, []).append(r["endpoint"])
    jobs = []
    for host, eps in sorted(blocked.items()):
        for url in candidates(host, hosts[host].get("text") or "", eps):
            jobs.append((host, url))
    print(f"{len(blocked)} hosts, {len(jobs)} allowed candidate URLs", flush=True)
    with gzip.open(out, "wt") as f, cf.ThreadPoolExecutor(24) as pool:
        for n, (row, (host, _)) in enumerate(zip(pool.map(fetch, [u for _, u in jobs]), jobs), 1):
            f.write(json.dumps(row | {"host": host, "endpoints": blocked[host]}, ensure_ascii=False) + "\n")
            if n % 2000 == 0:
                print(f"{n}/{len(jobs)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
