#!/usr/bin/env bash
# Deploy a self-hosted Open-Meteo NODE on a big-disk host, for GAIA to pull from.
#
#   sudo ./scripts/deploy_om_node.sh                       # TLS + bearer (default)
#   sudo OM_NODE_DOMAIN=om.modelmarket.dev ./scripts/deploy_om_node.sh
#   sudo OM_NODE_ALLOW_IPS="203.0.113.20" ./scripts/deploy_om_node.sh
#   sudo ./scripts/deploy_om_node.sh --no-tls              # private network only
#   sudo ./scripts/deploy_om_node.sh --print-token         # show the bearer again
#
# WHY A SEPARATE HOST
#   Weather-model data is 32-48 GB narrow, 150 GB+ comprehensive, plus daily sync
#   bandwidth. Putting it on the host with disk and letting GAIA pull over the
#   network keeps the oracle host small.
#
# WHAT THIS DOES NOT DO
#   It does not publish an open weather mirror. The container binds LOOPBACK only;
#   nginx is the sole edge and it REQUIRES a bearer token, plus an optional source-IP
#   allowlist. Two reasons, and both matter:
#     * unauthenticated, this is our synced data served at our bandwidth to anyone;
#     * Open-Meteo's server is AGPLv3. We run it UNMODIFIED and reachable only by our
#       own GAIA, so no third party ever interacts with it remotely and GAIA stays a
#       separate work. Do not remove the auth gate to "make testing easier", and do
#       not patch the image without publishing the patch.
#
# SYNC SCOPE — drives disk. Match to what GAIA actually reads:
#   weather  → temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m
#   air qual → a CAMS-class model; marine → a wave model. Each needs its own entry in
#   OM_NODE_MODELS or those relays answer 404 and their pins stay offline.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${OM_NODE_DOMAIN:-om.modelmarket.dev}"
# The Open-Meteo services only — this file is valid standalone, which is why they
# live apart from the gaia-backend rewiring overlay.
COMPOSE="$ROOT/gaia/docker-compose.om-node.yml"
TOKEN_FILE="${OM_NODE_TOKEN_FILE:-/etc/aicom/om-node.token}"
NGINX_AVAIL="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
EMAIL="${CERTBOT_EMAIL:-}"
ALLOW_IPS="${OM_NODE_ALLOW_IPS:-}"
MIN_FREE_GB="${OM_NODE_MIN_FREE_GB:-48}"
DO_TLS=1
PRINT_TOKEN_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --no-tls) DO_TLS=0 ;;
    --print-token) PRINT_TOKEN_ONLY=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

ensure_token() {
  install -d -m 0700 "$(dirname "$TOKEN_FILE")"
  if [[ ! -s "$TOKEN_FILE" ]]; then
    openssl rand -hex 32 > "$TOKEN_FILE"
    chmod 0600 "$TOKEN_FILE"
    echo "Generated a new bearer token at ${TOKEN_FILE}"
  fi
  TOKEN="$(cat "$TOKEN_FILE")"
}

if [[ "$PRINT_TOKEN_ONLY" -eq 1 ]]; then
  ensure_token
  echo "GAIA_OM_AUTH_TOKEN=${TOKEN}"
  exit 0
fi

echo "=== Open-Meteo node → ${DOMAIN} (for GAIA to pull from) ==="

# ── 1. Disk gate. A half-synced instance 404s every variable, which would silently
#       take every om-* pin offline on the GAIA side. Refuse instead.
docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
free_gb="$(df -BG --output=avail "$docker_root" 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)"
[[ -n "$free_gb" ]] || free_gb=0
if (( free_gb < MIN_FREE_GB )); then
  echo "REFUSING: need ~${MIN_FREE_GB} GB free on ${docker_root}; found ${free_gb} GB." >&2
  echo "  Narrow OM_NODE_VARIABLES and lower OM_NODE_MIN_FREE_GB, or use a bigger disk." >&2
  exit 1
