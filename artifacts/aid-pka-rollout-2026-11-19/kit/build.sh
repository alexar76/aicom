#!/usr/bin/env bash
# build.sh CONTAINER TAG — the AID overlay FROM the container's running image, on its host. Refuses unless
# the image's ard.py and signing.py are the 3.21.0 release files the overlay copies were made from.
set -euo pipefail
C="$1"; TAG="$2"
D="$(cd "$(dirname "$0")" && pwd)"
want_ard=a48223ca15d4db3a; want_sig=5fbd626b352eb8dd   # sha256 prefixes of the 3.21.0 files (git ce215c70b)
got_ard="$(docker exec "$C" sha256sum /app/aimarket_hub/hub_routes/ard.py | cut -c1-16)"
got_sig="$(docker exec "$C" sha256sum /app/aimarket_hub/signing.py | cut -c1-16)"
[[ "$got_ard" == "$want_ard" && "$got_sig" == "$want_sig" ]] || { echo "running files differ from 3.21.0: ard $got_ard sig $got_sig" >&2; exit 1; }
BASE_ID="$(docker inspect -f '{{.Image}}' "$C")"
BASE="aidpka-base-$C:20261119"
docker tag "$BASE_ID" "$BASE"
USER_="$(docker inspect -f '{{.Config.User}}' "$C")"; USER_="${USER_:-hub}"
echo "base ${BASE_ID:7:12} ($BASE) user $USER_ -> $TAG"
docker build -q --build-arg BASE="$BASE" --build-arg RUN_USER="$USER_" -t "$TAG" "$D"
docker run --rm --network none --entrypoint python -w /app "$TAG" -c \
  'import aimarket_hub, aimarket_hub.aid_pka as a; print("image", aimarket_hub.__version__, "aid_pka", a.TAG)'
echo "EXPECT=$BASE_ID"
