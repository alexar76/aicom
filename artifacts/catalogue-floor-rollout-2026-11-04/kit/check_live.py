"""Run inside a live hub (docker exec / venv): migration 066 and the recorded catalogue times."""
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
db = HubDatabase(HubConfig().db_path)
applied = {int(r["version"]) for r in db._conn.execute("SELECT version FROM _migrations").fetchall()}
rows = [dict(r) for r in db._conn.execute(
    "SELECT url, generated_at, recorded_at FROM peer_catalogue_watermarks ORDER BY url").fetchall()]
trusted = [p.url for p in db.list_peers() if p.trusted]
print(f"066 applied: {66 in applied}; recorded {len(rows)} of {len(trusted)} trusted peers")
for r in rows:
    print(f"  {r['url']}  generated_at {r['generated_at']}  recorded {r['recorded_at']}")
