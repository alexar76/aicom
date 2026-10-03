#!/usr/bin/env bash
# The hub's host-side companions: installed, verified and switched off together with the hub.
#
# Run ON the hub host, from a monorepo copy:
#
#   scripts/hub_host_companions.sh --install   # put every companion in place and start it
#   scripts/hub_host_companions.sh --verify    # exit 1 unless every companion runs AND works
#   scripts/hub_host_companions.sh --disable   # on the OLD host after a move: stop them all
#
# Why: none of these live in the hub image, `/health` says nothing about them, and a host move
# that carries only the container leaves them running on the old host against a hub that is
# gone. That happened on 2026-10-01: the escrow signer tunnel, the settlement sweep and the
# payment canary all stayed behind; no escrow debit reached the chain for two days and the
# canary went silent (aimarket-hub/docs/production-deployment.md §15).
#
# Companions:
#   escrow-signer-tunnel.service     SSH -L to the external escrow signer (HORKOS)
#   aicom-settlement-sweep.timer     submits signed escrow debits, publishes settlement.json
#   aicom-payment-canary.timer       daily outside-in payment check, publishes status.json
#
# Environment:
#   AICOM_HUB_CONTAINER      default modelmarket-hub
#   AICOM_VERIFY_WEBROOT     where verify.<domain> is served from (default /var/www/verify.modelmarket.dev)
#   AICOM_SIGNER_SSH_HOST    user@host of the signer, for --install of the tunnel (e.g. root@<signer-ip>);
#                            unset = the tunnel is not installed (a hub with no external signer)
set -euo pipefail

MODE="${1:---verify}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB="${AICOM_HUB_CONTAINER:-modelmarket-hub}"
WEBROOT="${AICOM_VERIFY_WEBROOT:-/var/www/verify.modelmarket.dev}"
SIGNER_HOST="${AICOM_SIGNER_SSH_HOST:-}"
TUNNEL_KEY=/root/.ssh/id_ed25519_signer_tunnel
UNITS=(aicom-settlement-sweep.timer aicom-payment-canary.timer)
fail=0
say()  { printf '%s\n' "$*"; }
bad()  { printf 'FAIL %s\n' "$*"; fail=1; }
good() { printf 'ok   %s\n' "$*"; }

hub_env() { docker exec "$HUB" printenv "$1" 2>/dev/null || true; }
uses_external_signer() { [ "$(hub_env AIMARKET_ESCROW_SUBMIT_STRATEGY)" = "external" ]; }

install() {
  install -d /usr/local/lib/aicom-settlement /usr/local/lib/aicom-canary "$WEBROOT"
  install -m 0644 "$ROOT/scripts/escrow_settlement_sweep.py" /usr/local/lib/aicom-settlement/
  install -m 0644 "$ROOT/scripts/payment_canary.py" /usr/local/lib/aicom-canary/
  for f in aicom-settlement-sweep.service aicom-settlement-sweep.timer \
           aicom-payment-canary.service aicom-payment-canary.timer; do
    install -m 0644 "$ROOT/deploy/$f" /etc/systemd/system/
  done
  if uses_external_signer; then
    [ -n "$SIGNER_HOST" ] || { say "the hub signs through an external signer: set AICOM_SIGNER_SSH_HOST"; exit 2; }
    [ -f "$TUNNEL_KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "escrow-signer-tunnel@$(hostname)" -f "$TUNNEL_KEY"
    sed "s|root@skopos-host|$SIGNER_HOST|" "$ROOT/escrow-signer/deploy/escrow-signer-tunnel.service" \
      > /etc/systemd/system/escrow-signer-tunnel.service
    UNITS+=(escrow-signer-tunnel.service)
    say "On the signer host, authorize this key ONCE (and pin its host key in /root/.ssh/known_hosts here):"
    say "  restrict,port-forwarding,permitopen=\"127.0.0.1:9500\",command=\"/bin/false\" $(cat "$TUNNEL_KEY.pub")"
  fi
  systemctl daemon-reload
  systemctl enable --now "${UNITS[@]}"
  systemctl start aicom-settlement-sweep.service aicom-payment-canary.service || true
}

disable() {
  for u in escrow-signer-tunnel.service aicom-settlement-sweep.timer aicom-payment-canary.timer; do
    systemctl disable --now "$u" 2>/dev/null && say "disabled $u" || true
  done
  # The canary used to be a root crontab line; comment it out rather than delete it.
  if command -v crontab >/dev/null && crontab -l 2>/dev/null | grep -q '^[^#].*payment_canary'; then
    crontab -l | sed 's|^\([^#].*payment_canary.*\)$|# disabled by hub_host_companions.sh: \1|' | crontab -
    say "commented out the payment_canary crontab line"
  fi
}

fresh() {  # fresh <file> <max-age-seconds> <json-field>
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys, time, datetime
path, max_age, field = sys.argv[1], float(sys.argv[2]), sys.argv[3]
d = json.load(open(path))
ts = d.get(field) or ""
age = time.time() - datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
print(f"{int(age)}s old")
sys.exit(0 if age <= max_age else 1)
PY
}

verify() {
  for u in aicom-settlement-sweep.timer aicom-payment-canary.timer; do
    systemctl is-active --quiet "$u" && good "$u active" || bad "$u not active (run --install)"
  done
  if uses_external_signer; then
    systemctl is-active --quiet escrow-signer-tunnel.service && good "escrow-signer-tunnel active" \
      || bad "escrow-signer-tunnel not active"
    url="$(hub_env AIMARKET_ESCROW_SIGNER_URL)"; url="${url%/sign}"
    if docker exec "$HUB" python -c "import sys,httpx;r=httpx.get('$url/health',timeout=8);sys.exit(0 if r.status_code==200 and 'address' in r.text else 1)" 2>/dev/null; then
      good "hub container reaches the signer at $url"
    else
      bad "hub container cannot reach the signer at $url — escrow debits will not reach the chain"
    fi
  fi
  if age=$(fresh "$WEBROOT/settlement.json" 2700 checked_at 2>/dev/null); then good "settlement.json fresh ($age)"
  else bad "settlement.json missing or stale in $WEBROOT ($age) — the sweep does not run HERE"; fi
  if age=$(fresh "$WEBROOT/status.json" 93600 checked_at 2>/dev/null); then good "status.json fresh ($age)"
  else bad "status.json missing or stale in $WEBROOT ($age) — the payment canary does not run HERE"; fi
  [ "$fail" = 0 ] && say "host companions: all present and working" || say "host companions: NOT complete — see FAIL lines"
  return "$fail"
}

case "$MODE" in
  --install) install; verify ;;
  --verify)  verify ;;
  --disable) disable ;;
  *) say "usage: $0 --install | --verify | --disable"; exit 2 ;;
esac
