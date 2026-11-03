import json, random, sys, urllib.request, urllib.error, collections, concurrent.futures as cf
from urllib.parse import urlsplit
eps = [l.split(" ", 1)[1].strip() for l in open(sys.argv[1]) if l.startswith("ABSENT ")]
hosts = sorted({"%s://%s" % (urlsplit(e).scheme, urlsplit(e).netloc) for e in eps})
random.seed(20261102); sample = random.sample(hosts, min(400, len(hosts)))
PATHS = ["/.well-known/mcp-server-card.json", "/.well-known/mcp/server-cards.json", "/.well-known/mcp.json"]
UA = {"User-Agent": "histor-audit/2026-11-02 (+https://histor.modelmarket.dev/#crawler; one-off count of server-card paths)", "Accept": "application/json"}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=10)
        body = r.read(1_048_577)
        if urlsplit(r.geturl()).netloc != urlsplit(u).netloc: return "redirect-away", None
        try: doc = json.loads(body)
        except Exception: return "200-not-json", None
        return "json", doc
    except urllib.error.HTTPError as e: return "http-%d" % e.code, None
    except Exception as e: return type(e).__name__, None
def check(h):
    out = {}
    for p in PATHS:
        st, doc = get(h + p)
        if st == "json":
            items = doc if isinstance(doc, list) else (doc.get("cards") or doc.get("servers") or [doc]) if isinstance(doc, dict) else []
            tools = any(isinstance(i, dict) and isinstance(i.get("tools"), list) and i.get("tools") for i in items)
            cardish = any(isinstance(i, dict) and ({"name", "serverInfo", "tools", "remotes", "transport", "endpoint", "url", "capabilities"} & set(i)) for i in items)
            st = "card+tools" if tools else ("card" if cardish else "json-other")
        out[p] = st
    return h, out
res = list(cf.ThreadPoolExecutor(16).map(check, sample))
print("absent endpoints", len(eps), "hosts", len(hosts), "sampled", len(sample))
for p in PATHS:
    c = collections.Counter(o[p] for _, o in res)
    print(p, dict(c.most_common(8)))
for h, o in res:
    if any(v.startswith("card") for v in o.values()): print("  FOUND", h, {k: v for k, v in o.items() if v.startswith("card")})
