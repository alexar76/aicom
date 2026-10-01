#!/usr/bin/env bash
# Deploy HISTOR on the host that serves histor.modelmarket.dev.
#
#   ./scripts/deploy_histor.sh --remote admin-vps     # from a laptop: sync the slice, deploy there
#   sudo ./scripts/deploy_histor.sh                   # on the host: redeploys whatever /opt/histor holds —
#                                                     #   use --remote, which syncs the monorepo first
#   sudo ./scripts/deploy_histor.sh --no-tls
#
# Prereqs on the host: Docker + compose, nginx, certbot; DNS A record histor.modelmarket.dev → it.
# Production is Postgres (docker-compose.postgres.yml); HISTOR_PROFILE=prod refuses anything else.
# First run creates /opt/histor/.env (0600) with a random operator token and Postgres password and
# prints only their NAMES. Later runs never rewrite it. Idempotent.
set -euo pipefail

DOMAIN="${HISTOR_PUBLIC_DOMAIN:-histor.modelmarket.dev}"
DEST="/opt/histor"
DO_TLS=1
REMOTE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-tls) DO_TLS=0 ;;
    --remote) REMOTE="${2:?--remote needs a host}"; shift ;;
    --remote=*) REMOTE="${1#--remote=}" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -n "$REMOTE" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  echo "Syncing the histor slice → ${REMOTE}:${DEST} …"
  ssh -o BatchMode=yes "$REMOTE" "mkdir -p ${DEST}/deploy/nginx"
  # The host keeps .env and nothing else of its own; everything else is the monorepo's. .env is
  # EXCLUDED, not just protected from deletion: a developer's local histor/.env must never be
  # copied over the production secrets.
  rsync -az --delete \
    --exclude '.env' --exclude '.env.*' --include '.env.example' \
    --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' \
    --exclude '.coverage' --exclude 'coverage.json' --exclude 'junit.xml' --exclude '.DS_Store' \
    --exclude 'data' --exclude 'scanner/node_modules' --exclude '.git' \
    --filter 'P deploy/deploy_histor.sh' \
    "$ROOT/histor/" "${REMOTE}:${DEST}/"
  scp -q -o BatchMode=yes "$ROOT/scripts/deploy_histor.sh" "${REMOTE}:${DEST}/deploy/deploy_histor.sh"
  flag=""
  [[ "$DO_TLS" -eq 1 ]] || flag="--no-tls"
  ssh -o BatchMode=yes "$REMOTE" "sudo bash ${DEST}/deploy/deploy_histor.sh ${flag}"
  exit 0
fi

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on the host, or use --remote <host> from a laptop" >&2; exit 1; }
cd "$DEST"
[[ -f docker-compose.yml && -f docker-compose.postgres.yml ]] || { echo "no histor slice in $DEST" >&2; exit 1; }

