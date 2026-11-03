"""One honest read of every remote endpoint whose last HISTOR read was a 402: HISTOR's own reader, its own
user agent, robots.txt consulted first, nothing paid. Prints why each one asks to be paid."""
import collections, concurrent.futures as cf, gzip, json, sys, threading
from urllib.parse import urlsplit
from histor.mcpclient import McpReader, USER_AGENT
from histor.robots import Fetcher, Policy

rows = [json.loads(l) for l in gzip.open(sys.argv[1], "rt")]
eps = [r for r in rows if not r["delisted"] and r["lastStatus"] == "http-402" and r["endpoint"].startswith("http")]
policy = Policy(fetch=Fetcher(user_agent=USER_AGENT))
reader = McpReader(timeout=20, robots=policy)
locks = collections.defaultdict(threading.Lock); guard = threading.Lock()
def one(r):
    with guard: lock = locks[urlsplit(r["endpoint"]).hostname]
    with lock:
        obs = reader.list_tools(r["endpoint"])
    return r["name"], r["endpoint"], obs.status, obs.detail
out = list(cf.ThreadPoolExecutor(4).map(one, eps))
print("user agent:", USER_AGENT)
print("endpoints", len(out), dict(collections.Counter(s for _, _, s, _ in out).most_common()))
with open("count_402.json", "w") as f:
    json.dump([{"name": n, "endpoint": e, "status": s, "detail": d} for n, e, s, d in out], f, indent=1)
for n, e, s, d in out:
    if s == "pay-per-crawl": print("  pay-per-crawl", e, "|", d)
