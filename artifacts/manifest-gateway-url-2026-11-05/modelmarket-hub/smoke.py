"""Inside the overlay image, no network: a throw-away hub on a temp DB with one gateway seller and one public one."""
import json
import os
import tempfile

for name in list(os.environ):
    if name.startswith(("AIMARKET_", "HUB_")) or "DATABASE" in name or name.startswith("PG"):
        del os.environ[name]
os.environ.update(AIMARKET_AUTO_CRAWL="0", AIMARKET_FEDERATION_ASSAY="0", AIMARKET_INVOKE_HOST_GATEWAY="aicom-diagnostics",
                  AIMARKET_ORACLE_FAMILY_URL="off")
tmp = tempfile.mkdtemp()
os.chdir(tmp)
from fastapi.testclient import TestClient  # noqa: E402
from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.models import Capability  # noqa: E402
from aimarket_hub.signing import Signer  # noqa: E402

config = HubConfig()
config.hub_url = "https://smoke.example"
config.db_path = os.path.join(tmp, "hub.db")
config.signing_key_path = os.path.join(tmp, "hub.key")
db = HubDatabase(config.db_path)
internal = "http://aicom-diagnostics:8124/diagnose"
db.upsert_capability(Capability(capability_id="aicom.diagnose@v1", product_id="aicom-diagnostics", name="Diag",
                                price_per_call_usd=0.1, trust_score=0.5, invoke_url=internal))
db.upsert_capability(Capability(capability_id="public@v1", product_id="public", name="Public", price_per_call_usd=0.1,
                                trust_score=0.5, invoke_url="https://seller.example.com/invoke"))
with TestClient(create_app(config=config, db=db, signer=Signer(config.signing_key_path))) as c:
    body = c.get("/ai-market/v2/manifest").text
    assert c.get("/ai-market/v2/health").status_code == 200
tools = {t["capability_id"]: t for t in json.loads(body)["tools"]}
assert "aicom-diagnostics:8124" not in body
assert tools["aicom.diagnose@v1"]["invoke_url"] == "https://smoke.example/ai-market/v2/invoke"
assert tools["public@v1"]["invoke_url"] == "https://seller.example.com/invoke"
assert db.get_capability("aicom-diagnostics", "aicom.diagnose@v1").invoke_url == internal
print("manifest gateway smoke ok: gateway seller shown as the hub, public seller unchanged, stored address kept, health 200")
