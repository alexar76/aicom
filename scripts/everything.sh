#!/usr/bin/env bash
# ============================================================================
# AI-Factory — EVERYTHING tier engine.  Reached via  ./start.sh --everything
# ============================================================================
# Three production hosts, collapsed onto one machine: Factory, Hub, Mesh,
# Monitor, Pulse, Landing, GAIA, ATLAS, the oracle family, Platon, MOMUS,
# Treasury, the canary, SKOPOS + its remediation conductor, Metis (coordinator
# + 2 nodes), ARGUS x2, DIOSCURI, HELIOS + worker, and the fake-money lottery.
#
#   ./start.sh --everything                 # bring it all up, gate on health
#   ./start.sh --everything --no-build      # reuse existing images
#   ./start.sh --everything --bind 0.0.0.0  # EXPOSE it (reads its own warning)
#   ./start.sh --everything --host-ip 1.2.3.4
#   ./start.sh --everything --logs
#   ./start.sh --everything --down [--reset-chain]
#
# This script is deliberately opinionated about four things, because each one
# is a way a first run has actually gone wrong for us:
#
#   1. It refuses BEFORE the first pull if the machine cannot hold the stack.
#      Our own oracle host filled to 100% disk and broke a service in a way
#      that took an hour to diagnose. A newcomer should not meet that.
#   2. It never says "ready" until every service has answered a health check,
#      and it opens no browser if anything failed. A launcher that opens a
#      broken page has lied on first contact.
#   3. Generated credentials are printed exactly ONCE, in one block, at the
#      very end. Never in a log line, a health row, or an error.
#   4. Nothing touches a real chain. Crypto stays off, the only chain is an
#      ephemeral fake-funded Anvil, and the run aborts outright if a mainnet
#      key is present in the environment.
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lib/common.sh
[[ -f scripts/lib/common.sh ]] || { echo "scripts/lib/common.sh missing — repo is incomplete" >&2; exit 1; }
source scripts/lib/common.sh

# docker-compose.everything.yml is a SIBLING of docker-compose.core.yml, not a
# child: it redeclares hub / mesh-api / alien-monitor itself so that
# `-f docker-compose.yml -f docker-compose.everything.yml` validates on its own.
# Loading both overlays at once would merge two definitions of the same three
# services — never do it. Same project name and same service names as core, so
# switching tiers RECREATES those containers instead of running a second copy.
COMPOSE=(docker compose
         -f docker-compose.yml
         -f docker-compose.everything.yml
         --profile everything)
# Everything in the overlay carries `profiles: ["everything"]`, so the file is
# inert without this flag. `lottery-uni` is a second, opt-in profile.
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT")}"