fi
echo "Disk: ${free_gb} GB free on ${docker_root} — ok"

ensure_token

# ── 2. The API + sync containers. Reuses the same overlay GAIA uses locally, so
#       there is one definition of how Open-Meteo is run, not two.
# Must track docker-compose.om-node.yml: at least one HOURLY model (ecmwf_ifs025
# alone is 3-hourly, so `current` returns null off the 3h boundary).
export GAIA_OM_SYNC_MODELS="${OM_NODE_MODELS:-dwd_icon,ecmwf_ifs025}"
# RAW variables. `sync` skips names a model does not carry IN SILENCE, so the derived
# surface_pressure / wind_speed_10m downloaded nothing; Open-Meteo derives them from
# pressure_msl and the u/v wind components.
export GAIA_OM_SYNC_VARIABLES="${OM_NODE_VARIABLES:-temperature_2m,relative_humidity_2m,pressure_msl,wind_u_component_10m,wind_v_component_10m}"
export GAIA_OM_SYNC_PAST_DAYS="${OM_NODE_PAST_DAYS:-2}"

echo "Starting open-meteo (serve + sync) — models=${GAIA_OM_SYNC_MODELS} vars=${GAIA_OM_SYNC_VARIABLES}"
docker compose -f "$COMPOSE" up -d

# ── 3. Publish the loopback port for nginx to reach.
#       The overlay deliberately has no `ports:`; on this host nginx is the only
#       consumer, so bind loopback explicitly rather than widening the overlay.
CID="$(docker compose -f "$COMPOSE" ps -q open-meteo)"
if [[ -z "$CID" ]]; then
  echo "open-meteo container did not start; check: docker compose -f $COMPOSE logs open-meteo" >&2
  exit 1
fi
OM_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$CID" | tr -d '[:space:]')"
[[ -n "$OM_IP" ]] || { echo "could not resolve open-meteo container IP" >&2; exit 1; }
echo "open-meteo container at ${OM_IP}:8080 (container network only)"

# ── 4. nginx edge: TLS + mandatory bearer + optional source-IP allowlist.
if ! command -v nginx >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nginx
fi

allow_block=""
if [[ -n "$ALLOW_IPS" ]]; then
  for ip in $ALLOW_IPS; do
    allow_block+="        allow ${ip};"$'\n'
  done
  allow_block+="        deny all;"$'\n'
fi

install -d /var/www/certbot
cat >"$NGINX_AVAIL" <<CONF
# Open-Meteo node for GAIA. Generated by scripts/deploy_om_node.sh — do not hand-edit.
#
# Auth is REQUIRED here, not optional: without it this is a free unauthenticated
# weather mirror on our bandwidth, and it would make third parties remote users of
# an AGPL program (see the script header).
upstream om_node { server ${OM_IP}:8080; keepalive 8; }

limit_req_zone \$binary_remote_addr zone=om_node:10m rate=30r/s;

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    # `http2 on;` is nginx >= 1.25 only, and an older host fails `nginx -t` on it,
    # aborting the deploy. The listen-parameter form works on both.
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    # Bearer gate. \$http_authorization is compared to the token this script
    # generated; GAIA sends it as GAIA_OM_AUTH_TOKEN.
    set \$om_expected "Bearer ${TOKEN}";

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }

    location / {
${allow_block}        if (\$http_authorization != \$om_expected) { return 401; }
        limit_req zone=om_node burst=60 nodelay;
        proxy_pass http://om_node;
        proxy_set_header Host \$host;
        proxy_read_timeout 30s;
    }
}
CONF
ln -sfn "$NGINX_AVAIL" "$NGINX_ENABLED"
chmod 0640 "$NGINX_AVAIL"

if [[ "$DO_TLS" -eq 1 ]]; then
  if ! command -v certbot >/dev/null; then
    apt-get update -qq && apt-get install -y -qq certbot python3-certbot-nginx
  fi
  if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    # HTTP-only vhost for the first issue, then reinstall the TLS conf above.
    cat >"$NGINX_AVAIL" <<HTTPONLY
