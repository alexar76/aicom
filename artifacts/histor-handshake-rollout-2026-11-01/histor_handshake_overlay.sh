#!/usr/bin/env bash
# One-off (2026-11-01): deploy 2cf275902 (HISTOR falls back to initialize when a server refuses the 2026-07-28
# server/discover the way a legacy server does) on top of the RUNNING image
# aicom-security:histor-histor-1-hc-live-20261031 (sha256:86ebc012…), keeping its OS patches, its baked env and its
# WARDEN build byte for byte. One file changes: histor/mcpclient.py, checked equal to 2cf275902^ (46abbd51efe7) in
# the running container and the host tree before this was written. No schema migration, __init__ stays 0.5.1.
# Run on admin-vps as root with mcpclient.py (git show 2cf275902:histor/histor/mcpclient.py) and smoke.py in $SRC.
#
# Rollback (also automatic below if /health does not come up):
#   cp /root/histor-backups/docker-compose.postgres.yml-pre-hs-20261101 /opt/histor/docker-compose.postgres.yml
#   install -m 0644 /root/histor-backups/mcpclient.py-pre-hs-20261101 /opt/histor/histor/mcpclient.py
#   cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
#     up -d --no-deps --no-build histor
#   /usr/local/sbin/skopos-warden-quality rebind sha256:86ebc012406364d4a57d48259d34125436a843881ec4653aa294f577a9a4d670
set -euo pipefail
SRC=/root/histor-handshake-20261101
BASE_REF=aicom-security:histor-histor-1-hc-live-20261031
NEW=aicom-security:histor-histor-1-hs-20261101
COMMIT=2cf275902
OLD_SHA=46abbd51efe7bd2f8a0bd9504b1f8709e562b87b6796e36a1eedabe8d543a9c7
cd /opt/histor
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
BK=/root/histor-backups
mkdir -p "$BK"

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
[[ "$running" == "$base" ]] || { echo "histor runs ${running:7:12}, not $BASE_REF (${base:7:12}); stop" >&2; exit 1; }
[[ "$(docker exec histor-histor-1 sha256sum /app/histor/mcpclient.py | cut -d' ' -f1)" == "$OLD_SHA" ]] \
  || { echo "the running mcpclient.py is not 2cf275902^; stop" >&2; exit 1; }
[[ -s "$SRC/mcpclient.py" && -s "$SRC/smoke.py" ]] || { echo "missing files in $SRC" >&2; exit 1; }
if pgrep -f "[r]ollout_os_candidates|[r]ollout_container" >/dev/null; then echo "an OS rollout is running; stop" >&2; exit 1; fi

cat > "$SRC/Dockerfile" <<EOF
FROM $BASE_REF
COPY --chown=root:root mcpclient.py /app/histor/
LABEL aicom.histor.overlay=hs-20261101 aicom.histor.app.mcpclient=$COMMIT
EOF
docker build -q -f "$SRC/Dockerfile" -t "$NEW" "$SRC"
new="$(docker image inspect --format '{{.Id}}' "$NEW")"
echo "new image ${new:7:12} FROM ${base:7:12}"
a="$(sha256sum "$SRC/mcpclient.py" | cut -d' ' -f1)"
b="$(docker run --rm --entrypoint sha256sum "$NEW" /app/histor/mcpclient.py | cut -d' ' -f1)"
[[ "$a" == "$b" ]] || { echo "mcpclient.py did not land in the image" >&2; exit 1; }
docker run --rm --entrypoint node "$NEW" /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden
docker run --rm -i --entrypoint python -e PYTHONPATH=/app -w /app "$NEW" - < "$SRC/smoke.py"
docker run --rm --entrypoint python "$NEW" -c "import histor.app, histor.crawler, histor.__main__; print('imports ok')"

cp -p docker-compose.postgres.yml "$BK/docker-compose.postgres.yml-pre-hs-20261101"
cp -p /opt/histor/histor/mcpclient.py "$BK/mcpclient.py-pre-hs-20261101"
was_crawling=0
curl -sf --max-time 3 http://127.0.0.1:9490/health | grep -q '"crawl_running":true' && was_crawling=1
echo "crawl running before: $was_crawling"

wait_healthy() {
  for _ in $(seq 1 120); do
    if health="$(curl -sf --max-time 3 http://127.0.0.1:9490/health)"; then return 0; fi
    sleep 2
  done
  return 1
}

sed -i "s#image: $BASE_REF #image: $NEW #" docker-compose.postgres.yml
grep -q "image: $NEW " docker-compose.postgres.yml || { echo "compose image line not changed" >&2; exit 1; }
"${COMPOSE[@]}" up -d --no-deps --no-build histor
echo -n "waiting for /health … "
if ! wait_healthy || [[ "$(docker inspect --format '{{.Image}}' histor-histor-1)" != "$new" ]]; then
  echo "the new image did not come up:" >&2
  "${COMPOSE[@]}" logs --tail 80 histor >&2
  cp -p "$BK/docker-compose.postgres.yml-pre-hs-20261101" docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-deps --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
fi
echo "ok: $health"
echo "$health" | grep -q '"service":"histor"' && echo "$health" | grep -q '"store":"postgresql"' || { echo "unexpected: $health" >&2; exit 1; }

# The host tree is what later overlays copy from: keep it in step so a rebuild from it does not drop this.
install -m 0644 "$SRC/mcpclient.py" /opt/histor/histor/mcpclient.py

if [[ -x /usr/local/sbin/skopos-warden-quality && -f /var/lib/momus-quality/live-image.json ]]; then
  if /usr/local/sbin/skopos-warden-quality rebind "$new"; then
    docker image tag "$new" histor:warden-remediation-base
    echo "MOMUS quality binding → ${new:7:12} (WARDEN unchanged, nothing re-measured)"
  else
    echo "WARNING: the MOMUS quality binding stays where it was" >&2
  fi
fi

if [[ "$was_crawling" -eq 1 ]]; then
  include_remote=true
  if "${COMPOSE[@]}" exec -T histor python -c \
    'import sys; from histor.config import load_settings; sys.exit(0 if load_settings().remote_interval_s > 0 else 1)'; then
    include_remote=false
  fi
  token="$(grep '^HISTOR_OPERATOR_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
  curl -sf --max-time 10 -X POST -H "x-histor-operator: ${token}" \
    "http://127.0.0.1:9490/api/v1/admin/crawl?include_remote=${include_remote}" >/dev/null \
    && echo "restarted the crawl the redeploy interrupted"
  unset token
fi
