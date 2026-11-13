#!/usr/bin/env bash
set -euo pipefail
umask 077
private_dir=/root/argus-checkout-browser/private
bind="$private_dir/browser-ws"
test "$(docker inspect -f '{{.State.Running}}' argus-checkout-browser)" = true
test "$(docker inspect -f '{{.State.Health.Status}}' argus)" = healthy
install -d -m 0700 "$private_dir"
if [[ ! -e "$bind" ]]; then
  temp=$(mktemp "$private_dir/.browser-ws.XXXXXX")
  trap 'rm -f -- "$temp"' EXIT
  docker exec argus cat /run/checkout/browser-ws > "$temp"
  test "$(wc -c < "$temp")" -le 128
  grep -Eq '^ws://argus-checkout-browser:47871/[A-Fa-f0-9]{64}$' "$temp"
  chown 1000:1000 "$temp"
  chmod 0600 "$temp"
  ln "$temp" "$bind"
fi
test "$(stat -c '%u:%g:%a' "$bind")" = '1000:1000:600'
