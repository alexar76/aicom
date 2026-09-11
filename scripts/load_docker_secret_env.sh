#!/bin/bash
# Load API keys from Docker secret mounts or data/secrets/llm/* files when env vars are unset.
# Sourced from entrypoint.sh — do not echo secret values.

_load_one_secret_env() {
  local var_name="$1"
  local secret_mount="$2"
  local data_file="$3"
  if [ -n "${!var_name:-}" ]; then
    return 0
  fi
  local val=""
  if [ -n "$secret_mount" ] && [ -f "$secret_mount" ]; then
    val="$(tr -d '\n\r' < "$secret_mount")"
  elif [ -n "$data_file" ] && [ -f "$data_file" ]; then
    val="$(tr -d '\n\r' < "$data_file")"
  fi
  if [ -n "$val" ]; then
    export "$var_name=$val"
  fi
}

load_llm_provider_secrets() {
  local root="${AIFACTORY_DATA_ROOT:-/app/data}"
  _load_one_secret_env DEEPSEEK_API_KEY /run/secrets/deepseek_api_key "${root}/secrets/llm/deepseek_api_key"
  _load_one_secret_env OPENROUTER_API_KEY /run/secrets/openrouter_api_key "${root}/secrets/llm/openrouter_api_key"
  _load_one_secret_env ANTHROPIC_API_KEY /run/secrets/anthropic_api_key "${root}/secrets/llm/anthropic_api_key"
  _load_one_secret_env GROQ_API_KEY /run/secrets/groq_api_key "${root}/secrets/llm/groq_api_key"
  _load_one_secret_env TOGETHER_API_KEY /run/secrets/together_api_key "${root}/secrets/llm/together_api_key"
}

load_sandbox_demo_password() {
  if [ -n "${AIFACTORY_SANDBOX_DEMO_PASSWORD:-}" ]; then
    return 0
  fi
  local pw_file="${AIFACTORY_DATA_ROOT:-/app/data}/secrets/sandbox_demo_password"
  if [ -f "$pw_file" ]; then
    export AIFACTORY_SANDBOX_DEMO_PASSWORD="$(tr -d '\n\r' < "$pw_file")"
    return 0
  fi
  mkdir -p "$(dirname "$pw_file")"
  python3 -c "import secrets; open('$pw_file','w').write(secrets.token_urlsafe(24))"
  chmod 600 "$pw_file" 2>/dev/null || true
  export AIFACTORY_SANDBOX_DEMO_PASSWORD="$(tr -d '\n\r' < "$pw_file")"
  echo "Generated sandbox demo password at $pw_file (inject into compose previews)."
}
