#!/usr/bin/env bash
# One-off (2026-10-31): put the desk kernel of b3c30e5ea (card checkout through Stripe, plus c3e0fa82e's
# per-desk USDC amount bands that never reached the desks) into tideline-api, on top of the RUNNING image
# aicom-security:tideline-api-os-20261031, keeping its OS patches. Demo mode stays as it is: card checkout
# is closed there. Also brings the shared web shell (/opt/cite-desks/kernel/web, bind-mounted into all five
# kernel desks) to b3c30e5ea; the new app.js reads an older API the old way (no `card` block → no card button).
# Files come from `git show b3c30e5ea:cite-desks/kernel/<f>` in $SRC/kernel.
#
# Rollback:
#   cp /root/cite-desks-backups/card-20261031/docker-compose.metis.yml /opt/cite-desks/tideline/
#   cp /root/cite-desks-backups/card-20261031/web/{app.js,index.html} /opt/cite-desks/kernel/web/
#   (and the desk_kernel files from /root/cite-desks-backups/card-20261031/desk_kernel/ to /opt/cite-desks/kernel/desk_kernel/)
#   cd /opt/cite-desks/tideline && docker compose -f docker-compose.yml -f docker-compose.metis.yml up -d --no-deps --no-build api
#   The card_checkouts table the new code creates is empty in demo mode and harmless to the old code.
set -euo pipefail
SRC=/root/desk-card-20261031
BK=/root/cite-desks-backups/card-20261031
BASE_REF=aicom-security:tideline-api-os-20261031
NEW=aicom-security:tideline-api-card-20261031
SITE=/usr/local/lib/python3.12/site-packages
PY=(desk_kernel/service/card.py desk_kernel/service/pay.py desk_kernel/service/api.py desk_kernel/service/main.py
    desk_kernel/service/config.py desk_kernel/service/models.py desk_kernel/i18n/catalogs.py desk_kernel/invoice_allocation.py)
WEB=(web/app.js web/index.html)
cd /opt/cite-desks/tideline
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.metis.yml)

running="$(docker inspect --format '{{.Image}}' tideline-api)"
base="$(docker image inspect --format '{{.Id}}' "$BASE_REF")"
[[ "$running" == "$base" ]] || { echo "tideline-api runs ${running:7:12}, not $BASE_REF; stop" >&2; exit 1; }
for f in "${PY[@]}" "${WEB[@]}"; do [[ -s "$SRC/kernel/$f" ]] || { echo "missing $SRC/kernel/$f" >&2; exit 1; }; done

mkdir -p "$BK/desk_kernel/service" "$BK/desk_kernel/i18n" "$BK/web"
cp -p docker-compose.metis.yml "$BK/"
for f in "${PY[@]}" "${WEB[@]}"; do [[ -f "/opt/cite-desks/kernel/$f" ]] && cp -p "/opt/cite-desks/kernel/$f" "$BK/$f"; done
docker exec tideline-db pg_dump -U tideline -d tideline -Fc > "$BK/tideline.dump"
echo "backup: $(du -sh "$BK" | cut -f1) in $BK"

{
  echo "FROM $BASE_REF"
  for f in "${PY[@]}"; do
    echo "COPY --chown=root:root --chmod=0644 kernel/$f /kernel/$f"
    echo "COPY --chown=root:root --chmod=0644 kernel/$f $SITE/$f"
  done
  echo "LABEL aicom.desk.overlay=card-20261031 aicom.desk.kernel=b3c30e5ea"
} > "$SRC/Dockerfile"
docker build -q -f "$SRC/Dockerfile" -t "$NEW" "$SRC"
new="$(docker image inspect --format '{{.Id}}' "$NEW")"
echo "new image ${new:7:12} FROM ${base:7:12}"
docker run --rm --entrypoint python -e DATABASE_URL=sqlite:// -e SEED_DEMO=true -e SCHEDULER_ENABLED=false \
  -e PAY_SCAN_INTERVAL_SECONDS=20 -e COOKIE_SECURE=true "$NEW" -c \
  "import desk_kernel.service.main, desk_kernel.service.card as c, desk_kernel.invoice_allocation; print('imports ok', c.CARD)"

sed -i "s#image: $BASE_REF #image: $NEW #" docker-compose.metis.yml
grep -q "image: $NEW " docker-compose.metis.yml || { echo "compose image line not changed" >&2; exit 1; }
for f in "${PY[@]}" "${WEB[@]}"; do install -m 0644 "$SRC/kernel/$f" "/opt/cite-desks/kernel/$f"; done
"${COMPOSE[@]}" up -d --no-deps --no-build api

for _ in $(seq 1 60); do
  [[ "$(docker inspect --format '{{.State.Health.Status}}' tideline-api)" == healthy ]] && break
  sleep 2
done
if [[ "$(docker inspect --format '{{.State.Health.Status}}' tideline-api)" != healthy ]]; then
  echo "tideline-api did not become healthy; rolling back" >&2
  docker logs --tail 60 tideline-api >&2 || true
  cp -p "$BK/docker-compose.metis.yml" docker-compose.metis.yml
  for f in "${PY[@]}" "${WEB[@]}"; do [[ -f "$BK/$f" ]] && cp -p "$BK/$f" "/opt/cite-desks/kernel/$f"; done
  "${COMPOSE[@]}" up -d --no-deps --no-build api
  exit 1
fi
docker exec tideline-api python -c "import urllib.request,json; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/public/pay/status')); print('usdc', d['enabled'], 'card', d['card']['enabled'], d['card']['closed_reason'][:40])"
