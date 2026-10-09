#!/usr/bin/env bash
# Deploy HESTIA, the hearth, on the host that serves hestia.modelmarket.dev (today: hunt,
# ssh alias competing-lab).
#
#   ./scripts/deploy_hestia.sh --remote competing-lab    # from a laptop: sync, then deploy there
#   sudo ./scripts/deploy_hestia.sh                       # on the host itself
#   sudo ./scripts/deploy_hestia.sh --no-tls
#   sudo ./scripts/deploy_hestia.sh --new-host            # first deploy, before DNS moves here
#   CERTBOT_EMAIL=you@x.dev ./scripts/deploy_hestia.sh --remote competing-lab
#
# What one run does, in order:
#   1. Refuses unless the A record of the domain points at THIS host (--new-host overrides).
#      A second hearth keeps a second ledger: payments, owners and names would split. A copy
#      kept for rollback on a previous host must never come up while this one serves.
#   2. hestia/.env on the host is the one source of settings. HESTIA_DEPLOY_TOKEN,
#      HESTIA_PUBLIC_BASE and HESTIA_POSTGRES_PASSWORD from the environment only fill it when
#      it has none; a value that differs from the file is refused, never laid over it.
#   3. Backs up before anything changes: a pg_dump of the ledger (migrations apply on boot)
#      and a rollback tag on every running image. Keeps the last 10 dumps and 3 tags.
#   4. Builds and starts with the profile HESTIA_RUNTIME needs (wasm: the sandbox runner too),
#      waits until the hearth AND the runner are healthy, and checks the runtime the hearth
#      reports against the file.
#   5. nginx: keeps the live TLS vhost (installs the repo copy when it differs), or
#      bootstraps HTTP and runs certbot.
#
# Prereqs: DNS A record hestia.modelmarket.dev -> this host (do not invent a box), Docker +
# compose, nginx, certbot. Never prints a secret. Idempotent. The laptop path rsyncs the
# Hestia slice only, never the whole monorepo, never --delete of /root/claudecode/aicom.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${HESTIA_PUBLIC_DOMAIN:-hestia.modelmarket.dev}"
PROJECT="hestia"
COMPOSE="$ROOT/hestia/docker-compose.yml"
LEDGER_OVERLAY="$ROOT/hestia/docker-compose.postgres.yml"
ENV_FILE="$ROOT/hestia/.env"
NGINX_CONF_SRC="$ROOT/deploy/nginx/hestia.modelmarket.dev.conf"
NGINX_AVAIL="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
BACKUP_DIR="${HESTIA_BACKUP_DIR:-/root/hestia-backups}"
KEEP_DUMPS=10
KEEP_TAGS=3
EMAIL="${CERTBOT_EMAIL:-}"
DO_TLS=1
NEW_HOST=0
REMOTE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-tls) DO_TLS=0 ;;
    --new-host) NEW_HOST=1 ;;
    --remote)
      REMOTE="${2:-}"
      [[ -n "$REMOTE" ]] || { echo "--remote requires a host" >&2; exit 1; }
      shift
      ;;
    --remote=*) REMOTE="${1#--remote=}" ;;
    -h|--help) sed -n '2,29p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done

install_remote() {
  local host="$REMOTE"
  local dest="/root/claudecode/aicom"
  echo "Rsync hestia slice + nginx conf + this script -> ${host}:${dest} ..."
  ssh -o BatchMode=yes "$host" "mkdir -p ${dest}/hestia ${dest}/deploy/nginx ${dest}/scripts"
  rsync -az --delete \
    --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' \
    --exclude '.coverage' --exclude '.DS_Store' --exclude 'data' \
    --exclude '.env' --exclude '.git' \
    --filter 'P .env' --filter 'P data/' \
    "$ROOT/hestia/" "${host}:${dest}/hestia/"
  scp -q -o BatchMode=yes "$NGINX_CONF_SRC" "${host}:${dest}/deploy/nginx/hestia.modelmarket.dev.conf"
  scp -q -o BatchMode=yes "$ROOT/scripts/deploy_hestia.sh" "${host}:${dest}/scripts/deploy_hestia.sh"

  local flags=""
  [[ "$DO_TLS" -eq 1 ]] || flags+=" --no-tls"
  [[ "$NEW_HOST" -eq 0 ]] || flags+=" --new-host"
  # Settings live in the host's hestia/.env. Nothing secret crosses this line: only
  # CERTBOT_EMAIL, and only when it is set.
  local env_prefix=""
  [[ -z "$EMAIL" ]] || env_prefix="CERTBOT_EMAIL=$(printf %q "$EMAIL") "
  ssh -o BatchMode=yes "$host" bash -s <<EOF
set -euo pipefail
cd ${dest}
chmod +x scripts/deploy_hestia.sh
if [[ "\$(id -u)" -eq 0 ]]; then
  ${env_prefix}./scripts/deploy_hestia.sh${flags}
else
  sudo ${env_prefix}./scripts/deploy_hestia.sh${flags}
fi
EOF
}

