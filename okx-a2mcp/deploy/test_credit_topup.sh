#!/usr/bin/env bash
# Exercise okx-a2mcp/deploy/credit-topup.sh against fake hub answers (curl/docker shimmed).
# Run: bash okx-a2mcp/deploy/test_credit_topup.sh okx-a2mcp/deploy/credit-topup.sh
# Every row must show injected=no; the two hostile answers must be refused with docker_calls=0.
set -u
SCRIPT="$1"
T="$(mktemp -d)"
mkdir -p "$T/bin" "$T/state"
echo key > "$T/key"
cat > "$T/bin/curl" <<'EOF'
#!/bin/sh
cat "$FAKE_ACCOUNT"
EOF
cat > "$T/bin/docker" <<'EOF'
#!/bin/sh
echo call >> "$DOCKER_LOG"; echo "granted 5 ok"
EOF
chmod +x "$T/bin/"*
MARK="$T/PWNED"

run() {
  printf '%s' "$2" > "$T/acct.json"
  rm -f "$T/state/"*; : > "$T/docker.log"
  PATH="$T/bin:/usr/bin:/bin" FAKE_ACCOUNT="$T/acct.json" DOCKER_LOG="$T/docker.log" \
    KEY_FILE="$T/key" STATE_DIR="$T/state" sh "$SCRIPT" > "$T/out" 2>&1
  local rc=$?
  printf '%-22s rc=%s docker_calls=%s injected=%s | %s\n' "$1" "$rc" \
    "$(wc -l < "$T/docker.log" | tr -d ' ')" "$([ -e "$MARK" ] && echo YES || echo no)" \
    "$(tail -1 "$T/out" | cut -c1-80)"
  rm -f "$MARK"
}

run grant      '{"account_id":"acct_0011aabbccddeeff","balance_usd":0.4}'
run skip       '{"account_id":"acct_0011aabbccddeeff","balance_usd":3}'
payload="0') + __import__('os').system('touch $MARK') + float('0"
run code-in-balance "{\"account_id\":\"acct_0011aabbccddeeff\",\"balance_usd\":\"$payload\"}"
run path-in-account '{"account_id":"acct_x/../../admin/x","balance_usd":0.1}'
rm -rf "$T"
