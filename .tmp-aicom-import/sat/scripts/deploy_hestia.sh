#!/usr/bin/env bash
# Deploy HESTIA — the hearth — on the host that will serve hestia.modelmarket.dev.
#
#   sudo HESTIA_DEPLOY_TOKEN=… ./scripts/deploy_hestia.sh
#   sudo HESTIA_DEPLOY_TOKEN=… ./scripts/deploy_hestia.sh --no-tls
#   sudo CERTBOT_EMAIL=you@x.dev HESTIA_DEPLOY_TOKEN=… ./scripts/deploy_hestia.sh
#   ./scripts/deploy_hestia.sh --remote my-vps
#
# Prereqs:
#   * DNS A record  hestia.modelmarket.dev → THIS host (do not invent a box)
#   * Docker + compose, nginx, certbot
#   * HESTIA_DEPLOY_TOKEN set to a high-entropy secret (empty token = locked writes)
#
# Not hunt. Not a laptop. Compose stays stub-only (no docker.sock).
# Idempotent: re-run after a pull. Loopback-only container; nginx is the TLS edge.
# Laptop path rsyncs the Hestia slice only — never the whole monorepo, never --delete
# of /root/claudecode/aicom.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${HESTIA_PUBLIC_DOMAIN:-hestia.modelmarket.dev}"
COMPOSE="$ROOT/hestia/docker-compose.yml"
LEDGER_OVERLAY="$ROOT/hestia/docker-compose.postgres.yml"
NGINX_CONF_SRC="$ROOT/deploy/nginx/hestia.modelmarket.dev.conf"
NGINX_AVAIL="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
EMAIL="${CERTBOT_EMAIL:-}"
DO_TLS=1
REMOTE=""
for arg in "$@"; do
  case "$arg" in
    --no-tls) DO_TLS=0 ;;
    --remote) ;;
    --remote=*) REMOTE="${arg#--remote=}" ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *)
      if [[ "$arg" == --* ]]; then
        echo "Unknown option: $arg" >&2
        exit 1
      fi
      ;;
  esac
done
args=("$@")
for i in "${!args[@]}"; do
  if [[ "${args[$i]}" == "--remote" ]]; then
    REMOTE="${args[$((i + 1))]:-}"
    [[ -n "$REMOTE" ]] || { echo "--remote requires host" >&2; exit 1; }
  fi
done

install_remote() {
  local host="$REMOTE"
  local dest="/root/claudecode/aicom"
  echo "Rsync hestia slice + nginx → ${host}:${dest} …"
  ssh -o BatchMode=yes "$host" "mkdir -p ${dest}/hestia ${dest}/deploy/nginx ${dest}/scripts"
  rsync -az --delete \
    --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' \
    --exclude '.coverage' --exclude '.DS_Store' --exclude 'data' \
    --exclude '.env' --exclude '.git' \
    --filter 'P .env' --filter 'P data/' \
    "$ROOT/hestia/" "${host}:${dest}/hestia/"
  scp -o BatchMode=yes "$NGINX_CONF_SRC" "${host}:${dest}/deploy/nginx/hestia.modelmarket.dev.conf"
  scp -o BatchMode=yes "$ROOT/scripts/deploy_hestia.sh" "${host}:${dest}/scripts/deploy_hestia.sh"

  local tls_flag=""
  [[ "$DO_TLS" -eq 1 ]] || tls_flag="--no-tls"
  local email_export=""
  [[ -n "$EMAIL" ]] && email_export="CERTBOT_EMAIL=$(printf %q "$EMAIL")"

  # Token stays on the host. Do not print it. Reuse compose/.env or the live box.
  ssh -o BatchMode=yes "$host" bash -s <<EOF
set -euo pipefail
cd ${dest}
chmod +x scripts/deploy_hestia.sh
if [[ -z "\${HESTIA_DEPLOY_TOKEN:-}" ]]; then
  if [[ -f .env ]]; then
    HESTIA_DEPLOY_TOKEN="\$(awk -F= '\$1=="HESTIA_DEPLOY_TOKEN"{print substr(\$0,index(\$0,"=")+1); exit}' .env)"
  fi
  if [[ -z "\${HESTIA_DEPLOY_TOKEN:-}" && -f hestia/.env ]]; then
    HESTIA_DEPLOY_TOKEN="\$(awk -F= '\$1=="HESTIA_DEPLOY_TOKEN"{print substr(\$0,index(\$0,"=")+1); exit}' hestia/.env)"
  fi
  if [[ -z "\${HESTIA_DEPLOY_TOKEN:-}" ]]; then
    box="\$(docker ps --format '{{.Names}}' | grep -E '(^|-)hestia(-|\$)' | head -n1 || true)"
    if [[ -n "\$box" ]]; then
      HESTIA_DEPLOY_TOKEN="\$(docker inspect "\$box" --format '{{range .Config.Env}}{{println .}}{{end}}' | awk -F= '\$1=="HESTIA_DEPLOY_TOKEN"{print substr(\$0,index(\$0,"=")+1); exit}')"
    fi
  fi
fi
if [[ -z "\${HESTIA_POSTGRES_PASSWORD:-}" ]]; then
  if [[ -f .env ]]; then
    HESTIA_POSTGRES_PASSWORD="\$(awk -F= '\$1=="HESTIA_POSTGRES_PASSWORD"{print substr(\$0,index(\$0,"=")+1); exit}' .env)"
  fi
  if [[ -z "\${HESTIA_POSTGRES_PASSWORD:-}" && -f hestia/.env ]]; then
    HESTIA_POSTGRES_PASSWORD="\$(awk -F= '\$1=="HESTIA_POSTGRES_PASSWORD"{print substr(\$0,index(\$0,"=")+1); exit}' hestia/.env)"
  fi
fi
export HESTIA_POSTGRES_PASSWORD
export HESTIA_DEPLOY_TOKEN
${email_export} sudo -E ./scripts/deploy_hestia.sh ${tls_flag}
EOF
}

