#!/usr/bin/env bash
# Rehearsal of migration 026 and its rollback on a throw-away Postgres 16, on a network with no way out, and of
# the subregistry's SQL on Postgres. Everything it makes is named hsr-reh-* and removed at the end. Touches
# nothing of production.
set -u
OLD=histor-histor:signed-fingerprints-20261119
NEW=histor-histor:subregistry-20261120
N=hsr-reh-net PG=hsr-reh-pg APP=hsr-reh-app VOL=hsr-reh-data
D=/root/histor-subregistry-20261120
PW=$(head -c 18 /dev/urandom | base64 | tr -dc 'a-z0-9' | head -c 20)
URL="postgresql://histor:$PW@$PG:5432/histor"
cleanup() { docker rm -f $APP $PG >/dev/null 2>&1; docker volume rm $VOL >/dev/null 2>&1; docker network rm $N >/dev/null 2>&1; }
trap cleanup EXIT
cleanup
docker network create --internal $N >/dev/null
docker volume create $VOL >/dev/null   # the keys must survive a restart, as /data does in production
docker run -d --name $PG --network $N --memory 256m -e POSTGRES_USER=histor -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=histor postgres:16-alpine >/dev/null
for i in $(seq 1 30); do docker exec $PG pg_isready -U histor -d histor >/dev/null 2>&1 && break; sleep 1; done
sleep 2
q() { echo "$1" | docker exec -i $PG psql -v ON_ERROR_STOP=1 -U histor -d histor -At; }
start() {  # image [extra docker args] -> waits for health; prints the outcome
  img=$1; shift
  docker rm -f $APP >/dev/null 2>&1
  docker run -d --name $APP --network $N --read-only --tmpfs /tmp -v $VOL:/data --memory 512m \
    -e HISTOR_DATABASE_URL="$URL" -e HISTOR_PROFILE=dev -e HISTOR_CRAWL_ON_START=0 -e HISTOR_CRAWL_INTERVAL_S=8640000 \
    -e HISTOR_REMOTE_INTERVAL_S=8640000 -e HISTOR_PUBLIC_BASE=http://127.0.0.1:9490 "$@" "$img" >/dev/null
  for i in $(seq 1 40); do
    s=$(docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{end}}' $APP 2>/dev/null)
    case "$s" in running/healthy) echo "  healthy; schema $(q 'SELECT max(version) FROM schema_migrations;')"; return 0;; exited/*) break;; esac
    sleep 3
  done
  echo "  NOT healthy ($s): $(docker logs $APP 2>&1 | grep -v -e '^\s*$' -e 'psycopg.pool' -e 'hint: you can' | grep -i -e error -e refus -e revision -e mismatch -e 'this build' -e Exception | tail -3 | cut -c1-260 | tr '\n' ' ')"
  return 1
}
get() { docker exec $APP python -c "import urllib.request,urllib.error,sys
try:
    r=urllib.request.urlopen('http://127.0.0.1:9490$1',timeout=8); print(r.status, r.headers.get('access-control-allow-origin'), r.read()[:200].decode())
except urllib.error.HTTPError as e: print(e.code, e.headers.get('content-type'), e.read()[:160].decode())"; }
echo "1. base image on an empty database"; start $OLD
echo "2. new image on that database, subregistry off"; start $NEW
echo "   /v0.1/servers: $(get '/v0.1/servers')"
echo "   table: $(q "SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='registry_entries';")"
echo "3. new image, subregistry on (no sync: the network has no way out)"; start $NEW -e HISTOR_SUBREGISTRY=1 -e HISTOR_SUBREGISTRY_SYNC_S=0
echo "   /v0.1/servers (empty): $(get '/v0.1/servers')"
echo "   /api/v1/subregistry: $(get '/api/v1/subregistry' | cut -c1-200)"
echo "4. the subregistry's statements on Postgres (calls from the new image)"
docker run --rm --network $N --read-only --tmpfs /tmp -e HISTOR_DATABASE_URL="$URL" --entrypoint python -w /app $NEW -c '
import json, os
from pathlib import Path
from histor import subregistry as sr
from histor.db import open_backend
from histor.store import Store
from histor.subject import REGISTRY_OFFICIAL
db = open_backend(Path("/tmp/none.sqlite3"), os.environ["HISTOR_DATABASE_URL"]); st = Store(db)
def e(name, version="1.0.0", latest=True, status="active", updated="2026-10-01T00:00:00.000000Z", **kw):
    return {"server": {"name": name, "version": version, "description": "d \ud800 \u0000", **kw},
            "_meta": {sr.OFFICIAL_KEY: {"status": status, "publishedAt": updated, "updatedAt": updated, "isLatest": latest}}}
recs = [e(f"io.example/s{i:02d}") for i in range(45)] + [e("com.Other/Thing", updated="2026-10-20T00:00:00Z"), e("io.example/gone", status="deleted", updated="2026-10-25T00:00:00Z")]
stats = {"read": 0, "stored": 0, "skipped": 0, "filtered": 0}
with db.transaction() as tx:
    sr._store_page(tx, recs, allow=None, seen_at="2026-11-01T12:00:00.000000Z", stats=stats)
    sr._store_page(tx, [e("io.example/s00", "1.1.0", updated="2026-11-02T00:00:00Z")], allow=None, seen_at="2026-11-02T12:00:00.000000Z", stats=stats)
    sr._store_page(tx, recs[1:4], allow=None, seen_at="2026-11-01T12:00:00.000000Z", stats=stats)   # the same page again: upsert
    tx.execute("INSERT INTO targets(id, name, endpoint, transport, registry, title, description, version, repository, website, first_listed, last_listed, delisted, skip_reason) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
               ("reh1", "io.example/s01", "https://s01.example/mcp", "streamable-http", REGISTRY_OFFICIAL, None, None, "1.0.0", None, None, "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z", "auth"))
B = "https://histor.test"
seen, cur = [], None
while True:
    p = sr.list_page(st, B, cursor=cur, limit=20)
    seen += [(s["server"]["name"], s["server"]["version"]) for s in p["servers"]]; cur = p["metadata"].get("nextCursor")
    if not cur: break
assert len(seen) == 47 and len(set(seen)) == 47, len(seen)
assert [s["server"]["name"] for s in sr.list_page(st, B, search="OTHER/th")["servers"]] == ["com.Other/Thing"]
assert sr.list_page(st, B, search="s0_")["servers"] == [] and sr.list_page(st, B, search="%")["servers"] == []
assert len(sr.list_page(st, B, version="latest", limit=100)["servers"]) == 46
assert [s["server"]["name"] for s in sr.list_page(st, B, updated_since="2026-10-15T00:00:00Z", limit=100)["servers"]] == ["com.Other/Thing", "io.example/gone", "io.example/s00"]
assert sr.one(st, B, "io.example/s00", "latest")["server"]["version"] == "1.1.0" and sr.one(st, B, "io.example/s00", "1.0.0")["_meta"][sr.OFFICIAL_KEY]["isLatest"] is False
assert [s["server"]["version"] for s in sr.versions(st, B, "io.example/s00")["servers"]] == ["1.1.0", "1.0.0"]
assert sr.one(st, B, "io.example/gone", "latest") is None and sr.one(st, B, "io.example/gone", "latest", include_deleted=True)
o = sr.one(st, B, "io.example/s01", "latest")
assert o["_meta"][sr.OBSERVED_KEY]["targets"][0]["notAttempted"] == "auth" and o["server"]["description"] == "d \ud800 \u0000"
with db.transaction() as tx:
    marked = sr._mark_unseen(tx, "2026-11-02T12:00:00.000000Z", guard=False)
    dropped = sr._drop_unlisted(tx, sr.parse_allow("io.example/*"))
s = sr.status(st, upstream="u", allow=None, public_base=B)
print("  ok: 47 entries paged, search, latest, updated_since, versions, deleted, observed, surrogate kept; marked", marked, "dropped", dropped, "status", s["servers"], s["entries"])
' 2>&1 | grep -E 'ok:|Error|Traceback|assert' | tail -6
q "DELETE FROM registry_entries; DELETE FROM targets WHERE id='reh1';" >/dev/null
echo "5. base image on the database at 26"; start $OLD
echo "6. rollback.sql, then the base image"; cat $D/rollback.sql | docker exec -i $PG psql -v ON_ERROR_STOP=1 -U histor -d histor -At >/dev/null && start $OLD
echo "7. new image again (re-applies 026)"; start $NEW -e HISTOR_SUBREGISTRY=1 -e HISTOR_SUBREGISTRY_SYNC_S=0
