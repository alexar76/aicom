#!/usr/bin/env bash
# The agent-factory operator kit: your Multica agents, guarded, buying on the AIMarket federation, in one
# command. Run it as root next to your Multica self-host (the folder with its docker-compose file). Safe to run
# again: every step checks what is already done, and nothing of yours is overwritten.
#
#   sudo ./onboard.sh --dir /opt/multica           set up (asks only for what is missing)
#   sudo ./onboard.sh --dir /opt/multica --check   change nothing: say what is ready and what is missing
#
# What it sets up, exactly as multica/manual describes and as our own installation runs:
#   - a Multica daemon in a hardened container (non-root, no capabilities, limits, no auto-update);
#   - an egress proxy: the daemon has no route out except to the hosts on an allowlist;
#   - the WARDEN flow guard for every agent, from a root-owned folder (checksum-verified npm package);
#   - the hub's MCP server for every agent, with a prepaid key (yours, or a new free one);
#   - checks of all of it, from inside the daemon, as the agent user.
#
# Options:
#   --hub URL           the hub agents buy from (default https://modelmarket.dev)
#   --allow HOST        one more host agents may reach (repeatable), e.g. --allow api.github.com
#   --model-key NAME    the model key's variable (default DEEPSEEK_API_KEY)
#   --backend SERVICE   your Multica backend's compose service (default: the one named backend)
#   --yes               take the defaults instead of asking (a new free hub key, start without asking)
#   --no-start          write everything, start nothing
#   --live-check        also run one real agent session (spends a little of the model key)
set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
HUB="https://modelmarket.dev" DIR="" BACKEND="" MODEL_KEY="DEEPSEEK_API_KEY" YES=0 START=1 CHECK_ONLY=0
LIVE=0 EXTRA_ALLOW=()
MULTICA_VERSION="${ONBOARD_MULTICA_VERSION:-0.8.0}"   # the versions the guard was tested on
OPENCODE_VERSION="${ONBOARD_OPENCODE_VERSION:-1.18.32}"
WARDEN_VERSION="0.23.0"
WARDEN_SHA1="e9fe195e36ce559d9e543e8eb3fd4bcd729fe434"
WARDEN_SHA512="sha512-xP9OV7bNhinFqAej0xu4IuAGyPVVsoQ79mRpaTB9ffnMxbCs/qbw1+/UXLAR9NykV4jDhT6fvc+VMHszsvgnWA=="
AGENT_SUBNET="${ONBOARD_AGENT_SUBNET:-10.250.0.0/24}"
OURS="docker-compose.aimarket.yml"

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="${2:?--dir needs a folder}"; shift ;;
    --hub) HUB="${2:?--hub needs a URL}"; shift ;;
    --allow) EXTRA_ALLOW+=("${2:?--allow needs a host}"); shift ;;
    --model-key) MODEL_KEY="${2:?--model-key needs a name}"; shift ;;
    --backend) BACKEND="${2:?--backend needs a service}"; shift ;;
    --yes) YES=1 ;;
    --no-start) START=0 ;;
    --check) CHECK_ONLY=1 ;;
    --live-check) LIVE=1 ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

if [ -t 1 ]; then G=$'\e[32m' R=$'\e[31m' Y=$'\e[33m' B=$'\e[1m' N=$'\e[0m'; else G= R= Y= B= N=; fi
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$*"; }
bad()  { printf '  %s✗%s %s\n' "$R" "$N" "$*"; FAILED=$((FAILED + 1)); }
fail() { printf '  %s✗%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
step() { printf '\n%s%s%s\n' "$B" "$*" "$N"; }
yes_no() { [ "$YES" = 1 ] && return 0; local v; read -r -p "  $1 [Y/n] " v; case "$v" in n|N|no|No) return 1 ;; *) return 0 ;; esac; }
FAILED=0

# ── where, and with what ─────────────────────────────────────────────────────────────────
[ -n "$DIR" ] || fail "say where your Multica self-host is: --dir /path/to/the/folder/with/its/docker-compose.yml"
DIR="$(cd "$DIR" && pwd)" || fail "no such folder: $DIR"
STATE="$DIR/aimarket-agents"
IS_ROOT=0; [ "$(id -u)" = 0 ] && IS_ROOT=1
if [ "$IS_ROOT" = 0 ] && [ "${ONBOARD_ALLOW_NONROOT:-0}" != 1 ] && [ "$CHECK_ONLY" = 0 ]; then
  fail "run it as root: the guard must live in files the agents' user cannot change (sudo ./onboard.sh …)"