ENV_FILE="$DEST/.env"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
ensure() {  # ensure KEY VALUE — append only when absent; never print the value
  grep -q "^$1=" "$ENV_FILE" || { printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"; echo "  created $1"; }
}
ensure HISTOR_PROFILE prod
ensure HISTOR_PUBLIC_BASE "https://${DOMAIN}"
ensure HISTOR_OPERATOR_TOKEN "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
ensure HISTOR_POSTGRES_PASSWORD "$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
ensure HISTOR_PQC 1

COMPOSE=(docker compose -p histor --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.postgres.yml)
IMAGE="histor-histor"

# Was a crawl running? It is interrupted by the recreate; with batching it loses at most one
# batch, and it is restarted below instead of waiting an hour for the scheduler's retry.
was_crawling=0
curl -sf --max-time 3 http://127.0.0.1:9490/health 2>/dev/null | grep -q '"crawl_running":true' && was_crawling=1
# Keep the running image as :prev, so a build that does not come up can be put back.
docker image inspect "${IMAGE}:latest" >/dev/null 2>&1 && docker image tag "${IMAGE}:latest" "${IMAGE}:prev"

wait_healthy() {
  for _ in $(seq 1 90); do
    if health="$(curl -sf --max-time 3 http://127.0.0.1:9490/health)"; then return 0; fi
    sleep 2
  done
  return 1
}

echo "=== HISTOR → https://${DOMAIN} (Postgres, profile prod) ==="
"${COMPOSE[@]}" up -d --build
echo -n "waiting for /health on 127.0.0.1:9490 … "
if ! wait_healthy; then
  echo "the new build did not come up:" >&2
  "${COMPOSE[@]}" logs --tail 80 histor >&2
  if docker image inspect "${IMAGE}:prev" >/dev/null 2>&1; then
    echo "rolling back to the previous image" >&2
    docker image tag "${IMAGE}:prev" "${IMAGE}:latest"
    "${COMPOSE[@]}" up -d --no-build histor
    wait_healthy && echo "previous image is serving again" >&2
  fi
  exit 1
fi
echo "ok"
echo "$health" | grep -q '"service":"histor"' || { echo "not histor: $health" >&2; exit 1; }
echo "$health" | grep -q '"store":"postgresql"' || { echo "production must run on Postgres: $health" >&2; exit 1; }
if [[ "$was_crawling" -eq 1 ]]; then
  token="$(grep '^HISTOR_OPERATOR_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
  curl -sf --max-time 10 -X POST -H "x-histor-operator: ${token}" http://127.0.0.1:9490/api/v1/admin/crawl >/dev/null \
    && echo "restarted the crawl the redeploy interrupted"
  unset token
fi

# Nightly backups: the log (pg_dump) and the keys. See docs/operations.md, "Backups".
install -m 0755 "$DEST/deploy/backup_histor.sh" /usr/local/sbin/histor-backup
cat > /etc/systemd/system/histor-backup.service <<UNIT
[Unit]
Description=HISTOR backup: pg_dump of the log and a copy of the keys
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/histor-backup
UNIT
cat > /etc/systemd/system/histor-backup.timer <<UNIT
[Unit]
Description=Nightly HISTOR backup
[Timer]
OnCalendar=*-*-* 03:40:00
RandomizedDelaySec=15m
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now histor-backup.timer >/dev/null
[[ -n "$(ls -A /var/backups/histor 2>/dev/null)" ]] || /usr/local/sbin/histor-backup

mkdir -p /var/www/certbot
AVAIL="/etc/nginx/sites-available/${DOMAIN}"
ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
LIVE_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
if [[ ! -f "$LIVE_CERT" ]]; then
  # HTTP-only bootstrap so the ACME challenge can be answered, then the TLS vhost.
  cat > "$AVAIL" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    location ^~ /.well-known/acme-challenge/ { root /var/www/certbot; default_type "text/plain"; try_files \$uri =404; }
    location / { proxy_pass http://127.0.0.1:9490; proxy_set_header Host \$host; }
}
NGINX
  ln -sf "$AVAIL" "$ENABLED"
  nginx -t && systemctl reload nginx
  if [[ "$DO_TLS" -eq 1 ]]; then
    account=(--register-unsafely-without-email)
    [[ -n "${CERTBOT_EMAIL:-}" ]] && account=(-m "$CERTBOT_EMAIL")
    certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" --non-interactive --agree-tos "${account[@]}"
  fi
fi
if [[ -f "$LIVE_CERT" ]]; then
  install -m 0644 "$DEST/deploy/nginx/${DOMAIN}.conf" "$AVAIL"
  ln -sf "$AVAIL" "$ENABLED"
fi
nginx -t && systemctl reload nginx

if [[ -f "$LIVE_CERT" ]]; then
  curl -sf --max-time 10 "https://${DOMAIN}/health" >/dev/null && echo "live: https://${DOMAIN}/health"
fi
echo "issuer did:key: $(docker compose -p histor exec -T histor python -m histor issuer 2>/dev/null | tail -1)"
echo "(add it to awr/adoption/metrics/own-keys.txt in the monorepo)"
