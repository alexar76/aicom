"""Do server cards' tool lists match what HISTOR last observed? One POST /api/v1/check per disallowed endpoint on a
host whose card lists every tool with a name and an inputSchema (no contribute, 2.1 s apart for the 30/min limit).

    python3 -I compare_cards.py cards.jsonl.gz compare.jsonl
"""
import gzip
import json
import sys
import time
import urllib.request

rows = [json.loads(line) for line in gzip.open(sys.argv[1], "rt") if line.strip()]
full = [r for r in rows if r["kind"] == "json" and (r.get("tools") or {}).get("shape") == "list"
        and r["tools"]["count"] and r["tools"]["withSchema"] == r["tools"]["count"] and r["tools"].get("tools")]
seen = set()
with open(sys.argv[2], "w") as out:
    for card in full:
        for endpoint in card["endpoints"]:
            if endpoint in seen:
                continue
            seen.add(endpoint)
            body = json.dumps({"endpoint": endpoint, "tools": card["tools"]["tools"]}).encode()
            req = urllib.request.Request("https://histor.modelmarket.dev/api/v1/check", data=body, method="POST",
                                         headers={"content-type": "application/json",
                                                  "user-agent": "histor-card-survey/1 (cross-check of server cards)"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    a = json.load(resp)
                row = {"endpoint": endpoint, "card": card["url"], "count": card["tools"]["count"], "match": a.get("match"),
                       "lastStatus": (a.get("target") or {}).get("lastStatus"), "digest": (a.get("query") or {}).get("toolSetDigest"),
                       "observed": (a.get("observed") or {}).get("toolSetDigest"), "digestError": a.get("digestError")}
            except Exception as exc:  # noqa: BLE001
                row = {"endpoint": endpoint, "card": card["url"], "error": type(exc).__name__}
            out.write(json.dumps(row) + "\n")
            out.flush()
            time.sleep(2.1)
print("checked", len(seen))