fi
for tool in docker curl python3; do command -v "$tool" >/dev/null || fail "$tool is not installed"; done
docker compose version >/dev/null 2>&1 || fail "docker compose (v2) is not available"
cd "$DIR"

MAIN=""
for f in compose.yaml compose.yml docker-compose.yaml docker-compose.yml; do [ -f "$f" ] && { MAIN="$f"; break; }; done
[ -n "$MAIN" ] || fail "no docker-compose file in $DIR: point --dir at your Multica self-host"

env_get() { [ -f "$1" ] && grep -E "^$2=" "$1" | tail -1 | cut -d= -f2- || true; }
env_set() {  # replace or append KEY=VALUE in a file, keep everything else, keep it 600
  local file="$1" k="$2" v="$3" tmp
  [ -f "$file" ] || ( umask 077; : > "$file" )
  tmp="$(mktemp)"
  awk -v k="$k" -v v="$v" 'BEGIN{done=0} $0 ~ "^" k "=" { if (!done) { print k "=" v; done=1 }; next } { print } END { if (!done) print k "=" v }' "$file" > "$tmp"
  cat "$tmp" > "$file"; rm -f "$tmp"; chmod 600 "$file"
}

BASE_FILES="$(env_get .env COMPOSE_FILE)"
if [ -z "$BASE_FILES" ]; then
  BASE_FILES="$MAIN"
  for f in compose.override.yaml compose.override.yml docker-compose.override.yaml docker-compose.override.yml; do
    [ -f "$f" ] && BASE_FILES="$BASE_FILES:$f"
  done
fi
BASE_FILES="$(printf '%s' "$BASE_FILES" | tr ':' '\n' | grep -vx "$OURS" | paste -sd: -)"
dc_base() { COMPOSE_FILE="$BASE_FILES" docker compose "$@"; }
dc() { COMPOSE_FILE="$BASE_FILES:$OURS" docker compose "$@"; }

SERVICES="$(dc_base config --services 2>/dev/null)" || fail "docker compose cannot read $BASE_FILES"
if [ -z "$BACKEND" ]; then
  BACKEND="$(printf '%s\n' "$SERVICES" | grep -x backend || true)"
  [ -n "$BACKEND" ] || BACKEND="$(printf '%s\n' "$SERVICES" | grep -E 'backend|server' | head -1 || true)"
fi
printf '%s\n' "$SERVICES" | grep -qx "$BACKEND" || fail "no Multica backend service found; name it with --backend (services: $(echo $SERVICES))"
for s in agents-daemon agents-egress; do
  if printf '%s\n' "$SERVICES" | grep -qx "$s"; then fail "your compose already has a service named $s"; fi
done
CONFIG_JSON="$(dc_base config --format json)"
cfg() { printf '%s' "$CONFIG_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }
BACKEND_PORT="$(cfg "e=d['services']['$BACKEND'].get('environment') or {}; print(e.get('PORT') or '8080')")"
BACKEND_NETS="$(cfg "print(' '.join(sorted((d['services']['$BACKEND'].get('networks') or {'default': None}).keys())))")"
APP_URL="$(cfg "e=d['services']['$BACKEND'].get('environment') or {}; print(e.get('MULTICA_APP_URL') or e.get('FRONTEND_ORIGIN') or '')")"
HUB_HOST="$(python3 -c "import sys,urllib.parse as u; print(u.urlparse(sys.argv[1]).hostname or '')" "$HUB")"
[ -n "$HUB_HOST" ] || fail "--hub is not a URL: $HUB"

model_host() {
  case "$1" in
    DEEPSEEK_API_KEY) echo api.deepseek.com ;;   OPENAI_API_KEY) echo api.openai.com ;;
    ANTHROPIC_API_KEY) echo api.anthropic.com ;; OPENROUTER_API_KEY) echo openrouter.ai ;;
    GEMINI_API_KEY|GOOGLE_API_KEY|GOOGLE_GENERATIVE_AI_API_KEY) echo generativelanguage.googleapis.com ;;
    MISTRAL_API_KEY) echo api.mistral.ai ;;      GROQ_API_KEY) echo api.groq.com ;;
    XAI_API_KEY) echo api.x.ai ;;                *) echo "" ;;
  esac
}

