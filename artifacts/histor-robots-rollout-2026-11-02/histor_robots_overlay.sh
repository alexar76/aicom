#!/usr/bin/env bash
# One-off (2026-11-02): HISTOR follows robots.txt (RFC 9309), commit 0643fee6e, on top of the RUNNING image
# aicom-security:histor-histor-1-wd-20261102 (sha256:914a930a…, WARDEN 0.22.4 from another session), keeping its OS
# patches, baked env and WARDEN build byte for byte. Five Python files change and robots.py is new; the landing
# (crawler FAQ, robots status) changes in seven files. Each replaced file was checked equal to main before
# 0643fee6e in the running container. The service applies migration 019 (one new table) before it listens.
# Run on admin-vps as root with the files of 0643fee6e and smoke.py in $SRC.
#
# Rollback (also automatic below if /health does not come up). Migration 019 stays: an unused table is harmless.
#   cp /root/histor-backups/docker-compose.postgres.yml-pre-rb-20261102 /opt/histor/docker-compose.postgres.yml
#   tar -C /opt/histor -xf /root/histor-backups/host-tree-pre-rb-20261102.tar
#   cd /opt/histor && docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml \
#     up -d --no-deps --no-build histor
#   /usr/local/sbin/skopos-warden-quality rebind sha256:914a930a93343f63a993d38f0d85c0288be0c83d1ca67ed33e3fd4cfae6b1dd9
#   docker image tag aicom-security:histor-histor-1-wd-20261102 histor:warden-remediation-base
set -euo pipefail
SRC=/root/histor-robots-20261102
BASE_REF=aicom-security:histor-histor-1-wd-20261102
WANT_BASE=sha256:914a930a93343f63a993d38f0d85c0288be0c83d1ca67ed33e3fd4cfae6b1dd9
NEW=aicom-security:histor-histor-1-rb-20261102
COMMIT=0643fee6e
cd /opt/histor
ENV_FILE=/opt/histor/.env
COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
BK=/root/histor-backups
mkdir -p "$BK"
PY=(robots.py mcpclient.py crawler.py store.py migrations.py check.py)
LANDING=(index.html assets/desk.js assets/i18n.js assets/i18n/ru.js assets/i18n/es.js assets/i18n/fr.js assets/i18n/zh.js)
declare -A WAS=(
  [/app/histor/mcpclient.py]=0e42ea4e3d1859a21f7f0913304965927cefa6115f87ab06ac2f97b58e08eb2a
  [/app/histor/crawler.py]=87d9b4c7ce8fafc6aeccc3d2df8d8714ad7c972ea563ef8e1e96b5f35214e759
  [/app/histor/store.py]=409d91328f6ad338f87717a301d97bf045d2468f84b60c2d7e6d4e21043b147b
  [/app/histor/migrations.py]=bb00c16ce005128bd3cb8f2ee9fbf3b9c0b8d0608ba5fc12fc1ce90660b7d86e
  [/app/histor/check.py]=3256ec1c251a29a71c6f7b95dc88f15705deb08bf25ac2622008861679f1024c
  [/app/docs/landing/index.html]=40327a2eee72b7b4d9f64ad68a5ec8f887f821010d6c4279d0f5d0d0c793294b
  [/app/docs/landing/assets/desk.js]=e057299949e0e9977d12152851616da5de2c5fa61dec2879fb93b992695d166c
  [/app/docs/landing/assets/i18n.js]=452bb55d477447e78c2dbcdc0127ab291837f068f12ed0cb6b3b7e86eb862da3
  [/app/docs/landing/assets/i18n/ru.js]=c4a2b749a7c1d3676329917b86b6596740f21f7b040d435fa43786b878d0012b
  [/app/docs/landing/assets/i18n/es.js]=62e85c65609fade9f4c522186016d161a14c7e6e11fa47971df054aab1462200
  [/app/docs/landing/assets/i18n/fr.js]=3af6db88943270ff2cc29537df907a8b099e74d72b4642ef1f6a65a4ef0f69f4
  [/app/docs/landing/assets/i18n/zh.js]=b160ccf1718004ea6b48cc1c42dbbc834884009b4c0ea5868f65f5770e961f9d
)

running="$(docker inspect --format '{{.Image}}' histor-histor-1)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
[[ "$running" == "$base" && "$base" == "$WANT_BASE" ]] || { echo "histor runs ${running:7:12}, not $BASE_REF; stop" >&2; exit 1; }
for f in "${!WAS[@]}"; do
  [[ "$(docker exec histor-histor-1 sha256sum "$f" | cut -d' ' -f1)" == "${WAS[$f]}" ]] \
    || { echo "the running $f is not main before $COMMIT; stop" >&2; exit 1; }
done
docker exec histor-histor-1 test ! -e /app/histor/robots.py || { echo "robots.py already in the image; stop" >&2; exit 1; }
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
LABEL aicom.histor.overlay=rb-20261102 aicom.histor.app.robots=$COMMIT
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

cp -p docker-compose.postgres.yml "$BK/docker-compose.postgres.yml-pre-rb-20261102"
tar -C /opt/histor -cf "$BK/host-tree-pre-rb-20261102.tar" $(printf 'histor/%s ' mcpclient.py crawler.py store.py migrations.py check.py) \
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
  cp -p "$BK/docker-compose.postgres.yml-pre-rb-20261102" docker-compose.postgres.yml
  "${COMPOSE[@]}" up -d --no-deps --no-build histor
  wait_healthy && echo "the previous image is serving again" >&2
  exit 1
}
if ! { sed -i "s|image: $BASE_REF |image: $NEW |" docker-compose.postgres.yml && grep -q "image: $NEW " docker-compose.postgres.yml; }; then
  cp -p "$BK/docker-compose.postgres.yml-pre-rb-20261102" docker-compose.postgres.yml
  echo "compose not changed as expected; restored" >&2
  exit 1
fi
"${COMPOSE[@]}" up -d --no-deps --no-build histor
if ! wait_healthy || [[ "$(docker inspect --format '{{.Image}}' histor-histor-1)" != "$new" ]]; then
  "${COMPOSE[@]}" logs --tail 60 histor >&2
  back "the new image did not come up"
fi
echo "ok: $health"
for f in mcpclient.py crawler.py store.py migrations.py check.py robots.py; do install -m 0644 "$SRC/histor/$f" "/opt/histor/histor/$f"; done
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
