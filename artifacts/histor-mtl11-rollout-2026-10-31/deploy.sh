#!/usr/bin/env bash
# One-off (2026-10-31): MTL/1.1 on HISTOR (aicom 8e0763168) as an overlay on the running image: subject.py,
# labels.py, crawler.py, store.py and the desk's desk.js; nothing else. The running image is the security
# rollout's aicom-security:histor-histor-1-python-20261031 (python upgrades); its app equals main except
# app.py/__init__.py (main's fingerprints endpoint and 0.5.2 are someone else's, not deployed) and keeps them.
# No migration, so rollback is the previous image:
#   cp /opt/histor/docker-compose.postgres.yml.pre-mtl11-20261031 /opt/histor/docker-compose.postgres.yml
#   docker compose -p histor --env-file /opt/histor/.env -f docker-compose.yml -f docker-compose.postgres.yml up -d --no-build histor
#   and, if the MOMUS binding was moved below, `skopos-warden-quality rebind <previous id>` (it was on fdb74875531b).
# Labels the new code issued stay in the log: they are valid signed MTL/1.1 labels.
set -euo pipefail
cd /opt/histor
D=/root/mtl11-20261031
NEW=histor-histor:mtl11-20261031
BASE_TAG=histor-histor:pre-mtl11-20261031
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
OLD_LINE='    image: aicom-security:histor-histor-1-python-20261031  # Verified security rollout 2026-10-31'
NEW_LINE='    image: histor-histor:mtl11-20261031  # MTL/1.1 overlay 2026-10-31 FROM aicom-security:histor-histor-1-python-20261031 (rollback: .pre-mtl11-20261031)'

date -u +"start %FT%TZ"
running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
docker image tag "$running" "$BASE_TAG"
echo "base = running image ${running:7:12}"
docker build -q --build-arg BASE="$BASE_TAG" -t "$NEW" "$D"
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D":/ctx:ro --entrypoint python "$NEW" /ctx/smoke.py
docker run --rm --entrypoint node "$NEW" /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden
b="$(docker run --rm --entrypoint sh "$BASE_TAG" -c 'sha256sum /app/scanner/node_modules/@aimarket/warden/dist/*.js | sha256sum')"
n="$(docker run --rm --entrypoint sh "$NEW" -c 'sha256sum /app/scanner/node_modules/@aimarket/warden/dist/*.js | sha256sum')"
[ "$b" = "$n" ] || { echo "WARDEN dist differs between base and new" >&2; exit 1; }
echo "WARDEN dist identical in base and new"

was_crawling=0
curl -sf --max-time 3 http://127.0.0.1:9490/health | grep -q '"crawl_running":true' && was_crawling=1
echo "crawl running before: $was_crawling"
grep -qxF "$OLD_LINE" docker-compose.postgres.yml || { echo "compose image line is not the expected one" >&2; exit 1; }
cp -p docker-compose.postgres.yml docker-compose.postgres.yml.pre-mtl11-20261031
python3 - "$OLD_LINE" "$NEW_LINE" <<'PY'
import sys
p = "/opt/histor/docker-compose.postgres.yml"; s = open(p).read()
assert s.count(sys.argv[1] + "\n") == 1
open(p, "w").write(s.replace(sys.argv[1] + "\n", sys.argv[2] + "\n"))
PY
wait_healthy() {
  for _ in $(seq 1 120); do
    if health="$(curl -sf --max-time 3 http://127.0.0.1:9490/health)"; then return 0; fi
    sleep 2
  done
  return 1
}
"${COMPOSE[@]}" up -d --no-build histor
echo -n "waiting for /health … "
if ! wait_healthy; then
  echo "the new image did not come up:" >&2
  "${COMPOSE[@]}" logs --tail 80 histor >&2 || true
  cp -p docker-compose.postgres.yml.pre-mtl11-20261031 docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
fi
echo "ok"
echo "$health"
now="$(docker inspect --format '{{.Image}}' histor-histor-1)"
[ "$now" = "$(docker image inspect --format '{{.Id}}' "$NEW")" ] || { echo "histor-histor-1 is not on $NEW" >&2; exit 1; }
echo "histor-histor-1 runs ${now:7:12} ($NEW)"
if [[ -x /usr/local/sbin/skopos-warden-quality && -f /var/lib/momus-quality/live-image.json ]]; then
  if /usr/local/sbin/skopos-warden-quality rebind "$now"; then
    docker image tag "$now" histor:warden-remediation-base
    echo "MOMUS quality binding -> ${now:7:12} (WARDEN unchanged, nothing re-measured)"
  else
    echo "WARNING: the MOMUS quality binding stays where it was" >&2
  fi
fi
if [[ "$was_crawling" -eq 1 ]]; then
  token="$(grep '^HISTOR_OPERATOR_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
  curl -sf --max-time 10 -X POST -H "x-histor-operator: ${token}" \
    "http://127.0.0.1:9490/api/v1/admin/crawl?include_remote=true" >/dev/null && echo "restarted the crawl the redeploy interrupted"
  unset token
fi
date -u +"done %FT%TZ"