# ── checks: what is ready, from inside the daemon, as the agent user ─────────────────────
check_all() {
  step "Checks"
  if [ -d "$STATE/opencode-guard" ]; then
    local loose
    loose="$(find "$STATE/opencode-guard" \( ! -user 0 -o -perm -g+w -o -perm -o+w \) -print 2>/dev/null | head -3)"
    if [ -z "$loose" ]; then ok "the guard's files are root's and nobody else may write them"
    elif [ "$IS_ROOT" = 0 ]; then warn "not run as root: ownership of the guard's files not checked"
    else bad "writable or not root's: $loose"; fi
    if [ -f "$STATE/opencode-guard/.kit-sha256" ] && (cd "$STATE/opencode-guard" && python3 - <<'PY'
import hashlib, sys
ok = True
for line in open(".kit-sha256"):
    digest, name = line.split(maxsplit=1)
    name = name.strip()
    if hashlib.sha256(open(name, "rb").read()).hexdigest() != digest:
        print(f"    changed: {name}"); ok = False
sys.exit(0 if ok else 1)
PY
    ); then ok "the guard's files are the ones installed (WARDEN $WARDEN_VERSION)"
    else bad "the guard's files changed since they were installed: run onboard.sh again"; fi
  else
    bad "the guard is not installed ($STATE/opencode-guard)"
  fi
  if ! dc ps --status running --services 2>/dev/null | grep -qx agents-daemon; then
    bad "the daemon container is not running (docker compose up -d agents-daemon, in $DIR)"
    return
  fi
  ok "the daemon container is running"
  local inside="docker compose exec -T -u node -w /tmp agents-daemon"
  local plugins
  plugins="$(COMPOSE_FILE="$BASE_FILES:$OURS" $inside sh -c 'opencode debug config 2>/dev/null | jq -c "[.plugin, (.mcp | keys)]"' 2>/dev/null || true)"
  case "$plugins" in
    *opencode-guard/plugin/warden.js*) ok "every OpenCode session loads the guard from /opt/opencode-guard" ;;
    *) bad "OpenCode does not list the guard (opencode debug config: ${plugins:-no answer})" ;;
  esac
  case "$plugins" in *aimarket*) ok "every OpenCode session has the hub's MCP server" ;;
    *) bad "OpenCode does not list the hub's MCP server" ;; esac
  local writable
  writable="$(COMPOSE_FILE="$BASE_FILES:$OURS" $inside sh -c 'for p in /opt /opt/opencode-guard /opt/opencode-guard/plugin /opt/opencode-guard/warden; do [ -w "$p" ] && echo "$p"; done' 2>/dev/null || true)"
  if [ -z "$writable" ]; then ok "the agent user cannot change any folder on the guard's path"
  else bad "the agent user can write: $writable"; fi
  if COMPOSE_FILE="$BASE_FILES:$OURS" $inside curl -fsS --max-time 15 -o /dev/null https://example.com 2>/dev/null; then
    bad "the daemon reached example.com: the egress allowlist is not in force"
  else ok "a host off the allowlist is refused (example.com)"; fi
  if COMPOSE_FILE="$BASE_FILES:$OURS" $inside curl -fsS --max-time 15 -o /dev/null "$HUB/ai-market/v2/health" 2>/dev/null; then
    ok "the hub answers through the proxy ($HUB_HOST)"
  else bad "the hub does not answer from inside the daemon ($HUB/ai-market/v2/health)"; fi
  local balance
  # The key goes to curl on stdin (-H @-), never on a command line another process could read.
  balance="$(COMPOSE_FILE="$BASE_FILES:$OURS" $inside sh -c 'printf "X-API-Key: %s\n" "$AIMARKET_API_KEY" | curl -fsS --max-time 15 -H @- "$0/ai-market/v2/account"' "$HUB" 2>/dev/null \
            | python3 -c 'import json,sys; print(json.load(sys.stdin).get("balance_usd"))' 2>/dev/null || true)"
  if [ -n "$balance" ]; then ok "the agents' hub key works: balance \$$balance"
  else bad "the agents' hub key is missing or refused"; fi
  if COMPOSE_FILE="$BASE_FILES:$OURS" $inside multica auth status 2>&1 | grep -qi "not authenticated"; then
    warn "the daemon is not logged in to Multica yet: docker compose exec -it agents-daemon multica auth login (in $DIR)"
  else ok "the daemon is logged in to Multica"; fi
  if [ "$LIVE" = 1 ]; then
    if COMPOSE_FILE="$BASE_FILES:$OURS" $inside sh -c 'opencode run "Reply with the single word OK." >/dev/null 2>&1; find ~/.local/state/warden -newer /proc/1 -type f | head -1' | grep -q .; then
      ok "a real session ran the guard (its state file is fresh)"
    else bad "a real session left no fresh guard state (is the model key set?)"; fi
  fi
}

