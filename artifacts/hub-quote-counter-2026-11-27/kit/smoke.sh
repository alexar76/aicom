#!/usr/bin/env bash
# smoke.sh NEW_TAG — on a throw-away database: migration 075 applies, a quote is counted and read back. No network.
set -euo pipefail
docker run --rm --network none -e AIMARKET_DB_PATH=/tmp/smoke.db --entrypoint python "$1" -c '
from aimarket_hub.database import HubDatabase
db = HubDatabase("/tmp/smoke.db")
db.record_external_quote("tutu-esim", "rest", "ok", plan_id="JP-1-7", price="3.49", currency="USD")
rows = db.external_quote_counts("tutu-esim")
assert len(rows) == 1 and rows[0]["quotes"] == 1 and rows[0]["route"] == "rest", rows
v = [r[0] for r in db._conn.execute("SELECT version FROM _migrations ORDER BY version DESC LIMIT 1")]
assert v == [75], v
print("smoke ok", rows, "migration", v[0])
' 2>&1 | tail -1
