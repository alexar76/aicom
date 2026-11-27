#!/usr/bin/env bash
# smoke.sh NEW_TAG — throw-away database, no network: migration 076 applies; an ok quote gets a 16-hex quote_id that the
# checkout link carries as mmq and the row stores; a link that already has mmq is refused and counted unavailable.
set -euo pipefail
docker run --rm --network none -e AIMARKET_DB_PATH=/tmp/smoke.db --entrypoint python "$1" -c '
import asyncio
import aimarket_hub.hub_routes.catalog  # noqa: F401
from aimarket_hub import tutu_esim
from aimarket_hub.database import HubDatabase
db = HubDatabase("/tmp/smoke.db")
link = "https://tutuesim.com/en/esim/japan/?src=aimarket&plan=JP-1-7"
async def ok(): return {"price": "3.49", "currency": "USD", "checkout_url": link}
async def theirs(): return {"price": "3.49", "currency": "USD", "checkout_url": link + "&mmq=x"}
tutu_esim.fetch_tutu_quote = ok
q = asyncio.run(tutu_esim.fetch_and_count_tutu_quote(db, "rest"))
qid = q["quote_id"]
assert len(qid) == 16 and q["checkout_url"] == link + "&mmq=" + qid, q
tutu_esim.fetch_tutu_quote = theirs
try:
    asyncio.run(tutu_esim.fetch_and_count_tutu_quote(db, "rest"))
    raise SystemExit("a link with mmq was accepted")
except tutu_esim.TutuQuoteUnavailable:
    pass
rows = [tuple(r) for r in db._conn.execute("SELECT outcome, price, quote_id FROM external_quotes ORDER BY rowid")]
assert rows == [("ok", "3.49", qid), ("unavailable", "", "")], rows
assert db.external_quote(qid)["price"] == "3.49"
v = db._conn.execute("SELECT MAX(version) FROM _migrations").fetchone()[0]
assert v == 76, v
print("smoke ok", q["checkout_url"], rows, "migration", v)
' 2>&1 | tail -1