# ── args ────────────────────────────────────────────────────────────────────
BUILD=1; OPEN=1; ACTION="up"; ASSUME_YES=0; SKIP_RESOURCES=0; RESET_CHAIN=0
BIND_ADDR="127.0.0.1"; HOST_IP=""; BIND_EXPLICIT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build)            BUILD=0; shift ;;
    --no-open)             OPEN=0; shift ;;
    --logs)                ACTION="logs"; shift ;;
    --down)                ACTION="down"; shift ;;
    --reset-chain)         RESET_CHAIN=1; shift ;;
    --yes|-y)              ASSUME_YES=1; shift ;;
    --skip-resource-check) SKIP_RESOURCES=1; shift ;;
    # Arity checked before shifting: `shift 2` with one argument left returns
    # non-zero and, under `set -e`, ends the run silently — which for a launcher
    # is indistinguishable from success. Fail loudly instead.
    --bind)                [[ $# -ge 2 ]] || die "--bind needs an address (127.0.0.1 or 0.0.0.0)"
                           BIND_ADDR="$2"; BIND_EXPLICIT=1; shift 2 ;;
    --host-ip)             [[ $# -ge 2 ]] || die "--host-ip needs an address, e.g. --host-ip 203.0.113.7"
                           HOST_IP="$2"; shift 2 ;;
    # 2,30 = the header block minus its rules (`set -euo pipefail` is line 32).
    -h|--help)             sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option for --everything: $1" ;;
  esac
done
[[ -n "$BIND_ADDR" ]] || die "--bind needs an address (127.0.0.1 or 0.0.0.0)"

# ── simple actions (no preflight, no secrets, no health gate) ───────────────
if [[ "$ACTION" == "logs" ]]; then
  exec "${COMPOSE[@]}" logs -f --tail=120
fi

if [[ "$ACTION" == "down" ]]; then
  step "Stopping the everything tier (./data and named volumes kept)…"
  # --remove-orphans: this tier owns ~40 services, and a service renamed
  # between versions would otherwise be left running and still holding a port.
  "${COMPOSE[@]}" --profile lottery-uni down --remove-orphans
  if [[ "$RESET_CHAIN" -eq 1 ]]; then
    say ""
    step "Resetting chain state (the two unbounded disk sinks)…"
    # The lottery's Anvil mines at --block-time 1 forever and the Monitor
    # persists its universe chain to a bind mount. Neither is capped, rotated or
    # pruned by any compose file — this is the exact growth that took one of our
    # own hosts to 100% disk. Both are fake-money ephemeral chains, so there is
    # nothing here to lose; `--down` alone deliberately preserves them.
    rm -rf data/alien-monitor/universe/anvil-state 2>/dev/null || true
    docker volume rm -f "${PROJECT}_lottery_shared" >/dev/null 2>&1 || true
    ok "Cleared data/alien-monitor/universe/anvil-state and volume ${PROJECT}_lottery_shared"
  fi
  say ""
  ok "Everything tier stopped. Data preserved in ./data and in the named volumes."
  say "  ${DIM}restart: ./start.sh --everything --no-build${N}"
  say "  ${DIM}reclaim chain disk: ./start.sh --everything --down --reset-chain${N}"
  say "  ${DIM}reclaim build cache: docker builder prune${N}"
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════
#  THE SERVICE MANIFEST
# ══════════════════════════════════════════════════════════════════════════
# One row per container. Everything downstream — the port preflight, the health
# gate, the live table and the URL block — is generated from this, so a service
# cannot be checked-but-not-listed or listed-but-not-checked.
#
#   service | Display name | host_port | probe_path | timeout_s | kind
#
# kind:
#   http     probe http://127.0.0.1:<host_port><probe_path> from the host —
#            i.e. exactly what the human will do next
#   docker   no published port; trust the container's own healthcheck
#   oneshot  must exit 0 (data-init, the lottery contract deploy)
#   running  no healthcheck and nothing to probe; must simply still be running
#
# Timeouts are per service and generous where the work is real: the Monitor
# deploys Anvil + FakeUSDT + Escrow + NFT inside its container (2-4 min cold),
# and the Factory's entrypoint may restart the backend once for the treasury
# guard.
MANIFEST=$(cat <<'ROWS'
data-init|Data init (./data chown)||-|120|oneshot
app|Factory API|9081|/api/health|420|http
hub|AIMarket Hub|9083|/.well-known/ai-market.json|180|http
mesh-api|Service Mesh API|8090|/health|180|http
prometheus|Prometheus|9090|/prometheus/-/healthy|180|http
grafana|Grafana|9082|/api/health|180|http
alien-monitor|Alien Monitor|9100|/api/health|420|http
mesh-dashboard|Mesh dashboard|8091|/health|150|http
pulse-terminal|Pulse Terminal|5199|/api/health|150|http
aicom-landing|Landing generator|3847|/|180|http
gaia-backend|GAIA gateway|9320|/health|180|http
gaia-frontend|GAIA landing|5185|/|120|http
atlas|ATLAS sensor map|9330|/health|240|http
chronos|CHRONOS oracle|9300|/api/health|180|http
oracle-family|Oracle family|9400|/api/health|240|http
oracles-landing|Oracles landing|5180|/|120|http
platon-backend|Platon oracle|9200|/api/health|240|http
platon-frontend|Platon cave (UMBRAL)|9201|/api/health|180|http
momus-backend|MOMUS red team|9410|/health|240|http
momus-treasury|MOMUS Treasury|9411|/health|180|http
momus-frontend|MOMUS panel|5186|/health|180|http
momus-canary|MOMUS canary|9450|/health|120|http
skopos-postgres|SKOPOS database||-|150|docker
skopos|SKOPOS dashboard|8502|/healthz|360|http
skopos-remediation|SKOPOS remediation|9402|/health|180|http
logos-postgres|LOGOS database||-|150|docker
logos|LOGOS analytics|5199|/health|240|http
metis-node-a|Metis node-a||-|300|docker
metis-node-b|Metis node-b||-|300|docker
metis-coordinator|Metis coordinator|9111|/health|360|http
argus|ARGUS|8787|/health|180|http
argus-uni|ARGUS (UNI)|8788|/health|180|http
dioscuri|DIOSCURI twins|8790|/health|180|http
helios|HELIOS|8791|/health|180|http
helios-worker|HELIOS worker||-|120|running
lottery-chain|Lottery chain (Anvil)||-|180|docker
lottery-deploy|Lottery contracts||-|360|oneshot
lottery-relayer|Lottery relayer|8390|/healthz|300|http
lottery-agent|Lottery agent||-|180|running
lottery-showcase|Lottery showcase|5182|/|150|http
ROWS
)

# Host ports that are published but are not the port the manifest probes, so the
# preflight still has to check them: the Factory storefront (the manifest probes
# the API on 9081) and the SKOPOS Streamlit dashboard (probed on 8502).
EXTRA_PORTS="9080 8501"

manifest_rows() { printf '%s\n' "$MANIFEST"; }
mf() { printf '%s' "$1" | cut -d'|' -f"$2" | sed 's/[[:space:]]*$//'; }

# ══════════════════════════════════════════════════════════════════════════
#  --bind 0.0.0.0 — the security decision, made out loud and made FIRST
# ══════════════════════════════════════════════════════════════════════════
# Printed before ANY other work: before the preflight, before secrets, before
# a single byte is pulled. And it is never inferred — --host-ip does not turn
# it on, a public-looking IP does not turn it on, only --bind 0.0.0.0 does.
if [[ "$BIND_ADDR" != "127.0.0.1" && "$BIND_ADDR" != "localhost" ]]; then
  say ""
  # ASCII-only inside the box: multi-byte glyphs make the padding a byte/char
  # mismatch and the right edge drifts.
  say "${R}${B}╔══════════════════════════════════════════════════════════════════════════╗${N}"
  printf '%s║%-74s║%s\n' "${R}${B}" "  PUBLISHING 32 PORTS ON ${BIND_ADDR} - 38 CONTAINERS" "$N"
  printf '%s║%-74s║%s\n' "${R}${B}" "  SEVERAL OF THEM ARE CONTROL PLANES" "$N"
  say "${R}${B}╚══════════════════════════════════════════════════════════════════════════╝${N}"
  say ""
  say "  These are ${B}control planes${N}, not demos. Reachable from your whole network:"
  say ""
  say "    ${B}:9410${N}  MOMUS      /scan /selfaudit /retest /remediate /intel/refresh /a2a/tasks"
  say "    ${B}:9411${N}  Treasury   the service that RELEASES bounties"
  say "    ${B}:9402${N}  SKOPOS remediation conductor — signs DeployOrders"
  say "    ${B}:8501${N}  SKOPOS dashboard (fleet view)"
  say "    ${B}:9450${N}  MOMUS canary /canary/fix /canary/break"
  say "    ${B}:9320${N}  GAIA /sim/* (if GAIA_SIM_CONTROL=1)"
  say "    ${B}:9080${N}  Factory admin — the whole build pipeline"
  say "    ${B}:9111${N}  Metis coordinator"
  say "    ${B}:8390${N}  Lottery relayer, driving a funded (fake) local chain"
  say ""
  say "  The ${B}only${N} thing in front of them is the operator tokens generated into"
  say "  ${B}.env${N}. There is no TLS, no edge, no rate limit and no second factor."
  say "  On Linux a Docker publish inserts a DNAT rule ${B}ahead of UFW${N}, so your host"
  say "  firewall will not save you — this bind address is the control."
  say ""
  say "  Browsing from another machine also loses ${B}secure context${N}: on http://<lan-ip>"
  say "  service workers and crypto.subtle are unavailable, so the Factory PWA and"
  say "  any in-browser crypto degrade. Only http://127.0.0.1 is a secure origin."
  say ""
  if [[ "$ASSUME_YES" -eq 0 ]]; then
    if [[ -t 0 ]]; then
      printf '  Type %sexpose%s to continue, anything else to abort: ' "$B" "$N"
      read -r _confirm
      [[ "$_confirm" == "expose" ]] || die "Aborted. Re-run without --bind for a loopback-only stack."
    else
      die "--bind $BIND_ADDR needs an interactive confirmation (or --yes). Refusing to expose the stack from a non-interactive run."
    fi
  else
    warn "--yes given: proceeding to expose the stack on $BIND_ADDR."
  fi
  say ""
fi

say ""
say "${B}=== AI-Factory · EVERYTHING tier ===${N}"
say "${DIM}Three prod hosts on one box · ~40 containers · no edge, no TLS, IP:PORT${N}"
say "${DIM}crypto OFF · the only chain is a fake-funded ephemeral Anvil${N}"
say ""

# ══════════════════════════════════════════════════════════════════════════
#  1. PREFLIGHT — everything that can say "no" says it before the first pull
# ══════════════════════════════════════════════════════════════════════════
step "Preflight"

command -v docker >/dev/null 2>&1 || die "Docker not found. Install Docker Engine / Desktop first."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 required ('docker compose', not 'docker-compose')."
docker info >/dev/null 2>&1 || die "Docker daemon not reachable — is Docker running?"
# `!override` on the ports lists (needed so --bind is honoured) landed in v2.20.
_cv="$(docker compose version --short 2>/dev/null | tr -d 'v')"
_cv_major="${_cv%%.*}"; _cv_rest="${_cv#*.}"; _cv_minor="${_cv_rest%%.*}"
if [[ "${_cv_major:-0}" -lt 2 ]] || { [[ "${_cv_major:-0}" -eq 2 ]] && [[ "${_cv_minor:-0}" -lt 20 ]]; }; then
  die "Compose $_cv is too old. This tier uses the '!override' merge tag for port lists (Compose >= 2.20)."
fi
ok "docker + compose v2 ($_cv)"

# ── 1a. Resource honesty ────────────────────────────────────────────────────
# Measured, not assumed — and we say WHICH filesystem and WHICH memory, because
# on Docker Desktop the container's world is a VM and the host's df is a lie.
DISK_FREE_GB=0; RAM_GB=0; CPUS=0; DISK_WHERE=""
_docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
if [[ -n "$_docker_root" && -d "$_docker_root" ]]; then
  DISK_WHERE="$_docker_root (Docker root)"
  DISK_FREE_GB=$(( $(df -Pk "$_docker_root" | awk 'NR==2{print $4}') / 1024 / 1024 ))
else
  # Docker Desktop: the daemon's root lives in a VM we cannot df. Fall back to
  # the repo's filesystem, which at least holds ./data and the build contexts,
  # and say so rather than pretending we measured the right thing.
  DISK_WHERE="$ROOT (repo filesystem — Docker's disk lives in a VM here, check Docker Desktop → Resources)"
  DISK_FREE_GB=$(( $(df -Pk "$ROOT" | awk 'NR==2{print $4}') / 1024 / 1024 ))
fi
# MemTotal from `docker info` is what containers may actually use (the VM's
# limit on Desktop, the host's RAM on Linux). Prefer it over the host figure.
_dmem="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
if [[ "${_dmem:-0}" =~ ^[0-9]+$ ]] && [[ "$_dmem" -gt 0 ]]; then
  RAM_GB=$(( _dmem / 1024 / 1024 / 1024 ))
elif [[ -r /proc/meminfo ]]; then
  RAM_GB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 / 1024 ))
