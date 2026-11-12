#!/usr/bin/env bash
# Run as root on admin-vps with the staged files: histor/{app,check}.py and docs/landing/index.html (replaced)
# and check_get_smoke.py. GET /api/v1/check, url read as the endpoint, a 400 that shows what to send
# (aicom 16fcc741c). The live app.py, check.py and index.html equal the commit's parent (b546dee95), checked
# 2026-11-09 19:32Z, so the staged files are the commit's own. Adapted from histor-mtl12-rollout-2026-11-06.
set -euo pipefail

[[ "$EUID" == 0 ]] || { echo "Run on admin-vps as root" >&2; exit 1; }
SOURCE="$(realpath "${1:?Pass the source staging directory}")"
BASE=aicom-security:histor-histor-1-wd-20261108
BASE_ID=sha256:2bd3090011aa43b8cd65c8352c3712f349126f5b43e5d7c84328ecc32bc3491a
CANDIDATE=aicom-security:histor-histor-1-chk-20261109
CONTAINER=histor-histor-1
PUBLIC=https://histor.modelmarket.dev
LOCAL=http://127.0.0.1:9490
COMPOSE_FILE=docker-compose.postgres.yml
REPLACED_FILES=(histor/app.py histor/check.py docs/landing/index.html)
NEW_FILES=()
FILES=("${REPLACED_FILES[@]}")
# The live image's files = the commit's parent b546dee95 (checked 2026-11-09 19:32Z, host copies equal too).
declare -A BASE_HASHES=(
  [histor/app.py]=9961605f5c1537a18235f840c9b0513b533f767e7c117a99c2fa0097c01f741c
  [histor/check.py]=330a7fb961a52372eb5615539418063927be4f5f8e9d321217108faa234a89db
  [docs/landing/index.html]=e42b71ec76659e5b8161f6bf900b24889f5e220cf4c1390353ec1b9cd3306d46
)
COMPOSE=(docker compose -p histor --env-file .env -f docker-compose.yml -f "$COMPOSE_FILE")
QUALITY=/usr/local/sbin/skopos-warden-quality
BINDING=/var/lib/momus-quality/live-image.json

fail() { echo "$*" >&2; exit 1; }
image_id() { docker inspect --format '{{.Image}}' "$CONTAINER"; }
hash_file() { sha256sum "$1" | cut -d' ' -f1; }
health_ok() {
  curl -fsS --max-time 4 "$LOCAL/health" | python3 -c '
import json, sys
health = json.load(sys.stdin)
assert health["ok"] and health["service"] == "histor"
assert health["profile"] == "prod" and health["store"] == "postgresql"
'
}
wait_healthy() {
  for _ in $(seq 1 60); do
    if health_ok 2>/dev/null; then return 0; fi
    sleep 2
  done
  return 1
}
verify_binding() {
  python3 - "$BINDING" "$1" <<'PY'
import json
import sys
from pathlib import Path

assert json.loads(Path(sys.argv[1]).read_text())["imageDigest"] == sys.argv[2]
PY
}

resume_crawl() {
  if (( ! WAS_CRAWLING )); then return; fi
  local include_remote=true token
  if "${COMPOSE[@]}" exec -T histor python -c 'import sys; from histor.config import load_settings; sys.exit(0 if load_settings().remote_interval_s > 0 else 1)'; then
    include_remote=false
  fi
  token="$(sed -n 's/^HISTOR_OPERATOR_TOKEN=//p' .env)"
  [[ -n "$token" ]] || return 1
  curl -fsS --max-time 10 -X POST -H "x-histor-operator: $token" \
    "$LOCAL/api/v1/admin/crawl?include_remote=$include_remote" >/dev/null
}

cd /opt/histor
exec 9>/run/lock/histor-chk-rollout.lock
flock -n 9 || fail "Another HISTOR /check rollout is running"
if pgrep -f '[r]ollout_os_candidates|[r]ollout_container' >/dev/null; then
  fail "An OS rollout is running"
fi
[[ "$(image_id)" == "$BASE_ID" && "$(docker image inspect --format '{{.Id}}' "$BASE")" == "$BASE_ID" ]] ||
  fail "Unexpected live image"
[[ -x "$QUALITY" ]] && verify_binding "$BASE_ID" || fail "Unexpected MOMUS binding"
health_ok
[[ "$(grep -Fc "image: $BASE" "$COMPOSE_FILE")" == 1 ]] || fail "Unexpected Compose image setting"
for f in "${!BASE_HASHES[@]}"; do
  live_hash="$(docker exec "$CONTAINER" sha256sum "/app/$f" | cut -d' ' -f1)"
  [[ "$live_hash" == "${BASE_HASHES[$f]}" ]] || fail "Unexpected live contents of $f"
done