if [ "$CHECK_ONLY" = 1 ]; then
  check_all
  [ "$FAILED" = 0 ] && { printf '\n%sReady.%s\n' "$G" "$N"; exit 0; }
  printf '\n%s%s check(s) failed.%s Run onboard.sh without --check to set up what is missing.\n' "$R" "$FAILED" "$N"
  exit 1
fi

step "Agent-factory kit for $DIR (backend: $BACKEND, hub: $HUB)"
install -d -m 755 "$STATE" "$STATE/daemon" "$STATE/egress"

# ── secrets: the agents' env file (600), never printed ───────────────────────────────────
step "Keys"
ENVF="$STATE/agents.env"
( umask 077; [ -f "$ENVF" ] || : > "$ENVF" ); chmod 600 "$ENVF"
if [ -n "$(env_get "$ENVF" "$MODEL_KEY")" ]; then ok "$MODEL_KEY is set"
elif [ "$YES" = 1 ] || [ ! -t 0 ]; then warn "$MODEL_KEY is not set: agents cannot run until you add it to $ENVF"
else
  printf '  %s (hidden; Enter to skip): ' "$MODEL_KEY"; read -rs v; echo
  if [ -n "$v" ]; then env_set "$ENVF" "$MODEL_KEY" "$v"; ok "$MODEL_KEY saved"; else warn "skipped: add $MODEL_KEY to $ENVF later"; fi
  unset v
fi
if [ -n "$(env_get "$ENVF" AIMARKET_API_KEY)" ]; then ok "AIMARKET_API_KEY is set"
else
  v=""
  if [ "$YES" = 0 ] && [ -t 0 ]; then
    printf '  Your prepaid key from %s/start (hidden; Enter for a new free key): ' "$HUB"; read -rs v; echo
  fi
  if [ -z "$v" ]; then
    reply="$(curl -fsS --max-time 20 -H 'Content-Type: application/json' \
             -d "{\"label\": \"multica operator kit $(hostname | cut -c1-40)\"}" "$HUB/ai-market/v2/accounts" 2>/dev/null || true)"
    v="$(printf '%s' "$reply" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("api_key",""))' 2>/dev/null || true)"
    [ -n "$v" ] || fail "$HUB did not open a key (it may issue keys by hand: get one at $HUB/start and run again)"
    acct="$(printf '%s' "$reply" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("account_id",""), d.get("balance_usd",""))')"
    ok "a new hub key was opened: account ${acct% *}, balance \$${acct#* }"
  fi
  env_set "$ENVF" AIMARKET_API_KEY "$v"; unset v reply
  ok "AIMARKET_API_KEY saved in $ENVF"
fi

# ── the guard: WARDEN from npm, checked against npm's own checksums, owned by root ───────
step "Guard (WARDEN $WARDEN_VERSION)"
GUARD="$STATE/opencode-guard"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
curl -fsSL --max-time 60 -o "$T/warden.tgz" "https://registry.npmjs.org/@aimarket/warden/-/warden-$WARDEN_VERSION.tgz" \
  || fail "could not download @aimarket/warden $WARDEN_VERSION from npm"
