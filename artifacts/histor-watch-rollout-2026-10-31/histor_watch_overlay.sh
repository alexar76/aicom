#!/usr/bin/env bash
# One-off (2026-10-31): deploy c7d273575 (HISTOR Watch: /api/v1/changes?after=&watch= with nextCursor, webhook
# source "changes", webhook delivery pinned to a checked public address) on top of the RUNNING image
# aicom-security:histor-histor-1-os-20261031 (sha256:e76bc016…), keeping its OS patches and its WARDEN build
# byte for byte. Only four files change: histor/{__main__,app,security_events,store}.py, checked equal to
# c7d273575^ in the running container before this was written. No schema migration.
# Run on admin-vps as root with the four files from `git show c7d273575:histor/histor/<f>` in $SRC.
#
# Rollback (also automatic below if /health does not come up):
#   cp /root/histor-backups/docker-compose.postgres.yml-pre-watch-20261031 /opt/histor/docker-compose.postgres.yml
#   cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
#     up -d --no-deps --no-build histor
#   then: skopos-warden-quality rebind <old image digest> if the binding had moved.
set -euo pipefail
SRC=/root/histor-watch-20261031
BASE_REF=aicom-security:histor-histor-1-os-20261031
NEW=aicom-security:histor-histor-1-watch-20261031
COMMIT=c7d273575
FILES=(__main__.py app.py security_events.py store.py)
cd /opt/histor
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
BK=/root/histor-backups
mkdir -p "$BK"

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
[[ "$running" == "$base" ]] || { echo "histor runs ${running:7:12}, not $BASE_REF (${base:7:12}); stop" >&2; exit 1; }
for f in "${FILES[@]}"; do [[ -s "$SRC/$f" ]] || { echo "missing $SRC/$f" >&2; exit 1; }; done

cat > "$SRC/Dockerfile" <<EOF
FROM $BASE_REF
COPY --chown=root:root __main__.py app.py security_events.py store.py /app/histor/
LABEL aicom.histor.overlay=watch-20261031 aicom.histor.app.watch=$COMMIT
EOF
docker build -q -f "$SRC/Dockerfile" -t "$NEW" "$SRC"
new="$(docker image inspect --format '{{.Id}}' "$NEW")"
echo "new image ${new:7:12} FROM ${base:7:12}"
docker run --rm --entrypoint node "$NEW" /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden
docker run --rm --entrypoint python "$NEW" -c \
  "import histor.app, histor.security_events as s, histor.store, histor.__main__; assert 'changes' in s.SOURCES; print('imports ok; webhook sources', s.SOURCES)"
for f in "${FILES[@]}"; do
  a="$(sha256sum "$SRC/$f" | cut -d' ' -f1)"; b="$(docker run --rm --entrypoint sha256sum "$NEW" "/app/histor/$f" | cut -d' ' -f1)"
  [[ "$a" == "$b" ]] || { echo "$f did not land in the image" >&2; exit 1; }
done

cp -p docker-compose.postgres.yml "$BK/docker-compose.postgres.yml-pre-watch-20261031"
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
  cp -p "$BK/docker-compose.postgres.yml-pre-watch-20261031" docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-deps --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
fi
echo "ok: $health"
echo "$health" | grep -q '"service":"histor"' && echo "$health" | grep -q '"store":"postgresql"' || { echo "unexpected: $health" >&2; exit 1; }

# The host tree is what later overlays copy from: keep it in step so a rebuild from it does not drop this.
for f in "${FILES[@]}"; do
  [[ -f "/opt/histor/histor/$f" ]] && cp -p "/opt/histor/histor/$f" "$BK/$f-pre-watch-20261031"
  install -m 0644 "$SRC/$f" "/opt/histor/histor/$f"
done

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
