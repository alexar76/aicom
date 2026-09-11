#!/usr/bin/env bash
# Deploy ATLAS — physical sensor map — Docker + nginx + Let's Encrypt (auto-renew).
#
# On the web host:
#   sudo ./scripts/deploy_atlas.sh
#   sudo CERTBOT_EMAIL=you@x.dev ./scripts/deploy_atlas.sh
#   sudo ./scripts/deploy_atlas.sh --no-tls
#
# From a laptop (rsync monorepo slice + remote install):
#   ./scripts/deploy_atlas.sh --remote root@203.0.113.10
#
# Prereqs:
#   * DNS A  atlas.modelmarket.dev → this host
#   * Docker + compose, nginx, certbot
# Public UI: no password / no basic auth.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${ATLAS_PUBLIC_DOMAIN:-atlas.modelmarket.dev}"
COMPOSE_PROD="$ROOT/atlas/docker-compose.yml"
COMPOSE_LOCAL="$ROOT/atlas/docker-compose.local.yml"
NGINX_CONF_SRC="$ROOT/deploy/nginx/atlas.modelmarket.dev.conf"
NGINX_AVAIL="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
EMAIL="${CERTBOT_EMAIL:-}"
DO_TLS=1
REMOTE=""
COMPOSE=""

for arg in "$@"; do
  case "$arg" in
    --no-tls) DO_TLS=0 ;;
    --local) COMPOSE="$COMPOSE_LOCAL" ;;
    --remote)
      ;;
    --remote=*)
      REMOTE="${arg#--remote=}"
      ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *)
      if [[ -z "$REMOTE" && "$arg" != --* ]]; then
        # allow: --remote host   (next token handled below)
        :
      fi
      ;;
  esac
done

# Parse --remote HOST (two-token form)
args=("$@")
for i in "${!args[@]}"; do
  if [[ "${args[$i]}" == "--remote" ]]; then
    REMOTE="${args[$((i + 1))]:-}"
    [[ -n "$REMOTE" ]] || { echo "--remote requires host" >&2; exit 1; }
  fi
done

pick_compose() {
  if [[ -n "$COMPOSE" ]]; then
    echo "$COMPOSE"
    return
  fi
  if docker network inspect ecosystem >/dev/null 2>&1; then
    echo "$COMPOSE_PROD"
  else
    echo "WARN: docker network 'ecosystem' missing — using local compose (no external net)" >&2
    echo "$COMPOSE_LOCAL"
  fi
}

