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

# ── model-id gate ───────────────────────────────────────────────────────────
# One definition, called from every deploy path, because this repo has been bitten
# before by the same rule living on two surfaces and only one of them being fixed.
#
# Deploying onto a model the provider no longer serves is a silent outage: the stack
# comes up, the health checks pass, and every generation fails at the first call.
# `deepseek-chat` was configured in 57 places and had been dead at DeepSeek for
# long enough that nobody could say when it died.
#
# Two outcomes only, and the difference is deliberate:
#   * a CONFIGURED id the provider does not serve  → block the deploy (exit 1)
#   * unreachable provider, or no key to ask with  → say so, continue
# The second must never block: a provider outage would otherwise stop a deploy that
# has nothing to do with it, and a gate that fails for unrelated reasons gets
# switched off — after which it protects nothing.
#
# AIFACTORY_SKIP_MODEL_ID_GATE=1 skips it. An operator who needs to ship during a
# provider incident should not have to edit a script to do it.
#
# Two callers, two different files, ONE rule:
#   deploy  → the EFFECTIVE config, i.e. what this machine is about to run.
#   publish → the TRACKED EXAMPLE, i.e. what a stranger who clones the public repo will
#             deploy from. The effective config is gitignored and never leaves the machine,
#             so at push time it is the example, and only the example, that can carry rot
#             out to other people.
# Pass the config path as $2 to check something other than the host's own.
model_id_gate() {
  local root="${1:-.}"
  local cfg="${2:-}"
  local script="$root/scripts/verify_model_ids.py"
  [[ -f "$script" ]] || { warn "model-id gate: $script missing — skipped"; return 0; }
  if [[ "${AIFACTORY_SKIP_MODEL_ID_GATE:-0}" == "1" ]]; then
    warn "model-id gate: skipped (AIFACTORY_SKIP_MODEL_ID_GATE=1)"
    return 0
  fi
  # No python3 at all: a deploy host that cannot run the check is not a deploy that should
  # stop. The check is a safety net, and a safety net that becomes a tripwire gets removed.
  if ! command -v python3 >/dev/null 2>&1; then
    warn "model-id gate: python3 not available — skipped"
    return 0
  fi
  local out status args
  args=(--suggest)
  # `$root` was accepted and then used only to locate the script — config discovery happened
  # from the CWD. Harmless while every caller `cd "$ROOT"` first, but a parameter that does
  # not do what its name says is a trap for the next caller, and CONFIG_CANDIDATES explicitly
  # anticipates a host holding several deployments.
  [[ -z "$cfg" && -f "$root/data/config/model_providers.yaml" ]] &&
    cfg="$root/data/config/model_providers.yaml"
  [[ -n "$cfg" ]] && args+=(--config "$cfg")
  # `out=$(cmd)` is a SIMPLE COMMAND: under `set -e` — which all four call sites use — a
  # non-zero substitution aborts the script right here, before `status=$?`, before the report
  # is printed and before `die` explains anything. Every block became a bare, silent `exit 1`.
  # Proof: `bash -c 'set -e; echo A; v="$(sh -c "exit 1")"; s=$?; echo B'` prints only A.
  # `if ...; then` puts it in a context `set -e` exempts, so the diagnostic survives.
  if out="$(python3 "$script" "${args[@]}" 2>&1)"; then status=0; else status=$?; fi
  # 2 means the checker could not run — a bug in it, a config shape it does not understand.
  # That is not a verdict about any model, and treating it as one would stop a deploy with a
  # message the reader cannot act on. Fail open, loudly.
  if (( status == 2 )); then
    warn "model-id gate: the check could not run — continuing (this is not a model verdict)"
    printf '%s\n' "$out" | sed 's/^/    /' || true
    return 0
  fi
  if (( status == 0 )); then
    ok "model ids: nothing configured is dead"
    # A dead id inside a DISABLED provider cannot block — but it is rot waiting for the day
    # someone flips `enabled: true`, so it must not be swallowed by the success path either.
    # `|| true` on every one of these: under `set -e` with `pipefail` — which all four callers
    # set — a grep that matches NOTHING exits 1 and kills the shell before `return 0`. That is
    # the same class of bug as the command substitution above, and this function reintroduced
    # it the moment it grew a second grep. Any grep whose miss is normal must be neutralised.
    printf '%s\n' "$out" | grep -E "DISABLED providers" | sed 's/^/  /' || true
    printf '%s\n' "$out" | grep -E "^[[:space:]]+ALIAS" | sed 's/^/  /' || true
    if printf '%s\n' "$out" | grep -qE "^[[:space:]]+\?"; then
      say "${DIM}   (some providers could not be asked — no key or unreachable; not a failure)${N}"
    fi
    return 0
  fi
  printf '%s\n' "$out"
  die "A configured model id is no longer served by its provider. Fix it (the list above is
what the provider serves now) or re-run with AIFACTORY_SKIP_MODEL_ID_GATE=1 to ship anyway."
}
