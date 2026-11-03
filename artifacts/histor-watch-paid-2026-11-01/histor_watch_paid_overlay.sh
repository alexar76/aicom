#!/usr/bin/env bash
# One-off (2026-11-01): deploy 36e226bd8 (HISTOR Watch for teams: /watch, /api/v1/watch/*, migration 018) in DEMO
# mode on top of the RUNNING image aicom-security:histor-histor-1-hs-20261101 (sha256:503fc8da…), keeping its OS
# patches, baked env, WARDEN build and the handshake fallback byte for byte. Files that change were checked in the
# running container against git first: config/migrations/security_events/service.py and the landing equal
# e3fa5b7e9 (main before this); app.py equals 44c04848a^, so the 2^63 cursor fix (44c04848a) ships with it.
# watch_paid.py is new. Compose gains HISTOR_WATCH_DEMO: "1" (plan and price shown, card payment closed).
# The service applies migration 018 (two new tables, nothing else touched) before it listens.
# Run on admin-vps as root with the files of 36e226bd8 and smoke.py in $SRC (layout below).
#
# Rollback (also automatic below if /health does not come up). Migration 018 stays: two unused tables are harmless
# to the old image, which never reads them.
#   cp /root/histor-backups/docker-compose.postgres.yml-pre-wp-20261101 /opt/histor/docker-compose.postgres.yml
#   tar -C /opt/histor -xf /root/histor-backups/host-tree-pre-wp-20261101.tar
#   cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
#     up -d --no-deps --no-build histor
#   /usr/local/sbin/skopos-warden-quality rebind sha256:503fc8da820c401a354084d6ded0edf1dec95615221c19f751b6a55207af30a1
set -euo pipefail
SRC=/root/histor-watch-paid-20261101
BASE_REF=aicom-security:histor-histor-1-hs-20261101
NEW=aicom-security:histor-histor-1-wp-20261101
COMMIT=36e226bd8
cd /opt/histor
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
BK=/root/histor-backups
mkdir -p "$BK"
PY=(app.py config.py migrations.py security_events.py service.py watch_paid.py)
LANDING=(index.html assets/desk.js assets/i18n.js assets/i18n/ru.js assets/i18n/es.js assets/i18n/fr.js assets/i18n/zh.js)
declare -A WAS=(
  [/app/histor/app.py]=c5d9d7fd096bc68408d09e6f01ad5d9b6d3214f7be52469eb3afee4fe79b99e1
  [/app/histor/config.py]=df70b4c1ff1c0f30efadd000b9f5294f98787dd77024bdb697052df46a973353
  [/app/histor/migrations.py]=99b59e6a596710593198c8f7c1a0416d1db2bae87d76cab39f711d864aa55614
  [/app/histor/security_events.py]=0dbd5b9dfc11e2970452074c4d9a9138ef3e45e82dab4e03cd69e815b67451ea
  [/app/histor/service.py]=377517539628a87e4caed02f34f381b213527e282b6029e9a40279679a5f2400
  [/app/docs/landing/index.html]=549c771e111ddb2436ef8c066559625f78b0b7b9928e0ae3b28e3a02d21504b6
  [/app/docs/landing/assets/desk.js]=7e6eb644dcf4e2e3a02fef52bf712832e750b72e815899f7528e31a05573781a
  [/app/docs/landing/assets/i18n.js]=3acdedb3f82dfc408ec41493ca8da3f15938387d96a81d98bb3a83010cf9e828
  [/app/docs/landing/assets/i18n/ru.js]=dd853dc5efb136ce68fb1ad7734216f0615dd732b3016ae1be671b7506f63b4f
  [/app/docs/landing/assets/i18n/es.js]=22ddd69cc0f842bc17abab8a28a3c81869e1b6bea80136b08badab2f3b2c1a9d
  [/app/docs/landing/assets/i18n/fr.js]=fc5d090ae0eedb5ada2a2a5caf552e4423d637061aba3badc9db009fdcdff186
  [/app/docs/landing/assets/i18n/zh.js]=82d75f9fa763f39fcee9032d38ccd2628a22d56eb43b28ab5f8db12948beffb5
)

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
[[ "$running" == "$base" ]] || { echo "histor runs ${running:7:12}, not $BASE_REF (${base:7:12}); stop" >&2; exit 1; }
for f in "${!WAS[@]}"; do
  [[ "$(docker exec histor-histor-1 sha256sum "$f" | cut -d' ' -f1)" == "${WAS[$f]}" ]] \
    || { echo "the running $f is not what this overlay was checked against; stop" >&2; exit 1; }
done
docker exec histor-histor-1 test ! -e /app/histor/watch_paid.py || { echo "watch_paid.py already in the image; stop" >&2; exit 1; }
for f in "${PY[@]}"; do [[ -s "$SRC/histor/$f" ]] || { echo "missing $SRC/histor/$f" >&2; exit 1; }; done
for f in "${LANDING[@]}"; do [[ -s "$SRC/landing/$f" ]] || { echo "missing $SRC/landing/$f" >&2; exit 1; }; done
[[ -s "$SRC/smoke.py" ]] || { echo "missing smoke.py" >&2; exit 1; }
if pgrep -f "[r]ollout_os_candidates|[r]ollout_container" >/dev/null; then echo "an OS rollout is running; stop" >&2; exit 1; fi
[[ "$(grep -c '^      HISTOR_PROFILE: prod$' docker-compose.postgres.yml)" == 1 ]] || { echo "compose env line not unique; stop" >&2; exit 1; }
grep -q HISTOR_WATCH_DEMO docker-compose.postgres.yml && { echo "compose already sets HISTOR_WATCH_DEMO; stop" >&2; exit 1; }