load_dotenv_keys() {
  # Soft-load DEEPSEEK / ATLAS_* from monorepo .env without printing secrets.
  local envf="$ROOT/.env"
  [[ -f "$envf" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^(DEEPSEEK_API_KEY|ATLAS_|CERTBOT_EMAIL)=' "$envf" | sed 's/\r$//' || true)
  set +a
  EMAIL="${CERTBOT_EMAIL:-$EMAIL}"
}

install_nginx_http() {
  install -d /var/www/certbot
  install -m 644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
  ln -sfn "$NGINX_AVAIL" "$NGINX_ENABLED"
  nginx -t
  systemctl reload nginx
}

issue_or_renew_tls() {
  [[ "$DO_TLS" -eq 1 ]] || { echo "Skipping TLS (--no-tls)"; return 0; }

  if ! command -v certbot >/dev/null; then
    apt-get update -qq
    apt-get install -y -qq certbot python3-certbot-nginx
  fi

  install -d /var/www/certbot

  # Prefer webroot so we keep a clean nginx conf (no certbot rewrite / return 404).
  local args=(certonly --webroot -w /var/www/certbot --non-interactive --agree-tos
              --keep-until-expiring -d "$DOMAIN")
  if [[ -n "$EMAIL" ]]; then
    args+=(-m "$EMAIL")
  else
    args+=(--register-unsafely-without-email)
  fi

  # Temporary HTTP-only vhost for first issue if cert missing.
  if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    cat >"$NGINX_AVAIL" <<HTTPONLY
upstream atlas_app { server 127.0.0.1:9330; keepalive 8; }
limit_req_zone \$binary_remote_addr zone=atlas_api:10m rate=30r/s;
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }
    location / { proxy_pass http://atlas_app; proxy_set_header Host \$host; }
}
HTTPONLY
    ln -sfn "$NGINX_AVAIL" "$NGINX_ENABLED"
    nginx -t && systemctl reload nginx
    certbot "${args[@]}"
  else
    certbot "${args[@]}" || true
  fi

  # Install full TLS nginx conf (ACME stays on :80).
  install -m 644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
  ln -sfn "$NGINX_AVAIL" "$NGINX_ENABLED"

  systemctl enable --now certbot.timer 2>/dev/null \
    || systemctl enable --now certbot.service 2>/dev/null \
    || true
  systemctl list-timers --all 2>/dev/null | grep -i certbot || true

  nginx -t && systemctl reload nginx
}

# ATLAS does not fetch Open-Meteo — GAIA does, and ATLAS maps its pins. So the fix
# for the non-commercial hosted ToS lives in scripts/deploy_gaia.sh (self-hosted by
# default). What belongs HERE is telling the operator what they just published:
# atlas.nearest.read@v1 defaults to layers=["weather"], so if those pins are served
# from Open-Meteo's free API, a paid SKU's default path resells non-commercial data.
om_licence_report() {
  echo "── Open-Meteo licence posture (weather pins) ──"
  curl -fsS --max-time 20 "http://127.0.0.1:9330/api/v1/snapshot" 2>/dev/null | python3 -c '
import json, sys
try:
    stations = json.load(sys.stdin).get("stations") or []
except Exception:
    print("  (snapshot unavailable — skipped)"); raise SystemExit(0)
wx = [s for s in stations if s.get("layer") == "weather"]
hosted = [s for s in wx
          if "open-meteo.com" in (s.get("source") or "").lower()
          and "operator-run" not in (s.get("source") or "").lower()]
selfhosted = [s for s in wx if "operator-run open-meteo" in (s.get("source") or "").lower()]
print(f"  weather pins: {len(wx)} | self-hosted OM: {len(selfhosted)} | hosted-free OM: {len(hosted)}")
if hosted:
    print(f"  WARNING: {len(hosted)} pin(s) come from Open-Meteo hosted free API (ToS: non-commercial).")
    print("  atlas.nearest.read@v1 defaults to layers=[weather] — a paid SKU would resell them.")
    print("  Fix on the GAIA host: sudo ./scripts/deploy_gaia.sh   (self-hosts Open-Meteo by default)")
' || echo "  (licence report skipped)"
}

smoke_local() {
  echo "── smoke ──"
  curl -fsS "http://127.0.0.1:9330/health" | head -c 200
  echo
  om_licence_report
  curl -fsS "http://127.0.0.1:9330/.well-known/ai-market.json" | head -c 240
  echo
  curl -fsS "http://127.0.0.1:9330/ai-market/v2/manifest" | head -c 240
  echo
  curl -fsS -o /dev/null -w "http://${DOMAIN}/health → %{http_code}\n" "http://${DOMAIN}/health" || true
  if [[ "$DO_TLS" -eq 1 ]]; then
    curl -fsS -o /dev/null -w "https://${DOMAIN}/health → %{http_code}\n" "https://${DOMAIN}/health" || true
    curl -fsS -o /dev/null -w "https://${DOMAIN}/ → %{http_code}\n" "https://${DOMAIN}/" || true
    curl -fsS -o /dev/null -w "https://${DOMAIN}/.well-known/ai-market.json → %{http_code}\n" \
      "https://${DOMAIN}/.well-known/ai-market.json" || true
    echo | openssl s_client -servername "$DOMAIN" -connect "${DOMAIN}:443" 2>/dev/null \
      | openssl x509 -noout -subject -dates 2>/dev/null || true
  fi
}

install_on_host() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
  fi
  load_dotenv_keys
  local compose
  compose="$(pick_compose)"

  echo "Building + starting atlas (127.0.0.1:9330) via $compose …"
  # Export public URL for compose interpolation when using prod file.
  export ATLAS_PUBLIC_URL="${ATLAS_PUBLIC_URL:-https://${DOMAIN}}"
  export ATLAS_GAIA_URL="${ATLAS_GAIA_URL:-https://iot.modelmarket.dev}"
  local env_args=()
  if [[ -f "$ROOT/.env" ]]; then
    env_args+=(--env-file "$ROOT/.env")
  fi
  docker compose -f "$compose" "${env_args[@]}" up -d --build

  echo -n "Waiting for atlas health on 127.0.0.1:9330 "
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:9330/health" >/dev/null 2>&1; then
      echo " ok"
      break
    fi
    echo -n "."
    sleep 1
  done
  curl -fsS "http://127.0.0.1:9330/health" >/dev/null \
    || { echo; echo "atlas did not become healthy; check: docker compose -f $compose logs atlas" >&2; exit 1; }

  install_nginx_http
  issue_or_renew_tls
  smoke_local

  echo
  echo "ATLAS up (public, no password):"
  echo "  https://${DOMAIN}/"
  echo "  https://${DOMAIN}/embed"
  echo "  https://${DOMAIN}/health"
  echo "  Alien Monitor defaults already use https://${DOMAIN}"
}

install_remote() {
  local host="$REMOTE"
  echo "Rsync atlas + nginx → ${host}:/root/claudecode/aicom/ …"
  ssh "$host" "mkdir -p /root/claudecode/aicom/atlas /root/claudecode/aicom/deploy/nginx /root/claudecode/aicom/scripts"
  # /data holds a dev signing key + watchbox registry; production keeps its own
  # on the atlas_data volume. Never let a laptop's copy overwrite the host's.
  rsync -az --delete \
    --exclude '.venv' --exclude 'backend/.venv' --exclude '__pycache__' \
    --exclude '.pytest_cache' --exclude '.coverage' --exclude '.DS_Store' \
    --exclude '/data' --exclude '.env' --exclude '/dist' \
    "$ROOT/atlas/" "$host:/root/claudecode/aicom/atlas/"
  scp "$NGINX_CONF_SRC" "$host:/root/claudecode/aicom/deploy/nginx/atlas.modelmarket.dev.conf"
  scp "$ROOT/scripts/deploy_atlas.sh" "$host:/root/claudecode/aicom/scripts/deploy_atlas.sh"

  local tls_flag=""
  [[ "$DO_TLS" -eq 1 ]] || tls_flag="--no-tls"
  local email_export=""
  [[ -n "$EMAIL" ]] && email_export="CERTBOT_EMAIL=$(printf %q "$EMAIL")"

  ssh "$host" bash -s <<EOF
set -euo pipefail
cd /root/claudecode/aicom
chmod +x scripts/deploy_atlas.sh
${email_export} sudo -E ./scripts/deploy_atlas.sh ${tls_flag}
EOF
}

if [[ -n "$REMOTE" ]]; then
  install_remote
elif [[ -d /etc/nginx/sites-available ]]; then
  install_on_host
else
  echo "Not the web host — use: $0 --remote root@HOST" >&2
  exit 1
fi
