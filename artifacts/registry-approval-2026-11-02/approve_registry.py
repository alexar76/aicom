# Runs INSIDE a hub container (`docker exec -i modelmarket-hub python - < approve_registry.py`).
# Approves https://registry.modelmarket.dev with the hub's own admin token, read from the environment and never
# printed, and prints the peer row before and after. Owner's yes: 2026-11-02 («Да, одобряй»).
# Rollback: the same call with {"url": URL, "trusted": false}, or DELETE /ai-market/v2/federation/peers?url=URL.
import json
import os
import urllib.error
import urllib.request

TOKEN = os.environ.get("AIMARKET_ADMIN_TOKEN", "")
URL = "https://registry.modelmarket.dev"


def call(method, path, body=None):
    for port in (os.environ.get("PORT"), os.environ.get("AIMARKET_PORT"), "8000", "9083", "8080"):
        if not port:
            continue
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return port, r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return port, e.code, {"error": e.read().decode()[:400]}
        except OSError:
            continue
    return None, None, {"error": "no local port answered"}


def row():
    _, _, d = call("GET", "/ai-market/v2/federation/peers")
    for name in ("peers", "pending"):
        for p in d.get(name) or []:
            if p.get("url") == URL:
                keep = {k: p.get(k) for k in ("url", "status", "trusted", "discoverer", "first_seen", "last_crawl")}
                return {**keep, "list": name}
    return None


print(json.dumps({"token_present": bool(TOKEN), "before": row()}))
port, status, resp = call("POST", "/ai-market/v2/federation/peers/approve", {"url": URL})
print(json.dumps({"approve_port": port, "approve_status": status, "approve": resp}))
print(json.dumps({"after": row()}))