server {
    listen 80;
    server_name ${DOMAIN};
    location ^~ /.well-known/acme-challenge/ { root /var/www/certbot; try_files \$uri =404; }
    location / { return 404; }
}
HTTPONLY
    nginx -t && systemctl reload nginx
    args=(certonly --webroot -w /var/www/certbot --non-interactive --agree-tos
          --keep-until-expiring -d "$DOMAIN")
    [[ -n "$EMAIL" ]] && args+=(-m "$EMAIL") || args+=(--register-unsafely-without-email)
    certbot "${args[@]}"
    # Re-run once to install the TLS conf now that the cert exists. Guarded: certbot
    # can succeed into a suffixed lineage (…-0001), leaving the path we test for
    # still absent — an unguarded re-exec would then loop forever as root.
    if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
      echo "certbot succeeded but /etc/letsencrypt/live/${DOMAIN}/fullchain.pem is absent." >&2
      echo "  Likely a suffixed lineage. Check: ls -d /etc/letsencrypt/live/${DOMAIN}*" >&2
      echo "  Then re-run with OM_NODE_DOMAIN set to that lineage name." >&2
      exit 1
    fi
    if [[ "${_OM_NODE_REEXEC:-0}" == "1" ]]; then
      echo "internal: already re-executed once; refusing to loop." >&2
      exit 1
    fi
    export _OM_NODE_REEXEC=1
    exec "$0" "$@"
  fi
  systemctl enable --now certbot.timer 2>/dev/null || true
else
  echo "--no-tls: keep this host reachable only over a private network (WireGuard/Tailscale)."
fi

nginx -t
systemctl reload nginx

# ── 5. Smoke: a healthy container is NOT a usable relay. Prove a synced value, and
#       prove the auth gate actually refuses an unauthenticated caller.
echo "── smoke ──"
probe="/v1/forecast?latitude=52.52&longitude=13.41&current=temperature_2m"
echo -n "Waiting for a synced reading (first sync of ${GAIA_OM_SYNC_MODELS} can take a while) "
ok=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 5 "http://${OM_IP}:8080${probe}" 2>/dev/null | grep -q '"temperature_2m"'; then
    ok=1; echo " — ok"; break
  fi
  echo -n "."; sleep 5
done
if [[ "$ok" -ne 1 ]]; then
  echo
  echo "WARN: no synced data yet — om-* pins stay offline until it lands." >&2
  echo "      Follow: docker compose -f $COMPOSE logs -f open-meteo-sync" >&2
fi

if [[ "$DO_TLS" -eq 1 ]]; then
  code_noauth="$(curl -s -o /dev/null -w '%{http_code}' "https://${DOMAIN}${probe}" || true)"
  code_auth="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${TOKEN}" \
               "https://${DOMAIN}${probe}" || true)"
  echo "edge without bearer → ${code_noauth} (must be 401)"
  echo "edge with bearer    → ${code_auth}"
  [[ "$code_noauth" == "401" ]] || echo "WARN: the auth gate is NOT refusing anonymous callers — fix before relying on it." >&2
fi

cat <<DONE

Open-Meteo node up. On the GAIA host, point GAIA at it:

  export GAIA_OM_BASE_URL=https://${DOMAIN}
  export GAIA_OM_AQ_BASE_URL=https://${DOMAIN}
  export GAIA_OM_MARINE_BASE_URL=https://${DOMAIN}
  export GAIA_OM_AUTH_TOKEN=${TOKEN}
  sudo -E ./scripts/deploy_gaia.sh

deploy_gaia.sh detects a remote origin: it skips the local open-meteo and the local
disk gate, and probes this node before relying on it.

Reminder: air-quality and marine need their own models synced here
(OM_NODE_MODELS) or those relays 404 and their pins stay offline.
DONE