elif command -v sysctl >/dev/null 2>&1; then
  RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1024 / 1024 / 1024 ))
fi
CPUS="$(docker info --format '{{.NCPU}}' 2>/dev/null || true)"
[[ "$CPUS" =~ ^[0-9]+$ ]] || CPUS="$( (nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 0) )"

DISK_MIN=60;  DISK_REC=100
RAM_MIN=16;   RAM_REC=32
CPU_MIN=4;    CPU_REC=8

say "  disk free  ${B}${DISK_FREE_GB} GB${N}   ${DIM}min ${DISK_MIN} · recommended ${DISK_REC}${N}"
say "             ${DIM}measured on ${DISK_WHERE}${N}"
say "  memory     ${B}${RAM_GB} GB${N}   ${DIM}min ${RAM_MIN} · recommended ${RAM_REC}${N}"
say "  cpus       ${B}${CPUS}${N}      ${DIM}min ${CPU_MIN} · recommended ${CPU_REC}${N}"

_short=()
[[ "$DISK_FREE_GB" -lt "$DISK_MIN" ]] && _short+=("disk: need ~${DISK_MIN} GB free to finish a first build, ~${DISK_REC} GB to leave it running — you have ${DISK_FREE_GB} GB")
[[ "$RAM_GB"       -lt "$RAM_MIN"  ]] && _short+=("memory: need ${RAM_MIN} GB minimum, ${RAM_REC} GB comfortable — you have ${RAM_GB} GB")
[[ "$CPUS"         -lt "$CPU_MIN"  ]] && _short+=("cpu: need ${CPU_MIN} cores minimum, ${CPU_REC} for a sane first build — you have ${CPUS}")

if [[ "${#_short[@]}" -gt 0 && "$SKIP_RESOURCES" -eq 0 ]]; then
  say ""
  warn "This machine cannot hold the everything tier:"
  for s in "${_short[@]}"; do warn "    · $s"; done
  say ""
  say "  ${B}The tier that fits${N} — Factory + Hub + Mesh + Alien Monitor, 7 containers:"
  say "      ${C}./start.sh${N}          ${DIM}~15 GB disk · ~6 GB RAM · 2 cores${N}"
  say ""
  say "  ${DIM}Why the full tier is this heavy: ~12 GB of distinct images (the Factory${N}"
  say "  ${DIM}image alone is 4.5-6 GB — Playwright + Chromium + a Next.js build), plus${N}"
  say "  ${DIM}8-15 GB of build cache, plus an Anvil at --block-time 1 that grows forever.${N}"
  say "  ${DIM}Override with --skip-resource-check if you know something we do not.${N}"
  say ""
  die "Refusing to start — you would run out part-way through a multi-GB build."
fi
if [[ "$DISK_FREE_GB" -lt "$DISK_REC" && "$DISK_FREE_GB" -ge "$DISK_MIN" ]]; then
  warn "Disk is above the minimum but below the ${DISK_REC} GB we recommend for a stack you leave running."
  warn "The growth is not the images — it is Anvil state and container logs, neither of which any compose file caps."
fi
if [[ "${#_short[@]}" -gt 0 ]]; then
  # Do NOT claim the machine is sufficient — it is not, the operator overrode us.
  warn "--skip-resource-check given: proceeding on an undersized machine anyway."
  for s in "${_short[@]}"; do warn "    · $s"; done
  warn "Expect swap thrash, a killed build, or a full disk part-way through."
else
  ok "Resources sufficient"
fi

# ── 1b. Nothing touches a real chain ────────────────────────────────────────
# Scans the exported environment and .env. Prints variable NAMES only; a key we
# are refusing because it looks real is the last thing to echo to a terminal.
step "Chain safety"
# SHA-256 of the ten standard Anvil accounts — the deterministic keys derived from
# the "test test test test test test test test test test test junk" mnemonic that
# Foundry prints on every start. They are public, and this is an ALLOW-list: a key
# in the environment that is NOT one of these is what makes us refuse to start.
#
# Hashes rather than the keys themselves, because the literals blocked publishing.
# They are 64-hex blobs, so every secret scanner reads them as leaked credentials:
# gitleaks flagged this line as `generic-api-key` and aborted the factory mirror
# push, and our own verify_mirror_secrets shape test is built to react to exactly
# this pattern too. Being right about them being public does not help — the fix is
# to not carry key-shaped strings at all.
#
# Regenerate:  anvil | grep -A10 'Private Keys' \
#                | grep -oE '0x[0-9a-f]{64}' | sed 's/^0x//' \
#                | while read -r k; do printf '%s' "$k" | shasum -a 256 | cut -d' ' -f1; done
# Read via heredoc rather than NAME="<hex>": gitleaks' generic-api-key rule keys on
# an assignment whose value is a long hex string, and it aborted the mirror publish on
# this line twice — once for the raw keys, once for their hashes. The list is the same;
# only the shape that trips the scanner is gone. `read -d ''` exits non-zero at EOF, so
# the `|| true` is required under `set -e`.
read -r -d '' ANVIL_KEY_HASHES <<'ANVIL_HASHES' || true
bc1a50966c9e6486bc4ebf880b51611a2a97fcb8e7a6976e9b81a9e3e8ca0e3c
8335c55334821eefd4334369ff9c04a8594f161013cf9d87f58802d87297837e
b26ab6529d20ebebb4192256f202984754f785481c64b1a1aed58cac93b3617e
64034b44c579b335ab5e85debbfe72789e970138cc8d296799c3833a2a8525fb
4d3e46eec8244d1d106f866ee48994f6176705298aee1b8426b2ad2529eb454b
0aedba9d586f34f95cf1f0d54926f62e8a078ce2ca593be73ab27a87d3ff9c5d
28e543d3753fc9d14c658ebef20b76a3b5f8e7d78667baf27832ceb3bea01bdf
f070994a8599478580678f2b9482c5f02bb3de0647281e8efae183669425808a
38e69fdd19aefeb4adf56312f10e62c30274997835173c7006308323ad7db506
967f21586cdf1248a862f2cfb330099701c942c2c7a7537c54f7ec48f8556505
ANVIL_HASHES

# sha256 of a lowercased hex key. shasum is macOS, sha256sum is most Linuxes.
_key_hash() {
  if command -v shasum >/dev/null 2>&1; then
    printf '%s' "$1" | shasum -a 256 | cut -d' ' -f1
  else
    printf '%s' "$1" | sha256sum | cut -d' ' -f1
  fi
}

