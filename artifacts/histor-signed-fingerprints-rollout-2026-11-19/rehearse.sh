#!/usr/bin/env bash
# Rehearsal of migration 025 and its rollback on a throw-away Postgres 16, on a network with no way out.
# Everything it makes is named hsf-reh-* and removed at the end. Touches nothing of production.
set -u
OLD=histor-histor:warden-0.31.0-prod
NEW=histor-histor:signed-fingerprints-20261119
N=hsf-reh-net PG=hsf-reh-pg APP=hsf-reh-app VOL=hsf-reh-data
D=/root/histor-signed-fingerprints-20261119
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
start() {  # image -> waits for health; prints the outcome
  docker rm -f $APP >/dev/null 2>&1
  docker run -d --name $APP --network $N --read-only --tmpfs /tmp -v $VOL:/data --memory 512m \
    -e HISTOR_DATABASE_URL="$URL" -e HISTOR_PROFILE=dev -e HISTOR_CRAWL_ON_START=0 -e HISTOR_CRAWL_INTERVAL_S=8640000 \
    -e HISTOR_REMOTE_INTERVAL_S=8640000 -e HISTOR_PUBLIC_BASE=http://127.0.0.1:9490 "$1" >/dev/null
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
    r=urllib.request.urlopen('http://127.0.0.1:9490$1',timeout=8); print(r.status, r.read()[:160].decode())
except urllib.error.HTTPError as e: print(e.code, e.read()[:160].decode())"; }
echo "1. old image on an empty database"; start $OLD
echo "2. new image on that database"; start $NEW
echo "   columns: $(q "SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='declaration_urls';")"
echo "   /api/v1/fingerprints (unknown server): $(get '/api/v1/fingerprints?profile=ai-sdk&endpoint=https://nowhere.example/mcp')"
echo "   /api/v1/fingerprints (no subject): $(get '/api/v1/fingerprints')"
echo "   /api/v1/stats: $(get '/api/v1/stats' | cut -c1-60)"
echo "3. the new statements on Postgres (store calls from the new image)"
docker run --rm --network $N --read-only --tmpfs /tmp -e HISTOR_DATABASE_URL="$URL" --entrypoint python -w /app $NEW -c '
import json, os
from pathlib import Path
from histor.db import open_backend
from histor.store import Store
from histor.subject import REGISTRY_OFFICIAL
db = open_backend(Path("/tmp/none.sqlite3"), os.environ["HISTOR_DATABASE_URL"]); st = Store(db)
ptr = json.dumps({"url": "https://example.ai/p.json", "hash": "sha256:" + "a" * 64, "name": "ai.example/pdf", "version": "1.0.0", "remotes": []})
d = "sha256-" + "A" * 43 + "="
with db.transaction() as tx:
    tx.execute("INSERT INTO targets(id, name, endpoint, transport, registry, title, description, version, repository, website, first_listed, last_listed, delisted, skip_reason) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
               ("reh1", "ai.example/pdf", "https://mcp.example.ai/mcp", "streamable-http", REGISTRY_OFFICIAL, None, None, "1.0.0", None, None, "2026-11-19T00:00:00Z", "2026-11-19T00:00:00Z", None))
    Store._note_read(tx, "reh1", "https://example.ai/p.json", "2026-11-19T00:00:00Z", None, ptr, json.dumps({"state": "verified", "inForce": {"toolSetDigest": {"contract": d, "extras": None}}}))
    Store._apply_declaration(tx, "reh1", "1.0.0", "2026-11-19T00:00:00Z", [], [{"digest": d, "source": "signed"}], {})
    Store._note_read(tx, "reh1", "https://example.ai/p.json", "2026-11-19T01:00:00Z", "invalid_signature: x", ptr, None)
f = st.declaration_file("reh1")
assert f["kind"] == "signed" and f["pointerHash"] == "sha256:" + "a" * 64 and f["statement"]["state"] == "verified" and f["lastError"].startswith("invalid_signature") and f["lastOk"] == "2026-11-19T00:00:00Z", f
rows = st.declaration_files(); assert rows and json.loads(rows[0]["pointer"])["version"] == "1.0.0", rows
out = st.refresh_declarations(rows, {"https://example.ai/p.json": (None, "http-503", {"state": "declaration_unreachable"})}, "2026-11-19T02:00:00Z")
assert out["unread"] == 1 and out["withdrawn"] == 0, out
assert st.declaration_file("reh1")["statement"]["state"] == "declaration_unreachable"
sets = st.declared_toolsets("reh1"); assert [(s["toolset"], s["source"], s["withdrawn_at"]) for s in sets] == [(d, "signed", None)], sets
print("  store calls on Postgres: ok")
' 2>&1 | grep -e 'store calls' -e Error -e Traceback | tail -4
echo "   page of that server: $(get '/api/v1/servers/reh1' | cut -c1-12)"
echo "4. old image on the database at 25 (must refuse)"; start $OLD && echo "  UNEXPECTED: the old image started"
echo "5. rollback.sql, then the old image"; cat $D/rollback.sql | docker exec -i $PG psql -v ON_ERROR_STOP=1 -U histor -d histor -At >/dev/null && echo "  rollback applied; schema $(q 'SELECT max(version) FROM schema_migrations;'); signed sets left active: $(q "SELECT count(*) FROM declared_toolsets WHERE source='signed' AND withdrawn_at IS NULL;"); pointer rows: $(q 'SELECT count(*) FROM declaration_urls;')"
start $OLD
echo "6. new image again"; start $NEW
echo "done"