# The landing has folders: --chmod=0644 would apply to assets/ and assets/i18n/ too and make them untraversable
# for the service user (uid 10001), so its modes are set here and COPY keeps them.
find "$SRC/landing" -type d -exec chmod 0755 {} +
find "$SRC/landing" -type f -exec chmod 0644 {} +
cat > "$SRC/Dockerfile" <<EOF
FROM $BASE_REF
COPY --chown=root:root --chmod=0644 histor/ /app/histor/
COPY --chown=root:root landing/ /app/docs/landing/
LABEL aicom.histor.overlay=wp-20261101 aicom.histor.app.watch_paid=$COMMIT
EOF
docker build -q -f "$SRC/Dockerfile" -t "$NEW" "$SRC"
new="$(docker image inspect --format '{{.Id}}' "$NEW")"
echo "new image ${new:7:12} FROM ${base:7:12}"
for f in "${PY[@]}"; do
  [[ "$(sha256sum "$SRC/histor/$f" | cut -d' ' -f1)" == "$(docker run --rm --entrypoint sha256sum "$NEW" "/app/histor/$f" | cut -d' ' -f1)" ]] \
    || { echo "$f did not land in the image" >&2; exit 1; }
done
for f in "${LANDING[@]}"; do
  [[ "$(sha256sum "$SRC/landing/$f" | cut -d' ' -f1)" == "$(docker run --rm --entrypoint sha256sum "$NEW" "/app/docs/landing/$f" | cut -d' ' -f1)" ]] \
    || { echo "$f did not land in the image" >&2; exit 1; }
done
[[ "$(docker run --rm --entrypoint sha256sum "$NEW" /app/histor/mcpclient.py | cut -d' ' -f1)" == "$(docker exec histor-histor-1 sha256sum /app/histor/mcpclient.py | cut -d' ' -f1)" ]] \
  || { echo "the handshake fallback did not survive; stop" >&2; exit 1; }
docker run --rm --entrypoint node "$NEW" /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden
docker run --rm -i --entrypoint python -e PYTHONPATH=/app -e HISTOR_PROFILE=dev -e HISTOR_WATCH_DEMO=1 -w /app "$NEW" - < "$SRC/smoke.py"

cp -p docker-compose.postgres.yml "$BK/docker-compose.postgres.yml-pre-wp-20261101"
tar -C /opt/histor -cf "$BK/host-tree-pre-wp-20261101.tar" histor/app.py histor/config.py histor/migrations.py \
  histor/security_events.py histor/service.py docs/landing
was_crawling=0
curl -sf --max-time 3 http://127.0.0.1:9490/health | grep -q '"crawl_running":true' && was_crawling=1
echo "crawl running before: $was_crawling"

wait_healthy() {
  for _ in $(seq 1 150); do
    if health="$(curl -sf --max-time 3 http://127.0.0.1:9490/health)"; then return 0; fi
    sleep 2
  done
  return 1
}

# Both edits or neither: on any failure the compose file goes back to the backup before the script stops.
# (Attempt 2 stopped between them, with the image line changed and nothing restarted; it was restored by hand.)
if ! { sed -i "s|image: $BASE_REF |image: $NEW |" docker-compose.postgres.yml \
       && sed -i 's|^      HISTOR_PROFILE: prod$|      HISTOR_PROFILE: prod\n      HISTOR_WATCH_DEMO: "1"   # HISTOR Watch for teams: plan shown, card payment closed (2026-11-01)|' docker-compose.postgres.yml \
       && grep -q "image: $NEW " docker-compose.postgres.yml && grep -q 'HISTOR_WATCH_DEMO: "1"' docker-compose.postgres.yml; }; then
  echo "compose not changed as expected; restored" >&2
  cp -p "$BK/docker-compose.postgres.yml-pre-wp-20261101" docker-compose.postgres.yml
  exit 1
fi
"${COMPOSE[@]}" up -d --no-deps --no-build histor
echo -n "waiting for /health … "
if ! wait_healthy || [[ "$(docker inspect --format '{{.Image}}' histor-histor-1)" != "$new" ]]; then
  echo "the new image did not come up:" >&2
  "${COMPOSE[@]}" logs --tail 80 histor >&2
  cp -p "$BK/docker-compose.postgres.yml-pre-wp-20261101" docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-deps --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
fi
echo "ok: $health"
echo "$health" | grep -q '"service":"histor"' && echo "$health" | grep -q '"store":"postgresql"' || { echo "unexpected: $health" >&2; exit 1; }
plan="$(curl -sf --max-time 5 http://127.0.0.1:9490/api/v1/watch/plan)"
echo "plan: $plan"
echo "$plan" | grep -q '"demo":true' && echo "$plan" | grep -q '"enabled":false' || { echo "the plan is not in demo" >&2; exit 1; }

# The host tree is what later overlays copy from: keep it in step so a rebuild from it does not drop this.
for f in "${PY[@]}"; do install -m 0644 "$SRC/histor/$f" "/opt/histor/histor/$f"; done
for f in "${LANDING[@]}"; do install -D -m 0644 "$SRC/landing/$f" "/opt/histor/docs/landing/$f"; done

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
