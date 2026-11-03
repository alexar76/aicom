#!/usr/bin/env bash
# One-off (2026-11-01): the five kernel desks' web containers get kernel/web/nginx.conf with
# Cache-Control: no-cache for .html/.js/.css (aicom, see the comment at the top of that file).
# Each new image is FROM the image the desk runs (the security session's *-web-os-20261031, OS patches
# kept) with only the config replaced; the site files stay bind-mounted from /opt/cite-desks/kernel/web.
# Run on skopos-vps as root with nginx.conf in $SRC.
#
# Rollback per desk (also automatic below when a check fails):
#   cp /root/cite-desks-backups/nocache-20261101/<desk>-docker-compose.metis.yml /opt/cite-desks/<desk>/docker-compose.metis.yml
#   cd /opt/cite-desks/<desk> && docker compose -p <desk> -f docker-compose.yml -f docker-compose.metis.yml up -d --no-deps --no-build web
set -euo pipefail
SRC=/root/desk-nocache-20261101
BK=/root/cite-desks-backups/nocache-20261101
TAG=nc-20261101
mkdir -p "$BK"
[[ -s "$SRC/nginx.conf" ]] || { echo "missing $SRC/nginx.conf" >&2; exit 1; }

for d in ${DESKS:-tideline solrecord seamark plinth smokeproof}; do
  echo "== $d"
  cd "/opt/cite-desks/$d"
  base="$(grep -oE "image: aicom-security:$d-web-[A-Za-z0-9._-]+" docker-compose.metis.yml | head -1 | cut -d' ' -f2)"
  [[ -n "$base" ]] || { echo "$d: no web image pinned in docker-compose.metis.yml; stop" >&2; exit 1; }
  running="$(docker inspect "$d-web" --format '{{.Image}}')"
  [[ "$(docker image inspect --format '{{.Id}}' "$base")" == "$running" ]] \
    || { echo "$d: $d-web does not run $base; stop" >&2; exit 1; }
  new="aicom-security:$d-web-$TAG"
  printf 'FROM %s\nCOPY nginx.conf /etc/nginx/conf.d/default.conf\nLABEL aicom.desk.overlay=%s\n' "$base" "$TAG" > "$SRC/Dockerfile.$d"
  docker build -q -f "$SRC/Dockerfile.$d" -t "$new" "$SRC" > /dev/null
  # The desk's own network, where its API answers to "api" (the web container also sits on metisnet).
  net="$(docker inspect "$d-web" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' | tr ' ' '\n' | grep -x "${d}_default" || true)"
  [[ -n "$net" ]] || { echo "$d: web container is not on ${d}_default; stop" >&2; exit 1; }
  docker run --rm --network "$net" --entrypoint nginx "$new" -t 2>&1 | tail -1
  port="$(docker port "$d-web" 80/tcp | head -1 | sed 's/.*://')"

  cp -p docker-compose.metis.yml "$BK/$d-docker-compose.metis.yml"
  sed -i "s#image: $base #image: $new #; s#image: $base\$#image: $new#" docker-compose.metis.yml
  grep -q "image: $new" docker-compose.metis.yml || { echo "$d: compose line not changed" >&2; exit 1; }
  docker compose -p "$d" -f docker-compose.yml -f docker-compose.metis.yml up -d --no-deps --no-build web 2>&1 | tail -1

  ok=0
  for _ in $(seq 1 30); do
    if headers="$(curl -s -D - -o /dev/null --max-time 5 "http://127.0.0.1:$port/app.js")" \
       && grep -qi '^cache-control: no-cache' <<< "$headers" && grep -qi '^content-security-policy:' <<< "$headers" \
       && curl -sf --max-time 5 "http://127.0.0.1:$port/api/public/health" > /dev/null; then
      ok=1; break
    fi
    sleep 1
  done
  if [[ $ok -ne 1 || "$(docker inspect "$d-web" --format '{{.Config.Image}}')" != "$new" ]]; then
    echo "$d: checks failed, rolling back" >&2
    cp -p "$BK/$d-docker-compose.metis.yml" docker-compose.metis.yml
    docker compose -p "$d" -f docker-compose.yml -f docker-compose.metis.yml up -d --no-deps --no-build web
    exit 1
  fi
  echo "$d: ok on :$port — $(grep -i '^cache-control' <<< "$headers" | tr -d '\r'), CSP kept, API through the proxy answers"
done