if [[ -n "$REMOTE" ]]; then
  install_remote
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the host that serves ${DOMAIN}: sudo $0" >&2
  echo "From a laptop: $0 --remote competing-lab" >&2
  exit 1
fi
for required in "$COMPOSE" "$LEDGER_OVERLAY" "$NGINX_CONF_SRC"; do
  if [[ ! -f "$required" ]]; then
    echo "ERROR: missing $required. Sync hestia/ (and the nginx conf) onto this host first;" >&2
    echo "production deploy requires the ledger overlay docker-compose.postgres.yml." >&2
    exit 1
  fi
done

# ── 1. this host, and no other ────────────────────────────────────────────────
host_ips="$(hostname -I 2>/dev/null || true)"
dns_ips="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ' || true)"
dns_matches_host=0
for ip in $dns_ips; do
  for own in $host_ips; do
    if [[ "$ip" == "$own" ]]; then
      dns_matches_host=1
    fi
  done
done
if [[ "$dns_matches_host" -eq 0 && "$NEW_HOST" -eq 0 ]]; then
  echo "ERROR: ${DOMAIN} resolves to '${dns_ips:-nothing}', not to this host (${host_ips})." >&2
  echo "Another hearth serves it. A second one here would keep a second ledger, and payments," >&2
  echo "owners and names would split between them. Deploy where DNS points, or pass" >&2
  echo "--new-host to bring a hearth up before the A record moves here." >&2
  exit 1
fi

# ── 2. hestia/.env is the one source of settings ──────────────────────────────
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

env_value() {
  awk -F= -v key="$1" '$1==key{print substr($0,index($0,"=")+1); exit}' "$ENV_FILE"
}

# The file wins. A value in the environment fills the file when the file has none, and is
# refused when it differs: compose would lay it over the file for this one run, and the next
# deploy without it would quietly undo it. Afterwards the variable is unset, so compose reads
# the file alone. Values are compared, never printed.
settle() {
  local name="$1" fallback="${2:-}" in_file in_env value
  in_file="$(env_value "$name")"
  in_env="${!name:-}"
  if [[ -n "$in_file" ]]; then
    if [[ -n "$in_env" && "$in_env" != "$in_file" ]]; then
      echo "ERROR: $name in the environment differs from hestia/.env. Change it in the file" >&2
      echo "(the hearth reads only the file), or unset it here." >&2
      exit 1
    fi
  else
    value="${in_env:-$fallback}"
    if [[ -z "$value" ]]; then
      echo "ERROR: $name is empty. Put it in hestia/.env on this host" >&2
      echo "(HESTIA_DEPLOY_TOKEN: empty token refuses every write — set a secret)." >&2
      exit 1
    fi
    printf '%s=%s\n' "$name" "$value" >> "$ENV_FILE"
    echo "hestia/.env: $name added"
  fi
  unset "$name"
}
settle HESTIA_DEPLOY_TOKEN
settle HESTIA_PUBLIC_BASE "https://${DOMAIN}"
settle HESTIA_POSTGRES_PASSWORD "$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
chmod 600 "$ENV_FILE"

RUNTIME="$(env_value HESTIA_RUNTIME)"
RUNTIME="${RUNTIME:-stub}"
PROFILE_ARGS=()
SERVICES=(hestia)
if [[ "$RUNTIME" == "wasm" ]]; then
  # The sandbox runner is a compose profile: without it, it is neither built nor started,
  # and a wasm hearth keeps calling an old runner (or none).
  PROFILE_ARGS=(--profile wasm)
  SERVICES+=(hestia-runner)
fi

compose() {
  # ${a[@]+"${a[@]}"}: an empty array under `set -u` is an error before bash 4.4.
  docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE" -f "$LEDGER_OVERLAY" \
    ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} "$@"
}

echo "=== HESTIA deploy -> https://${DOMAIN} (runtime ${RUNTIME}: ${SERVICES[*]}) ==="

# ── 3. backups before anything changes ────────────────────────────────────────
TS="$(date -u +%Y%m%d-%H%M%S)"
DUMP=""
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
if [[ -n "$(compose ps -q hestia-postgres 2>/dev/null || true)" ]]; then
  DUMP="$BACKUP_DIR/hestia-pg-${TS}.sql.gz"
  (umask 077; compose exec -T hestia-postgres pg_dump -U hestia -d hestia | gzip > "$DUMP")
  tables="$(gzip -dc "$DUMP" | grep -c '^CREATE TABLE public\.' || true)"
  if [[ "${tables:-0}" -lt 1 ]]; then
    echo "ERROR: the ledger dump $DUMP holds no tables; not deploying." >&2
    exit 1
  fi
  echo "Ledger backed up: $DUMP (${tables} tables)"
  # Names carry the UTC time, so name order is age order (a file's mtime can lie).
  ls -1 "$BACKUP_DIR"/hestia-pg-*.sql.gz | sort -r | tail -n +$((KEEP_DUMPS + 1)) | xargs -r rm -f
else
  echo "No running ledger yet: nothing to back up."
fi

