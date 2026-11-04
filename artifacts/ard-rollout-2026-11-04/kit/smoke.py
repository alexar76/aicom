"""ARD door smoke, inside the new image with no network: a throw-away hub on a temp DB, no live settings."""
import os
import sys
import tempfile

for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_")) or "DATABASE" in name or name.startswith("PG"):
        del os.environ[name]
os.environ.update(AIMARKET_AUTO_CRAWL="0", AIMARKET_FEDERATION_ASSAY="0")
tmp = tempfile.mkdtemp()
os.chdir(tmp)

import base64, hashlib, json  # noqa: E402
from urllib.parse import urlparse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from aimarket_hub import ard  # noqa: E402
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
db.upsert_capability(Capability(capability_id="smoke.weather@v1", product_id="smoke", name="Weather",
                                description="Current weather for a city.", price_per_call_usd=0.01,
                                trust_score=0.5, invoke_url="https://provider.example/w"))
signer = Signer(config.signing_key_path)
path = lambda url: urlparse(url).path + ("?" + urlparse(url).query if urlparse(url).query else "")  # noqa: E731
with TestClient(create_app(config=config, db=db, signer=signer)) as c:
    m = c.get("/.well-known/ard.json")
    assert m.status_code == 200 and m.headers["content-type"] == "application/ard+json", (m.status_code, m.headers)
    entries = json.loads(m.content)["entries"]
    assert [e["type"] for e in entries] == [ard.REGISTRY_TYPE, ard.A2A_CARD_TYPE, ard.MCP_CARD_TYPE,
                                           ard.DISCOVERY_DOCUMENT_TYPE], [e["type"] for e in entries]
    for e in entries:
        assert ard.verify_trust_manifest(e["trustManifest"], signer.public_key_b64), e["identifier"]
        if "digest" in e:
            assert e["digest"] == "sha256:" + hashlib.sha256(c.get(path(e["url"])).content).hexdigest(), e["url"]
    did = c.get("/.well-known/did.json").json()
    assert base64.urlsafe_b64decode(did["verificationMethod"][0]["publicKeyJwk"]["x"] + "=") == \
        base64.b64decode(signer.public_key_b64)
    assert '<https://smoke.example/.well-known/ard.json>; rel="ard"' in c.head("/").headers.get_list("link")
    s = c.post("/ard/v1/search", json={"query": {"text": "weather"}})
    assert s.status_code == 200, s.text
    hit = next(r for r in s.json()["results"] if r["identifier"] == "urn:air:smoke.example:smoke:smoke.weather@v1")
    assert hit["digest"] == "sha256:" + hashlib.sha256(c.get(path(hit["url"])).content).hexdigest()
    assert ard.verify_trust_manifest(hit["trustManifest"], signer.public_key_b64)
    assert c.post("/ard/v1/search", json={"query": {"text": "x", "filter": {"nope": "1"}}}).status_code == 400
    assert c.get("/ard/v1/agents").status_code == 200
    assert c.post("/ard/v1/explore", json={"resultType": {"facets": [{"field": "type"}]}}).status_code == 200
    assert c.get("/ai-market/v2/health").status_code == 200
    assert c.get("/.well-known/agent-marketplace").status_code == 200
print("ARD smoke ok:", len(entries), "manifest entries, search hit signed, digests match, health 200")
