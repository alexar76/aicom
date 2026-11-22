"""Run inside the candidate image (catalogue design rollout 2026-11-22) (as its own user, from /app, no network): build the app on a scratch data
dir and check what this rollout adds, before anything live is touched."""
import hashlib
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from hestia.app import build_app
from hestia.config import Settings

tmp = Path(tempfile.mkdtemp())
c = TestClient(build_app(Settings.for_test(tmp)))
out = {}
r = c.get("/agents", follow_redirects=False)
out["redirect"] = [r.status_code, r.headers.get("location")]
page = c.get("/agents/")
out["index"] = [page.status_code, page.headers["content-type"], '<script src="live.js"></script>' in page.text]
catalog = c.get("/agents/catalog.json").json()
bad = []
for agent in catalog["agents"]:
    s = c.get("/agents/" + agent["source_file"])
    if s.headers["content-type"] != "text/plain; charset=utf-8" or hashlib.sha256(s.content).hexdigest() != agent["handler_sha256"]:
        bad.append(agent["slug"])
out["agents"], out["bad"] = len(catalog["agents"]), bad
out["live_js"] = c.get("/agents/live.js").headers["content-type"]
out["landing_link"] = 'href="/agents/"' in c.get("/").text
out["escape"] = c.get("/agents/..%2f..%2fhestia%2fapp.py").status_code
out["health"] = c.get("/health").json().get("ok")
# What this rollout adds: the landing look, the proof card, the fonts it borrows from the hearth.
out["pages"] = [c.get(f"/agents/index{lang}.html").status_code for lang in ("", ".ru", ".es", ".fr", ".zh")]
out["design"] = all(m in page.text for m in ('class="hero-grid"', "data-live-sha=", 'href="/fonts/fonts.css"'))
out["fonts"] = c.get("/fonts/fonts.css").status_code
out["live_js_new"] = "data-live-sha" in c.get("/agents/live.js").text
print(json.dumps(out))