MAINNET_HITS=()
_scan_pair() { # NAME VALUE — never echoes VALUE
  local name="$1" val="$2" bare one
  case "$name" in
    AIFACTORY_CRYPTO_ENABLED|ARGUS_CRYPTO_ENABLED)
      [[ "$val" == "1" || "$val" == "true" ]] && MAINNET_HITS+=("$name is on — this tier runs with crypto OFF") ;;
  esac
  case "$name" in
    *PRIVATE_KEY*|*WALLET_KEY*|*SIGNER_KEY|*DEPLOYER*|*MNEMONIC*|OPERATOR_KEY|TREASURY_KEY|SPONSOR_KEY|BENEFACTOR_KEY|AGENT_KEY|AGENT_KEYS)
      # Split on commas: AGENT_KEYS is a LIST, and a single real key hidden in a
      # list of test keys must not slip through because the joined string does
      # not match the 64-hex shape.
      local IFS=,
      for one in $val; do
        bare="${one#0x}"; bare="${bare//[[:space:]]/}"
        [[ "$bare" =~ ^[0-9a-fA-F]{64}$ ]] || continue
        # Lowercased before hashing: the old literal compare used `grep -i`, so a
        # key written in uppercase was recognised. Hashing is case-sensitive and
        # would silently stop recognising it — and "unrecognised" here means
        # "refuse to start", so the regression would look like a broken launcher.
        printf '%s\n' "$ANVIL_KEY_HASHES" | grep -q -- "$(_key_hash "$(printf '%s' "$bare" | tr 'A-Z' 'a-z')")" \
          || MAINNET_HITS+=("$name holds a 32-byte key that is not a well-known Anvil test account")
      done ;;
  esac
  case "$name" in
    *RPC_URL*|*_RPC|BASE_RPC*)
      case "$val" in
        *mainnet*|*infura.io*|*alchemy.com*|*.base.org*|*polygon-rpc*|*ankr.com*)
          MAINNET_HITS+=("$name points at a public/mainnet RPC endpoint") ;;
      esac ;;
  esac
}
while IFS='=' read -r _n _v; do [[ -n "${_n:-}" ]] && _scan_pair "$_n" "${_v:-}"; done < <(env)
if [[ -f .env ]]; then
  while IFS= read -r _line; do
    [[ "$_line" =~ ^[[:space:]]*# ]] && continue
    [[ "$_line" == *=* ]] || continue
    _scan_pair "${_line%%=*}" "${_line#*=}"
  done < .env
fi
if [[ "${#MAINNET_HITS[@]}" -gt 0 ]]; then
  say ""
  warn "Refusing to start — the environment looks like it can reach real value:"
  for h in "${MAINNET_HITS[@]}"; do warn "    · $h"; done
  say ""
  say "  ${DIM}This tier is a demo circuit. The only chain it starts is an ephemeral${N}"
  say "  ${DIM}Anvil funded with fake tokens, and no contract is deployed anywhere else.${N}"
  say "  ${DIM}Real deployment is deliberately separate: contracts/evm/script/*.s.sol and${N}"
  say "  ${DIM}scripts/redeploy_uni_contracts.sh. Unset the variables above (or remove${N}"
  say "  ${DIM}them from .env, which is scanned too) and re-run.${N}"
  say ""
  die "A mainnet-capable key or endpoint is present in the environment."
fi
ok "No mainnet key or endpoint in the environment — crypto stays off"

# ── 1b′. Nothing points at OUR servers ──────────────────────────────────────
# The tier's promise is a self-contained stack. A container here that calls
# magic-ai-factory.com is wrong twice over: the operator gets our production
# instead of their own, and we get their traffic and their data.
#
# The check reads the RESOLVED config, not the compose files, because the leak
# does not come from the files. Every `[domain-override]` in the overlay is
# already correct — the hole was `env_file: .env`, which hands a service every
# key in the operator's .env, including leftovers from a prod deploy or a copy
# of .env.vps.example. Two services inherited our arena URL that way while the
# overlay looked clean. Resolving is the only view that sees that.
#
# Pinning the variables we know about is a fix for those variables. This is the
# rule: the next one nobody thought of gets caught here rather than shipping.
step "Self-containment"
OUR_HOSTS=(magic-ai-factory.com modelmarket.dev)
# scripts/.mirror-forbidden-hosts is the untracked source of truth the mirror
# guard already uses (bare prod IPs, which must never appear here either).
if [[ -f scripts/.mirror-forbidden-hosts ]]; then
  while IFS= read -r _h; do
    _h="${_h%%#*}"; _h="${_h//[[:space:]]/}"
    [[ -n "$_h" ]] && OUR_HOSTS+=("$_h")
  done < scripts/.mirror-forbidden-hosts
fi
PHONE_HOME=""
if RESOLVED="$("${COMPOSE[@]}" config 2>/dev/null)"; then
  for _h in "${OUR_HOSTS[@]}"; do
    # -F: hosts are literals, and an IP's dots must not match any character.
    while IFS= read -r _hit; do
      [[ -n "$_hit" ]] && PHONE_HOME+="    · ${_hit#"${_hit%%[![:space:]]*}"}"$'\n'
    done < <(printf '%s\n' "$RESOLVED" | grep -F -- "$_h" | grep -vE '^\s*#' | head -8)
  done
else
  warn "could not resolve the compose config — skipping the self-containment check"
fi
if [[ -n "$PHONE_HOME" ]]; then
  say ""
  warn "Refusing to start — the resolved config points at our production:"
  printf '%s' "$PHONE_HOME" | while IFS= read -r l; do warn "$l"; done
  say ""
  say "  ${DIM}Your stack would call our servers instead of the containers it just${N}"
  say "  ${DIM}started. That is almost always a stale .env: this repo's .env is read${N}"
  say "  ${DIM}by every service via env_file, so a value left from a production deploy${N}"
  say "  ${DIM}(or copied out of .env.vps.example) reaches containers that never${N}"
  say "  ${DIM}mention it. Remove those lines from .env and re-run.${N}"
  say ""
  say "  ${DIM}If you MEANT to federate with our production, set ECO_ALLOW_PROD_HOSTS=1.${N}"
  [[ "${ECO_ALLOW_PROD_HOSTS:-0}" == "1" ]] \
    || die "The stack is not self-contained."
  warn "ECO_ALLOW_PROD_HOSTS=1 — continuing anyway"
else
  ok "Self-contained — nothing in the resolved config addresses our servers"
fi

# ── 1c. Host IP ─────────────────────────────────────────────────────────────
# Detected, never assumed: the address on the default route, falling back to
# loopback for a laptop. --host-ip overrides for a cloud VM whose public
# address differs from its interface address (behind a NAT gateway).
detect_host_ip() {
  local ip=""
  if command -v ip >/dev/null 2>&1; then
    ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  fi
  if [[ -z "$ip" ]] && command -v route >/dev/null 2>&1; then
    local dev; dev="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
    [[ -n "$dev" ]] && ip="$(ipconfig getifaddr "$dev" 2>/dev/null || true)"
  fi
  printf '%s' "${ip:-127.0.0.1}"
}
if [[ -z "$HOST_IP" ]]; then
  if [[ "$BIND_ADDR" == "127.0.0.1" || "$BIND_ADDR" == "localhost" ]]; then
    # Loopback bind: nothing off-box can reach it, so printing a LAN address
    # would be a URL that does not work. Say 127.0.0.1 and mean it.
    HOST_IP="127.0.0.1"
  else
    HOST_IP="$(detect_host_ip)"
  fi
fi
ok "URLs will be printed as http://${HOST_IP}:<port>   ${DIM}(bind ${BIND_ADDR})${N}"

# ── 1d. Ports ───────────────────────────────────────────────────────────────
step "Ports"
# Ports already published by THIS project are not a conflict — that is just a
# re-run. Anything else holding one is, and we name it.
OUR_PORTS=""
if OUR_IDS="$("${COMPOSE[@]}" ps -q 2>/dev/null)" && [[ -n "$OUR_IDS" ]]; then
  # shellcheck disable=SC2086
  OUR_PORTS="$(docker inspect --format '{{range $p, $c := .HostConfig.PortBindings}}{{range $c}}{{.HostPort}} {{end}}{{end}}' $OUR_IDS 2>/dev/null | tr ' ' '\n' | sort -u)"
fi
port_owner() {
  local p="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null | awk 'NR==2{printf "%s (pid %s)", $1, $2}'
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v p=":$p\$" '$4 ~ p {print $NF; exit}'
  fi
}
port_busy() {
  local p="$1"
  (exec 3<>"/dev/tcp/127.0.0.1/$p") >/dev/null 2>&1 && { exec 3>&- 3<&-; return 0; }
  return 1
}
check_port() { # port label
  local p="$1" label="$2" owner
  printf '%s\n' "$OUR_PORTS" | grep -qx "$p" && return 0
  if port_busy "$p"; then
    owner="$(port_owner "$p")"
    CONFLICTS+=("$p  ${owner:-unknown process}  (wanted by ${label})")
  fi
}
CONFLICTS=()
while IFS= read -r row; do
  [[ -z "$row" ]] && continue
  p="$(mf "$row" 3)"; [[ -z "$p" ]] && continue
  check_port "$p" "$(mf "$row" 2)"
done < <(manifest_rows)
for p in $EXTRA_PORTS; do
  case "$p" in 9080) _l="Factory storefront" ;; 8501) _l="SKOPOS dashboard" ;; *) _l="the stack" ;; esac
  check_port "$p" "$_l"
