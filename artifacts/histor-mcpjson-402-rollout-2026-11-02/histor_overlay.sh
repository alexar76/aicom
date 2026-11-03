#!/usr/bin/env bash
# One-off (2026-11-02, owner: «Yes, roll it out»): on top of the RUNNING image aicom-security:histor-histor-1-cd-20261102
# (sha256:e3aa16e9…, server cards), keeping its OS patches, baked env and WARDEN build byte for byte:
#   f6bb99cb5  cards at /.well-known/mcp.json, migration 021, the "Outside checks" section of the page;
#   7256435da  a 402 says why (pay-per-crawl / payment-required / http-402 + message), a day's back-off, page and /check.
# Five Python files and eight landing files change; each was checked equal to main before f6bb99cb5 in the running
# container. The service applies migration 021 (an UPDATE of absent/robots card rows) before it listens.
# Run on admin-vps as root with the files of 7256435da and smoke.py in $SRC.
#
# Rollback (also automatic below if /health does not come up). Migration 021 stays: it only made rows due sooner.
#   cp /root/histor-backups/docker-compose.postgres.yml-pre-mj-20261102 /opt/histor/docker-compose.postgres.yml
#   tar -C /opt/histor -xf /root/histor-backups/host-tree-pre-mj-20261102.tar
#   cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
#     up -d --no-deps --no-build histor
#   /usr/local/sbin/skopos-warden-quality rebind sha256:e3aa16e9ecea0228064b8f88125dd56556e810917773845eb78d1a953b235a6b
#   docker image tag aicom-security:histor-histor-1-cd-20261102 histor:warden-remediation-base
set -euo pipefail
SRC=/root/histor-mj-20261102
BASE_REF=aicom-security:histor-histor-1-cd-20261102
WANT_BASE=sha256:e3aa16e9ecea0228064b8f88125dd56556e810917773845eb78d1a953b235a6b
NEW=aicom-security:histor-histor-1-mj-20261102
COMMIT=7256435da
cd /opt/histor
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
BK=/root/histor-backups
mkdir -p "$BK"
PY=(cards.py migrations.py mcpclient.py remote_schedule.py check.py)
LANDING=(index.html assets/histor.css assets/desk.js assets/i18n.js assets/i18n/ru.js assets/i18n/es.js assets/i18n/fr.js assets/i18n/zh.js)
declare -A WAS=(
  [/app/histor/cards.py]=2b97a757a16bfc3b726157a8554b27cdca0ed3a881d4c6e062f3d20209940c48
  [/app/histor/migrations.py]=0892642981b047e6dbd7f59883f7107982827a286912faf30d3d6ca57d7a7dd3
  [/app/histor/mcpclient.py]=074909e4491f07380fb47c6d648b046dbf7bd5c771ba97240b105610421c5d1b
  [/app/histor/remote_schedule.py]=4768c9ba9b6c1c70c421842ba899ca44bfa556e96c0e5464b1470f37d33dfe8f
  [/app/histor/check.py]=5294bdc00e9764fb36b86bd0c967c2ea5e3a12ed05bf31cd6437ee093084bac2
  [/app/docs/landing/index.html]=c5233f2d8ced0cfe8462d0430e0e955ef532573a2096f5f338498b0f7c85d379
  [/app/docs/landing/assets/histor.css]=5704024a5004f21df86ae878722a375eded60e7d6d097398518ec4aab85ce504
  [/app/docs/landing/assets/desk.js]=3f446f97947d96ab660b7bfc0b0032f4aa46e5d7f44bfa0b5f5dbca1e468f8ad
  [/app/docs/landing/assets/i18n.js]=5ac6da780e0cd1655a7d22b615133203b5dac0772a81256dc5965a1edf1d4417
  [/app/docs/landing/assets/i18n/ru.js]=1db1735afaba763bea62bd39f8a5023d5d41b7b840c24f37fa56b095035162b2
  [/app/docs/landing/assets/i18n/es.js]=7a1498f5aecee595abd1c73a5327bac88449b236422da78407c19ed5ce723afe
  [/app/docs/landing/assets/i18n/fr.js]=871e8fa22cc506c273689f9d470d0653a078348ca54a5d7e4ef684760ae103dc
  [/app/docs/landing/assets/i18n/zh.js]=a8c67307479ac51da3ef4e109d4bb2a3e76515a660ca8e260dc02aa7bfd1314e
)

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
[[ "$running" == "$base" && "$base" == "$WANT_BASE" ]] || { echo "histor runs ${running:7:12}, not $BASE_REF; stop" >&2; exit 1; }
for f in "${!WAS[@]}"; do
  [[ "$(docker exec histor-histor-1 sha256sum "$f" | cut -d' ' -f1)" == "${WAS[$f]}" ]] \
    || { echo "the running $f is not main before f6bb99cb5; stop" >&2; exit 1; }
