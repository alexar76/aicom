"""x402-bridge overlay smoke, inside the new image with no network: a throw-away hub on a temp DB."""
import os
import stat
import subprocess
import sys
import tempfile

for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_")) or "DATABASE" in name or name.startswith("PG"):
        del os.environ[name]
os.environ.update(AIMARKET_AUTO_CRAWL="0", AIMARKET_FEDERATION_ASSAY="0", AIMARKET_CREDITS_ENABLED="1")
# The live hub runs `python -m aimarket_hub serve` from /app, so it imports /app/aimarket_hub; the copy in
# site-packages is an older wheel. Import the one that runs.
sys.path.insert(0, "/app")
tmp = tempfile.mkdtemp()
os.chdir(tmp)

from fastapi.testclient import TestClient  # noqa: E402
from aimarket_hub import x402_bridge  # noqa: E402
from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.models import Peer  # noqa: E402
from aimarket_hub.signing import Signer  # noqa: E402

assert x402_bridge.__file__.startswith("/app/"), x402_bridge.__file__

config = HubConfig()
config.hub_url = "https://smoke.example"
config.db_path = os.path.join(tmp, "hub.db")
config.signing_key_path = os.path.join(tmp, "hub.key")
db = HubDatabase(config.db_path)
db.upsert_peer(Peer(url="https://silent.example", name="Silent", last_crawl="2026-10-01T00:00:00Z", trusted=True))
with TestClient(create_app(config=config, db=db, signer=Signer(config.signing_key_path))) as c:
    assert c.get("/ai-market/v2/health").status_code == 200
    tables = {r[0] for r in db._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"x402_bridge_payments", "x402_bridge_state"} <= tables, tables
    status = c.get("/ai-market/v2/x402-bridge").json()
    assert status["enabled"] is False and "off" in status["reason"], status
    peers = c.get("/ai-market/v2/federation/peers").json()
    row = next(p for p in peers["peers"] if p["url"] == "https://silent.example")
    assert peers["silent_after_days"] == 7 and row["liveness"] == "silent", row
    funnel = c.get("/ai-market/v2/federation/funnel").json()
    assert any(h["url"] == "https://silent.example" and h["liveness"] == "silent" for h in funnel["hubs"]), funnel
    page = c.get("/hubs").text
    assert "Onboarding funnel" in page and "silent" in page
    assert c.post("/ai-market/v2/observed/invoke", json={"url": "https://x.example/a"}).status_code == 503

    key = os.path.join(tmp, "bridge.key")
    subprocess.run([sys.executable, "-m", "aimarket_hub.x402_bridge", "keygen", key], check=True,
                   capture_output=True, cwd="/app")
    assert stat.S_IMODE(os.stat(key).st_mode) == 0o600
    os.environ.update(AIMARKET_X402_BRIDGE="1", AIMARKET_X402_BRIDGE_KEY_FILE=key)
    status = c.get("/ai-market/v2/x402-bridge").json()
    assert status["enabled"] is True and status["wallet"].startswith("0x"), status
    assert c.post("/ai-market/v2/observed/invoke", json={"url": "https://x.example/a"}).status_code == 401
print("x402-bridge smoke ok: migration 067, bridge status off/on, silent label, funnel, /hubs, observed invoke gate")
