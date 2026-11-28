"""era_sample.py CSV PSL_PY_DIR PUBLIC_SUFFIX_LIST N SEED OUT.jsonl — do servers that answer MCP 2026-07-28 list the same tools to a
handshake client?

Sample: rows of remote_protocols.csv (the 26 Nov export of HISTOR's remote observations) whose last successful
read was on 2026-07-28, one per registrable domain, N of them drawn with a fixed seed; our own domains left out.
Every one was read by HISTOR's crawler through 26 Nov, so its robots rules already admit this reader.
Each server gets two read-only reads a second apart: server/discover + tools/list (2026-07-28), then
initialize asking 2025-06-18 + tools/list. One JSON line per server: both digests, tool counts, and for a
difference the tools and top-level members that differ.
"""
import csv, json, random, sys, time, urllib.request
from pathlib import Path

import read_eras as R

csv_path, psl_dir, psl_dat, n, seed, out_path = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), Path(sys.argv[6])
sys.path.insert(0, psl_dir)
import psl  # noqa: E402  (the article's public-suffix helper)

R.UA = "histor/0.11.0 (+https://histor.modelmarket.dev/#crawler; read-only: discover + tools/list; era cross-check)"
OURS = ("modelmarket.dev", "attestedmemory.net", "independentai.network", "pingblip.com")
domain = psl.make(psl_dat)


rows = [r for r in csv.DictReader(open(csv_path)) if r["last_protocol"] == "2026-07-28" and r["transport"] == "streamable-http"]
by_domain = {}
for r in rows:
    d = domain(r["host"])
    if d and not d.endswith(OURS):
        by_domain.setdefault(d, []).append(r)
rng = random.Random(seed)
domains = sorted(by_domain)
rng.shuffle(domains)
done = {json.loads(line)["target_id"] for line in out_path.read_text().splitlines()} if out_path.exists() else set()
print(f"{len(rows)} modern rows on {len(by_domain)} domains; sampling {n}; {len(done)} already read", flush=True)


def endpoint_of(target_id):
    req = urllib.request.Request(f"https://histor.modelmarket.dev/api/v1/servers/{target_id}", headers={"User-Agent": R.UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        s = json.load(r)["server"]
    return s.get("name"), s.get("endpoint")


def differences(a, b):
    A, B = {t.get("name"): t for t in a if isinstance(t, dict)}, {t.get("name"): t for t in b if isinstance(t, dict)}
    out = {"only_modern": sorted(set(A) - set(B), key=str)[:20], "only_handshake": sorted(set(B) - set(A), key=str)[:20], "members": {}}
    for name in set(A) & set(B):
        for k in ("description", "inputSchema", "outputSchema"):
            if A[name].get(k) != B[name].get(k):
                out["members"][k] = out["members"].get(k, 0) + 1
    return out


with out_path.open("a") as f:
    taken = 0
    for d in domains:
        if taken >= n:
            break
        row = rng.choice(by_domain[d])
        taken += 1
        if row["target_id"] in done:
            continue
        rec = {"target_id": row["target_id"], "domain": d, "host": row["host"]}
        try:
            rec["name"], url = endpoint_of(row["target_id"])
            modern = R.read(url, "modern")
            time.sleep(1)
            old = R.read(url, "hs-2025-06-18")
            raw_m, raw_h = modern.pop("raw", None), old.pop("raw", None)
            rec.update(modern=modern, handshake=old, read_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            if raw_m is not None and raw_h is not None and modern.get("digest") != old.get("digest"):
                rec["differ"] = differences(raw_m, raw_h)
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
        f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
        time.sleep(1)
print("done", flush=True)
