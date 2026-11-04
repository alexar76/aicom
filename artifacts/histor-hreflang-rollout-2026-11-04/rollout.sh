#!/usr/bin/env bash
# Run as root on admin-vps with the three changed HISTOR files staged.
set -euo pipefail

[[ "$EUID" == 0 ]] || { echo "Run on admin-vps as root" >&2; exit 1; }
SOURCE="$(realpath "${1:?Pass the source staging directory}")"
BASE=aicom-security:histor-histor-1-mongodb-review-note-20261104
BASE_ID=sha256:103105ed227b3cb3d1ba6dcd24e1b8f4f40393304e7f9ecf2a3f7ad217193720
CANDIDATE=aicom-security:histor-histor-1-hreflang-20261104
CONTAINER=histor-histor-1
PUBLIC=https://histor.modelmarket.dev
LOCAL=http://127.0.0.1:9490
COMPOSE_FILE=docker-compose.postgres.yml
REPLACED_FILES=(histor/app.py docs/landing/assets/desk.js)
NEW_FILES=(histor/server_page_text.py)
FILES=("${REPLACED_FILES[@]}" "${NEW_FILES[@]}")
declare -A BASE_HASHES=(
  [histor/app.py]=c9046b5a094104796fdb168d60efbe0172799d978b139ae57d4704e6c9a7a60c
  [docs/landing/assets/desk.js]=bda8cdba94e69fd7a8843ce3c3c66727c82e1d579025742ab8b94dd39d134ded
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
exec 9>/run/lock/histor-hreflang-rollout.lock
flock -n 9 || fail "Another HISTOR hreflang rollout is running"
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
  [[ "$live_hash" == "${BASE_HASHES[$f]}" && "$(hash_file "$f")" == "${BASE_HASHES[$f]}" ]] ||
    fail "Unexpected live or host contents of $f"
done
for f in "${NEW_FILES[@]}"; do
  [[ ! -e "$f" && ! -L "$f" ]] || fail "Existing host file $f"
  docker exec "$CONTAINER" test ! -e "/app/$f" || fail "Existing image file $f"
done

WORK="$(mktemp -d /tmp/histor-hreflang-build.XXXXXXXX)"
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
    rm -f -- "${NEW_FILES[@]}" || restored=1
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

# Exercise ASGI routing against a disposable database before touching production.
docker run --rm -i --network none -e HISTOR_PROFILE=dev -e HISTOR_DATABASE_URL= \
  -e HISTOR_PUBLIC_BASE="$PUBLIC" -e HISTOR_DATA_DIR=/tmp/histor-smoke \
  -e HISTOR_PQC=0 -e HISTOR_WITNESS_LOGS= -v "$SOURCE/verify.py:/tmp/verify.py:ro" \
  --entrypoint python "$CANDIDATE" - <<'PYSMOKE'
import asyncio
import sys

import httpx

sys.path.insert(0, "/tmp")
from verify import LANGS, PUBLIC, check_html
from histor.app import create_app
from histor.config import load_settings
from histor.service import build


async def smoke():
    services = build(load_settings())
    target_id = "0123456789abcdef"
    path = "/s/" + target_id
    try:
        services.store.target = lambda _: {
            "id": target_id, "title": "Fixture", "name": "example/fixture",
            "transport": "streamable-http", "endpoint": "https://example.com/mcp",
            "description": "", "current_toolset": "digest", "current_count": 1,
            "first_pinned": None, "unchanged_since": None, "last_ok": None,
            "ok_observations": 1, "changes": 0,
        }
        services.store.blob_text = lambda *_: '[{"name":"example","description":"Example tool"}]'
        transport = httpx.ASGITransport(app=create_app(services))
        async with httpx.AsyncClient(transport=transport, base_url=PUBLIC) as client:
            for lang in LANGS:
                page = await client.get(path, params={"lang": lang})
                page.raise_for_status()
                check_html(page.text, PUBLIC + path, "example/fixture", lang)
    finally:
        services.close()


asyncio.run(smoke())
print("Candidate ASGI smoke passed for all five languages")
PYSMOKE

[[ "$(image_id)" == "$BASE_ID" ]] && verify_binding "$BASE_ID" || fail "Live image changed during build"
install -d -m 0700 /root/histor-backups
BACKUP="$(mktemp -d /root/histor-backups/hreflang-20261104.XXXXXXXX)"
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
python3 "$SOURCE/verify.py" "$LOCAL" > "$SOURCE/origin-check.json"
curl -fsS --max-time 10 "$LOCAL/assets/desk.js" > "$WORK/desk.live"
cmp -s "$WORK/desk.live" "$WORK/docs/landing/assets/desk.js" || fail "Live desk asset mismatch"
for f in "${FILES[@]}"; do
  install -m 0644 "$WORK/$f" "$f"
done
"$QUALITY" rebind "$candidate_id"
verify_binding "$candidate_id"
docker image tag "$CANDIDATE" histor:warden-remediation-base
COMPLETED=1
resume_crawl || echo "Interrupted crawl could not be restarted" >&2
echo "Serving $candidate_id; rollout backup $BACKUP"
