#!/usr/bin/env bash
# Deploy SYMMARTYS without replacing the existing provider identity.
# Usage: deploy_symmartys.sh [--remote HOST] [--dest /opt/PATH] [--site FILE]
#        deploy_symmartys.sh --check [--dest /opt/PATH]
#        deploy_symmartys.sh --render-vhost OUTPUT [--dest /opt/PATH]
# Existing /opt/emporion is preferred automatically; its .env and Docker data volume stay.
# --fresh-volume is an explicit new-identity installation, never an upgrade shortcut.
# A running legacy container is refused. Follow deploy/SYMMARTYS-UPGRADE.md for cutover.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/../deploy/symmartys_state.py"
TEMPLATE="$SCRIPT_DIR/../deploy/nginx/symmartys.modelmarket.dev.conf"
DEST=""
PREFIX="/providers/symmartys"
SITE="${SYMMARTYS_NGINX_SITE:-}"
REMOTE=""
CHECK=0
FRESH=0
RENDER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="${2:?--remote needs a host}"; shift ;;
    --remote=*) REMOTE="${1#--remote=}" ;;
    --dest) DEST="${2:?--dest needs an absolute directory}"; shift ;;
    --dest=*) DEST="${1#--dest=}" ;;
    --site) SITE="${2:?--site needs an nginx site file}"; shift ;;
    --check) CHECK=1 ;;
    --fresh-volume) FRESH=1 ;;
    --render-vhost) RENDER="${2:?--render-vhost needs an output file}"; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
[[ -f "$HELPER" ]] || { echo "missing deploy/symmartys_state.py" >&2; exit 1; }

if [[ -n "$REMOTE" ]]; then
  [[ "$REMOTE" =~ ^[[:alnum:]_][[:alnum:]_.@:-]*$ ]] || { echo "invalid SSH host" >&2; exit 2; }
  [[ -z "$RENDER" ]] || { echo "render the vhost locally with an explicit --dest" >&2; exit 2; }
  remote() { local command; printf -v command '%q ' "$@"; ssh -o BatchMode=yes "$REMOTE" "$command"; }
  if [[ -z "$DEST" ]]; then
    DEST="$(remote bash -c 'if [[ -d /opt/emporion ]]; then echo /opt/emporion; else echo /opt/symmartys; fi')"
  fi
  DEST="$(python3 "$HELPER" destination --dest "$DEST")"
  # Read-only refusal before rsync: do not replace or stop the legacy runtime.
  remote sudo -n bash -c 'docker info >/dev/null && if [[ "$(docker inspect --format "{{.State.Running}}" emporion 2>/dev/null || true)" == true ]]; then echo "Legacy container is running; follow deploy/SYMMARTYS-UPGRADE.md before cutover." >&2; exit 1; fi'
  [[ "$CHECK" -eq 0 ]] || { echo "Run --check on the host after staging the new source and helper; no remote files changed." >&2; exit 2; }
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  remote mkdir -p "$DEST/src/oracles" "$DEST/src/symmartys" "$DEST/deploy/nginx"
  common=(--exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'data'
          --exclude '.env' --exclude '.env.*' --exclude '.DS_Store' --exclude '.git')
  rsync -az --delete "${common[@]}" "$ROOT/symmartys/" "$REMOTE:$DEST/src/symmartys/"
  rsync -az --delete "${common[@]}" "$ROOT/oracles/core/" "$REMOTE:$DEST/src/oracles/core/"
  scp -q -o BatchMode=yes "$ROOT/scripts/deploy_symmartys.sh" "$ROOT/deploy/symmartys_state.py" "$REMOTE:$DEST/deploy/"
  scp -q -o BatchMode=yes "$TEMPLATE" "$REMOTE:$DEST/deploy/nginx/symmartys.modelmarket.dev.conf"
  options=(--dest "$DEST")
  [[ -n "$SITE" ]] && options+=(--site "$SITE")
  [[ "$FRESH" -eq 1 ]] && options+=(--fresh-volume)
  remote sudo -n bash "$DEST/deploy/deploy_symmartys.sh" "${options[@]}"
  exit 0
fi

dest_options=()
[[ -n "$DEST" ]] && dest_options=(--dest "$DEST")
DEST="$(python3 "$HELPER" destination "${dest_options[@]}")"
if [[ -n "$RENDER" ]]; then
  python3 "$HELPER" render-vhost --dest "$DEST" --template "$TEMPLATE" --output "$RENDER"
  echo "Rendered vhost for $DEST; review it before installation."
  exit 0
fi
[[ "$CHECK" -eq 1 || "$(id -u)" -eq 0 ]] || { echo "run as root on the host, or use --remote HOST" >&2; exit 1; }
[[ -f "$DEST/src/symmartys/docker-compose.yml" ]] || { echo "no symmartys slice in $DEST/src" >&2; exit 1; }
ENV_FILE="$DEST/.env"
STATE=(python3 "$HELPER" --env-file "$ENV_FILE")
[[ "$FRESH" -eq 1 ]] && STATE+=(--fresh-volume)
# A prospective plan validates required state and reports key NAMES only. No .env is sourced.
"${STATE[@]}" plan
VOLUME_NAME="$("${STATE[@]}" volume)"
EXPECTED_KEY="$("${STATE[@]}" expected-key)"
docker info >/dev/null
if [[ "$(docker inspect --format '{{.State.Running}}' emporion 2>/dev/null || true)" == true ]]; then
  echo "Legacy container emporion is running; no state was changed. Follow deploy/SYMMARTYS-UPGRADE.md." >&2
  exit 1
fi
publishers="$(docker ps --filter publish=9351 --format '{{.Names}}')"
while IFS= read -r publisher; do
  [[ -z "$publisher" || "$publisher" == symmartys ]] || {
    echo "Port 9351 belongs to another container; no state was changed." >&2; exit 1;
  }
