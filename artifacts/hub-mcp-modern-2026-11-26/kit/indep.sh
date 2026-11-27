#!/usr/bin/env bash
# indep.sh prepare|smoke|roll|rollback — Independent's hub (systemd + venv): MCP 2026-07-28 beside the
# handshake, over the running httpvalid venv, 2026-11-26.
#   prepare  copy the running venv, put in the changed files (refuses unless the running ones are the expected ones)
#   smoke    the new venv answers both protocol eras on a throw-away SQLite database (no migration in this change)
#   roll     drop-in 99k (sorts after 99j), restart, wait for health
#   rollback remove that drop-in, daemon-reload, restart (back to the httpvalid venv via 99j)
set -euo pipefail
OLDV=/opt/independentai/venvs/hub-3.22.0-httpvalid-20261126
NEWV=/opt/independentai/venvs/hub-3.22.0-mcp0728-20261126
K="$(cd "$(dirname "$0")" && pwd)"
UNIT=independentai-hub.service
DROPIN=/etc/systemd/system/$UNIT.d/99k-hub-mcp0728-20261126.conf
pkg() { echo "$("$1/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/aimarket_hub"; }
case "${1:-}" in
prepare)
  test ! -e "$NEWV"
  running="$(tr '\0' ' ' < "/proc/$(systemctl show -p MainPID --value "$UNIT")/cmdline")"
  [[ "$running" == "$OLDV/bin/python "* ]] || { echo "the service does not run from $OLDV: $running"; exit 3; }
  P="$(pkg "$OLDV")"
  have="$(for f in mcp_gateway.py hub_routes/ai_catalog.py static/well-known/mcp/server-card.json; do echo "$f $(sha256sum "$P/$f" | cut -c1-12)"; done)"
  want="mcp_gateway.py a81bde47a61d
hub_routes/ai_catalog.py 1e5fb7d2a40e
static/well-known/mcp/server-card.json b5134a7a40b2"
  [[ "$have" == "$want" ]] || { echo "unexpected running files:"; diff <(echo "$want") <(echo "$have"); exit 3; }
  test ! -e "$P/mcp_modern.py"
  cp -a "$OLDV" "$NEWV"
  N="$(pkg "$NEWV")"
  install -m 644 "$K/files/mcp_modern.py" "$N/mcp_modern.py"
  install -m 644 "$K/files/hub_routes/ai_catalog.py" "$N/hub_routes/ai_catalog.py"
  install -m 644 "$K/files/static/well-known/mcp/server-card.json" "$N/static/well-known/mcp/server-card.json"
  install -m 644 "$K/gateway/mcp_gateway-3220.py" "$N/mcp_gateway.py"
  for f in mcp_modern.py mcp_gateway.py hub_routes/ai_catalog.py; do echo "$f $(sha256sum "$N/$f" | cut -c1-12)"; done
  ;;
smoke)
  install -m 644 "$K/smoke_mcp.py" /tmp/hub-mcp0728-smoke.py
  U="$(systemctl show -p User --value "$UNIT")"; U="${U:-root}"
  (cd /tmp && sudo -u "$U" env SMOKE_EXPECT_PKG="$(pkg "$NEWV")/" "$NEWV/bin/python" /tmp/hub-mcp0728-smoke.py 2>&1 | tail -2)
  rm -f /tmp/hub-mcp0728-smoke.py
  ;;
roll)
  cat > "$DROPIN" <<EOD
[Service]
# 2026-11-26: MCP 2026-07-28 beside the initialize handshake (main 9886575bc: mcp_modern.py, mcp_gateway.py,
# ai_catalog.py, server card 1.4.0) over the httpvalid venv. No migration.
# Rollback = delete this file, daemon-reload, restart (back to $OLDV via 99j).
ExecStart=
ExecStart=$NEWV/bin/python -m aimarket_hub serve
EOD
  date -u +"switch %FT%TZ"
  systemctl daemon-reload; systemctl restart "$UNIT"
  for i in $(seq 1 60); do curl -fsS -o /dev/null http://127.0.0.1:9083/ai-market/v2/health 2>/dev/null && break; sleep 1; done
  systemctl is-active "$UNIT"; tr '\0' ' ' < "/proc/$(systemctl show -p MainPID --value "$UNIT")/cmdline"; echo
  ;;
rollback)
  rm -f "$DROPIN"; systemctl daemon-reload; systemctl restart "$UNIT"; systemctl is-active "$UNIT"
  ;;
*) echo "usage: $0 prepare|smoke|roll|rollback" >&2; exit 2 ;;
esac
