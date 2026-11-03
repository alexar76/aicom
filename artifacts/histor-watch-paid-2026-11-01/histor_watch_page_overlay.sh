#!/usr/bin/env bash
# One-off (2026-11-01): the /watch page fixes of 2dbd3e9a1 (endpoint field styled like the site's inputs; a disabled
# button looks disabled) on top of the RUNNING aicom-security:histor-histor-1-wp-20261101 (sha256:d834b00d…).
# Two static files change; both were checked equal to 36e226bd8 in the running container first. Nothing else moves.
# Run on admin-vps as root with desk.js and histor.css of 2dbd3e9a1 in $SRC.
#
# Rollback (also automatic below if /health does not come up):
#   cp /root/histor-backups/docker-compose.postgres.yml-pre-wpp-20261101 /opt/histor/docker-compose.postgres.yml
#   tar -C /opt/histor -xf /root/histor-backups/host-landing-pre-wpp-20261101.tar
#   cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
#     up -d --no-deps --no-build histor
#   /usr/local/sbin/skopos-warden-quality rebind sha256:d834b00de443aaec72ebb09654ec5dcee78091831be74e42a4f6037ba0a30baa
set -euo pipefail
SRC=/root/histor-watch-page-20261101
BASE_REF=aicom-security:histor-histor-1-wp-20261101
NEW=aicom-security:histor-histor-1-wpp-20261101
cd /opt/histor
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
BK=/root/histor-backups
declare -A WAS=(
  [desk.js]=17f11d97bc607f13e676320b7fcad61f6593ad0ceac820a54f52ec8a6daaf1d4
  [histor.css]=0e779f94cd0865a4ebdea77366bfefe0911ba296172691af4c2f2360a5d9991f
)

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
[[ "$running" == "$base" ]] || { echo "histor runs ${running:7:12}, not $BASE_REF; stop" >&2; exit 1; }
for f in "${!WAS[@]}"; do
  [[ "$(docker exec histor-histor-1 sha256sum "/app/docs/landing/assets/$f" | cut -d' ' -f1)" == "${WAS[$f]}" ]] \
    || { echo "the running $f is not 36e226bd8's; stop" >&2; exit 1; }
  [[ -s "$SRC/assets/$f" ]] || { echo "missing $SRC/assets/$f" >&2; exit 1; }
done
if pgrep -f "[r]ollout_os_candidates|[r]ollout_container" >/dev/null; then echo "an OS rollout is running; stop" >&2; exit 1; fi

find "$SRC/assets" -type d -exec chmod 0755 {} +
find "$SRC/assets" -type f -exec chmod 0644 {} +
cat > "$SRC/Dockerfile" <<EOF
FROM $BASE_REF
COPY --chown=root:root assets/ /app/docs/landing/assets/
LABEL aicom.histor.overlay=wpp-20261101
EOF
docker build -q -f "$SRC/Dockerfile" -t "$NEW" "$SRC"
new="$(docker image inspect --format '{{.Id}}' "$NEW")"
echo "new image ${new:7:12} FROM ${base:7:12}"
for f in "${!WAS[@]}"; do
  [[ "$(sha256sum "$SRC/assets/$f" | cut -d' ' -f1)" == "$(docker run --rm --entrypoint sha256sum "$NEW" "/app/docs/landing/assets/$f" | cut -d' ' -f1)" ]] \
    || { echo "$f did not land readable in the image" >&2; exit 1; }
done
docker run --rm --entrypoint node "$NEW" /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden

cp -p docker-compose.postgres.yml "$BK/docker-compose.postgres.yml-pre-wpp-20261101"
tar -C /opt/histor -cf "$BK/host-landing-pre-wpp-20261101.tar" docs/landing/assets/desk.js docs/landing/assets/histor.css
was_crawling=0
curl -sf --max-time 3 http://127.0.0.1:9490/health | grep -q '"crawl_running":true' && was_crawling=1
wait_healthy() {
  for _ in $(seq 1 150); do
    if health="$(curl -sf --max-time 3 http://127.0.0.1:9490/health)"; then return 0; fi
    sleep 2
  done
  return 1
}
if ! { sed -i "s|image: $BASE_REF |image: $NEW |" docker-compose.postgres.yml && grep -q "image: $NEW " docker-compose.postgres.yml; }; then
  echo "compose not changed as expected; restored" >&2
  cp -p "$BK/docker-compose.postgres.yml-pre-wpp-20261101" docker-compose.postgres.yml
  exit 1
fi
"${COMPOSE[@]}" up -d --no-deps --no-build histor
if ! wait_healthy || [[ "$(docker inspect --format '{{.Image}}' histor-histor-1)" != "$new" ]]; then
  echo "the new image did not come up:" >&2
  "${COMPOSE[@]}" logs --tail 60 histor >&2
  cp -p "$BK/docker-compose.postgres.yml-pre-wpp-20261101" docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-deps --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
fi
echo "ok: $health"
for f in "${!WAS[@]}"; do install -m 0644 "$SRC/assets/$f" "/opt/histor/docs/landing/assets/$f"; done
if [[ -x /usr/local/sbin/skopos-warden-quality && -f /var/lib/momus-quality/live-image.json ]]; then
  if /usr/local/sbin/skopos-warden-quality rebind "$new"; then
    docker image tag "$new" histor:warden-remediation-base
    echo "MOMUS quality binding → ${new:7:12}"
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
