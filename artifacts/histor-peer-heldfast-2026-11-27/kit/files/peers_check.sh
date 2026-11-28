#!/usr/bin/env bash
# Cross-check HISTOR with the observers listed in $CONF (histor/peers.py, docs/cross-check.md). Installed as
# /usr/local/sbin/histor-peers and run by histor-peers.timer every day at 12:00 UTC.
#
# Every peer in the list is run, and the result lands in $DIR/peers/<slug>/<YYYY-MM-DD>/ with
# $DIR/peers/<slug>/latest → newest; $DIR/peers/index.json lists every peer with its newest day and results. Each
# peer's `aliases` become links $DIR/<alias> → peers/<slug>, so an address given out before the list existed keeps
# working; a real directory of that name is left alone and reported. The $KEEP_DAYS newest days of each peer are kept.
#
# One run per method, each in a throw-away container from the service's own image, as export_dataset.sh and
# witness_push.sh do, read-only, with only what its method needs:
#   "digest" and "fingerprints" peers
#                       host network (HISTOR's API on the loopback port, the peers' files over the network),
#                       no setting of the service, no volume
#   "field-diff" peers  the compose network, the database settings copied from the service (never printed) and the
#                       data volume read-only, because they compare with HISTOR's records in the database
# An image built before histor.peers existed gets $MODULES mounted (installed next to this script; the image
# carries them from the next deploy on). $MODULES/peer_xcheck.py, when installed, is mounted over the image's copy
# for the "field-diff" run; without it, an image with no histor.peer_xcheck gets $PEER_MODULE.
#
#   histor-peers                 every peer, dated today
#   histor-peers --peer SLUG     one peer (repeatable), dated today
#
# Exit status: 1 when a run failed or a source could not be fetched or read (what could be read is still
# published), 2 for a missing or invalid list, 0 otherwise.
set -euo pipefail

APP="${HISTOR_APP_CONTAINER:-histor-histor-1}"
CONF="${HISTOR_PEERS_FILE:-/etc/histor/peers.json}"
DIR="${HISTOR_DATASET_DIR:-/var/lib/histor-datasets}"
MODULES="${HISTOR_PEERS_MODULES:-/usr/local/lib/histor-peers}"
PEER_MODULE="${HISTOR_PEER_MODULE:-/usr/local/lib/histor-dataset/peer_xcheck.py}"
NETWORK="${HISTOR_NETWORK:-histor_default}"
VOLUME="${HISTOR_DATA_VOLUME:-histor_histor-data}"
UIDGID="${HISTOR_UIDGID:-65532:65532}"
API="${HISTOR_LOCAL_API:-http://127.0.0.1:9490}"
KEEP_DAYS="${HISTOR_PEERS_KEEP_DAYS:-120}"

if [[ ! -s "$CONF" ]]; then
  echo "no $CONF: no peers to cross-check with"
  exit 0
fi
methods="$(python3 -c 'import json,sys; print(" ".join(sorted({p["method"] for p in json.load(open(sys.argv[1]))})))' "$CONF")" \
  || { echo "$CONF is not a JSON list of peers" >&2; exit 2; }
day="$(date -u +%F)"
image="$(docker inspect "$APP" --format '{{.Config.Image}}')"

common=(-v "$CONF:/peers.json:ro")
if ! docker run --rm --entrypoint python "$image" -c 'import histor.peers' 2> /dev/null; then
  for f in peers.py digest_xcheck.py; do
    [[ -f "$MODULES/$f" ]] || { echo "the image has no histor.peers and $MODULES/$f is missing" >&2; exit 1; }
    common+=(-v "$MODULES/$f:/app/histor/$f:ro")
  done
fi
install -d -m 0755 "$DIR/peers"
common+=(-v "$DIR/peers:/published:ro")
install -d -m 0700 -o "${UIDGID%%:*}" -g "${UIDGID##*:}" "$DIR/.staging"
stages=()
trap 'rm -rf "${stages[@]}"' EXIT

