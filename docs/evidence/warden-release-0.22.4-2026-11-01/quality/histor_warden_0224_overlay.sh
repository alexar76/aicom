#!/usr/bin/env bash
# One-off (2026-11-02): HISTOR on admin-vps moves to WARDEN 0.22.4 — image wd-20261102 (sha256:914a930a…),
# the running wd-20261101 (WARDEN 0.22.3) with its vendored WARDEN replaced by the npm archive
# (stage-candidate.py in this folder). Only after the MOMUS candidate run passed for that image.
# Then `live` publishes the receipt npm's check:quality reads and moves the MOMUS binding; if `live`
# refuses, HISTOR goes back to wd-20261101.
#
# Rollback (also automatic below):
#   cp /root/histor-backups/docker-compose.postgres.yml-pre-wd-20261102 /opt/histor/docker-compose.postgres.yml
#   cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
#     up -d --no-deps --no-build histor
#   /usr/local/sbin/skopos-warden-quality live sha256:8cc613352e2299e78c94d164cfddeb924e729a3455a9bed012cb29ac26b0502c
#     (re-publishes the 0.22.3 receipt from its still-valid full evaluation; `rebind` cannot cross a build change)
#   docker image tag aicom-security:histor-histor-1-wd-20261101 histor:warden-remediation-base
set -euo pipefail
BASE_REF=aicom-security:histor-histor-1-wd-20261101
NEW=aicom-security:histor-histor-1-wd-20261102
WANT_NEW=sha256:914a930a93343f63a993d38f0d85c0288be0c83d1ca67ed33e3fd4cfae6b1dd9
HOOK=/usr/local/sbin/skopos-warden-quality
cd /opt/histor
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
BK=/root/histor-backups

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
new="$(docker image inspect --format '{{.Id}}' "$NEW")"
[[ "$running" == "$base" ]] || { echo "histor runs ${running:7:12}, not $BASE_REF; stop" >&2; exit 1; }
[[ "$new" == "$WANT_NEW" ]] || { echo "$NEW is ${new:7:12}, not the evaluated image; stop" >&2; exit 1; }
if pgrep -f "[r]ollout_os_candidates|[r]ollout_container" >/dev/null; then echo "an OS rollout is running; stop" >&2; exit 1; fi
"$HOOK" authorize "$new" || { echo "the candidate receipt does not authorize ${new:7:12}; stop" >&2; exit 1; }
echo "candidate receipt authorizes ${new:7:12}"

cp -p docker-compose.postgres.yml "$BK/docker-compose.postgres.yml-pre-wd-20261102"
was_crawling=0
curl -sf --max-time 3 http://127.0.0.1:9490/health | grep -q '"crawl_running":true' && was_crawling=1
wait_healthy() {
  for _ in $(seq 1 150); do
    if health="$(curl -sf --max-time 3 http://127.0.0.1:9490/health)"; then return 0; fi
    sleep 2
  done
  return 1
}
back() {
  echo "$1; going back to $BASE_REF" >&2
  cp -p "$BK/docker-compose.postgres.yml-pre-wd-20261102" docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-deps --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
}
if ! { sed -i "s|image: $BASE_REF |image: $NEW |" docker-compose.postgres.yml && grep -q "image: $NEW " docker-compose.postgres.yml; }; then
  cp -p "$BK/docker-compose.postgres.yml-pre-wd-20261102" docker-compose.postgres.yml
  echo "compose not changed as expected; restored" >&2
  exit 1
fi
"${COMPOSE[@]}" up -d --no-deps --no-build histor
if ! wait_healthy || [[ "$(docker inspect --format '{{.Image}}' histor-histor-1)" != "$new" ]]; then
  "${COMPOSE[@]}" logs --tail 60 histor >&2
  back "the new image did not come up"
fi
echo "ok: $health"
version="$(docker exec histor-histor-1 node /app/scanner/scan.mjs describe | python3 -c 'import json,sys; print(json.load(sys.stdin)["warden"]["version"])')"
[[ "$version" == "0.22.4" ]] || back "the sidecar reports WARDEN $version"
"$HOOK" live "$new" || back "MOMUS live promotion refused"
docker image tag "$new" histor:warden-remediation-base
echo "MOMUS live receipt and binding → ${new:7:12}"

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
