#!/usr/bin/env bash
# Deploy EMPORION behind the modelmarket.dev nginx, at https://modelmarket.dev/providers/emporion/.
#
#   ./scripts/deploy_emporion.sh --remote factory-vps      # from a laptop: sync, then deploy there
#   sudo ./scripts/deploy_emporion.sh                      # on the host: redeploy what /opt/emporion holds
#
# Served under a path of an existing name, so no DNS record is needed; to give it a name of
# its own later, add the A record, a server block, and set EMPORION_PUBLIC_URL in /opt/emporion/.env.
#
# The host keeps /opt/emporion/.env and the emporion_data volume (signing key) and nothing else
# of its own. The running image is kept as emporion:prev; a build that does not come up healthy
# is replaced by it again. nginx is changed only through one snippet file and one include line,
# with a backup and `nginx -t` before any reload. Idempotent.
set -euo pipefail

DEST="/opt/emporion"
PREFIX="/providers/emporion"
SITE="${EMPORION_NGINX_SITE:-}"
REMOTE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="${2:?--remote needs a host}"; shift ;;
    --remote=*) REMOTE="${1#--remote=}" ;;
    --site) SITE="${2:?--site needs an nginx site file}"; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -n "$REMOTE" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  echo "Syncing emporion + oracle-core → ${REMOTE}:${DEST}/src …"
  ssh -o BatchMode=yes "$REMOTE" "mkdir -p ${DEST}/src/oracles ${DEST}/src/emporion ${DEST}/deploy"
  common=(--exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'data'
          --exclude '.env' --exclude '.env.*' --exclude '.DS_Store' --exclude '.git')
  rsync -az --delete "${common[@]}" "$ROOT/emporion/" "${REMOTE}:${DEST}/src/emporion/"
  rsync -az --delete "${common[@]}" "$ROOT/oracles/core/" "${REMOTE}:${DEST}/src/oracles/core/"
  scp -q -o BatchMode=yes "$ROOT/scripts/deploy_emporion.sh" "${REMOTE}:${DEST}/deploy/deploy_emporion.sh"
  site_arg=""
  [[ -n "$SITE" ]] && site_arg="--site ${SITE}"
  ssh -o BatchMode=yes "$REMOTE" "sudo bash ${DEST}/deploy/deploy_emporion.sh ${site_arg}"
  exit 0
fi

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on the host, or use --remote <host> from a laptop" >&2; exit 1; }
[[ -f "$DEST/src/emporion/docker-compose.yml" ]] || { echo "no emporion slice in $DEST/src" >&2; exit 1; }

