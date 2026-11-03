#!/usr/bin/env bash
# Run as root on admin-vps. Pass a staging directory with the five source files
# in their /opt/histor layout (histor/app.py and docs/landing/...).
set -euo pipefail

[[ "$EUID" == 0 ]] || { echo "Run on admin-vps as root" >&2; exit 1; }
SOURCE="$(realpath "${1:?Pass the source staging directory}")"
BASE=aicom-security:histor-histor-1-mj-20261102
BASE_ID=sha256:aebbc1ff7fa000ee0c20fc6f62e544ab2fb1fddc7e1d55dac788dea0d8a5a005
CANDIDATE=aicom-security:histor-histor-1-mongodb-20261103
CONTAINER=histor-histor-1
PUBLIC=https://histor.modelmarket.dev
LOCAL=http://127.0.0.1:9490
GUIDE=/mongodb-mcp-read-only-tools.html
COMPOSE_FILE=docker-compose.postgres.yml
APP=histor/app.py
INDEX=docs/landing/index.html
NEW_FILES=(
  docs/landing/mongodb-mcp-read-only-tools.html
  docs/landing/assets/compare-tool-names.js
  docs/landing/assets/tool-comparison.css
)
FILES=("$APP" "$INDEX" "${NEW_FILES[@]}")
declare -A BASE_HASHES=(
  ["$APP"]=d4780f8b376b8890aad8a9be5d235f3bcbbadc69f09c8685b009e6ec0f155685
  ["$INDEX"]=6563eff0acd5031489cc816db0f7e4d25cfd92e6edd0e06d512b63494bc212ad
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
exec 9>/run/lock/histor-mongodb-rollout.lock
flock -n 9 || fail "Another MongoDB rollout is running"
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

WORK="$(mktemp -d /tmp/histor-mongodb-build.XXXXXXXX)"
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
    cp -p "$BACKUP/$APP" "$APP" || restored=1
    cp -p "$BACKUP/$INDEX" "$INDEX" || restored=1
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
cat > "$WORK/Dockerfile" <<DOCKERFILE
FROM $BASE
COPY --chown=root:root histor/app.py /app/histor/app.py
COPY --chown=root:root docs/landing/ /app/docs/landing/
LABEL aicom.histor.overlay=mongodb-20261103
DOCKERFILE
docker build -q --network none -t "$CANDIDATE" "$WORK"
candidate_id="$(docker image inspect --format '{{.Id}}' "$CANDIDATE")"
for f in "${FILES[@]}"; do
  candidate_hash="$(docker run --rm --network none --entrypoint sha256sum "$CANDIDATE" "/app/$f" | cut -d' ' -f1)"
  [[ "$candidate_hash" == "$(hash_file "$WORK/$f")" ]] || fail "Candidate content mismatch for $f"
done
docker run --rm --entrypoint node "$CANDIDATE" \
  /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden

# The candidate handles real ASGI requests against its own disposable SQLite store.
docker run --rm -i --network none -e HISTOR_PROFILE=dev -e HISTOR_DATABASE_URL= \
  -e HISTOR_PUBLIC_BASE="$PUBLIC" -e HISTOR_DATA_DIR=/tmp/histor-smoke \
  -e HISTOR_PQC=0 -e HISTOR_WITNESS_LOGS= --entrypoint python "$CANDIDATE" - <<'PY'
import asyncio

import httpx

from histor.app import create_app
from histor.config import load_settings
from histor.service import build


async def smoke():
    services = build(load_settings())
    guide = "/mongodb-mcp-read-only-tools.html"
    try:
        transport = httpx.ASGITransport(app=create_app(services))
        async with httpx.AsyncClient(transport=transport, base_url=services.settings.public_base) as client:
            page = await client.get(guide)
            page.raise_for_status()
            assert page.headers["content-type"].startswith("text/html")
            assert 'id="compare-tools"' in page.text
            assert (await client.head(guide)).status_code == 200
            assert guide[1:] in (await client.get("/")).text
            assert f"<loc>{services.settings.public_base}{guide}</loc>" in (await client.get("/sitemap-site.xml")).text
            for path in ("/assets/compare-tool-names.js", "/assets/tool-comparison.css"):
                asset = await client.get(path)
                assert asset.status_code == 200 and asset.content
    finally:
        services.close()


asyncio.run(smoke())
print("Candidate smoke passed for the guide, assets, home link and sitemap")
PY

[[ "$(image_id)" == "$BASE_ID" ]] && verify_binding "$BASE_ID" || fail "Live image changed during build"
install -d -m 0700 /root/histor-backups
BACKUP="$(mktemp -d /root/histor-backups/mongodb-20261103.XXXXXXXX)"
cp -p --parents "$COMPOSE_FILE" "$APP" "$INDEX" "$BACKUP"
if curl -fsS --max-time 4 "$LOCAL/health" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["crawl_running"] else 1)'; then
  WAS_CRAWLING=1
fi
SWITCHED=1
# Mark the transaction before touching Compose so every subsequent error rolls it back.
sed -i -E "s~(^[[:space:]]*image:[[:space:]]*)$BASE([[:space:]]|$)~\1$CANDIDATE\2~" "$COMPOSE_FILE"
grep -Fq "image: $CANDIDATE" "$COMPOSE_FILE" || fail "Compose replacement failed"
"${COMPOSE[@]}" up -d --no-deps --no-build histor
wait_healthy && [[ "$(image_id)" == "$candidate_id" ]] || fail "Candidate failed production health"
curl -fsS --max-time 10 "$LOCAL$GUIDE" > "$WORK/guide.live"
cmp -s "$WORK/guide.live" "$WORK/docs/landing${GUIDE}" || fail "Live guide mismatch"
curl -fsS --max-time 10 "$LOCAL/sitemap-site.xml" | grep -F "<loc>$PUBLIC$GUIDE</loc>" >/dev/null ||
  fail "Live sitemap lacks the guide"
for f in "${NEW_FILES[@]:1}"; do
  asset_path="${f#docs/landing}"
  curl -fsS --max-time 10 "$LOCAL$asset_path" > "$WORK/asset.live"
  cmp -s "$WORK/asset.live" "$WORK/$f" || fail "Live asset mismatch for $asset_path"
done
for f in "${FILES[@]}"; do
  install -m 0644 "$WORK/$f" "$f"
done
"$QUALITY" rebind "$candidate_id"
verify_binding "$candidate_id"
docker image tag "$CANDIDATE" histor:warden-remediation-base
COMPLETED=1
resume_crawl || echo "Interrupted crawl could not be restarted" >&2
echo "Serving $candidate_id; rollout backup $BACKUP"