ROLLBACK_TAGS=()
for svc in "${SERVICES[@]}"; do
  cid="$(compose ps -q "$svc" 2>/dev/null || true)"
  [[ -n "$cid" ]] || continue
  repo="${PROJECT}-${svc}"
  docker tag "$(docker inspect -f '{{.Image}}' "$cid")" "${repo}:pre-deploy-${TS}"
  ROLLBACK_TAGS+=("${repo}:pre-deploy-${TS}")
  docker images --format '{{.Tag}}' "$repo" | grep '^pre-deploy-' | sort -r \
    | tail -n +$((KEEP_TAGS + 1)) | while read -r old; do
        docker rmi "${repo}:${old}" >/dev/null 2>&1 || true
      done
done
[[ ${#ROLLBACK_TAGS[@]} -eq 0 ]] || echo "Rollback images: ${ROLLBACK_TAGS[*]}"

rollback_hint() {
  echo "Roll back: docker tag each ${PROJECT}-<service>:pre-deploy-${TS} as ${PROJECT}-<service>:latest," >&2
  echo "  then: docker compose -p ${PROJECT} --env-file hestia/.env -f hestia/docker-compose.yml \\" >&2
  echo "        -f hestia/docker-compose.postgres.yml ${PROFILE_ARGS[*]:-} up -d --no-build" >&2
  [[ -z "$DUMP" ]] || echo "  If a migration ran, restore $DUMP into hestia-postgres." >&2
}

# ── 4. build, start, and prove it came up as configured ───────────────────────
echo "Building + starting (hearth on 127.0.0.1:9480, ledger in hestia-postgres) ..."
compose up -d --build

wait_healthy() {
  local svc="$1" cid status="missing"
  for _ in $(seq 1 90); do
    cid="$(compose ps -q "$svc" 2>/dev/null || true)"
    if [[ -n "$cid" ]]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")"
    fi
    if [[ "$status" == "healthy" ]]; then
      echo "$svc: healthy"
      return 0
    fi
    if [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]]; then
      break
    fi
    sleep 2
  done
  echo "ERROR: $svc is ${status}; check: docker compose -p ${PROJECT} logs $svc" >&2
  return 1
}
for svc in "${SERVICES[@]}"; do
  wait_healthy "$svc" || { rollback_hint; exit 1; }
done

health="$(curl -sf --max-time 5 http://127.0.0.1:9480/health || true)"
if [[ "$health" != *'"service":"hestia"'* ]]; then
  echo "health did not identify as hestia: $health" >&2
  rollback_hint
  exit 1
fi
reported="$(printf '%s' "$health" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("runtime", ""))')"
if [[ "$reported" != "$RUNTIME" ]]; then
  echo "ERROR: the hearth reports runtime '${reported}', hestia/.env says '${RUNTIME}'." >&2
  rollback_hint
  exit 1
fi
echo "Hearth answers as hestia, runtime ${reported}."

# ── 5. nginx, the TLS edge ────────────────────────────────────────────────────
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

LIVE_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
if [[ "$DO_TLS" -eq 1 && "$dns_matches_host" -eq 0 && ! -f "$LIVE_CERT" ]]; then
  echo "DNS ${DOMAIN} -> ${dns_ips:-nothing}, this host IPs: ${host_ips}."
  echo "Skipping certbot until the A record points at this host."
  DO_TLS=0
fi

SKIPPED_EXISTING_CERT=0
NGINX_CHANGED=1
if [[ -f "$LIVE_CERT" ]]; then
  # Keep the existing TLS vhost. hostname -I may list a docker bridge first;
  # do not replace a live cert with the HTTP bootstrap.
  echo "Live cert already present for ${DOMAIN}; keeping TLS vhost, not re-issuing."
  if [[ -f "$NGINX_AVAIL" ]] && cmp -s "$NGINX_CONF_SRC" "$NGINX_AVAIL"; then
    echo "nginx vhost unchanged."
    NGINX_CHANGED=0
  else
    install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
    echo "nginx vhost updated from the repo copy."
  fi
  DO_TLS=0
  SKIPPED_EXISTING_CERT=1
else
  install_http_bootstrap
fi
if [[ ! -L "$NGINX_ENABLED" ]]; then
  ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
  NGINX_CHANGED=1
fi
if [[ "$NGINX_CHANGED" -eq 1 ]]; then
  nginx -t
  systemctl enable nginx >/dev/null 2>&1 || true
  systemctl reload nginx
fi

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
elif [[ "$SKIPPED_EXISTING_CERT" -eq 1 ]]; then
  systemctl enable --now certbot.timer >/dev/null 2>&1 || true
else
  echo "Serving plain HTTP on :80 (TLS skipped until DNS matches this host)."
fi

echo
echo "=== HESTIA on this host ==="
echo "  Health:   http://127.0.0.1:9480/health"
echo "  Console:  http://127.0.0.1:9480/ui/"
echo "  Public:   https://${DOMAIN}/"
echo "  Roster:   https://${DOMAIN}/v1/hearth"
[[ -z "$DUMP" ]] || echo "  Ledger dump before this deploy: $DUMP"
[[ ${#ROLLBACK_TAGS[@]} -eq 0 ]] || echo "  Rollback images: ${ROLLBACK_TAGS[*]}"
