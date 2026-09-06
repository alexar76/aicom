#!/usr/bin/env bash
# Deploy GAIA — physical-world oracle gateway — on the ORACLE HOST (203.0.113.20),
# alongside the oracle family, published on its own domain iot.modelmarket.dev.
#
#   sudo ./scripts/deploy_gaia.sh              # build + up + nginx + TLS
#   sudo ./scripts/deploy_gaia.sh --no-tls     # skip certbot (HTTP only / behind another edge)
#   sudo CERTBOT_EMAIL=you@x.dev ./scripts/deploy_gaia.sh
#   sudo ./scripts/deploy_gaia.sh --om-hosted  # om-* from Open-Meteo's hosted free API
#
# OPEN-METEO: self-hosted BY DEFAULT (gaia/docker-compose.om-node.yml + .om-selfhost.yml), because
# the hosted free API's ToS is non-commercial while the data itself is CC BY 4.0.
# Needs disk for weather-model data (~32-48 GB narrow, 150 GB+ comprehensive) — this
# script refuses rather than half-deploying if the disk is too small. `--om-hosted`
# opts out and is correct for a free/demo deployment; it is a licence violation the
# moment you enable payments, which GAIA then refuses to boot.
#
# Prereqs (same host as the oracles):
#   * DNS A record  iot.modelmarket.dev → 203.0.113.20  (you add this in the panel)
#   * Docker + docker compose, nginx, certbot present (the oracle host already has them)
#   * the shared `ecosystem` docker network exists (created by the hub/oracles stack)
#
# Idempotent: re-run to redeploy after a `git pull`. Loopback-only containers,
# nginx is the sole TLS edge (matches the oracle-family topology).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# GAIA answers on both a descriptive (iot) and a branded (gaia) hostname; the
# first is the canonical/primary (nginx site filename, cert lineage name).
DOMAINS="${GAIA_PUBLIC_DOMAINS:-iot.modelmarket.dev gaia.modelmarket.dev}"
read -r DOMAIN _ <<<"$DOMAINS"   # primary = first token
COMPOSE="$ROOT/gaia/docker-compose.yml"
NGINX_CONF_SRC="$ROOT/deploy/nginx/iot.modelmarket.dev.conf"
NGINX_AVAIL="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
EMAIL="${CERTBOT_EMAIL:-}"
DO_TLS=1
OM_SELFHOST=1
# Two files: the Open-Meteo services (valid standalone, so a big-disk host can run
# just them) plus the thin overlay that repoints gaia-backend at them.
OM_NODE_FILE="$ROOT/gaia/docker-compose.om-node.yml"
OM_OVERLAY="$ROOT/gaia/docker-compose.om-selfhost.yml"
# Narrow variable set → the low end of the disk range. Raise both together.
OM_MIN_FREE_GB="${GAIA_OM_MIN_FREE_GB:-48}"
for arg in "$@"; do
  case "$arg" in
    --no-tls) DO_TLS=0 ;;
    --om-hosted) OM_SELFHOST=0 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the oracle host (203.0.113.20): sudo $0" >&2
  exit 1
fi

echo "=== GAIA deploy → https://${DOMAIN} (physical-world oracle gateway) ==="

# ── 1. The shared ecosystem network (GAIA joins it; never owns it) ────────────
if ! docker network inspect ecosystem >/dev/null 2>&1; then
  echo "Creating shared 'ecosystem' docker network (was absent)…"
  docker network create ecosystem
fi

# ── 1b. Open-Meteo origin: self-hosted by default (licence), disk-gated ───────
# Pre-flight the disk BEFORE composing. `open-meteo sync` failing halfway leaves an
# API that answers 404 for every variable, and GAIA would then mark every om-* pin
# offline — a silent coverage loss across 21 of 34 weather pins. Refuse instead.
COMPOSE_FILES=(-f "$COMPOSE")
# Three modes, not two. If GAIA_OM_BASE_URL already points at an operator-run
# instance on ANOTHER host (the big-disk node), we must neither start a local
# open-meteo nor demand local disk for model data we are not storing.
OM_REMOTE=""
if [[ -n "${GAIA_OM_BASE_URL:-}" ]]; then
  case "${GAIA_OM_BASE_URL}" in
    *open-meteo.com*)
      # Their own host — free tier or the customer endpoint of a paid plan. Either
      # way there is nothing to run and nothing to store locally.
      OM_SELFHOST=0
      ;;
    http://open-meteo:8080)
      # Explicitly the compose-internal instance: keep the local self-host path.
      ;;
    *)
      OM_REMOTE="${GAIA_OM_BASE_URL}"
      OM_SELFHOST=0
      ;;
  esac
fi

