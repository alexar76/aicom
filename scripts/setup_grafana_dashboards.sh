#!/usr/bin/env bash
# Import bundled Grafana dashboards (idempotent). Requires Grafana on :9082.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GRAF="${AICOM_PORT_GRAFANA:-9082}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
COOKIE_JAR="${TMPDIR:-/tmp}/gf_import_cookies.txt"
# Public URL when nginx subpath is active (cookie Path=/grafana matches /grafana/api/*).
GRAF_API_BASE="${GRAFANA_PUBLIC_URL:-https://magic-ai-factory.com/grafana}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

USER="${GRAFANA_ADMIN_USER:-admin}"
PASS="${GRAFANA_ADMIN_PASSWORD:-}"
if [[ -z "$PASS" ]]; then
  echo "ERROR: GRAFANA_ADMIN_PASSWORD missing in $ENV_FILE" >&2
  exit 1
fi

rm -f "$COOKIE_JAR"
curl -sf -X POST "${GRAF_API_BASE}/login" \
  -H 'Content-Type: application/json' \
  -d "{\"user\":\"${USER}\",\"password\":\"${PASS}\"}" \
  -c "$COOKIE_JAR" >/dev/null

DS_UID="$(curl -sf -b "$COOKIE_JAR" "${GRAF_API_BASE}/api/datasources" \
  | python3 -c "import sys,json; ds=json.load(sys.stdin); print(next((d['uid'] for d in ds if d.get('type')=='prometheus'), ''))")"
if [[ -z "$DS_UID" ]]; then
  echo "ERROR: no Prometheus datasource in Grafana" >&2
  exit 1
fi

import_one() {
  local file="$1"
  python3 - "$file" "$DS_UID" "$COOKIE_JAR" "$GRAF_API_BASE" <<'PY'
import json, sys, urllib.request, http.cookiejar
from pathlib import Path

path, ds_uid, cookie_jar, api_base = sys.argv[1:5]
dash = json.loads(Path(path).read_text(encoding="utf-8"))

def patch(obj):
    if isinstance(obj, dict):
        if obj.get("type") == "prometheus" and "uid" in obj:
            obj["uid"] = ds_uid
        for v in obj.values():
            patch(v)
    elif isinstance(obj, list):
        for v in obj:
            patch(v)

patch(dash)
payload = json.dumps({"dashboard": dash, "overwrite": True}).encode()
req = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/dashboards/db",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
jar = http.cookiejar.MozillaCookieJar(cookie_jar)
jar.load(ignore_discard=True, ignore_expires=True)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
with opener.open(req) as resp:
    out = json.load(resp)
print(f"{Path(path).name}: {out.get('url', out.get('status', out))}")
PY
}

for dash in \
  "$ROOT/grafana/dashboards/ai_factory.json" \
  "$ROOT/grafana/dashboards/factory-iq.json" \
  "$ROOT/grafana/dashboards/ecosystem-overview.json" \
  "$ROOT/grafana/dashboards/hub-invokes.json"
do
  [[ -f "$dash" ]] && import_one "$dash"
done

echo "Grafana dashboards imported (datasource uid=${DS_UID})."
