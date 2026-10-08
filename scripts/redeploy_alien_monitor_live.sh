#!/usr/bin/env bash
# Rebuild and recreate an Alien Monitor container in place, keeping its environment.
#
#   monitor.modelmarket.dev     → alien-monitor-live (:9101, ALIEN_MODE=real)
#   monitor-uni.modelmarket.dev → alien-monitor      (:9100, ALIEN_MODE=universe)
#
# Why this script exists: BOTH containers were created by a bare `docker run` and were in no
# script at all — `docker-compose.prod.yml` describes them but did not create them (neither
# carries a compose label), so `compose up` would recreate them from compose's own defaults
# and drop the ~54 environment variables they actually run with. Redeploying by hand meant
# reconstructing those from `docker inspect`, live DeepSeek / Postgres / ATLAS secrets among
# them. Every value is copied through a 0600 env-file and NEVER printed; only names reach
# stdout. (A hand-rolled predecessor dumped captured run args to a log, with a live API key
# in it.)
#
# Usage (on the host):
#   ./scripts/redeploy_alien_monitor_live.sh                        # build, recreate LIVE
#   ./scripts/redeploy_alien_monitor_live.sh alien-monitor --image alien-monitor:TAG
#   ./scripts/redeploy_alien_monitor_live.sh --no-build             # reuse current image
#
# Both public maps serve at `/`, so one image with VITE_BASE_PATH=/ fits both — pass the tag
# the first run built with --image rather than building twice. If they ever serve at
# different base paths that stops being true: the path is baked in at build time.
set -euo pipefail

NAME="${ALIEN_LIVE_CONTAINER:-alien-monitor-live}"
PINNED_IMAGE=""
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="/root/.${NAME}.env"
TAG="alien-monitor:live-$(date -u +%Y%m%d-%H%M%S)"
BUILD=1
while (( $# )); do
  case "$1" in
    --no-build) BUILD=0 ;;
    --image)    PINNED_IMAGE="${2:-}"; BUILD=0; shift ;;
    -*)         echo "unknown option: $1" >&2; exit 2 ;;
    *)          NAME="$1" ;;
  esac
  shift
done
ENV_FILE="/root/.${NAME}.env"

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }
docker inspect "$NAME" >/dev/null 2>&1 || { echo "$NAME is not present — nothing to recreate" >&2; exit 1; }

# ── capture the running container's shape ────────────────────────────────────
# Env goes straight to a private file. PATH/LANG/PYTHON_* and GPG_KEY come from the base
# image and must not be pinned across a rebuild, or a new base image cannot change them.
umask 077
export ENV_FILE
docker inspect "$NAME" | python3 -c '
import json, os, sys
spec = json.load(sys.stdin)[0]
skip = {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256",
        "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"}
env_path = os.environ["ENV_FILE"]
with open(env_path, "w", encoding="utf-8") as fh:
    for entry in spec["Config"]["Env"]:
        name = entry.split("=", 1)[0]
        if name not in skip:
            fh.write(entry + "\n")
# Mount modes. `docker inspect` reports the mode of the container being REPLACED, which is
# only trustworthy while nothing has ever recreated it wrongly — and an earlier run of this
# script forced :ro on everything, so the inspected mode became the mistake. So the one
# destination the image genuinely writes to is pinned here, from docker-compose.prod.yml
# which declares it without :ro: the UNI realm stores its Anvil state and
# universe_config.json under /app/data/universe, and a read-only bind there loses the
# bubble chain on the next restart. Everything else is config the container has no business
# editing, and is mounted read-only whatever the old container said.
WRITABLE = {"/app/data/universe"}
mounts = []
writable_sources = []
for m in spec.get("Mounts") or []:
    suffix = "" if m["Destination"] in WRITABLE else ":ro"
    mounts.append("%s:%s%s" % (m["Source"], m["Destination"], suffix))
    if m["Destination"] in WRITABLE:
        writable_sources.append(m["Source"])
port = next((e.split("=", 1)[1] for e in spec["Config"]["Env"] if e.startswith("ALIEN_PORT=")), "9101")
with open(env_path + ".shape", "w", encoding="utf-8") as fh:
    # Quoted: an unquoted assignment makes the shell try to EXECUTE the mount list.
    fh.write("MOUNTS=%s\n" % json.dumps(" ".join("-v %s" % m for m in mounts)))
    fh.write("PORT=%s\n" % json.dumps(port))
    fh.write("WRITABLE_SOURCES=%s\n" % json.dumps(" ".join(writable_sources)))
print("captured %d env vars (values not shown)" % sum(1 for _ in open(env_path, encoding="utf-8")))
'
# shellcheck disable=SC1090
source "$ENV_FILE.shape"

echo "container : $NAME"
echo "own port  : $PORT"
echo "mounts    : $MOUNTS"

if (( BUILD )); then
  echo "building  : $TAG (VITE_BASE_PATH=/)"
  docker build -t "$TAG" --build-arg VITE_BASE_PATH=/ -f "$ROOT/alien-monitor/Dockerfile" "$ROOT"
else
  TAG="${PINNED_IMAGE:-$(docker inspect "$NAME" --format '{{.Config.Image}}')}"
  docker image inspect "$TAG" >/dev/null 2>&1 || { echo "image $TAG not present" >&2; exit 1; }
  echo "reusing   : $TAG"
fi

# The container runs as uid 10001, so the one host directory it writes must be its own.
for src in ${WRITABLE_SOURCES:-}; do
  [[ -d "$src" ]] && chown -R 10001:10001 "$src"
done

docker rm -f "$NAME" >/dev/null
# The healthcheck probes THIS container's port. Inheriting the image's :9100 probe under
# --network host tested the OTHER (UNI) container, so LIVE reported healthy no matter what
# state it was in — the same defect this deployment has hit before.
# shellcheck disable=SC2086
# Not root, no capabilities, no escalation: the monitor's read APIs are public and it
# shares the host's network namespace. uid 10001 is the image's own monitor user.
docker run -d --name "$NAME" \
  --network host --restart unless-stopped \
  --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges:true \
  --env-file "$ENV_FILE" \
  $MOUNTS \
  --health-cmd "python -c \"import json,urllib.request; d=json.loads(urllib.request.urlopen('http://127.0.0.1:$PORT/api/health',timeout=5).read()); exit(0 if d.get('status')=='ok' else 1)\"" \
  --health-interval 30s --health-timeout 10s --health-retries 3 \
  "$TAG" python main.py

for _ in $(seq 1 30); do
  sleep 2
  if curl -fsS -m 5 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo "healthy   : http://127.0.0.1:$PORT/api/health"
    exit 0
  fi
done
echo "FAILED to come up — last logs:" >&2
docker logs --tail 40 "$NAME" >&2
exit 1
