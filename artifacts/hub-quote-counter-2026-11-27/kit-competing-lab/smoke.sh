#!/usr/bin/env bash
# smoke.sh NEW_TAG — throw-away database, no network: migration 075 applies; the REST route's call counts an ok quote
# with its price and an unavailable one; the catalog routes module imports.
set -euo pipefail
docker run --rm --network none -e AIMARKET_DB_PATH=/tmp/smoke.db --entrypoint python "$1" -c '
import asyncio
import aimarket_hub.hub_routes.catalog  # noqa: F401  (the route module imports the new function)
from aimarket_hub import tutu_esim
from aimarket_hub.database import HubDatabase
db = HubDatabase("/tmp/smoke.db")
async def ok(): return {"price": "3.49", "currency": "USD"}
async def down(): raise tutu_esim.TutuQuoteUnavailable("x")
tutu_esim.fetch_tutu_quote = ok
asyncio.run(tutu_esim.fetch_and_count_tutu_quote(db, "rest"))
tutu_esim.fetch_tutu_quote = down
try:
    asyncio.run(tutu_esim.fetch_and_count_tutu_quote(db, "rest"))
except tutu_esim.TutuQuoteUnavailable:
    pass
rows = db._conn.execute("SELECT service_id, route, outcome, price FROM external_quotes ORDER BY rowid").fetchall()
assert [tuple(r) for r in rows] == [("tutu-esim", "rest", "ok", "3.49"), ("tutu-esim", "rest", "unavailable", "")], rows
v = db._conn.execute("SELECT MAX(version) FROM _migrations").fetchone()[0]
assert v == 75, v
print("smoke ok", [tuple(r) for r in rows], "migration", v)
' 2>&1 | tail -1
