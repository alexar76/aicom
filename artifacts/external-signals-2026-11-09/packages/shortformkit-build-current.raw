"""Join registry entries with probe results -> data/servers.json, data/servers.csv and README.md.

Keeps servers that answered tools/list without credentials, then removes mass-generated entries (same tool set more than
3 times, same description more than twice, more than 2 servers per registrable domain or per host on shared hosting).
Each server gets a topic from keywords; 'featured' picks up to 25 per topic (one per publisher, 3 to 40 tools, fastest first).
"""
import collections, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "build"
SHARED = {"workers.dev", "vercel.app", "onrender.com", "railway.app", "fly.dev", "supabase.co", "run.app", "netlify.app", "herokuapp.com", "github.io",
          "pages.dev", "deno.dev", "modal.run", "replit.app", "azurewebsites.net", "amazonaws.com", "web.app", "firebaseapp.com", "glitch.me", "hf.space",
          "cloudfunctions.net", "appspot.com", "koyeb.app", "ondigitalocean.app", "up.railway.app", "azurecontainerapps.io", "smithery.ai"}
TOPICS = [  # (topic, regex on title + description + tool names), first match wins
    ("Search and web", r"\b(search|web ?search|scrap|crawl|browser|serp|news)\b"),
    ("Documentation and knowledge", r"\b(docs?|documentation|knowledge|wiki|reference|library docs|manual|glossary)\b"),
    ("Developer tools", r"\b(github|gitlab|code|npm|pypi|package|sdk|api testing|regex|json|sql|database|devops|deploy|kubernetes|docker|cloud)\b"),
    ("Finance and crypto", r"\b(financ|stock|crypto|bitcoin|ethereum|token|defi|market data|forex|invoice|tax|accounting|bank|payment|price)\w*"),
    ("Weather, maps and travel", r"\b(weather|forecast|map|geo\w*|location|travel|flight|airport|hotel|ferry|train|transit|route|address)\b"),
    ("Media and content", r"\b(video|image|photo|audio|music|youtube|podcast|transcri\w*|tiktok|instagram|font|design|color)\b"),
    ("Science, health and research", r"\b(science|research|paper|arxiv|pubmed|health|medical|clinical|drug|biolog\w*|chemi\w*|gene|climate)\b"),
    ("Open data and government", r"\b(open data|government|census|statistic\w*|dataset|public records|legal|law|court|regulation|election)\b"),
    ("Business and marketing", r"\b(seo|marketing|crm|lead|sales|ecommerce|shop|product|company|business|job|recruit|real estate)\b"),
    ("AI, agents and memory", r"\b(llms?|memory|prompts?|embeddings?|rag|reasoning|vector|multi agent|agent memory|orchestrat\w*)\b"),
    ("Utilities", r"\b(calculat\w*|convert\w*|time|date|calendar|qr|pdf|unit|random|uuid|hash|email|translate|dictionary)\b"),
]


def reg(u):
    h = u.split("/")[2].split("?")[0].split(":")[0].lower()
    p = h.split(".")
    if len(p) >= 3 and p[-2] in ("co", "com", "org", "net", "ac", "gov") and len(p[-1]) == 2:
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def topic(x):
    # the topic with the most keyword hits in title and description wins; tool names only break a tie of zero
    s = " ".join([x["title"], x["name"].split("/")[-1], x["description"]]).lower().replace("_", " ").replace("-", " ")
    best = max(((len(re.findall(rx, s)), -i, t) for i, (t, rx) in enumerate(TOPICS)), default=(0, 0, "Other"))
    if best[0]:
        return best[2]
    s2 = " ".join(x["tool_names"]).lower().replace("_", " ")
    for t, rx in TOPICS[1:]:  # "search" alone in a tool name says nothing
        if re.search(rx, s2):
            return t
    return "Other"


reg_rows = json.loads((R / "registry_remotes.json").read_text())
probe = json.loads((R / "probe.json").read_text())
by_url = {}
for r in reg_rows:
    if r.get("type") == "streamable-http" and not r.get("headers"):
        by_url.setdefault(r["url"], r)