if [[ -n "$REMOTE" ]]; then
  install_remote
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the host that will own ${DOMAIN}: sudo HESTIA_DEPLOY_TOKEN=… $0" >&2
  echo "From a laptop: $0 --remote my-vps" >&2
  exit 1
fi

TOKEN="${HESTIA_DEPLOY_TOKEN:-}"
if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: HESTIA_DEPLOY_TOKEN is empty. Empty token refuses every write — set a secret." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE" ]]; then
  echo "ERROR: missing $COMPOSE — sync hestia/ onto this host first." >&2
  exit 1
fi
if [[ ! -f "$LEDGER_OVERLAY" ]]; then
  echo "ERROR: missing $LEDGER_OVERLAY — production deploy requires the ledger overlay." >&2
  exit 1
fi
ENV_FILE="$ROOT/hestia/.env"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
if ! grep -q '^HESTIA_DEPLOY_TOKEN=' "$ENV_FILE"; then
  printf 'HESTIA_DEPLOY_TOKEN=%s\n' "$TOKEN" >> "$ENV_FILE"
fi
if [[ -z "${HESTIA_POSTGRES_PASSWORD:-}" ]]; then
  HESTIA_POSTGRES_PASSWORD="$(awk -F= '$1=="HESTIA_POSTGRES_PASSWORD"{print substr($0,index($0,"=")+1); exit}' "$ENV_FILE")"
fi
if [[ -z "${HESTIA_POSTGRES_PASSWORD:-}" ]]; then
  HESTIA_POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  printf 'HESTIA_POSTGRES_PASSWORD=%s\n' "$HESTIA_POSTGRES_PASSWORD" >> "$ENV_FILE"
fi
export HESTIA_POSTGRES_PASSWORD
export HESTIA_DATABASE_URL="postgresql://hestia:${HESTIA_POSTGRES_PASSWORD}@hestia-postgres:5432/hestia"
if grep -q '^HESTIA_DATABASE_URL=' "$ENV_FILE"; then
  tmp="$(mktemp)"
  awk -v url="$HESTIA_DATABASE_URL" '
    BEGIN { done=0 }
    $0 ~ /^HESTIA_DATABASE_URL=/ { print "HESTIA_DATABASE_URL=" url; done=1; next }
    { print }
    END { if (!done) print "HESTIA_DATABASE_URL=" url }
  ' "$ENV_FILE" > "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
else
  printf 'HESTIA_DATABASE_URL=%s\n' "$HESTIA_DATABASE_URL" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
if [[ ! -f "$NGINX_CONF_SRC" ]]; then
  echo "ERROR: missing $NGINX_CONF_SRC" >&2
  exit 1
