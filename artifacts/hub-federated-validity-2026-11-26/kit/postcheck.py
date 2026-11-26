# Run inside a hub (new code): what the bound serves and hides now. Read-only.
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase, _verified_since

cfg = HubConfig()
db = HubDatabase(cfg.db_path)
stored = {}
for c in db.list_capabilities(limit=None, include_unverified=True):
    stored.setdefault(c.source_hub, 0)
    stored[c.source_hub] += 1
served = {}
for c in db.list_capabilities(limit=None):
    served.setdefault(c.source_hub, 0)
    served[c.source_hub] += 1
hidden = {h: n - served.get(h, 0) for h, n in stored.items() if n - served.get(h, 0)}
print(f"bound={cfg.federated_max_unverified_s}s since={_verified_since()} stored={sum(stored.values())} "
      f"served={sum(served.values())} federated_served={db.count_federated()} hidden={hidden}")
