#!/usr/bin/env bash
# Install / restore Claude Code → DeepSeek (idempotent).
# Canonical config: config/claude-code/
# API key:          data/secrets/llm/deepseek_api_key  (gitignored)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_DIR="$ROOT/config/claude-code"
KEY_FILE="$ROOT/data/secrets/llm/deepseek_api_key"
ENV_OUT="${CLAUDE_CODE_DEEPSEEK_ENV:-/root/.config/claude-code/deepseek.env}"
SETTINGS_OUT="${CLAUDE_CODE_SETTINGS:-/root/.claude/settings.json}"
MARKER='api.deepseek.com/anthropic'
QUIET=0

usage() {
  cat <<'EOF'
Usage: install-claude-code-deepseek.sh [--quiet] [--check]

Installs ~/.claude/settings.json and ~/.config/claude-code/deepseek.env from
config/claude-code/ in this repo. Reads the API key from:
  data/secrets/llm/deepseek_api_key
or, if missing, migrates from an existing deepseek.env / DEEPSEEK_API_KEY.

--quiet   Only print errors
--check   Exit 0 if config is present and valid, 1 otherwise (no writes)
EOF
}

log() { [[ "$QUIET" -eq 0 ]] && echo "$@" || true; }
err() { echo "install-claude-code-deepseek: $*" >&2; }

read_key() {
  local k=""
  if [[ -f "$KEY_FILE" ]]; then
    k="$(tr -d '\n\r' <"$KEY_FILE")"
  elif [[ -f "$ENV_OUT" ]]; then
    # shellcheck disable=SC1090
    set +u
    # shellcheck source=/dev/null
    source "$ENV_OUT" 2>/dev/null || true
    set -u
    k="${ANTHROPIC_AUTH_TOKEN:-}"
    if [[ -n "$k" ]]; then
      mkdir -p "$(dirname "$KEY_FILE")"
      printf '%s' "$k" >"$KEY_FILE"
      chmod 600 "$KEY_FILE"
      log "Migrated API key into $KEY_FILE"
    fi
  elif [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    k="$DEEPSEEK_API_KEY"
    mkdir -p "$(dirname "$KEY_FILE")"
    printf '%s' "$k" >"$KEY_FILE"
    chmod 600 "$KEY_FILE"
    log "Saved DEEPSEEK_API_KEY into $KEY_FILE"
  fi
  if [[ -z "$k" ]]; then
    err "No DeepSeek API key. Create $KEY_FILE or set DEEPSEEK_API_KEY."
    return 1
  fi
  printf '%s' "$k"
}

config_ok() {
  [[ -f "$SETTINGS_OUT" ]] && grep -qF "$MARKER" "$SETTINGS_OUT" 2>/dev/null \
    && [[ -f "$ENV_OUT" ]] && grep -qF "$MARKER" "$ENV_OUT" 2>/dev/null \
    && grep -qF 'ANTHROPIC_AUTH_TOKEN=sk-' "$ENV_OUT" 2>/dev/null
}

install_files() {
  local key="$1"
  mkdir -p "$(dirname "$ENV_OUT")" "$(dirname "$SETTINGS_OUT")"
  sed "s|__DEEPSEEK_API_KEY__|${key}|g" "$TEMPLATE_DIR/deepseek.env.template" >"$ENV_OUT"
  chmod 600 "$ENV_OUT"
  cp "$TEMPLATE_DIR/settings.json" "$SETTINGS_OUT"
  chmod 600 "$SETTINGS_OUT"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -q|--quiet) QUIET=1; shift ;;
    --check) QUIET=1; config_ok && exit 0 || exit 1 ;;
    -h|--help) usage; exit 0 ;;
    *) err "unknown option: $1"; usage; exit 2 ;;
  esac
done

[[ -f "$TEMPLATE_DIR/settings.json" ]] || { err "missing $TEMPLATE_DIR/settings.json"; exit 2; }
[[ -f "$TEMPLATE_DIR/deepseek.env.template" ]] || { err "missing template"; exit 2; }

if config_ok; then
  log "Claude Code DeepSeek config OK"
  exit 0
fi

key="$(read_key)" || exit 1
install_files "$key"
log "Installed Claude Code DeepSeek → $SETTINGS_OUT , $ENV_OUT"
