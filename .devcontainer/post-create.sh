#!/usr/bin/env bash
# devcontainer postCreate — prepare .env, pull an LLM key from a Codespaces secret
# if present, then tell the user the single command to run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

[[ -f .env ]] || cp .env.demo .env

# If a known LLM key is exposed as an env var (Codespaces/Dev Container secret),
# write it into .env so ./start.sh picks it up. Never overwrite an existing one.
injected=""
for k in DEEPSEEK_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY TOGETHER_API_KEY GROQ_API_KEY; do
  val="${!k:-}"
  if [[ -n "$val" ]] && ! grep -qE "^${k}=.+" .env; then
    printf '%s=%s\n' "$k" "$val" >> .env
    injected="$k"
  fi
done

echo ""
echo "==================================================================="
echo "  AI-Factory core — ready to launch"
echo "==================================================================="
if [[ -n "$injected" ]]; then
  echo "  LLM key from secret: $injected  ✓  (real AI enabled)"
else
  echo "  No LLM key yet. For real AI, add ONE to .env, e.g.:"
  echo "      DEEPSEEK_API_KEY=sk-...   (or set it as a Codespaces secret)"
  echo "  (Without a key the stack still runs; the Monitor works.)"
fi
echo ""
echo "  ▶ Run:   ./start.sh --no-open"
echo "    then open the forwarded ports (Factory :9080, Monitor :9100/monitor/)."
echo "==================================================================="