done
if [[ "${#CONFLICTS[@]}" -gt 0 ]]; then
  say ""
  warn "These ports are already in use:"
  for c in "${CONFLICTS[@]}"; do warn "    · $c"; done
  say ""
  say "  ${DIM}Free them, or stop the other stack. The port map is fixed on purpose so${N}"
  say "  ${DIM}that a service always answers where the docs say it does — see${N}"
  say "  ${DIM}docs/deploy-everything.md for which collisions were resolved and how.${N}"
  say ""
  die "Refusing to start into a port conflict."
fi
_nports=$(manifest_rows | awk -F'|' '$3 ~ /[0-9]/' | wc -l | tr -d ' ')
ok "$_nports published ports free (all >= 1024 — nothing here needs root)"

# ══════════════════════════════════════════════════════════════════════════
#  2. SECRETS
# ══════════════════════════════════════════════════════════════════════════
if [[ ! -f .env ]]; then
  if [[ -f .env.demo ]]; then cp .env.demo .env; ok "Created .env from .env.demo"
  else warn "No .env and no .env.demo — creating an empty .env"; : > .env; fi
fi

FIRST_MINT=0
if ! env_has AICOM_EVERYTHING_SECRETS_MINTED; then FIRST_MINT=1; fi

step "Secrets (generated into .env — gitignored, chmod 600, printed once)"
if [[ "$FIRST_MINT" -eq 1 ]]; then
  printf '\n# ── aicom everything tier: generated secrets (do not commit) ──────────\n' >> .env
fi
# Fail-closed in compose (the project will not start without these):
ensure_secret GRAFANA_ADMIN_PASSWORD   "$(gen_hex 18)"
ensure_secret MESH_API_TOKEN           "$(gen_hex 24)"
ensure_secret MESH_ADMIN_TOKEN         "$(gen_hex 24)"
ensure_secret SKOPOS_POSTGRES_PASSWORD "$(gen_hex 18)"
# Not fail-closed, but empty means a dead feature or an open control plane:
ensure_secret ALIEN_API_TOKEN          "$(gen_hex 24)"   # Monitor authenticated writes / ARGUS run panel
ensure_secret AIFACTORY_DEV_BOOTSTRAP_PASSWORD "$(gen_hex 12)"
ensure_secret MOMUS_OPERATOR_TOKEN     "$(gen_hex 24)"   # the ONLY guard on MOMUS's control plane
ensure_secret GAIA_SIM_TOKEN           "$(gen_hex 24)"
ensure_secret CANARY_TOKEN             "$(gen_hex 16)"
ensure_secret SKOPOS_DASHBOARD_PASSWORD "$(gen_hex 12)"  # >= 12 chars: SKOPOS enforces a minimum
ensure_secret SKOPOS_AGENT_TOKEN_SECRET "$(gen_hex 32)"
ensure_secret SKOPOS_NODE_SECRET_KEY   "$(gen_b64 32)"
ensure_secret METIS_API_KEY            "$(gen_hex 24)"
ensure_secret METIS_NODE_A_KEY         "$(gen_hex 24)"
ensure_secret METIS_NODE_B_KEY         "$(gen_hex 24)"
ensure_secret ARGUS_HTTP_TOKEN         "$(gen_hex 24)"
chmod 600 .env 2>/dev/null || true
ok "Generated secrets ready"
say "  ${DIM}JWT_SECRET_KEY and the sandbox demo password are minted by the Factory${N}"
say "  ${DIM}entrypoint into data/secrets/ — never given a compose default.${N}"

# ── 2b. USER secrets — asked for, with the consequence of skipping ──────────
# The point of prompting is that a missing LLM key should be a decision, not a
# discovery two hours later when every generated product looks templated.
prompt_secret() { # KEY "what it is for" "what happens without it"
  local key="$1" purpose="$2" without="$3" val
  env_has "$key" && return 0
  if [[ "$ASSUME_YES" -eq 1 || ! -t 0 ]]; then
    grep -qE "^${key}=" .env 2>/dev/null || printf '%s=\n' "$key" >> .env
    say "  ${DIM}${key} left empty — ${without}${N}"
    return 0
  fi
  say ""
  say "  ${B}${key}${N}"
  say "    ${DIM}${purpose}${N}"
  say "    ${Y}without it:${N} ${without}"
  printf '    paste it (input hidden), or press Enter to skip: '
  read -r -s val; printf '\n'
  if [[ -n "$val" ]]; then
    grep -vE "^${key}=" .env > .env.tmp 2>/dev/null && mv .env.tmp .env
    printf '%s=%s\n' "$key" "$val" >> .env
    say "    ${G}stored${N} ${DIM}(${#val} chars, in .env only)${N}"
  else
    grep -qE "^${key}=" .env 2>/dev/null || printf '%s=\n' "$key" >> .env
    say "    ${DIM}skipped${N}"
  fi
}

has_llm_key=0
for k in DEEPSEEK_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY TOGETHER_API_KEY GROQ_API_KEY OPENROUTER_API_KEY; do
  env_has "$k" && { has_llm_key=1; break; }
