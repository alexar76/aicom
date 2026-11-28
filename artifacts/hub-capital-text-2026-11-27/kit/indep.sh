#!/usr/bin/env bash
# indep.sh prepare|roll|rollback — Independent's hub (systemd + venv): hub 3.22.5's public-text change over the running
# mcp0728 venv, 2026-11-27.
#   prepare  copy the running venv, apply patch_text.py to its aimarket_hub, check /openapi.json on a throw-away SQLite
#   roll     pg_dump backup, drop-in 99l (sorts after 99k), restart, wait for health
#   rollback remove that drop-in, daemon-reload, restart (back to the mcp0728 venv via 99k)
set -euo pipefail
OLDV=/opt/independentai/venvs/hub-3.22.0-mcp0728-20261126
NEWV=/opt/independentai/venvs/hub-3.22.0-capitaltext-20261127
K="$(cd "$(dirname "$0")" && pwd)"
UNIT=independentai-hub.service
DROPIN=/etc/systemd/system/$UNIT.d/99l-hub-capitaltext-20261127.conf
DB=independentai_hub
pkg() { "$1/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])'; }
case "${1:-}" in
prepare)
  test ! -e "$NEWV"
  [[ "$(tr '\0' ' ' < "/proc/$(systemctl show -p MainPID --value "$UNIT")/cmdline")" == "$OLDV/bin/python -m aimarket_hub serve " ]] \
    || { echo "the unit does not run $OLDV"; exit 3; }
  "$OLDV/bin/python" "$K/patch_text.py" "$(pkg "$OLDV")/aimarket_hub" --check
  cp -a "$OLDV" "$NEWV"
  "$NEWV/bin/python" "$K/patch_text.py" "$(pkg "$NEWV")/aimarket_hub"
  "$NEWV/bin/python" -m compileall -q "$(pkg "$NEWV")/aimarket_hub/hub_routes/capital.py" "$(pkg "$NEWV")/aimarket_hub/api_models.py" "$(pkg "$NEWV")/aimarket_hub/capital_pricing.py"
  (cd /tmp && env -i PATH=/usr/bin:/bin HOME=/tmp AIMARKET_AUTO_CRAWL=0 AIMARKET_FEDERATION_ASSAY=0 "$NEWV/bin/python" -c '
import json, re, tempfile, os, aimarket_hub
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
d = tempfile.mkdtemp(); c = HubConfig(); c.hub_url = "https://smoke.example"
c.db_path = os.path.join(d, "hub.db"); c.signing_key_path = os.path.join(d, "hub.key")
doc = create_app(config=c, db=HubDatabase(c.db_path), signer=Signer(c.signing_key_path)).openapi()
s = json.dumps(doc); tags = doc["paths"]["/api/v2/capital/pricing"]["get"]["tags"]
print(aimarket_hub.__file__, "| openapi acex:", len(re.findall("acex", s, re.I)), "| capital tag:", tags, "| paths:", len(doc["paths"]))
assert not re.search("acex", s, re.I) and tags == ["capital"]
' 2>&1 | grep -v warn | tail -1)
  ;;
roll)
  T="$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p /var/backups/independentai
  sudo -u postgres pg_dump -Fc "$DB" > "/var/backups/independentai/hub-pre-capitaltext-$T.dump"
  chmod 600 "/var/backups/independentai/hub-pre-capitaltext-$T.dump"; ls -la "/var/backups/independentai/hub-pre-capitaltext-$T.dump"
  cat > "$DROPIN" <<EOD
[Service]
# 2026-11-27: hub 3.22.5's public-text change (Agent Capital Exchange, never the acronym; OpenAPI tag "capital")
# over the mcp0728 venv. Rollback = delete this file, daemon-reload, restart (back to $OLDV via 99k).
ExecStart=
ExecStart=$NEWV/bin/python -m aimarket_hub serve
EOD
  systemctl daemon-reload; systemctl restart "$UNIT"
  for i in $(seq 1 60); do curl -fsS -o /dev/null http://127.0.0.1:9083/ai-market/v2/health 2>/dev/null && break; sleep 1; done
  systemctl is-active "$UNIT"; tr '\0' ' ' < "/proc/$(systemctl show -p MainPID --value "$UNIT")/cmdline"; echo
  ;;
rollback)
  rm -f "$DROPIN"; systemctl daemon-reload; systemctl restart "$UNIT"; systemctl is-active "$UNIT"
  ;;
*) echo "usage: $0 prepare|roll|rollback" >&2; exit 2 ;;
esac