fi

echo "=== HESTIA deploy → https://${DOMAIN} (hearth, not catalogue) ==="

if ! docker network inspect ecosystem >/dev/null 2>&1; then
  echo "Creating shared 'ecosystem' docker network (was absent)…"
  docker network create ecosystem
fi

export HESTIA_DEPLOY_TOKEN="$TOKEN"
export HESTIA_PUBLIC_BASE="${HESTIA_PUBLIC_BASE:-https://${DOMAIN}}"
echo "Building + starting hestia (127.0.0.1:9480) with dedicated hestia-postgres, public base ${HESTIA_PUBLIC_BASE}"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" -f "$LEDGER_OVERLAY" up -d --build

echo -n "Waiting for hestia health on 127.0.0.1:9480 "
for i in $(seq 1 60); do
  if curl -sf --max-time 3 http://127.0.0.1:9480/health >/dev/null; then
    echo "— ok"; break
  fi
  echo -n "."
  sleep 1
  if [[ "$i" -eq 60 ]]; then
    echo
    echo "hestia did not become healthy; check: docker compose -f $COMPOSE logs hestia" >&2
    exit 1
  fi
done

health="$(curl -sf --max-time 5 http://127.0.0.1:9480/health)"
echo "$health" | grep -q '"service":"hestia"' || {
  echo "health did not identify as hestia: $health" >&2
  exit 1
}

if ! command -v nginx >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nginx
fi
mkdir -p /var/www/certbot

install_http_bootstrap() {
  cat > "$NGINX_AVAIL" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    client_max_body_size 256k;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }
    location / {
        proxy_pass http://127.0.0.1:9480;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
}

host_ips="$(hostname -I 2>/dev/null || true)"
dns_ip="$(dig +short "$DOMAIN" A 2>/dev/null | tail -n1 || true)"
dns_matches_host=0
if [[ -n "$dns_ip" ]]; then
  for ip in $host_ips; do
    if [[ "$ip" == "$dns_ip" ]]; then
      dns_matches_host=1
      break
    fi
  done
fi
LIVE_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
if [[ "$DO_TLS" -eq 1 && -n "$dns_ip" && "$dns_matches_host" -eq 0 && ! -f "$LIVE_CERT" ]]; then
  echo "DNS ${DOMAIN} → ${dns_ip}, this host IPs: ${host_ips}."
  echo "Skipping certbot until the A record points at this host."
  DO_TLS=0
fi

if [[ -f "$LIVE_CERT" ]]; then
  # Keep the existing TLS vhost. hostname -I may list a docker bridge first;
  # do not replace a live cert with the HTTP bootstrap.
  echo "Live cert already present for ${DOMAIN}; keeping TLS vhost, not re-issuing."
  install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
  DO_TLS=0
  SKIPPED_EXISTING_CERT=1
elif [[ "$DO_TLS" -eq 1 ]]; then
  install_http_bootstrap
  SKIPPED_EXISTING_CERT=0
else
  install_http_bootstrap
  SKIPPED_EXISTING_CERT=0
fi
ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx

if [[ "$DO_TLS" -eq 1 ]]; then
  if ! command -v certbot >/dev/null; then
    apt-get install -y -qq certbot python3-certbot-nginx
  fi
  CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect --cert-name "${DOMAIN}" -d "${DOMAIN}")
  if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
  certbot "${CERTBOT_ARGS[@]}"
  install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
  nginx -t
  systemctl reload nginx
  systemctl enable --now certbot.timer >/dev/null 2>&1 || true
elif [[ "${SKIPPED_EXISTING_CERT:-0}" -eq 1 ]]; then
  systemctl enable --now certbot.timer >/dev/null 2>&1 || true
else
  echo "Serving plain HTTP on :80 (TLS skipped until DNS matches this host)."
fi

echo
echo "=== HESTIA on this host ==="
echo "  Health:  http://127.0.0.1:9480/health"
echo "  Console: http://127.0.0.1:9480/ui/"
echo "  Public:  https://${DOMAIN}/  (after DNS + TLS)"
echo "  Roster:  https://${DOMAIN}/v1/hearth"
echo
echo "Verify from outside once the A record hits this host:"
echo "  curl -sS https://${DOMAIN}/health"
echo "  curl -sS https://${DOMAIN}/v1/hearth"