raw = []
for u, p in probe.items():
    if p["status"] == "open" and p.get("tools", 0) > 0 and u in by_url:
        r = by_url[u]
        raw.append({"name": r["name"], "title": r["title"], "description": r["description"].strip(), "url": u, "website": r["website"], "repo": r["repo"],
                    "tools": p["tools"], "tool_names": p.get("tool_names", []), "ms": p.get("ms"), "ann": p.get("ann") or {}})
ts = collections.Counter(tuple(sorted(x["tool_names"])) for x in raw)
dc = collections.Counter(x["description"].lower() for x in raw)
servers, per = [], collections.Counter()
for x in sorted(raw, key=lambda x: (x["ms"] or 99999)):
    if len(x["description"]) < 25 or x["description"].startswith("{") or dc[x["description"].lower()] > 2 or ts[tuple(sorted(x["tool_names"]))] > 3:
        continue
    key = x["url"].split("/")[2].lower() if reg(x["url"]) in SHARED else reg(x["url"])
    if per[key] >= 2:
        continue
    per[key] += 1
    x["topic"] = topic(x)
    servers.append(x)
servers.sort(key=lambda s: (s["title"] or s["name"].split("/")[-1]).lower())

featured, seen_pub = {}, set()
for x in sorted(servers, key=lambda x: (not (x["website"] or x["repo"]), x["ms"] or 99999)):
    pub = x["name"].split("/")[0]
    if not 3 <= x["tools"] <= 40 or pub in seen_pub or len(featured.get(x["topic"], [])) >= 25:
        continue
    seen_pub.add(pub)
    featured.setdefault(x["topic"], []).append(x["url"])

counts = {k: sum(1 for p in probe.values() if p["status"] == k) for k in ("open", "auth", "down")}
tested = max((p.get("tested", "") for p in probe.values()), default="")
stats = {"registry_remotes": len(reg_rows), "probed": len(probe), "answered_open": counts["open"], "auth": counts["auth"], "down": counts["down"],
         "open_pct": round(100 * counts["open"] / max(1, len(probe))), "listed": len(servers),
         "featured": sum(len(v) for v in featured.values()), "topics": collections.Counter(x["topic"] for x in servers).most_common()}
# tool annotations as the servers declare them (readOnlyHint / destructiveHint): self-reported, not verified by us
openp = [p for p in probe.values() if p["status"] == "open" and p.get("tools")]
tools_all = sum(p["tools"] for p in openp)
ann = {k: sum((p.get("ann") or {}).get(k, 0) for p in openp) for k in ("annotated", "read_only", "destructive")}
stats["annotations"] = {"open_servers": len(openp), "tools": tools_all, **ann,
                        "servers_any_annotation": sum(1 for p in openp if (p.get("ann") or {}).get("annotated")),
                        "servers_no_annotation": sum(1 for p in openp if not (p.get("ann") or {}).get("annotated"))}
