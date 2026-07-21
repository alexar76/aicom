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
WRAPPER_OUT="${CLAUDE_CODE_WRAPPER:-${HOME}/.local/bin/claude}"
MARKER='api.deepseek.com/anthropic'
QUIET=0

usage() {
  cat <<'EOF'
Usage: install-claude-code-deepseek.sh [--quiet] [--check]

Installs ~/.claude/settings.json, ~/.config/claude-code/deepseek.env, and a
~/.local/bin/claude wrapper from config/claude-code/ in this repo. Reads the
API key from:
  data/secrets/llm/deepseek_api_key
or, if missing, migrates from an existing deepseek.env / DEEPSEEK_API_KEY.

DeepSeek auth model (no conflict on restart):
  - Key lives in deepseek.env as DEEPSEEK_API_KEY (never ANTHROPIC_AUTH_TOKEN).
  - Claude Code reads it via settings.json → apiKeyHelper.
  - Shell startup unsets ANTHROPIC_AUTH_TOKEN and prepends ~/.local/bin so the
    `claude` wrapper strips any stale token inherited from Cursor / old sessions.

Do NOT add 'source ~/.config/claude-code/deepseek.env' to ~/.bashrc.

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
    k="${DEEPSEEK_API_KEY:-${ANTHROPIC_AUTH_TOKEN:-}}"
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
    && grep -qF 'DEEPSEEK_API_KEY' "$SETTINGS_OUT" 2>/dev/null \
    && [[ -f "$ENV_OUT" ]] && grep -qF "$MARKER" "$ENV_OUT" 2>/dev/null \
    && grep -qF 'DEEPSEEK_API_KEY=sk-' "$ENV_OUT" 2>/dev/null \
    && [[ -x "$WRAPPER_OUT" ]] \
    && grep -qF 'ANTHROPIC_AUTH_TOKEN' "$WRAPPER_OUT" 2>/dev/null
}

install_files() {
  local key="$1"
  mkdir -p "$(dirname "$ENV_OUT")" "$(dirname "$SETTINGS_OUT")" "$(dirname "$WRAPPER_OUT")"
  sed "s|__DEEPSEEK_API_KEY__|${key}|g" "$TEMPLATE_DIR/deepseek.env.template" >"$ENV_OUT"
  chmod 600 "$ENV_OUT"
  cp "$TEMPLATE_DIR/settings.json" "$SETTINGS_OUT"
  chmod 600 "$SETTINGS_OUT"
  install_claude_wrapper
}

install_claude_wrapper() {
  cat >"$WRAPPER_OUT" <<'WRAPPER'
#!/usr/bin/env bash
# Managed by aicom/scripts/install-claude-code-deepseek.sh
# Strip ANTHROPIC_AUTH_TOKEN from the environment before launching Claude Code.
# The API key is supplied via ~/.claude/settings.json → apiKeyHelper →
# ~/.config/claude-code/deepseek.env (DEEPSEEK_API_KEY). Exporting
# ANTHROPIC_AUTH_TOKEN in the shell causes "Auth conflict" on every start.
CLAUDE_PKG="/usr/lib/node_modules/@anthropic-ai/claude-code"
REAL_BIN="$CLAUDE_PKG/bin/claude.exe"
WRAPPER_CJS="$CLAUDE_PKG/cli-wrapper.cjs"

claude_native_ready() {
  [[ -f "$REAL_BIN" ]] \
    && [[ -x "$REAL_BIN" ]] \
    && ! grep -q 'native binary not installed' "$REAL_BIN" 2>/dev/null
}

if claude_native_ready; then
  exec env -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_API_KEY "$REAL_BIN" "$@"
fi

if [[ -f "$WRAPPER_CJS" ]]; then
  exec env -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_API_KEY node "$WRAPPER_CJS" "$@"
fi

echo "claude: Claude Code not installed. Run:" >&2
echo "  npm install -g @anthropic-ai/claude-code --include=optional" >&2
echo "  node $CLAUDE_PKG/install.cjs" >&2
exit 1
WRAPPER
  chmod 755 "$WRAPPER_OUT"
}

ensure_claude_code_binary() {
  local pkg="/usr/lib/node_modules/@anthropic-ai/claude-code"
  [[ -f "$pkg/install.cjs" ]] || return 0
  if [[ -f "$pkg/bin/claude.exe" ]] \
    && grep -q 'native binary not installed' "$pkg/bin/claude.exe" 2>/dev/null; then
    log "Claude Code native binary missing — running postinstall"
    node "$pkg/install.cjs" 2>/dev/null || true
    [[ -f "$pkg/bin/claude.exe" ]] && chmod +x "$pkg/bin/claude.exe" 2>/dev/null || true
  fi
}

# Never source deepseek.env from ~/.bashrc — and always unset stale tokens that
# Cursor / old sessions may have injected into the environment.
ensure_bashrc_claude() {
  local rc="${HOME}/.bashrc"
  [[ -f "$rc" ]] || return 0

  # Remove legacy lines that sourced deepseek.env (exports ANTHROPIC_AUTH_TOKEN).
  if grep -qF '.config/claude-code/deepseek.env' "$rc" 2>/dev/null; then
    sed -i '/\.config\/claude-code\/deepseek\.env/d' "$rc"
    log "Removed deepseek.env source from $rc"
  fi

  local marker='# aicom: claude-code deepseek (managed — do not edit)'
  if grep -qF "$marker" "$rc" 2>/dev/null; then
    return 0
  fi

  # Insert BEFORE `[ -z "$PS1" ] && return` so non-interactive shells (cron,
  # Cursor subshells) also strip ANTHROPIC_AUTH_TOKEN.
  local tmp
  tmp="$(mktemp)"
  awk -v block="$(cat <<'AWKBLOCK'

# aicom: claude-code deepseek (managed — do not edit)
# Must run before the interactive-only guard below — Cursor terminals inherit
# ANTHROPIC_AUTH_TOKEN from parent processes; strip it so apiKeyHelper is the
# sole auth path. Key: ~/.config/claude-code/deepseek.env → DEEPSEEK_API_KEY.
/root/claudecode/aicom/scripts/install-claude-code-deepseek.sh -q 2>/dev/null || true
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"
AWKBLOCK
)" '
    /^\[ -z "\$PS1" \] && return/ && !done { print block; done=1 }
    { print }
  ' "$rc" >"$tmp"
  mv "$tmp" "$rc"
  log "Inserted Claude Code env guard at top of $rc"
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
  ensure_bashrc_claude
  ensure_claude_code_binary
  install_claude_wrapper
  log "Claude Code DeepSeek config OK"
  exit 0
fi

key="$(read_key)" || exit 1
ensure_claude_code_binary
install_files "$key"
ensure_bashrc_claude
log "Installed Claude Code DeepSeek → $SETTINGS_OUT , $ENV_OUT , $WRAPPER_OUT"
