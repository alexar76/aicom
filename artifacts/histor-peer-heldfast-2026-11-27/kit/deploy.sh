#!/usr/bin/env bash
# deploy.sh build|install|rollback — heldfast on HISTOR's peer list (method "fingerprints"), 2026-11-27.
#   build    image histor-histor:heldfast-peer-20261127 FROM the app's image + peers.py, fingerprint_xcheck.py; checks
#            that the new image loads the new peers.json; the current image is tagged pre-heldfast-peer-20261127
#   install  back up, then: tag histor-histor → the new image (the runner reads the tag; the app holds its image by ID),
#            /usr/local/sbin/histor-peers, /etc/histor/peers.json, and the build source /opt/histor (histor/ + deploy/)
#   rollback the tag back to pre-heldfast-peer-20261127 and the backed-up files back
# Order matters: an image without the "fingerprints" method rejects the new list (exit 2 for every peer).
set -euo pipefail
K="$(cd "$(dirname "$0")" && pwd)"; B="$K/backup"
APPIMG="$(docker inspect histor-histor-1 -f '{{.Image}}')"
NEW=histor-histor:heldfast-peer-20261127; PRE=histor-histor:pre-heldfast-peer-20261127
FILES="/usr/local/sbin/histor-peers /etc/histor/peers.json /opt/histor/histor/peers.py /opt/histor/deploy/peers_check.sh /opt/histor/deploy/peers.json"
case "${1:-}" in
build)
  if ! docker image inspect "$PRE" >/dev/null 2>&1; then   # a rebuild keeps the base tagged by the first build
    [[ "$(docker image inspect histor-histor -f '{{.Id}}')" == "$APPIMG" ]] || { echo "histor-histor is not the app's image"; exit 3; }
    docker tag "$APPIMG" "$PRE"
  fi
  [[ "$(docker image inspect "$PRE" -f '{{.Id}}')" == "$APPIMG" ]] || { echo "$PRE is not the app's image"; exit 3; }
  docker build -q --build-arg BASE="$PRE" -t "$NEW" "$K" >/dev/null   # BuildKit cannot start FROM a bare image id
  docker run --rm --network none -v "$K/files/peers.json:/peers.json:ro" --entrypoint python "$NEW" -c '
from histor import peers, fingerprint_xcheck
p = peers.load_config(open("/peers.json").read())
print("methods", peers.METHODS, "| peers", [(x["slug"], x["method"]) for x in p])'
  docker image inspect "$NEW" -f "$NEW = {{.Id}}"
  ;;
install)
  mkdir -p "$B"; for f in $FILES; do cp -a "$f" "$B/$(echo "$f" | tr / _)"; done
  docker tag "$NEW" histor-histor
  install -m 0755 "$K/files/peers_check.sh" /usr/local/sbin/histor-peers
  install -m "$(stat -c %a /etc/histor/peers.json)" -o "$(stat -c %u /etc/histor/peers.json)" -g "$(stat -c %g /etc/histor/peers.json)" \
    "$K/files/peers.json" /etc/histor/peers.json
  install -m 0644 "$K/files/peers.py" "$K/files/fingerprint_xcheck.py" /opt/histor/histor/
  install -m 0755 "$K/files/peers_check.sh" /opt/histor/deploy/peers_check.sh
  install -m 0644 "$K/files/peers.json" /opt/histor/deploy/peers.json
  docker image inspect histor-histor -f "histor-histor = {{.Id}}"; sha256sum $FILES /opt/histor/histor/fingerprint_xcheck.py | cut -c1-16,64-
  ;;
rollback)
  docker tag "$PRE" histor-histor
  for f in $FILES; do cp -a "$B/$(echo "$f" | tr / _)" "$f"; done
  rm -f /opt/histor/histor/fingerprint_xcheck.py
  docker image inspect histor-histor -f "histor-histor = {{.Id}}"
  ;;
*) echo "usage: $0 build|install|rollback" >&2; exit 2 ;;
esac