import csv
keep = ("name", "title", "description", "url", "topic", "tools", "tool_names", "website", "repo")
rows = [{**{k: s.get(k) for k in keep}, "tools_annotated": s["ann"].get("annotated", 0), "tools_read_only": s["ann"].get("read_only", 0),
         "tools_destructive": s["ann"].get("destructive", 0)} for s in servers]
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "servers.json").write_text(json.dumps({"tested": tested, "stats": stats, "servers": rows}, ensure_ascii=False, indent=1))
with (ROOT / "data" / "servers.csv").open("w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["name", "title", "topic", "url", "tools", "tool_names", "description", "website", "repo", "tools_annotated", "tools_read_only", "tools_destructive"])
    for r in rows:
        w.writerow([r["name"], r["title"], r["topic"], r["url"], r["tools"], " ".join(r["tool_names"]), r["description"], r["website"], r["repo"],
                    r["tools_annotated"], r["tools_read_only"], r["tools_destructive"]])

ORDER = ["Search and web", "Documentation and knowledge", "Developer tools", "Weather, maps and travel", "Media and content", "Finance and crypto",
         "Science, health and research", "Open data and government", "Business and marketing", "AI, agents and memory", "Utilities", "Other"]
by_url = {s["url"]: s for s in servers}
cell = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
md = [f"""# Free remote MCP servers (tested weekly)

Remote [Model Context Protocol](https://modelcontextprotocol.io) servers from the [official MCP Registry](https://registry.modelcontextprotocol.io) that answer **without any API key, token or login**. Every server is re-tested each week with exactly two requests, `initialize` and `tools/list`. No tool is ever called.

**Last run: {tested}** · {stats['probed']:,} endpoints tested · **{stats['answered_open']:,} open ({stats['open_pct']} %)** · {stats['auth']:,} need auth · {stats['down']:,} not working · {stats['listed']:,} listed after removing copies

- Tool annotations (as declared by the servers, not verified): {stats['annotations']['servers_no_annotation']:,} of {stats['annotations']['open_servers']:,} open servers annotate none of their tools. Of {stats['annotations']['tools']:,} tools, {stats['annotations']['annotated']:,} carry annotations, {stats['annotations']['read_only']:,} say readOnlyHint true, {stats['annotations']['destructive']:,} say destructiveHint true. Per server in the `tools_annotated`, `tools_read_only` and `tools_destructive` columns. Note: we only see the tools a server lists without a key.
- Full list: [`data/servers.csv`](data/servers.csv) and [`data/servers.json`](data/servers.json)
- Browse with search and topics: [shortformkit.com/free-remote-mcp-servers](https://shortformkit.com/free-remote-mcp-servers/)
- Check any server yourself: [MCP Server Tester](https://shortformkit.com/mcp-server-tester/)
- Analysis with charts (failure reasons, hosting, tool counts): [State of remote MCP servers 2026](https://shortformkit.com/state-of-remote-mcp-servers-2026/)
- Key numbers with dates, ready to cite: [MCP statistics 2026](https://shortformkit.com/mcp-statistics/)

## Add a server to your client

| Client | How |
|---|---|
| Claude (claude.ai, desktop) | Customize, Connectors, + Add, Add custom connector, paste the URL |
| Claude Code | `claude mcp add --transport http NAME URL` |
| Cursor | `{{"mcpServers": {{"NAME": {{"url": "URL"}}}}}}` in `~/.cursor/mcp.json` |
| VS Code | `{{"servers": {{"NAME": {{"type": "http", "url": "URL"}}}}}}` in `.vscode/mcp.json` |

## Is your server in the list?

Show its live status in your README. The badge re-tests the endpoint about once an hour (same two read-only requests) and links to the full test result:

```markdown
[![MCP status](https://shortformkit.com/api/mcp-badge?url=YOUR_URL_ENCODED)](https://shortformkit.com/mcp-server-tester/?url=YOUR_URL_ENCODED)
```

Replace `YOUR_URL_ENCODED` with your endpoint, URL-encoded, or run the [MCP Server Tester](https://shortformkit.com/mcp-server-tester/) once and copy the ready-made badge from the result.

## Picks by topic

Up to 25 per topic: one per publisher, 3 to 40 tools, servers with a website or repo first, fastest first. Open means usable without signing up, not an endorsement: read what a server does before you connect it.
"""]
for t in ORDER:
    us = featured.get(t) or []
    if not us:
        continue
    md.append(f"\n### {t}\n\n| Server | What it does | URL | Tools |\n|---|---|---|---|")
    for u in us:
        s = by_url[u]
        name = cell(s["title"] or s["name"].split("/")[-1])
        link = s.get("website") or s.get("repo")
        md.append(f"| {'[' + name + '](' + link + ')' if link else name} | {cell(s['description'][:140])} | `{u}` | {s['tools']} |")
md.append(f"""
## Method

1. `scripts/fetch_registry.py` reads every server (latest version) from the registry and keeps remote endpoints.
2. `scripts/probe.py` tests Streamable HTTP endpoints that need no headers, at most 5 URLs per host, no temporary tunnels, 10 s timeout.
3. `scripts/make_directory.py` drops mass-generated copies (same tool set more than 3 times, same description more than twice, more than 2 per domain) and assigns topics by keyword.

The workflow in `.github/workflows/weekly.yml` runs this every Monday and commits the result. Data: CC BY 4.0. Code: MIT.

Maintained by [Shortform Kit](https://shortformkit.com), which runs its own free remote MCP server for social video transcripts and creator data: `https://shortformkit.com/mcp`.
""")
(ROOT / "README.md").write_text("\n".join(md) + "\n")
print(json.dumps(stats, indent=1))