ENV_FILE="$DEST/.env"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
ensure() {  # ensure KEY VALUE — append only when absent; never print the value
  grep -q "^$1=" "$ENV_FILE" || { printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"; echo "  created $1"; }
}
ensure EMPORION_PUBLIC_URL "https://modelmarket.dev${PREFIX}"
ensure ORACLE_PQC 1
# The GitHub Pages landing reads the live lists for its scene (public data, no cookies).
ensure EMPORION_CORS_ORIGINS "https://alexar76.github.io"

COMPOSE=(docker compose -p emporion --env-file "$ENV_FILE" -f "$DEST/src/emporion/docker-compose.yml")
IMAGE="emporion"
docker image inspect "${IMAGE}:latest" >/dev/null 2>&1 && docker image tag "${IMAGE}:latest" "${IMAGE}:prev"

wait_healthy() {
  for _ in $(seq 1 60); do
    curl -sf --max-time 3 http://127.0.0.1:9351/health >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

echo "Building and starting EMPORION …"
"${COMPOSE[@]}" up -d --build
if ! wait_healthy; then
  echo "EMPORION did not come up healthy" >&2
  "${COMPOSE[@]}" logs --tail 40 emporion >&2 || true
  if docker image inspect "${IMAGE}:prev" >/dev/null 2>&1; then
    echo "rolling back to ${IMAGE}:prev" >&2
    docker image tag "${IMAGE}:prev" "${IMAGE}:latest"
    "${COMPOSE[@]}" up -d --no-build
    wait_healthy || echo "the previous image is not healthy either" >&2
  fi
  exit 1
fi
echo "  healthy on 127.0.0.1:9351"

# ── nginx: one snippet, one include in the HTTPS server block of modelmarket.dev ──
SNIPPET="/etc/nginx/snippets/emporion.conf"
if [[ -z "$SITE" ]]; then
  # The apex only: a word boundary would also match atlas.modelmarket.dev and friends.
  SITE="$(grep -lE 'server_name([[:space:]]+[^;[:space:]]+)*[[:space:]]+modelmarket\.dev([[:space:]]|;)' \
          /etc/nginx/sites-enabled/* 2>/dev/null | xargs -r grep -l 'listen[^;]*443' | head -1 || true)"
fi
[[ -n "$SITE" && -f "$SITE" ]] || { echo "no nginx site for modelmarket.dev found; pass --site" >&2; exit 1; }
SITE="$(readlink -f "$SITE")"
mkdir -p /etc/nginx/snippets
cat > "$SNIPPET.new" <<NGINX
# EMPORION — managed by deploy_emporion.sh; edit there, not here.
location = ${PREFIX} { return 301 ${PREFIX}/; }
# The call log's operator API (/ops/v1/*) stays on loopback; token-gated, but not public.
location ^~ ${PREFIX}/ops/ { return 404; }
location ${PREFIX}/ {
    proxy_pass http://127.0.0.1:9351/;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_read_timeout 90s;
    client_max_body_size 256k;
}
NGINX
stamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="/root/nginx-backups"
mkdir -p "$backup_dir"
cp -a "$SITE" "$backup_dir/$(basename "$SITE").${stamp}-before-emporion"
[[ -f "$SNIPPET" ]] && cp -a "$SNIPPET" "$backup_dir/emporion.conf.${stamp}"
mv "$SNIPPET.new" "$SNIPPET"
if ! grep -q 'snippets/emporion.conf' "$SITE"; then
  python3 - "$SITE" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path).read()
# The first server block that listens on 443 and names modelmarket.dev gets the include,
# right after its server_name line.
blocks = list(re.finditer(r"server\s*\{", text))
for m in blocks:
    depth, i = 0, m.end() - 1
    while i < len(text):
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0: break
        i += 1
    body = text[m.start():i]
    names = re.search(r"server_name([^;]*);", body)
    apex = names and "modelmarket.dev" in names.group(1).split()
    if re.search(r"listen[^;]*443", body) and apex:
        sn = re.search(r"server_name[^;]*;", body)
        at = m.start() + sn.end()
        text = text[:at] + "\n    include snippets/emporion.conf;" + text[at:]
        open(path, "w").write(text)
        print("  include added to", path)
        break
else:
    sys.exit("no HTTPS server block for modelmarket.dev in " + path)
PY
fi
if ! nginx -t 2>/dev/null; then
  echo "nginx -t failed — restoring the site and the snippet" >&2
  cp -a "$backup_dir/$(basename "$SITE").${stamp}-before-emporion" "$SITE"
  if [[ -f "$backup_dir/emporion.conf.${stamp}" ]]; then
    cp -a "$backup_dir/emporion.conf.${stamp}" "$SNIPPET"
  else
    rm -f "$SNIPPET"
  fi
  nginx -t
  exit 1
fi
systemctl reload nginx
echo "  nginx reloaded (backup: $backup_dir/$(basename "$SITE").${stamp}-before-emporion)"

# After a reload the old workers keep serving their open connections with the old config
# for a while, so the first answers may still be 404; give the new workers up to ~30 s.
for path in health ai-market/v2/manifest; do
  for _ in $(seq 1 10); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://modelmarket.dev${PREFIX}/${path}")"
    [[ "$code" == "200" ]] && break
    sleep 3
  done
  echo "  https://modelmarket.dev${PREFIX}/${path} → ${code}"
  [[ "$code" == "200" ]] || { echo "public check failed" >&2; exit 1; }
done
echo "EMPORION deployed."