python3 - "$T/warden.tgz" "$WARDEN_SHA1" "$WARDEN_SHA512" <<'PY' || fail "the WARDEN package does not match npm's published checksums: not installed"
import base64, hashlib, sys
data = open(sys.argv[1], "rb").read()
sha512 = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
sys.exit(0 if hashlib.sha1(data).hexdigest() == sys.argv[2] and sha512 == sys.argv[3] else 1)
PY
ok "package matches npm's sha1 and sha512"
tar -xzf "$T/warden.tgz" -C "$T"
STRIP="\"AIMARKET_API_KEY\", \"$MODEL_KEY\""
install -d -m 755 "$GUARD" "$GUARD/plugin" "$GUARD/warden"
rm -f "$GUARD/warden/"*.js
install -m 644 "$T"/package/dist/opencode-plugin.js "$T"/package/dist/flow-guard*.js "$GUARD/warden/"
cat > "$T/warden.js" <<JS
// The WARDEN flow guard for every agent on this daemon (written by onboard.sh). Export only the plugin:
// OpenCode calls every exported function as one.
import { createWardenPlugin } from '../warden/opencode-plugin.js';

export const WardenFlowGuard = createWardenPlugin({
  block: 'data',
  // Keys only the OpenCode process needs; shell commands get them blank.
  stripEnv: [$STRIP],
});
JS
install -m 644 "$T/warden.js" "$GUARD/plugin/warden.js"
python3 - "$HUB" > "$T/opencode.json" <<'PY'
import json, sys
print(json.dumps({
    "$schema": "https://opencode.ai/config.json",
    "mcp": {"aimarket": {"type": "remote", "url": sys.argv[1].rstrip("/") + "/mcp",
                         "headers": {"X-API-Key": "{env:AIMARKET_API_KEY}"}}},
}, indent=2))
PY
install -m 644 "$T/opencode.json" "$GUARD/opencode.json"
(cd "$GUARD" && find plugin warden opencode.json -type f | sort | while read -r f; do
   printf '%s  %s\n' "$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$f")" "$f"
 done > .kit-sha256)
chmod 644 "$GUARD/.kit-sha256"
OWNER="root-owned"
if [ "$IS_ROOT" = 1 ]; then chown -R 0:0 "$GUARD"; chown 0:0 "$STATE"; else OWNER="NOT root-owned (not run as root)"; fi
ok "installed in $GUARD ($(ls "$GUARD/warden" | wc -l | tr -d ' ') files), $OWNER, hub MCP server included"

# ── the egress allowlist ─────────────────────────────────────────────────────────────────
step "Egress allowlist"
cp "$KIT/daemon/Dockerfile" "$KIT/daemon/entrypoint.sh" "$STATE/daemon/"
cp "$KIT/egress/Dockerfile" "$STATE/egress/"
sed "s#^Allow .*#Allow $AGENT_SUBNET#" "$KIT/egress/tinyproxy.conf" > "$STATE/egress/tinyproxy.conf"
{
  echo "# Hosts the agents may reach, one anchored regex per line (written by onboard.sh; --allow adds more)."
  for h in $(model_host "$MODEL_KEY") models.dev "$HUB_HOST" ${EXTRA_ALLOW[@]+"${EXTRA_ALLOW[@]}"}; do
    [ -n "$h" ] && printf '^%s$\n' "$(printf '%s' "$h" | sed 's/[.]/\\./g')"
  done
} | awk '!seen[$0]++' > "$STATE/egress/allow"
ok "agents may reach: $(grep -v '^#' "$STATE/egress/allow" | sed 's/[\\^$]//g' | paste -sd' ' -)"

# ── the compose fragment, joined to yours through COMPOSE_FILE ──────────────────────────
step "Compose"
NETS_YAML="$(for n in $BACKEND_NETS agent; do printf '      - %s\n' "$n"; done | awk '!seen[$0]++')"
cat > "$OURS" <<YAML
# Written by the AIMarket agent-factory kit (multica/operator-kit/onboard.sh). It adds the agents' daemon, its
# egress proxy and their network to your Multica stack, and nothing else of yours changes but one line: the
# backend joins the agents' network so the daemon can reach it. To remove the kit: docker compose down
# agents-daemon agents-egress, delete this file and the COMPOSE_FILE line onboard.sh added to .env.
services:
  $BACKEND:
    networks:
