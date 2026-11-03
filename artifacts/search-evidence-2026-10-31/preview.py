"""Isolated, read-only browser preview. All sellers and offers below are test fixtures."""
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

os.environ.update(AIMARKET_AUTO_CRAWL="0", AIMARKET_FEDERATION_ASSAY="0", AIFACTORY_CRYPTO_ENABLED="0")

import uvicorn
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.crawler import Crawler
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer

temporary = tempfile.TemporaryDirectory(prefix="search-evidence-preview-")
root = Path(temporary.name)
cfg = HubConfig()
cfg.hub_url = "http://127.0.0.1:8769"
cfg.db_path = str(root / "preview.db")
cfg.signing_key_path = str(root / "hub.key")
cfg.seed_list = []
cfg.crawl_initial_delay_s = 86400
db = HubDatabase(cfg.db_path)
signer, peer_signer = Signer(cfg.signing_key_path), Signer(root / "fixture-peer.key")
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
peer = "https://signed-preview.example"
db.upsert_peer(Peer(url=peer, name="Preview catalog", public_key=peer_signer.public_key_b64,
                    trusted=True, last_crawl=stamp))
manifest = {"protocol_version": "v2", "generated_at": stamp, "capabilities_count": 1, "tools": [{
    "name": "Weather forecast · preview", "capability_id": "weather.preview@v1",
    "product_id": "weather", "description": "Weather forecast for a city. Local test fixture.",
    "input_schema": {"type": "object", "required": ["city"], "properties": {"city": {"type": "string"}}},
    "price_per_call_usd": 0.003,
}]}
manifest["signature"] = peer_signer.sign_manifest(manifest)
assert signer.verify_manifest_signature(manifest, peer_signer.public_key_b64)
crawler = Crawler(config=cfg, db=db, signer=signer)
crawler._index_manifest_capabilities(manifest, peer, "Preview catalog", evidence={
    "kind": "signed_catalogue", "scope": "catalogue", "signer": peer,
    "signer_public_key": peer_signer.public_key_b64, "checked_at": stamp, "checked_by": cfg.hub_url,
})
seller = "https://observed-preview.example"
db.upsert_observed_seller(seller, name="Observed weather · preview",
                         consent={"by": "local fixture", "at": stamp, "how": "test fixture"})
db.save_observed_seller_observation(seller, {
    "name": "Observed weather · preview", "discovery_url": seller + "/.well-known/x402",
    "observed_at": stamp, "pinned_pay_to": "0x1111111111111111111111111111111111111111",
    "routes": [{"url": seller + "/weather", "method": "POST", "description": "Observed weather quote. Local test fixture.",
                "price_usd": 0.002, "amount_atomic": "2000", "network": "eip155:8453",
                "asset": "USDC", "pay_to": "0x1111111111111111111111111111111111111111",
                "probed_at": stamp, "listed": True, "result": "quoted"}],
})
app = create_app(config=cfg, db=db, signer=signer)
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8769, log_level="warning")