# publish <stage>: move each peer's folder and the index into place.
publish() {
  local stage="$1" peer_dir slug out
  chown -R root:root "$stage"
  chmod -R a+rX,go-w "$stage"
  for peer_dir in "$stage"/*/; do
    [[ -d "$peer_dir" ]] || continue
    slug="$(basename "$peer_dir")"
    out="$DIR/peers/$slug"
    install -d -m 0755 "$out"
    rm -rf "${out:?}/$day"
    mv "$peer_dir" "$out/$day"
    ln -sfn "$day" "$out/latest.tmp" && mv -T "$out/latest.tmp" "$out/latest"
    ls -1d "$out"/20??-??-?? 2> /dev/null | sort | head -n -"$KEEP_DAYS" | xargs -r rm -rf
    echo "histor peers: $out/$day"
  done
  [[ -s "$stage/index.json" ]] && mv "$stage/index.json" "$DIR/peers/index.json"
}

status=0
for method in digest fingerprints field-diff; do
  [[ " $methods " == *" $method "* ]] || continue
  stage="$DIR/.staging/peer-checks-$method-$day"
  rm -rf "$stage"
  install -d -m 0700 -o "${UIDGID%%:*}" -g "${UIDGID##*:}" "$stage"
  stages+=("$stage")
  mounts=("${common[@]}" -v "$stage:/export")
  if [[ $method == digest || $method == fingerprints ]]; then
    net=(--network host)
    envs=()
    limits=(--memory 256m --pids-limit 32)
  else
    envfile="$(mktemp)"
    stages+=("$envfile")
    chmod 600 "$envfile"
    docker inspect "$APP" --format '{{range .Config.Env}}{{println .}}{{end}}' \
      | grep -E '^(HISTOR_PROFILE|HISTOR_DATABASE_URL|HISTOR_OPERATOR_TOKEN|HISTOR_PUBLIC_BASE|HISTOR_DATA_DIR|HISTOR_OPT_OUT|HISTOR_PQC)=' \
      > "$envfile"
    net=(--network "$NETWORK")
    envs=(--env-file "$envfile")
    # 2 GB: the peer's changes.json reached 76 MB on 2026-11-21 and parses to about 0.85 GB (histor/peer_xcheck.py).
    limits=(--memory 2g --pids-limit 64)
    mounts+=(-v "$VOLUME:/data:ro")
    if [[ -f "$MODULES/peer_xcheck.py" ]]; then
      mounts+=(-v "$MODULES/peer_xcheck.py:/app/histor/peer_xcheck.py:ro")
    elif ! docker run --rm --entrypoint python "$image" -c 'import histor.peer_xcheck' 2> /dev/null; then
      [[ -f "$PEER_MODULE" ]] || { echo "the image has no histor.peer_xcheck and $PEER_MODULE is missing" >&2; status=1; continue; }
      mounts+=(-v "$PEER_MODULE:/app/histor/peer_xcheck.py:ro")
    fi
  fi
  run_status=0
  docker run --rm --name "histor-peers-$method-$day" --user "$UIDGID" --read-only --tmpfs /tmp \
    --cap-drop ALL --security-opt no-new-privileges:true "${limits[@]}" "${net[@]}" "${envs[@]}" "${mounts[@]}" \
    --entrypoint python "$image" -m histor.peers --config /peers.json --out /export --published /published \
    --histor "$API" --day "$day" --method "$method" "$@" || run_status=$?
  if [[ $run_status -eq 2 ]]; then
    echo "$CONF is not a valid peer list" >&2
    exit 2
  fi
  [[ $run_status -eq 0 ]] || status=1
  publish "$stage"
done

# Older addresses: $DIR/<alias> → peers/<slug>.
python3 - "$CONF" <<'PY' | while read -r alias slug; do
import json, sys
for p in json.load(open(sys.argv[1])):
    for a in p.get("aliases", []):
        print(a, p["slug"])
PY
  link="$DIR/$alias"
  if [[ -L "$link" || ! -e "$link" ]]; then
    ln -sfn "peers/$slug" "$link.tmp" && mv -T "$link.tmp" "$link"
  else
    echo "alias $link is a real directory: move its days into $DIR/peers/$slug/ and rerun" >&2
  fi
done
exit "$status"