if [[ -n "$OM_REMOTE" ]]; then
  echo "Open-Meteo: REMOTE operator-run instance ${OM_REMOTE} — no local model data."
  if [[ "$OM_REMOTE" == http://* ]] && [[ -z "${GAIA_OM_AUTH_TOKEN:-}" ]]; then
    echo "  WARN: plaintext http across hosts with no GAIA_OM_AUTH_TOKEN." >&2
    echo "        Put TLS + a bearer in front of it (deploy/nginx/om.modelmarket.dev.conf)," >&2
    echo "        or keep the hop inside a private network (WireGuard/Tailscale)." >&2
  fi
  # Prove the remote origin actually answers with a synced value before we rely on it.
  om_probe="${OM_REMOTE%/}/v1/forecast?latitude=52.52&longitude=13.41&current=temperature_2m"
  om_hdr=()
  [[ -n "${GAIA_OM_AUTH_TOKEN:-}" ]] && om_hdr=(-H "Authorization: Bearer ${GAIA_OM_AUTH_TOKEN}")
  if curl -fsS --max-time 15 "${om_hdr[@]}" "$om_probe" 2>/dev/null | grep -q '"temperature_2m"'; then
    echo "  remote instance serves a synced reading — ok"
  else
    echo "  WARN: ${OM_REMOTE} did not return temperature_2m." >&2
    echo "        Either the sync has not landed or the edge rejected us; om-* pins will" >&2
    echo "        stay offline until it does. Check on that host:" >&2
    echo "          docker compose -f gaia/docker-compose.om-node.yml logs -f open-meteo-sync" >&2
  fi
elif [[ "$OM_SELFHOST" -eq 1 ]]; then
  docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo /var/lib/docker)"
  free_gb="$(df -BG --output=avail "$docker_root" 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)"
  if [[ -z "$free_gb" ]]; then free_gb=0; fi
  if (( free_gb < OM_MIN_FREE_GB )); then
    cat >&2 <<MSG

REFUSING: self-hosted Open-Meteo needs ~${OM_MIN_FREE_GB} GB free on ${docker_root}; found ${free_gb} GB.
Weather-model data is the cost of not billing calls against a non-commercial ToS.
Pick one:
  * put it on a big-disk host instead (recommended when this one is tight):
      sudo ./scripts/deploy_om_node.sh            # on that host
      GAIA_OM_BASE_URL=https://om.example.dev GAIA_OM_AUTH_TOKEN=… $0   # here
  * free up disk (or set GAIA_OM_MIN_FREE_GB if you sync a narrower variable set)
  * buy an Open-Meteo plan: set GAIA_OM_BASE_URL to the customer endpoint
    + GAIA_OM_API_KEY, then re-run with --om-hosted
  * stay non-commercial: re-run with --om-hosted and leave payments off
    (AIFACTORY_CRYPTO_ENABLED=0)
MSG
    exit 1
  fi
  COMPOSE_FILES+=(-f "$OM_NODE_FILE" -f "$OM_OVERLAY")
  echo "Open-Meteo: SELF-HOSTED (${free_gb} GB free on ${docker_root}) — om-* relays commercially clean."
elif [[ -n "${GAIA_OM_BASE_URL:-}" ]]; then
  echo "Open-Meteo: HOSTED at ${GAIA_OM_BASE_URL} — no local instance, no model data."
  if [[ -z "${GAIA_OM_API_KEY:-}" && "${GAIA_OM_ALLOW_HOSTED_COMMERCIAL:-0}" != "1" ]]; then
    echo "  NOTE: no GAIA_OM_API_KEY and no GAIA_OM_ALLOW_HOSTED_COMMERCIAL — GAIA will" >&2
    echo "        refuse om-* relays if payments are on (free-tier ToS is non-commercial)." >&2
  fi
else
  echo "Open-Meteo: HOSTED FREE API (--om-hosted). Non-commercial ToS —"
  echo "  GAIA refuses to boot om-* relays if AIFACTORY_CRYPTO_ENABLED=1."
fi

# Host .env is gitignored. Pass it via --env-file so ${GAIA_*} interpolate
# without sourcing bash (secrets may contain ! and other metacharacters).
COMPOSE_ENV=()
if [[ -f "$ROOT/.env" ]]; then
  COMPOSE_ENV+=(--env-file "$ROOT/.env")
fi

# ── 2. Build + (re)start the loopback-only containers ─────────────────────────
# Build context is the monorepo root (the backend image needs oracle-core).
echo "Building + starting gaia-backend (127.0.0.1:9320) + gaia-frontend (127.0.0.1:5185)…"
docker compose "${COMPOSE_ENV[@]}" "${COMPOSE_FILES[@]}" up -d --build

# ── 2b. Prove the self-hosted instance actually serves a reading ──────────────
# The API answers only for variables that have been synced, so a healthy container
# is not evidence of a usable relay. Check one real value through GAIA's own device.
if [[ "$OM_SELFHOST" -eq 1 ]]; then
  echo -n "Waiting for self-hosted Open-Meteo to serve a synced reading "
  om_ok=0
  for _ in $(seq 1 60); do
    if docker compose "${COMPOSE_FILES[@]}" exec -T gaia-backend python -c "
import sys, urllib.request, json
u='http://open-meteo:8080/v1/forecast?latitude=52.52&longitude=13.41&current=temperature_2m'
try:
    d=json.load(urllib.request.urlopen(u, timeout=5))
    sys.exit(0 if (d.get('current') or {}).get('temperature_2m') is not None else 1)
except Exception:
    sys.exit(1)
" >/dev/null 2>&1; then om_ok=1; echo " — ok"; break; fi
    echo -n "."; sleep 5
  done
  if [[ "$om_ok" -ne 1 ]]; then
    echo
    echo "WARN: self-hosted Open-Meteo is up but has no synced data yet." >&2
    echo "      First sync of ${GAIA_OM_SYNC_MODELS:-ecmwf_ifs025} can take a while; om-* pins stay" >&2
    echo "      offline until it lands. Follow: docker compose ${COMPOSE_FILES[*]} logs -f open-meteo-sync" >&2
  fi
fi

# ── 3. Health gate — do not touch nginx until the backend answers ─────────────
echo -n "Waiting for gaia-backend health on 127.0.0.1:9320 "
for i in $(seq 1 30); do
  if curl -sf --max-time 3 http://127.0.0.1:9320/health >/dev/null; then
    echo "— ok"; break
  fi
  echo -n "."; sleep 1
  if [[ "$i" -eq 30 ]]; then
    echo; echo "gaia-backend did not become healthy; check: docker compose ${COMPOSE_FILES[*]} logs gaia-backend" >&2
    exit 1
  fi
done
curl -sf --max-time 3 http://127.0.0.1:5185/ >/dev/null \
  && echo "gaia-frontend serving on 127.0.0.1:5185 — ok" \
  || echo "WARN: gaia-frontend not answering on 127.0.0.1:5185 yet (check its logs)"

# ── 4. nginx edge ─────────────────────────────────────────────────────────────
if ! command -v nginx >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nginx
fi
install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
mkdir -p /var/www/certbot
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx

# ── 5. TLS via Let's Encrypt ──────────────────────────────────────────────────
# The site conf already points at /etc/letsencrypt/live/${DOMAIN}/. `certbot --nginx`
# must not rewrite that file: a lock from another lineage used to abort after we
# overwrote a working 443 block, and SNI then served logos.modelmarket.dev.
if [[ "$DO_TLS" -eq 1 ]]; then
  if ! command -v certbot >/dev/null; then
    apt-get install -y -qq certbot python3-certbot-nginx
  fi
  CERT_LIVE="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
  if [[ -f "$CERT_LIVE" ]]; then
    echo "TLS lineage ${DOMAIN} already present — keeping repo nginx conf (no certbot --nginx rewrite)."
  else
    for _ in $(seq 1 12); do
      if [[ ! -e /var/lib/letsencrypt/.certbot.lock && ! -e /tmp/certbot.lock ]]; then
        break
      fi
      echo "certbot lock held — waiting"
      sleep 5
    done
    CERTBOT_ARGS=(certonly --webroot -w /var/www/certbot --non-interactive --agree-tos --cert-name "${DOMAIN}")
    for d in $DOMAINS; do
      if getent hosts "$d" >/dev/null 2>&1; then
        CERTBOT_ARGS+=(-d "$d")
      else
        echo "WARN: ${d} does not resolve yet — skipping it in the cert (re-run after DNS propagates)."
      fi
    done
    if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
    certbot "${CERTBOT_ARGS[@]}"
  fi
  [[ -f "$CERT_LIVE" ]] || { echo "ERROR: missing $CERT_LIVE — HTTPS vhost will fail nginx -t" >&2; exit 1; }
  nginx -t
  systemctl reload nginx
else
  echo "Skipping certbot (--no-tls). Serving plain HTTP on :80."
fi

echo
echo "=== GAIA live ==="
echo "  Landing (3D):   https://${DOMAIN}/"
echo "  Manifest:       https://${DOMAIN}/ai-market/v2/manifest"
echo "  Verifier slot:  https://${DOMAIN}/v1/verify"
echo "  WoT directory:  https://${DOMAIN}/wot"
echo "  Health:         https://${DOMAIN}/health"
echo
echo "Point the hub's Pay-on-Verified escrow at GAIA with:"
echo "  AIMARKET_VERIFY_METIS_URL=https://${DOMAIN}  AIMARKET_VERIFY_VERIFIER_ID=gaia.verify@v1"