WORK="$(mktemp -d /tmp/histor-chk-build.XXXXXXXX)"
SWITCHED=0
COMPLETED=0
WAS_CRAWLING=0
BACKUP=
cleanup() {
  local status=$?
  trap - EXIT
  rm -rf -- "$WORK"
  if (( SWITCHED && ! COMPLETED )); then
    set +e
    echo "Restoring prior HISTOR deployment from $BACKUP" >&2
    local restored=0
    cp -p "$BACKUP/$COMPOSE_FILE" "$COMPOSE_FILE" || restored=1
    for f in "${REPLACED_FILES[@]}"; do
      cp -p "$BACKUP/$f" "$f" || restored=1
    done
    "${COMPOSE[@]}" up -d --no-deps --no-build histor || restored=1
    wait_healthy && [[ "$(image_id)" == "$BASE_ID" ]] || restored=1
    if ! verify_binding "$BASE_ID" 2>/dev/null; then
      "$QUALITY" rebind "$BASE_ID" && verify_binding "$BASE_ID" || restored=1
    fi
    docker image tag "$BASE" histor:warden-remediation-base || restored=1
    resume_crawl || echo "Interrupted crawl could not be restarted after rollback" >&2
    if (( restored )); then
      echo "Rollback needs operator attention" >&2
    else
      echo "Prior image and host files restored" >&2
    fi
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for f in "${FILES[@]}"; do
  [[ -s "$SOURCE/$f" ]] || fail "Missing staged file $f"
  install -D -m 0644 "$SOURCE/$f" "$WORK/$f"
done
{
  printf 'FROM %s\n' "$BASE"
  for f in "${FILES[@]}"; do
    printf 'COPY --chown=root:root %s /app/%s\n' "$f" "$f"
  done
  printf 'LABEL aicom.histor.overlay=%s\n' "${CANDIDATE##*:}"
} > "$WORK/Dockerfile"
docker build -q --network none -t "$CANDIDATE" "$WORK"
candidate_id="$(docker image inspect --format '{{.Id}}' "$CANDIDATE")"
for f in "${FILES[@]}"; do
  candidate_hash="$(docker run --rm --network none --entrypoint sha256sum "$CANDIDATE" "/app/$f" | cut -d' ' -f1)"
  [[ "$candidate_hash" == "$(hash_file "$WORK/$f")" ]] || fail "Candidate content mismatch for $f"
done
docker run --rm --entrypoint node "$CANDIDATE" \
  /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden

# Exercise GET /check, the url field and the 400 against a disposable database before touching production.
# PYTHONPATH=/app: production runs `python -m histor serve` from /app, so the overlay in /app/histor wins over the
# older wheel in site-packages; a script in /tmp would otherwise import that wheel (first 2026-11-04 run: 404).
docker run --rm --network none -e PYTHONPATH=/app -e HISTOR_PROFILE=dev -e HISTOR_DATABASE_URL= \
  -e HISTOR_PUBLIC_BASE="$PUBLIC" -e HISTOR_DATA_DIR=/tmp/histor-smoke \
  -e HISTOR_PQC=0 -e HISTOR_WITNESS_LOGS= -v "$SOURCE/check_get_smoke.py:/tmp/check_get_smoke.py:ro" \
  --entrypoint python "$CANDIDATE" /tmp/check_get_smoke.py

[[ "$(image_id)" == "$BASE_ID" ]] && verify_binding "$BASE_ID" || fail "Live image changed during build"
install -d -m 0700 /root/histor-backups
BACKUP="$(mktemp -d /root/histor-backups/chk-20261109.XXXXXXXX)"
cp -p --parents "$COMPOSE_FILE" "${REPLACED_FILES[@]}" "$BACKUP"
if curl -fsS --max-time 4 "$LOCAL/health" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["crawl_running"] else 1)'; then
  WAS_CRAWLING=1
fi
SWITCHED=1
# Mark the transaction before touching Compose so every subsequent error rolls it back.
sed -i -E "s~(^[[:space:]]*image:[[:space:]]*)$BASE([[:space:]]|$)~\1$CANDIDATE\2~" "$COMPOSE_FILE"
grep -Fq "image: $CANDIDATE" "$COMPOSE_FILE" || fail "Compose replacement failed"
"${COMPOSE[@]}" up -d --no-deps --no-build histor
wait_healthy && [[ "$(image_id)" == "$candidate_id" ]] || fail "Candidate failed production health"
# Production answers a GET for a listed server with that server, sends a browser to the form, and still
# serves the noDigest API and the tiles.
SID="$(curl -fsS --max-time 30 "$LOCAL/api/v1/servers?limit=1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["servers"][0]["id"])')"
EP="$(curl -fsS --max-time 30 "$LOCAL/api/v1/servers/$SID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["server"]["endpoint"])')"
curl -fsS --max-time 30 -G "$LOCAL/api/v1/check" --data-urlencode "endpoint=$EP" | python3 -c '
import json, sys
a = json.load(sys.stdin)
assert a["type"] == "histor.check/v1" and a["target"]["id"] == sys.argv[1] and a.get("signature"), a
' "$SID" || fail "Live GET /check does not answer for a listed server"
[[ "$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -H 'Accept: text/html' "$LOCAL/api/v1/check")" == "303 $LOCAL/check" ]] ||
  fail "Live GET /check from a browser is not sent to the form"
curl -fsS --max-time 30 "$LOCAL/api/v1/servers?state=undigested&limit=1" | python3 -c '
import json, sys
s = json.load(sys.stdin)["servers"]
assert s and s[0]["noDigest"]["reason"] == "not_digestible", s[:1]
' || fail "Live API does not return noDigest"
[[ "$(curl -fsS --max-time 20 "$LOCAL/log/tile/0/000" | wc -c)" == 8192 ]] || fail "Live full tile 0/000 is not 8192 bytes"
for f in "${FILES[@]}"; do
  install -m 0644 "$WORK/$f" "$f"
done
"$QUALITY" rebind "$candidate_id"
verify_binding "$candidate_id"
docker image tag "$CANDIDATE" histor:warden-remediation-base
COMPLETED=1
resume_crawl || echo "Interrupted crawl could not be restarted" >&2
echo "Serving $candidate_id; rollout backup $BACKUP"