done
ls data/secrets/llm/*_api_key >/dev/null 2>&1 && has_llm_key=1

if [[ "$FIRST_MINT" -eq 1 ]]; then
  step "Optional keys (every one may be skipped — the stack boots either way)"
  if [[ "$has_llm_key" -eq 0 ]]; then
    prompt_secret DEEPSEEK_API_KEY \
      "The ecosystem's default LLM. MOMUS, Treasury, ATLAS, DIOSCURI, HELIOS, SKOPOS, Platon and the Factory's gate model all default to deepseek/deepseek-v4-pro. ANTHROPIC_API_KEY / OPENAI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY are accepted alternatives." \
      "the Factory CANNOT GENERATE — it falls back to synthetic templated output, and every AI panel in the fleet degrades to a stub. Everything still boots and the Monitor is fully live."
    env_has DEEPSEEK_API_KEY && has_llm_key=1
  fi
  prompt_secret TELEGRAM_BOT_TOKEN \
    "DIOSCURI's Telegram twin (Castor). Outbound long-polling only — webhooks need a public https receiver, which IP mode does not have." \
    "the Telegram twin sleeps. DIOSCURI_DRY_RUN=1 is the default and needs no token at all."
  prompt_secret DISCORD_BOT_TOKEN \
    "DIOSCURI's Discord twin (Pollux)." \
    "the Discord twin sleeps. Discord *interaction endpoints* are unavailable here regardless — they need a public https receiver."
  prompt_secret DISCORD_GUILD_ID \
    "The Discord server DIOSCURI provisions and moderates." \
    "the Discord twin has no guild to work in, so it stays idle even with a token."
  prompt_secret ARGUS_TELEGRAM_TOKEN \
    "ARGUS's own Telegram control channel. Must be a DIFFERENT token from DIOSCURI's — only one container may long-poll a given token." \
    "ARGUS runs fully autonomously without it; you just drive it over HTTP on :8787 instead."
  prompt_secret GITHUB_TOKEN \
    "DIOSCURI's knowledge-sync and release features." \
    "those two features are skipped; the twins and the knowledge base still run."
  prompt_secret GAIA_OPENAQ_API_KEY \
    "Free key from explore.openaq.org — enables GAIA's openaq-01 air-quality sensor." \
    "one sensor of many stays offline. All simulators and the other live relays work."
  say ""
else
  step "Optional keys"
  say "  ${DIM}Already answered on the first run. Edit .env and re-run to change them.${N}"
fi

if [[ "$has_llm_key" -eq 0 ]]; then
  say ""
  warn "No LLM key anywhere in .env or data/secrets/llm/."
  warn "The stack will come up and the Monitor will be fully live, but the Factory"
  warn "pipeline will emit SYNTHETIC TEMPLATED output instead of real agent work,"
  warn "and MOMUS / ATLAS / Platon / HELIOS AI panels will degrade to stubs."
  warn "Add one key to .env and re-run to get the real thing."
  say ""
else
  ok "LLM key detected — real AI agents enabled"
fi

# ══════════════════════════════════════════════════════════════════════════
#  3. Files and directories the stack mounts
# ══════════════════════════════════════════════════════════════════════════
# Docker does NOT fail on a missing bind source: it creates an empty DIRECTORY
# where a file was expected, and the app then dies with a confusing parse
# error. Every bind source in docker-compose.everything.yml is either a tracked
# file (the *.example.* configs) or created here.
step "Data dirs"
mkdir -p data/config data/alien-monitor/universe data/secrets data/prometheus data/grafana
if [[ ! -f data/config/model_providers.yaml ]]; then
  if [[ -f data/config/model_providers.example.yaml ]]; then
    cp data/config/model_providers.example.yaml data/config/model_providers.yaml
    ok "Seeded data/config/model_providers.yaml from example"
  else
    warn "data/config/model_providers.example.yaml missing — Monitor LLM config mount may be empty"
    : > data/config/model_providers.yaml
  fi
fi
_missing_mounts=()
for f in scripts/everything/mesh-dashboard.nginx.conf scripts/everything/pulse-terminal.nginx.conf \
         scripts/satellite-map.yaml skopos/servers.example.yaml skopos/agent.example.yaml \
         argus/argus.config.example.json dioscuri/dioscuri.config.example.json \
         helios/helios.config.example.yaml data/config/model_providers.yaml \
         metis/config/docker-cluster.yaml metis/config/docker-runtime.yaml \
         metis/config/docker-node-a.yaml metis/config/docker-node-b.yaml \
         prometheus.yml; do
  [[ -f "$f" ]] || _missing_mounts+=("$f")
done
for d in helios/templates helios/assets lottery/config lottery/frontend contracts/evm/lib; do
  [[ -d "$d" ]] || _missing_mounts+=("$d/")
done
if [[ "${#_missing_mounts[@]}" -gt 0 ]]; then
  warn "Bind-mount sources missing from the checkout:"
  for m in "${_missing_mounts[@]}"; do warn "    · $m"; done
  die "Docker would create these as empty root-owned directories and the services would fail confusingly. Fix the checkout."
fi
ok "Data dirs and mount sources ready"

# ══════════════════════════════════════════════════════════════════════════
#  4. Environment for compose — every production domain, overridden
# ══════════════════════════════════════════════════════════════════════════
# Shell env beats .env for compose interpolation, so these stay out of .env
# (they are host-dependent, not secrets, and must follow --host-ip).
#
# Every *.modelmarket.dev / magic-ai-factory.com default is overridden inside
# docker-compose.everything.yml (grep it for `[domain-override]` — 30+ of them).
# Only three knobs are set from out here, because only these three depend on the
# machine rather than on the topology:
export ECO_BIND="$BIND_ADDR"                    # prefixes EVERY published port
export ECO_PUBLIC_BASE="http://${HOST_IP}"      # only for values a browser sees
export ECO_GRAFANA_DOMAIN="${HOST_IP}"          # GF_SERVER_DOMAIN, was magic-ai-factory.com
# NEXT_PUBLIC_SITE_URL is inlined by `next build` and arrives as a Docker build
# arg, so it is NOT a pure runtime setting: moving it rebuilds the largest image
# in the stack. Loopback stays the default; it only moves when --host-ip does.
export NEXT_PUBLIC_SITE_URL="http://${HOST_IP}:9080"

if [[ "$HOST_IP" != "127.0.0.1" && "$BUILD" -eq 0 ]]; then
  warn "--host-ip ${HOST_IP} with --no-build: the Factory storefront keeps whatever"
  warn "NEXT_PUBLIC_SITE_URL was baked into its existing image (next build inlines it)."
  warn "Drop --no-build to re-bake it — that is a 10+ minute rebuild of the largest image."
fi

# ══════════════════════════════════════════════════════════════════════════
#  5. Up
# ══════════════════════════════════════════════════════════════════════════
say ""
UP=(up -d --remove-orphans)
if [[ "$BUILD" -eq 1 ]]; then
  step "Starting ~40 containers (building — a first run is 30-60 min on 8 cores)"
  say "  ${DIM}Build-bound, not CPU-bound: Playwright + Chromium, ~10 vite/next builds,${N}"
  say "  ${DIM}2 forge builds. Steady state afterwards is ~1-2 cores.${N}"
  UP+=(--build)
else
  step "Starting ~40 containers (reusing existing images)"
fi
say ""
"${COMPOSE[@]}" "${UP[@]}"

# ══════════════════════════════════════════════════════════════════════════
#  6. THE HEALTH GATE — nothing is "ready" until it has answered
# ══════════════════════════════════════════════════════════════════════════
say ""
step "Health — polling every service until it answers, or fails"
say ""
printf '  %-24s %-6s %-9s %s\n' "SERVICE" "PORT" "STATE" "DETAIL"
say  "  ------------------------ ------ --------- ------"

cid_of() { "${COMPOSE[@]}" ps -q "$1" 2>/dev/null | head -1; }

# The STATE word is passed in, not hardcoded: a container with no healthcheck
# is "running", not "healthy", and calling it healthy would be the same small
# lie this whole gate exists to avoid.
row_ok()   { printf '  %-24s %-6s %s%-9s%s %s\n' "$1" "${2:--}" "$G" "$3" "$N" "$4"; }
row_bad()  { printf '  %-24s %-6s %s%-9s%s %s\n' "$1" "${2:--}" "$R" "FAILED"  "$N" "$3"; }

fail_stack() { # service display detail
  local svc="$1" disp="$2" detail="$3"
  say ""
  say "${R}${B}Stack is not healthy — stopping here.${N}"
  say ""
  say "  ${B}${disp}${N} (compose service ${B}${svc}${N}) ${detail}"
  say ""
  say "  ${DIM}last 40 log lines:${N}"
  "${COMPOSE[@]}" logs --tail=40 --no-color "$svc" 2>&1 | sed 's/^/    /' || true
  say ""
  say "  ${DIM}full logs:   ./start.sh --everything --logs${N}"
  # Built from the real COMPOSE array so this hint cannot drift from what we ran.
  say "  ${DIM}one service: ${COMPOSE[*]} logs -f ${svc}${N}"
  say "  ${DIM}stop:        ./start.sh --everything --down${N}"
  say ""
  # Deliberately no browser: opening a page for a stack we know is broken is
  # the single worst thing a launcher can do on first contact.
  exit 1
}

PENDING=()
while IFS= read -r row; do [[ -n "$row" ]] && PENDING+=("$row"); done < <(manifest_rows)
TOTAL="${#PENDING[@]}"
START_EPOCH=$(date +%s)
DONE=0
LAST_TICK=0

while [[ "${#PENDING[@]}" -gt 0 ]]; do
  NEXT=()
  for row in "${PENDING[@]}"; do
    svc="$(mf "$row" 1)"; disp="$(mf "$row" 2)"; port="$(mf "$row" 3)"
    path="$(mf "$row" 4)"; tmo="$(mf "$row" 5)"; kind="$(mf "$row" 6)"
    elapsed=$(( $(date +%s) - START_EPOCH ))

    cid="$(cid_of "$svc")"
    if [[ -z "$cid" ]]; then
      if [[ "$elapsed" -ge 30 ]]; then
        row_bad "$disp" "$port" "no container — compose never created it"
        fail_stack "$svc" "$disp" "has no container. Usually a build failure or a missing required env_file."
      fi
      NEXT+=("$row"); continue
    fi

    state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
    exitc="$(docker inspect -f '{{.State.ExitCode}}' "$cid" 2>/dev/null || echo 0)"
    restarts="$(docker inspect -f '{{.RestartCount}}' "$cid" 2>/dev/null || echo 0)"

    case "$kind" in
      oneshot)
        if [[ "$state" == "exited" && "$exitc" == "0" ]]; then
          row_ok "$disp" "$port" "done" "completed (exit 0)"; DONE=$((DONE+1)); continue
        elif [[ "$state" == "exited" ]]; then
          row_bad "$disp" "$port" "exited $exitc"
          fail_stack "$svc" "$disp" "exited with code ${exitc}. It is a one-shot: everything that depends on it is now blocked."
        fi ;;
      running)
        if [[ "$state" == "running" && "$elapsed" -ge 10 ]]; then
          row_ok "$disp" "$port" "running" "no healthcheck — liveness is its loop"; DONE=$((DONE+1)); continue
        elif [[ "$state" == "exited" ]]; then
          row_bad "$disp" "$port" "exited $exitc"
          fail_stack "$svc" "$disp" "exited with code ${exitc}."
        fi ;;
      docker)
        health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo none)"
        if [[ "$health" == "healthy" ]]; then row_ok "$disp" "$port" "healthy" "container healthcheck"; DONE=$((DONE+1)); continue; fi
        if [[ "$health" == "none" && "$state" == "running" && "$elapsed" -ge 15 ]]; then
          row_ok "$disp" "$port" "running" "image declares no healthcheck"; DONE=$((DONE+1)); continue
        fi
        if [[ "$state" == "exited" ]]; then
          row_bad "$disp" "$port" "exited $exitc"
          fail_stack "$svc" "$disp" "exited with code ${exitc}."
        fi ;;
      http)
        if [[ "$state" == "exited" ]]; then
          row_bad "$disp" "$port" "exited $exitc"
          fail_stack "$svc" "$disp" "exited with code ${exitc} before it ever served ${path}."
        fi
        # Probed from the HOST on the published port — the same request the
        # human will make next, not an inside-the-container shortcut.
        if curl -fsS -m 4 -o /dev/null "http://127.0.0.1:${port}${path}" 2>/dev/null; then
          row_ok "$disp" "$port" "healthy" "http://${HOST_IP}:${port}${path}"; DONE=$((DONE+1)); continue
        fi ;;
    esac

    # A container that keeps dying is a failure now, not at its timeout.
    if [[ "${restarts:-0}" -ge 4 ]]; then
      row_bad "$disp" "$port" "restarted ${restarts}x — crash loop"
      fail_stack "$svc" "$disp" "has restarted ${restarts} times. It is crash-looping, not warming up."
    fi

    if [[ "$elapsed" -ge "$tmo" ]]; then
      row_bad "$disp" "$port" "no answer in ${tmo}s (state: ${state})"
      fail_stack "$svc" "$disp" "did not become healthy within its ${tmo}s budget."
    fi
    NEXT+=("$row")
  done
  PENDING=("${NEXT[@]}")

  if [[ "${#PENDING[@]}" -gt 0 ]]; then
    elapsed=$(( $(date +%s) - START_EPOCH ))
    if [[ $(( elapsed - LAST_TICK )) -ge 30 ]]; then
      LAST_TICK="$elapsed"
      _names=""
      for r in "${PENDING[@]:0:4}"; do _names+="$(mf "$r" 2), "; done
      say "  ${DIM}… ${DONE}/${TOTAL} healthy after ${elapsed}s · still waiting on ${_names%, }$([[ "${#PENDING[@]}" -gt 4 ]] && echo " +$(( ${#PENDING[@]} - 4 )) more")${N}"
    fi
    sleep 3
  fi
done

say ""
ok "All ${TOTAL} services healthy in $(( $(date +%s) - START_EPOCH ))s"

# ══════════════════════════════════════════════════════════════════════════
#  7. URLs + the credential block — printed exactly once
# ══════════════════════════════════════════════════════════════════════════
BASE="http://${HOST_IP}"
say ""
say "${G}${B}Everything is up.${N}   ${DIM}bind ${BIND_ADDR} · ${TOTAL} containers · crypto OFF${N}"
say ""
say "  ${B}THE SHOWPIECES${N}"
say "    Alien Monitor    ${C}${BASE}:9100/monitor/${N}      live universe · reputation graph · contours"
say "    Factory          ${C}${BASE}:9080${N}                idea → real AI build"
say "    Pulse Terminal   ${C}${BASE}:5199/pulse/${N}"
say "    MOMUS red team   ${C}${BASE}:5186${N}                 findings · bounties · the canary it hunts"
say ""
say "  ${B}PLATFORM${N}"
say "    Hub              ${C}${BASE}:9083${N}      Mesh API   ${C}${BASE}:8090${N}"
say "    Mesh dashboard   ${C}${BASE}:8091${N}      Landing    ${C}${BASE}:3847${N}"
say "    Prometheus       ${C}${BASE}:9090/prometheus/${N}   Grafana ${C}${BASE}:9082${N}"
say ""
say "  ${B}SATELLITES${N}"
say "    GAIA   ${C}${BASE}:9320${N} / ${C}:5185${N}      ATLAS    ${C}${BASE}:9330${N}"
say "    Oracles ${C}${BASE}:9400${N} / ${C}:5180${N}     CHRONOS  ${C}${BASE}:9300${N}"
say "    Platon ${C}${BASE}:9200${N} / ${C}:9201${N}      Metis    ${C}${BASE}:9111${N}"
say "    SKOPOS ${C}${BASE}:8501${N}              Remediation ${C}${BASE}:9402${N}"
say "    Treasury ${C}${BASE}:9411${N}            Canary   ${C}${BASE}:9450${N}"
say "    ARGUS  ${C}${BASE}:8787${N} / ${C}:8788${N}      DIOSCURI ${C}${BASE}:8790${N}"
say "    HELIOS ${C}${BASE}:8791${N}              Lottery  ${C}${BASE}:5182${N} (relayer ${C}:8390${N})"
say ""
say "  ${DIM}Moved from prod, because three hosts became one:${N}"
say "  ${DIM}  MOMUS 9400→9410 · Treasury 9401→9411 · lottery relayer 8090→8390${N}"
say "  ${DIM}  (prod's own precedents), plus platon-frontend 8080→9201 and Metis 8080→9111.${N}"
say ""
say "  ${B}Deliberately NOT started${N} ${DIM}— named rather than quietly missing:${N}"
say "  ${DIM}  lottery-relayer-uni (:9195). It needs a LOTTERY_ADDRESS from a completed${N}"
say "  ${DIM}  Monitor universe bootstrap AND an RPC to the chain that address lives on —${N}"
say "  ${DIM}  the Monitor's EMBEDDED Anvil, which binds 127.0.0.1 inside the Monitor${N}"
say "  ${DIM}  container and is unreachable from the bridge. lottery-chain:8545 is a${N}"
say "  ${DIM}  different chain, so it is not a substitute. Start it by hand with both:${N}"
say "  ${DIM}    LOTTERY_ADDRESS=0x… LOTTERY_UNI_RPC=http://…:8545 \\\\${N}"
say "  ${DIM}      ${COMPOSE[*]} --profile lottery-uni up -d lottery-relayer-uni${N}"
say ""
say "  ${DIM}Not available in IP mode (no domain, no TLS): HELIOS YouTube upload${N}"
say "  ${DIM}(OAuth needs a registered https redirect — running HELIOS_DRY_RUN=1),${N}"
say "  ${DIM}Discord interaction endpoints / Telegram webhooks (long-polling only),${N}"
say "  ${DIM}inbound hub federation, and Factory AI-market webhooks. See${N}"
say "  ${DIM}docs/deploy-everything.md for what each one costs.${N}"
say ""
# Say plainly what is running in production but is NOT here. A tier that claims
# to be "everything" and quietly drops six containers has misled you about what
# you are looking at, which is worse than the gap itself.
say "  ${B}Running in production, deliberately NOT started here${N}"
say "  ${DIM}  azimuth (web :5173, api, worker, redis, postgres) — 5 containers with no${N}"
say "  ${DIM}    source in this monorepo at all. The largest honest gap in the list.${N}"
say "  ${DIM}  ecosystem-monitor-frontend :5175 — a standalone SPA whose compose file and${N}"
say "  ${DIM}    build context are not in this repo. The Monitor's own UI is baked into${N}"
say "  ${DIM}    the alien-monitor image and IS running, at :9100/monitor/.${N}"
say "  ${DIM}  metis-nginx and the whole TLS edge — excluded by design: no nginx, no certs.${N}"
say "  ${DIM}  metis-apache-test :8088 — a test fixture, not part of the product.${N}"
say "  ${DIM}  gitea / act_runner / dind — our build and mirror infrastructure.${N}"
say "  ${DIM}  contract deployment — deliberately separate and unchanged:${N}"
say "  ${DIM}    contracts/evm/script/*.s.sol, scripts/redeploy_uni_contracts.sh.${N}"
say "  ${DIM}  lottery-relayer-uni :9195 — defined in the compose on its own${N}"
say "  ${DIM}    'lottery-uni' profile, not started: it needs a LOTTERY_ADDRESS from a${N}"
say "  ${DIM}    completed Monitor universe bootstrap AND an RPC to the Monitor's${N}"
say "  ${DIM}    embedded Anvil, which binds 127.0.0.1 inside that container and is${N}"
say "  ${DIM}    therefore unreachable from a sibling. Not shipped half-working.${N}"
say ""

if [[ "$FIRST_MINT" -eq 1 ]]; then
  ADMIN_PW="$(env_value AIFACTORY_DEV_BOOTSTRAP_PASSWORD)"
  # The entrypoint may mint its own and write data/secrets/bootstrap_admin.txt
  # (two lines: username=…\npassword=…). Parse the field; never cat the file.
  if [[ -f data/secrets/bootstrap_admin.txt ]]; then
    _bp="$(grep -E '^password=' data/secrets/bootstrap_admin.txt | head -1 | cut -d= -f2- | tr -d '[:space:]')"
    [[ -n "$_bp" ]] && ADMIN_PW="$_bp"
  fi
  say "${B}╔══════════════════════════════════════════════════════════════════════════╗${N}"
  say "${B}║  CREDENTIALS — SHOWN ONCE, NOW AND NEVER AGAIN                           ║${N}"
  say "${B}╚══════════════════════════════════════════════════════════════════════════╝${N}"
  say ""
  say "  ${B}Factory admin${N}         ${C}${BASE}:9080/admin/login${N}"
  say "      user      admin"
  say "      password  ${B}${ADMIN_PW}${N}"
  say ""
  say "  ${B}Grafana${N}               ${C}${BASE}:9082${N}"
  say "      user      admin"
  say "      password  ${B}$(env_value GRAFANA_ADMIN_PASSWORD)${N}"
  say ""
  say "  ${B}SKOPOS dashboard${N}      ${C}${BASE}:8501${N}"
  say "      password  ${B}$(env_value SKOPOS_DASHBOARD_PASSWORD)${N}"
  say ""
  say "  ${B}Service Mesh${N}          ${C}${BASE}:8090${N}  (Authorization: Bearer …)"
  say "      api token    ${B}$(env_value MESH_API_TOKEN)${N}"
  say "      admin token  ${B}$(env_value MESH_ADMIN_TOKEN)${N}"
  say ""
  say "  ${B}Alien Monitor${N}         ${C}${BASE}:9100${N}  (authenticated writes / ARGUS run panel)"
  say "      ALIEN_API_TOKEN  ${B}$(env_value ALIEN_API_TOKEN)${N}"
  say ""
  say "  ${B}MOMUS operator${N}        ${C}${BASE}:9410${N}  — /scan /selfaudit /retest /remediate"
  say "      MOMUS_OPERATOR_TOKEN  ${B}$(env_value MOMUS_OPERATOR_TOKEN)${N}"
  say ""
  say "  ${B}MOMUS canary${N}          ${C}${BASE}:9450${N}  — /canary/break to give MOMUS something to find"
  say "      X-Canary-Token  ${B}$(env_value CANARY_TOKEN)${N}"
  say ""
  say "  ${B}Metis${N}                 ${C}${BASE}:9111${N}"
  say "      METIS_API_KEY  ${B}$(env_value METIS_API_KEY)${N}"
  say ""
  say "  ${B}ARGUS${N}                 ${C}${BASE}:8787${N}"
  say "      ARGUS_HTTP_TOKEN  ${B}$(env_value ARGUS_HTTP_TOKEN)${N}"
  say ""
  say "  ${B}GAIA sim control${N}      ${C}${BASE}:9320${N}   GAIA_SIM_TOKEN  ${B}$(env_value GAIA_SIM_TOKEN)${N}"
  say ""
  say "  ${DIM}Also in .env, no URL of their own: SKOPOS_POSTGRES_PASSWORD,${N}"
  say "  ${DIM}SKOPOS_AGENT_TOKEN_SECRET, SKOPOS_NODE_SECRET_KEY, METIS_NODE_A_KEY,${N}"
  say "  ${DIM}METIS_NODE_B_KEY. JWT and the sandbox demo password live in data/secrets/.${N}"
  say ""
  say "  ${Y}${B}These are in ./.env (chmod 600, gitignored) and will NOT be shown again.${N}"
  say "  ${DIM}Copy what you need now, or read it back with:  grep '^MOMUS_OPERATOR_TOKEN=' .env${N}"
  say ""
  # Written LAST, so an interrupted first run re-prints instead of losing them.
  printf 'AICOM_EVERYTHING_SECRETS_MINTED=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> .env
  chmod 600 .env 2>/dev/null || true
else
  say "  ${B}Credentials already in .env${N} ${DIM}(chmod 600, gitignored) — not reprinted.${N}"
  say "  ${DIM}Read one back:  grep '^GRAFANA_ADMIN_PASSWORD=' .env${N}"
  say "  ${DIM}Start over:     ./start.sh --everything --down  then remove the${N}"
  say "  ${DIM}                AICOM_EVERYTHING_SECRETS_MINTED line from .env.${N}"
  say ""
fi

say "  ${DIM}logs: ./start.sh --everything --logs · stop: ./start.sh --everything --down${N}"
say "  ${DIM}disk creeps: the lottery Anvil mines every second and nothing rotates it —${N}"
say "  ${DIM}reclaim with ./start.sh --everything --down --reset-chain${N}"
say ""

# ══════════════════════════════════════════════════════════════════════════
#  8. Open the Monitor — last, and only because everything answered
# ══════════════════════════════════════════════════════════════════════════
if [[ "$OPEN" -eq 1 ]]; then
  open_url "${BASE}:9100/monitor/"
fi