$NETS_YAML

  agents-daemon:
    image: aimarket-multica-daemon:$MULTICA_VERSION-$OPENCODE_VERSION
    build:
      context: ./aimarket-agents/daemon
      args: { MULTICA_VERSION: "$MULTICA_VERSION", OPENCODE_VERSION: "$OPENCODE_VERSION" }
    container_name: aimarket-agents-daemon
    depends_on: [$BACKEND, agents-egress]
    env_file: [./aimarket-agents/agents.env]
    environment:
      MULTICA_SERVER_URL: http://$BACKEND:$BACKEND_PORT
      MULTICA_APP_URL: "$APP_URL"
      MULTICA_DAEMON_DEVICE_NAME: "$(hostname | cut -c1-40)"
      MULTICA_DAEMON_MAX_CONCURRENT_TASKS: "2"
      MULTICA_DAEMON_AUTO_UPDATE: "false"
      MULTICA_OPENCODE_TRANSPORT: run
      OPENCODE_CONFIG_DIR: /opt/opencode-guard
      HTTPS_PROXY: http://agents-egress:8888
      https_proxy: http://agents-egress:8888
      HTTP_PROXY: http://agents-egress:8888
      http_proxy: http://agents-egress:8888
      NO_PROXY: $BACKEND,localhost,127.0.0.1
      no_proxy: $BACKEND,localhost,127.0.0.1
    volumes:
      - agents_home:/home/node
      - ./aimarket-agents/opencode-guard:/opt/opencode-guard   # root-owned; not :ro (OpenCode stops on EROFS)
    networks: [agent]
    mem_limit: 3g
    cpus: 2
    pids_limit: 1024
    security_opt: ["no-new-privileges:true"]
    cap_drop: [ALL]
    restart: unless-stopped

  agents-egress:
    image: aimarket-multica-egress:$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()+open(sys.argv[2],"rb").read()).hexdigest()[:12])' "$STATE/egress/allow" "$STATE/egress/tinyproxy.conf")
    build: { context: ./aimarket-agents/egress }
    container_name: aimarket-agents-egress
    networks: [agent, agents_out]
    read_only: true
    tmpfs: ["/tmp", "/run"]
    mem_limit: 128m
    cpus: 0.5
    pids_limit: 128
    security_opt: ["no-new-privileges:true"]
    cap_drop: [ALL]
    restart: unless-stopped

networks:
  agent:
    internal: true          # no route out and no outside DNS: only the proxy leaves
    ipam: { config: [{ subnet: "$AGENT_SUBNET" }] }
  agents_out: {}

volumes:
  agents_home: {}
YAML
[ "$(env_get .env COMPOSE_FILE)" = "$BASE_FILES:$OURS" ] || env_set .env COMPOSE_FILE "$BASE_FILES:$OURS"
dc config --quiet || fail "docker compose rejects the result; nothing was started ($OURS is left for you to read)"
ok "$OURS written; COMPOSE_FILE in .env = $BASE_FILES:$OURS"

# ── start ────────────────────────────────────────────────────────────────────────────────
if [ "$START" = 1 ] && yes_no "Build and start the agents' daemon and proxy now?"; then
  step "Start"
  dc build agents-egress agents-daemon
  dc up -d --no-deps agents-egress agents-daemon
  # The backend joins the agents' network without being recreated: no downtime. The compose file keeps it
  # there on its next recreate.
  backend_id="$(dc ps -q "$BACKEND" | head -1)"
  net="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$(dc ps -q agents-daemon)")_agent"
  if [ -n "$backend_id" ] && ! docker inspect -f '{{json .NetworkSettings.Networks}}' "$backend_id" | grep -q "\"$net\""; then
    docker network connect --alias "$BACKEND" "$net" "$backend_id"
  fi
  ok "started"
  sleep 3
fi

check_all
printf '\n%sNext%s\n' "$B" "$N"
echo "  - Log the daemon in to Multica once:  cd $DIR && docker compose exec -it agents-daemon multica auth login"
echo "  - Teach agents the market's rules:    multica skill import --url https://github.com/alexar76/aicom/tree/main/multica/community/aimarket"
echo "  - Sell your agents' work:             multica/manual §9-10, and a provider account at $HUB/start?role=provider"
echo "  - Check again any time:               sudo $0 --dir $DIR --check"
[ "$FAILED" = 0 ] || exit 1
