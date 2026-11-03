#!/usr/bin/env bash
# One-off (2026-10-31): put GET /api/v1/servers/{id}/fingerprints (fd13c806e) on prod HISTOR as an overlay
# on the running image, keeping its MOMUS-measured WARDEN build byte for byte (the 10-26 overlay method).
# Only two files change: histor/app.py (main == prod + the endpoint) and the new histor/fingerprints.py.
# Nothing else from main rides along (main's __version__ 0.5.2 bump stays out). No migration.
# Run on admin-vps as root from the directory that holds this script, app.py and fingerprints.py.
#
# The HISTOR image is pinned by name in docker-compose.postgres.yml (not :latest), so the script rewrites
# that line; the previous file stays as docker-compose.postgres.yml.pre-fingerprints-20261031.
# Rollback (also automatic below if /health does not come up), no database step needed:
#   cp docker-compose.postgres.yml.pre-fingerprints-20261031 docker-compose.postgres.yml && <compose> up -d --no-build histor
#   then rebind MOMUS to the old image and tag it histor:warden-remediation-base.
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"
cd /opt/histor
BASE=histor-histor:pre-fingerprints-20261031
NEW=histor-histor:fingerprints-20261031
COMMIT=fd13c806e
EXPECT_RUNNING=histor-histor:mtl11-20261031
PINNED=docker-compose.postgres.yml
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
grep -q "image: $EXPECT_RUNNING " "$PINNED" || { echo "$PINNED does not pin $EXPECT_RUNNING" >&2; exit 1; }
[[ "$(docker inspect --format '{{.Config.Image}}' histor-histor-1)" == "$EXPECT_RUNNING" ]] \
  || { echo "histor-histor-1 no longer runs $EXPECT_RUNNING; re-check the diff before overlaying" >&2; exit 1; }
# The running app.py must be exactly what the overlay's app.py was diffed against.
docker exec histor-histor-1 sha256sum /app/histor/app.py | cut -d' ' -f1 | grep -qx "$(cut -d' ' -f1 "$KIT/prod-app.sha256")" \
  || { echo "prod app.py changed since the diff" >&2; exit 1; }
docker image tag "$running" "$BASE"
echo "base = running image ${running:7:12}"

cat > "$KIT/Dockerfile" <<EOF
FROM $BASE
COPY --chown=root:root app.py fingerprints.py /app/histor/
LABEL aicom.histor.app.overlay=$COMMIT
EOF
docker build -q -f "$KIT/Dockerfile" -t "$NEW" "$KIT"
docker run --rm --entrypoint node "$NEW" /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden
docker run --rm --entrypoint python "$NEW" -c \
  "import histor.app, histor.crawler, histor.dataset; from histor import fingerprints; assert fingerprints.FORMATS == ('vercel-ai', 'heldfast', 'agentavow-v1'); print('app imports; fingerprints', fingerprints.FORMATS)"
echo -n "WARDEN dist files in base / new: "
docker run --rm --entrypoint sh "$BASE" -c 'ls /app/scanner/node_modules/@aimarket/warden/dist/*.js | wc -l' | tr '\n' ' '
docker run --rm --entrypoint sh "$NEW" -c 'ls /app/scanner/node_modules/@aimarket/warden/dist/*.js | wc -l'

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

[[ -f "$PINNED.pre-fingerprints-20261031" ]] || cp -p "$PINNED" "$PINNED.pre-fingerprints-20261031"
sed -i "s|image: $EXPECT_RUNNING .*|image: $NEW  # fingerprints endpoint overlay 2026-10-31 FROM $EXPECT_RUNNING (rollback: .pre-fingerprints-20261031)|" "$PINNED"
grep -q "image: $NEW " "$PINNED"
"${COMPOSE[@]}" up -d --no-build histor
echo -n "waiting for /health … "
if ! wait_healthy; then
  echo "the new image did not come up:" >&2
  "${COMPOSE[@]}" logs --tail 80 histor >&2
  cp -p "$PINNED.pre-fingerprints-20261031" "$PINNED"
  "${COMPOSE[@]}" up -d --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
fi
echo "ok"
[[ "$(docker inspect --format '{{.Config.Image}}' histor-histor-1)" == "$NEW" ]] || { echo "container not recreated on $NEW" >&2; exit 1; }
echo "$health" | grep -q '"service":"histor"' && echo "$health" | grep -q '"store":"postgresql"' || { echo "unexpected: $health" >&2; exit 1; }

if [[ -x /usr/local/sbin/skopos-warden-quality && -f /var/lib/momus-quality/live-image.json ]]; then
  image="$(docker inspect --format '{{.Image}}' histor-histor-1)"
  if /usr/local/sbin/skopos-warden-quality rebind "$image"; then
    docker image tag "$image" histor:warden-remediation-base
    echo "MOMUS quality binding → ${image:7:12} (WARDEN unchanged, nothing re-measured)"
  else
    echo "WARNING: the MOMUS quality binding stays on the previous image" >&2
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
