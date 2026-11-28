#!/usr/bin/env bash
# probe.sh CONTAINER... — running image, user, where aimarket_hub is imported from, version, and patch_text.py --check
# (fed on stdin: some hub containers have a read-only root filesystem).
D="$(cd "$(dirname "$0")" && pwd)"
for C in "$@"; do
  IMG="$(docker inspect -f '{{.Config.Image}}' "$C")"; U="$(docker inspect -f '{{.Config.User}}' "$IMG")"
  PKG="$(docker exec "$C" python3 -c 'import aimarket_hub,os;print(os.path.dirname(aimarket_hub.__file__), aimarket_hub.__version__)')"
  R="$(docker exec -i "$C" python3 - "${PKG% *}" --check < "$D/patch_text.py" | tr '\n' ' ')"
  echo "$C | $IMG | user=${U:-root} | $PKG | $R"
done
