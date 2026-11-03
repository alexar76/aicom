"""Temporary own-origin observation for live UI QA. Never creates a foreign seller."""
import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:9083/ai-market/v2/federation/observed-sellers"
ORIGIN = "https://modelmarket.dev"
NAME = "modelmarket.dev — deployment self-test"
HEADERS = {"Authorization": "Bearer " + os.environ["AIMARKET_ADMIN_TOKEN"], "Content-Type": "application/json"}


def call(method, path="", body=None):
    request = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                      headers=HEADERS, method=method)
    with urlopen(request, timeout=90) as response:
        return json.load(response)


mode = sys.argv[1]
sellers = call("GET")["sellers"]
existing = next((seller for seller in sellers if seller["origin"] == ORIGIN), None)
if mode == "add":
    assert existing is None, "Own origin already exists: do not overwrite"
    try:
        result = call("POST", body={
            "origin": ORIGIN, "name": NAME,
            "consent": {"by": "alexar76 operator deployment self-test", "at": datetime.now(timezone.utc).isoformat(),
                        "how": "Own origin; temporary 3.17.0 search QA; unpaid 402 probe only"},
            "routes": [ORIGIN + "/x402/x402-check"],
        })
        assert result["seller"]["routes_served"] == 1, result["seller"].get("last_error")
        print(json.dumps(result))
    except Exception:
        created = next((s for s in call("GET")["sellers"] if s["origin"] == ORIGIN), None)
        if created and created["name"] == NAME:
            call("DELETE", "?origin=https%3A%2F%2Fmodelmarket.dev")
        raise
elif mode == "delete":
    assert existing and existing["name"] == NAME, "Refusing to delete a record not owned by this test"
    result = call("DELETE", "?origin=https%3A%2F%2Fmodelmarket.dev")
    assert all(s["origin"] != ORIGIN for s in call("GET")["sellers"])
    print(json.dumps({"deleted": result, "testRecordAbsent": True}))
else:
    raise SystemExit("Use add or delete")