done
for f in "${PY[@]}"; do [[ -s "$SRC/histor/$f" ]] || { echo "missing $SRC/histor/$f" >&2; exit 1; }; done
for f in "${LANDING[@]}"; do [[ -s "$SRC/landing/$f" ]] || { echo "missing $SRC/landing/$f" >&2; exit 1; }; done
[[ -s "$SRC/smoke.py" ]] || { echo "missing smoke.py" >&2; exit 1; }
if pgrep -f "[r]ollout_os_candidates|[r]ollout_container" >/dev/null; then echo "an OS rollout is running; stop" >&2; exit 1; fi
avail_kb="$(df --output=avail / | tail -1)"
(( avail_kb > 1500000 )) || { echo "less than 1.5 GB free on /; stop" >&2; exit 1; }

# Modes in the staging tree: COPY --chmod would also apply to the landing's folders and make them untraversable.
find "$SRC/histor" "$SRC/landing" -type d -exec chmod 0755 {} +
find "$SRC/histor" "$SRC/landing" -type f -exec chmod 0644 {} +
cat > "$SRC/Dockerfile" <<DOCKERFILE
FROM $BASE_REF
COPY --chown=root:root histor/ /app/histor/
COPY --chown=root:root landing/ /app/docs/landing/
LABEL aicom.histor.overlay=mj-20261102 aicom.histor.app.mcpjson=f6bb99cb5 aicom.histor.app.payment402=$COMMIT
DOCKERFILE
docker build -q -f "$SRC/Dockerfile" -t "$NEW" "$SRC"
new="$(docker image inspect --format '{{.Id}}' "$NEW")"
echo "new image ${new:7:12} FROM ${base:7:12}"
for f in "${PY[@]}"; do
  [[ "$(sha256sum "$SRC/histor/$f" | cut -d' ' -f1)" == "$(docker run --rm --entrypoint sha256sum "$NEW" "/app/histor/$f" | cut -d' ' -f1)" ]] \
    || { echo "$f did not land in the image" >&2; exit 1; }
done
for f in "${LANDING[@]}"; do
  [[ "$(sha256sum "$SRC/landing/$f" | cut -d' ' -f1)" == "$(docker run --rm --entrypoint sha256sum "$NEW" "/app/docs/landing/$f" | cut -d' ' -f1)" ]] \
    || { echo "$f did not land readable in the image" >&2; exit 1; }
done
docker run --rm --entrypoint node "$NEW" /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden
docker run --rm --network none -e PYTHONPATH=/app -e HISTOR_PROFILE=dev -v "$SRC/smoke.py:/smoke.py:ro" --entrypoint python "$NEW" /smoke.py

cp -p docker-compose.postgres.yml "$BK/docker-compose.postgres.yml-pre-mj-20261102"
tar -C /opt/histor -cf "$BK/host-tree-pre-mj-20261102.tar" $(printf 'histor/%s ' "${PY[@]}") $(printf 'docs/landing/%s ' "${LANDING[@]}")
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
  cp -p "$BK/docker-compose.postgres.yml-pre-mj-20261102" docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-deps --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
}
if ! { sed -i "s|image: $BASE_REF |image: $NEW |" docker-compose.postgres.yml && grep -q "image: $NEW " docker-compose.postgres.yml; }; then
  cp -p "$BK/docker-compose.postgres.yml-pre-mj-20261102" docker-compose.postgres.yml
  echo "compose not changed as expected; restored" >&2
  exit 1
fi
"${COMPOSE[@]}" up -d --no-deps --no-build histor
if ! wait_healthy || [[ "$(docker inspect --format '{{.Image}}' histor-histor-1)" != "$new" ]]; then
  "${COMPOSE[@]}" logs --tail 60 histor >&2
  back "the new image did not come up"
fi
echo "ok: $health"
for f in "${PY[@]}"; do install -m 0644 "$SRC/histor/$f" "/opt/histor/histor/$f"; done
for f in "${LANDING[@]}"; do install -m 0644 "$SRC/landing/$f" "/opt/histor/docs/landing/$f"; done
if /usr/local/sbin/skopos-warden-quality rebind "$new"; then
  docker image tag "$new" histor:warden-remediation-base
  echo "MOMUS quality binding → ${new:7:12}"
else
  echo "WARNING: the MOMUS quality binding stays where it was" >&2
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
