#!/usr/bin/env bash
# build.sh CONTAINER — image FROM the running one with this change; refuses when a running file is not
# the expected version. catalog.py: 8d3ee72e1c0a = 3.22.0, 02674f6adb3d = hub.modelmarket.dev's own,
# 5b7529957413 = main; each gets the same patch (kit/catalog/).
set -euo pipefail
C="$1"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
h() { docker exec "$C" sha256sum "/app/aimarket_hub/$1" | cut -c1-12; }
want="config.py 747104c4b6d1
crawler.py f584cea89b63
database.py e9cfd5e7026b
realm.py c5c13552b507
hub_routes/wellknown.py cbff1787ba8c
migrations.py 12df83981701
models.py 3b2024764fd9"
have="$(for f in config.py crawler.py database.py realm.py hub_routes/wellknown.py migrations.py models.py; do echo "$f $(h $f)"; done)"
[[ "$have" == "$want" ]] || { echo "unexpected running files in $C:"; diff <(echo "$want") <(echo "$have"); exit 3; }
case "$(h hub_routes/catalog.py)" in
  8d3ee72e1c0a) CAT=3220 ;; 02674f6adb3d) CAT=hub ;; 5b7529957413) CAT=main ;;
  *) echo "unknown catalog.py in $C: $(h hub_routes/catalog.py)"; exit 3 ;;
esac
NEW="${BASE%%:*}:${BASE##*:}-httpvalid-20261126"
NEW="${NEW/-fedvalid-20261126-httpvalid/-httpvalid}"
docker build -q --build-arg BASE="$BASE" --build-arg CATALOG="$CAT" -t "$NEW" "$D" >/dev/null
echo "$NEW (catalog $CAT)"
