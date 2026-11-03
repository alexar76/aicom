#!/usr/bin/env bash
# One-off (2026-11-02): HISTOR reads MCP server cards as declarations, commit 706b71bb7, on top of the RUNNING image
# aicom-security:histor-histor-1-rb-20261102 (sha256:d2f3b3dc…, robots.txt support), keeping its OS
# patches, baked env and WARDEN build byte for byte. Seven Python files change and cards.py is new; the landing
# (card line on the server page) changes in six files. Each replaced file was checked equal to main before
# 706b71bb7 in the running container. The service applies migration 020 (one new table) before it listens.
# Run on admin-vps as root with the files of 706b71bb7 and smoke.py in $SRC.
#
# Rollback (also automatic below if /health does not come up). Migration 020 stays: an unused table is harmless.
#   cp /root/histor-backups/docker-compose.postgres.yml-pre-cd-20261102 /opt/histor/docker-compose.postgres.yml
#   tar -C /opt/histor -xf /root/histor-backups/host-tree-pre-cd-20261102.tar
#   cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
#     up -d --no-deps --no-build histor
#   /usr/local/sbin/skopos-warden-quality rebind sha256:d2f3b3dcea1e9f8f5de1006b05c2925adc2b8f28ca91eef71967412832270e88
#   docker image tag aicom-security:histor-histor-1-rb-20261102 histor:warden-remediation-base
set -euo pipefail
SRC=/root/histor-cards-20261102
BASE_REF=aicom-security:histor-histor-1-rb-20261102
WANT_BASE=sha256:d2f3b3dcea1e9f8f5de1006b05c2925adc2b8f28ca91eef71967412832270e88
NEW=aicom-security:histor-histor-1-cd-20261102
COMMIT=706b71bb7
cd /opt/histor
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
BK=/root/histor-backups
mkdir -p "$BK"
PY=(cards.py crawler.py store.py migrations.py check.py app.py service.py declared.py)
LANDING=(assets/desk.js assets/i18n.js assets/i18n/ru.js assets/i18n/es.js assets/i18n/fr.js assets/i18n/zh.js)
declare -A WAS=(
  [/app/histor/crawler.py]=874dd90bfc21da042dd322ef83fab11e4151501501eac69ca15db976abe11b9c
  [/app/histor/store.py]=44d332b5711f3c40986bca955030aa94cebf6b6cb91a692d93a98c3949cb43a0
  [/app/histor/migrations.py]=73afa11aa0d8bd5e3960cb0c19b7d1972ff42ed1496733e9909e9dd439948fe2
  [/app/histor/check.py]=3e669012bc8d3f1f101ffe135c264b760c4bbc03fe4349f427e3f322af62c98e
  [/app/histor/app.py]=d5065a6abc8f8dca4e33e388601dfbf495800d7da435f917615aa9fc18273ed8
  [/app/histor/service.py]=c838f3cefb11085d20cc46d32f41a0dfb1a793226da003e92293e2c1d2115cb3
  [/app/histor/declared.py]=82633a07f4825b8921ffb586a41018749958116c39084b77dd6aa64b84a5ba7e
  [/app/docs/landing/assets/desk.js]=931ca3466e6adf561f39848c91d827e0cedcf95ca9fb3352f3cbb44267def445
  [/app/docs/landing/assets/i18n.js]=16270d4ddf8bbe2e4035c6725d34438d19171cd25d0be643a4a6563d51990068
  [/app/docs/landing/assets/i18n/ru.js]=b851b376f9004e8ad8f5f8a778788280d24ac4ded74fd2e88b1d6bec49ad8cb2
  [/app/docs/landing/assets/i18n/es.js]=adb1c7109b1de6c13270a3786206fc7e6673633f382fd2c2a6bdf3c42517e825
  [/app/docs/landing/assets/i18n/fr.js]=e847d01efbadf4d2095650f3e8f7f6c1de64a4bffa7b95d4c03ff277a1b3de06
  [/app/docs/landing/assets/i18n/zh.js]=35b5939c5462a06252ff182a1cc034685406a977130a48d4b9720cf38dead0af
)

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
[[ "$running" == "$base" && "$base" == "$WANT_BASE" ]] || { echo "histor runs ${running:7:12}, not $BASE_REF; stop" >&2; exit 1; }
for f in "${!WAS[@]}"; do
  [[ "$(docker exec histor-histor-1 sha256sum "$f" | cut -d' ' -f1)" == "${WAS[$f]}" ]] \
    || { echo "the running $f is not main before $COMMIT; stop" >&2; exit 1; }
done
docker exec histor-histor-1 test ! -e /app/histor/cards.py || { echo "cards.py already in the image; stop" >&2; exit 1; }
for f in "${PY[@]}"; do [[ -s "$SRC/histor/$f" ]] || { echo "missing $SRC/histor/$f" >&2; exit 1; }; done
for f in "${LANDING[@]}"; do [[ -s "$SRC/landing/$f" ]] || { echo "missing $SRC/landing/$f" >&2; exit 1; }; done
[[ -s "$SRC/smoke.py" ]] || { echo "missing smoke.py" >&2; exit 1; }
if pgrep -f "[r]ollout_os_candidates|[r]ollout_container" >/dev/null; then echo "an OS rollout is running; stop" >&2; exit 1; fi

# Modes in the staging tree: COPY --chmod would also apply to the landing's folders and make them untraversable.
find "$SRC/histor" "$SRC/landing" -type d -exec chmod 0755 {} +
find "$SRC/histor" "$SRC/landing" -type f -exec chmod 0644 {} +
cat > "$SRC/Dockerfile" <<EOF
FROM $BASE_REF
COPY --chown=root:root histor/ /app/histor/
COPY --chown=root:root landing/ /app/docs/landing/
LABEL aicom.histor.overlay=cd-20261102 aicom.histor.app.cards=$COMMIT
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
    || { echo "$f did not land readable in the image" >&2; exit 1; }
done
docker run --rm --entrypoint node "$NEW" /app/scanner/quality/check-quality-gate.mjs /app/scanner/node_modules/@aimarket/warden
docker run --rm --network none -e PYTHONPATH=/app -e HISTOR_PROFILE=dev -v "$SRC/smoke.py:/smoke.py:ro" --entrypoint python "$NEW" /smoke.py

cp -p docker-compose.postgres.yml "$BK/docker-compose.postgres.yml-pre-cd-20261102"
tar -C /opt/histor -cf "$BK/host-tree-pre-cd-20261102.tar" $(printf 'histor/%s ' crawler.py store.py migrations.py check.py app.py service.py declared.py) \
  $(printf 'docs/landing/%s ' "${LANDING[@]}")
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
  cp -p "$BK/docker-compose.postgres.yml-pre-cd-20261102" docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-deps --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
}
if ! { sed -i "s|image: $BASE_REF |image: $NEW |" docker-compose.postgres.yml && grep -q "image: $NEW " docker-compose.postgres.yml; }; then
  cp -p "$BK/docker-compose.postgres.yml-pre-cd-20261102" docker-compose.postgres.yml
  echo "compose not changed as expected; restored" >&2
  exit 1
fi
"${COMPOSE[@]}" up -d --no-deps --no-build histor
if ! wait_healthy || [[ "$(docker inspect --format '{{.Image}}' histor-histor-1)" != "$new" ]]; then
  "${COMPOSE[@]}" logs --tail 60 histor >&2
  back "the new image did not come up"
fi
echo "ok: $health"
for f in cards.py crawler.py store.py migrations.py check.py app.py service.py declared.py; do install -m 0644 "$SRC/histor/$f" "/opt/histor/histor/$f"; done
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
