#!/usr/bin/env bash
# Deprecated wrapper — use scripts/switch_llm_profile.sh openrouter-all
exec "$(dirname "$0")/switch_llm_profile.sh" openrouter-all "$@"
