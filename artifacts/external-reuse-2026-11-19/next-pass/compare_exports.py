"""Compare published observations offline; no requests to the listed MCP endpoints."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
from urllib.request import Request, urlopen

HF = "https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions/resolve/7350d0180291701e09835046f5b479e4b1c24c16/"
PEER = "https://raw.githubusercontent.com/yassinht/mcp-transparency-log/4b28233c1b0ccb70f14cfe81cce9732a8d9476a7/docs/data/peers/tool-digests-latest.jsonl"
URLS = {"histor": HF + "servers.jsonl.gz", "manifest": HF + "manifest.json", "peer": PEER}


def fetch(item):
    label, url = item
    request = Request(url, headers={"User-Agent": "alexar76-public-export-comparison"})
    with urlopen(request, timeout=40) as response:
        return label, response.read()


def timestamp(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def index(rows, fields):
    found = defaultdict(list)
    for row in rows:
        if row.get("name") and row.get("endpoint"):
            found[(row["name"], row["endpoint"])].append(tuple(row.get(k) for k in fields))
    return found


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        files = dict(pool.map(fetch, URLS.items()))
    manifest = json.loads(files["manifest"])
    assert sha256(files["histor"]).hexdigest() == manifest["files"]["servers.jsonl.gz"]["sha256"]
    h = index((json.loads(line) for line in gzip.decompress(files["histor"]).splitlines()),
              ["toolSetDigest", "lastObserved", "delisted", "lastStatus"])
    p = index((json.loads(line) for line in files["peer"].splitlines()), ["digest", "read_at"])
    counts = Counter()
    bands = {24: Counter(), 48: Counter()}
    for key in h.keys() & p.keys():
        counts["overlapping_name_endpoint_pairs"] += 1
        if len(h[key]) != 1 or len(p[key]) != 1:
            counts["ambiguous"] += 1
            continue
        hd, ht, delisted, status = h[key][0]
        pd, pt = p[key][0]
        if delisted or status != "ok" or not all((hd, ht, pd, pt)):
            counts["missing_successful_pair"] += 1
            continue
        counts["comparable_without_time_limit"] += 1
        gap = abs((timestamp(pt) - timestamp(ht)).total_seconds())
        for hours, matches in bands.items():
            if gap <= hours * 3600:
                matches["same" if hd == pd else "different"] += 1
    result = dict(verified_utc=datetime.now(timezone.utc).isoformat(), inputs=URLS,
                  sha256={k: sha256(v).hexdigest() for k,v in files.items()},
                  counts=dict(counts), by_max_gap_hours=bands,
                  note="Exact (registry name, endpoint) pairs, unique in both exports. HISTOR snapshot 16 Nov, Surfacelog reads 17 Nov. Last successful observations only where HISTOR lastStatus is ok and listed. A changed digest can reflect an intervening update or client-specific output. Bands are cumulative; pairs can share an endpoint.")
    print(json.dumps(result, indent=2))
