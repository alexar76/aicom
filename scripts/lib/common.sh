# shellcheck shell=bash
# ============================================================================
# scripts/lib/common.sh — the bits ./start.sh and ./scripts/everything.sh both
# need, in one place.
# ============================================================================
# Sourced, never executed. Extracted only because two launchers were otherwise
# going to carry byte-identical copies of the colour table, the four say/step/
# ok/warn/die helpers, the secret minting and the HTTP wait — and a divergence
# between them would show up as "the core tier generated a token the full tier
# cannot read". Anything used by exactly one caller stays in that caller.
#
# Contract: the sourcing script has already `cd`-ed to the repo root, so `.env`
# is the repo's .env.
# ============================================================================

# ── pretty ──────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  B=$'\033[1m'; DIM=$'\033[2m'; R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[1;33m'; C=$'\033[0;36m'; N=$'\033[0m'
else
  B=""; DIM=""; R=""; G=""; Y=""; C=""; N=""
fi
say()  { printf '%s\n' "$*"; }
step() { printf '%s▶%s %s\n' "$C" "$N" "$*"; }
ok()   { printf '%s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%s!%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%s✗ %s%s\n' "$R" "$*" "$N" >&2; exit 1; }

# ── secrets ─────────────────────────────────────────────────────────────────
# python3's `secrets` first because it is the CSPRNG we can reason about;
# openssl is the fallback that exists on every macOS and Linux we target.
gen_hex() { python3 -c "import secrets;print(secrets.token_hex(${1:-24}))" 2>/dev/null || openssl rand -hex "${1:-24}"; }
gen_b64() { python3 -c "import base64,os;print(base64.b64encode(os.urandom(${1:-32})).decode())" 2>/dev/null || openssl rand -base64 "${1:-32}" | tr -d '\n'; }

# append KEY=<generated> to .env only if KEY is not already set (non-empty).
# NEVER prints the value — only the name. A generated secret must appear in
# exactly one place on screen (the final credential block) and nowhere else.
ensure_secret() {
  local key="$1" val="$2"
  if grep -qE "^${key}=.+" .env 2>/dev/null; then return 0; fi
  # remove any empty definition, then append
  if grep -qE "^${key}=" .env 2>/dev/null; then
    grep -vE "^${key}=" .env > .env.tmp && mv .env.tmp .env
  fi
  printf '%s=%s\n' "$key" "$val" >> .env
  say "  ${DIM}generated ${key}${N}"
}

# Read a value back out of .env. Used to build the credential block; callers
# must not log the result anywhere except that block.
env_value() {
  grep -E "^${1}=" .env 2>/dev/null | head -1 | cut -d= -f2-
}

# Is KEY present and non-empty in .env?
env_has() { grep -qE "^${1}=.+" .env 2>/dev/null; }

# ── health ──────────────────────────────────────────────────────────────────
# wait_http NAME URL [TIMEOUT_S] — dotted progress line, returns 1 on timeout.
wait_http() {
  local name="$1" url="$2" timeout="${3:-90}" start elapsed
  start=$(date +%s)
  printf '  waiting for %s' "$name"
  while true; do
    if curl -fsS -m 3 "$url" >/dev/null 2>&1; then printf ' %s✓%s\n' "$G" "$N"; return 0; fi
    elapsed=$(( $(date +%s) - start ))
    if [[ "$elapsed" -ge "$timeout" ]]; then printf ' %s(still warming after %ss)%s\n' "$Y" "$timeout" "$N"; return 1; fi
    printf '.'; sleep 3
  done
}

# ── browser ─────────────────────────────────────────────────────────────────
open_url() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then open "$url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 || true
  fi
}