done <<< "$publishers"
if ! docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
  [[ "$FRESH" -eq 1 ]] || { echo "The named data volume does not exist; refusing a new identity." >&2; exit 1; }
  [[ "$CHECK" -eq 1 ]] || docker volume create "$VOLUME_NAME" >/dev/null
fi
if [[ "$CHECK" -eq 1 ]]; then
  echo "Read-only preflight passed for $DEST; no files, containers, volumes or nginx were changed."
  exit 0
fi
if [[ -z "$SITE" ]]; then
  # The apex only: a word boundary would also match atlas.modelmarket.dev and friends.
  SITE="$(grep -lE 'server_name([[:space:]]+[^;[:space:]]+)*[[:space:]]+modelmarket\.dev([[:space:]]|;)' \
          /etc/nginx/sites-enabled/* 2>/dev/null | xargs -r grep -l 'listen[^;]*443' | head -1 || true)"
fi
[[ -n "$SITE" && -f "$SITE" ]] || { echo "no nginx site for modelmarket.dev found; pass --site" >&2; exit 1; }
SITE="$(readlink -f "$SITE")"
nginx -t >/dev/null
"${STATE[@]}" apply
chmod 600 "$ENV_FILE"
COMPOSE=(docker compose -p symmartys --env-file "$ENV_FILE" -f "$DEST/src/symmartys/docker-compose.yml")
# Do not print rendered Compose configuration: it contains the operator's secrets.
"${COMPOSE[@]}" config --quiet
IMAGE="symmartys"
HAD_PREVIOUS=0
if docker image inspect "${IMAGE}:latest" >/dev/null 2>&1; then
  docker image tag "${IMAGE}:latest" "${IMAGE}:prev"
  HAD_PREVIOUS=1
fi
rollback_candidate() {
  if [[ "$HAD_PREVIOUS" -eq 1 ]]; then
    echo "Restoring the previous SYMMARTYS image; legacy runtime is untouched." >&2
    docker image tag "${IMAGE}:prev" "${IMAGE}:latest"
    "${COMPOSE[@]}" up -d --no-build || true
  else
    "${COMPOSE[@]}" stop symmartys || true
    echo "Candidate stopped. The retained legacy container can be restored by the operator." >&2
  fi
}
check_identity() {
  local base="$1"
  curl -fsS --max-time 5 "$base/health" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="ok" and d.get("service")=="symmartys"' 2>/dev/null || return 1
  curl -fsS --max-time 5 "$base/ai-market/v2/manifest" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); tools=d.get("tools",[]); assert tools and all(t.get("product_id")=="symmartys" and t.get("capability_id","").startswith("symmartys.") for t in tools); expected=sys.argv[1]; assert not expected or d.get("signature",{}).get("public_key")==expected' "$EXPECTED_KEY" 2>/dev/null
}
wait_healthy() {
  for _ in $(seq 1 60); do
    check_identity http://127.0.0.1:9351 && return 0
    sleep 2
  done
  return 1
}
echo "Building and starting SYMMARTYS with the explicitly selected data volume …"
if ! "${COMPOSE[@]}" up -d --build || ! wait_healthy; then
  echo "Candidate did not start with the expected provider identity." >&2
  rollback_candidate
  exit 1
fi
echo "  healthy with SYMMARTYS capabilities and the expected signing identity"

# ── nginx: one snippet, one include in the HTTPS server block of modelmarket.dev ──
SNIPPET="/etc/nginx/snippets/symmartys.conf"

mkdir -p /etc/nginx/snippets
cat > "$SNIPPET.new" <<NGINX
# SYMMARTYS — managed by deploy_symmartys.sh; edit there, not here.
location = ${PREFIX} { return 301 ${PREFIX}/; }
# The call log's operator API (/ops/v1/*) stays on loopback; token-gated, but not public.
location ^~ ${PREFIX}/ops/ { return 404; }
location = ${PREFIX}/ {
    root ${DEST}/src/symmartys/docs/landing;
    try_files /index.html =404;
    default_type text/html;
    expires -1;
}
location ^~ ${PREFIX}/assets/ {
    alias ${DEST}/src/symmartys/docs/landing/assets/;
    expires 1h;
}
location ^~ ${PREFIX}/fonts/ {
    alias ${DEST}/src/symmartys/docs/landing/fonts/;
    expires 1h;
}
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
cp -a "$SITE" "$backup_dir/$(basename "$SITE").${stamp}-before-symmartys"
[[ -f "$SNIPPET" ]] && cp -a "$SNIPPET" "$backup_dir/symmartys.conf.${stamp}"
mv "$SNIPPET.new" "$SNIPPET"
if ! grep -q 'snippets/symmartys.conf' "$SITE"; then
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
        text = text[:at] + "\n    include snippets/symmartys.conf;" + text[at:]
        open(path, "w").write(text)
        print("  include added to", path)
        break
else:
    sys.exit("no HTTPS server block for modelmarket.dev in " + path)
PY
fi
if ! nginx -t 2>/dev/null; then
  echo "nginx -t failed — restoring the site and the snippet" >&2
  cp -a "$backup_dir/$(basename "$SITE").${stamp}-before-symmartys" "$SITE"
  if [[ -f "$backup_dir/symmartys.conf.${stamp}" ]]; then
    cp -a "$backup_dir/symmartys.conf.${stamp}" "$SNIPPET"
  else
    rm -f "$SNIPPET"
  fi
  nginx -t
  exit 1
fi
systemctl reload nginx
echo "  nginx reloaded (backup: $backup_dir/$(basename "$SITE").${stamp}-before-symmartys)"

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
echo "SYMMARTYS deployed."
