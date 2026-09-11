#!/usr/bin/env bash
# Rebuild and recreate a container IN PLACE, keeping the environment it already runs with.
#
# Every long-lived service on this host was created by a bare `docker run` and lives in no
# script: `alien-monitor` (:9100 UNI map), `alien-monitor-live` (:9101 LIVE map),
# `modelmarket-hub` (:9083), `modelmarket-hub-uni` (:9183). Compose files describe some of
# them but did not create them — none carries a compose label — so `compose up` would
# rebuild them from compose's own defaults and DROP the 54-95 environment variables they
# actually run with, live DeepSeek / OpenRouter / Postgres / ATLAS secrets among them.
# Reconstructing those by hand from `docker inspect` is how a secret ends up in a log.
#
# So: capture, rebuild, recreate. Every value is copied through a 0600 env-file and NEVER
# printed; only names reach stdout.
#
# Usage (on the host):
#   ./scripts/redeploy_in_place.sh alien-monitor-live
#   ./scripts/redeploy_in_place.sh alien-monitor --image alien-monitor:TAG
#   ./scripts/redeploy_in_place.sh modelmarket-hub --dockerfile aimarket-hub/Dockerfile
#   ./scripts/redeploy_in_place.sh modelmarket-hub-uni --image modelmarket-hub:TAG
#   ./scripts/redeploy_in_place.sh alien-monitor-live --no-build   # reuse current image
#
# Both public maps serve at `/`, so one monitor image (VITE_BASE_PATH=/) fits both — pass
# the tag the first run built with --image rather than building twice. If they ever serve at
# different base paths that stops being true: the path is baked in at build time. The same
# applies to the two hubs, which are the same code with different environments.
set -euo pipefail

NAME="${REDEPLOY_CONTAINER:-alien-monitor-live}"
PINNED_IMAGE=""
DOCKERFILE="alien-monitor/Dockerfile"
BUILD_ARGS=(--build-arg "VITE_BASE_PATH=/")
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="/root/.${NAME}.env"
TAG=""
BUILD=1
while (( $# )); do
  case "$1" in
    --no-build) BUILD=0 ;;
    --image)      PINNED_IMAGE="${2:-}"; BUILD=0; shift ;;
    --dockerfile) DOCKERFILE="${2:-}"; shift ;;
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
EXTRA_ENV="/root/.${NAME}.extra.env"
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
# script forced :ro on everything, so the inspected mode became the mistake. So the
# destinations the images genuinely write to are pinned here from their compose files, which
# declare them without :ro: the UNI realm stores its Anvil state and universe_config.json
# under /app/data/universe, and a hub keeps its channel ledger and peer database under
# /app/data. A read-only bind on either loses money or a chain on the next restart.
# Everything else is config the container has no business editing, and is mounted read-only
# whatever the old container said.
WRITABLE = {"/app/data/universe", "/app/data"}
mounts = []
for m in spec.get("Mounts") or []:
    suffix = "" if m["Destination"] in WRITABLE else ":ro"
    mounts.append("%s:%s%s" % (m["Source"], m["Destination"], suffix))
# The port this container serves on, asked of the container — never assumed. Guessing the
# monitor ALIEN_PORT made the health check for the rebuilt HUB probe :9101, i.e. the
# monitor, and report "healthy" while the hub was in a crash loop.
port = ""
for name in ("ALIEN_PORT", "AIMARKET_HUB_PORT", "PORT", "HUB_PORT"):
    port = next((e.split("=", 1)[1] for e in spec["Config"]["Env"] if e.startswith(name + "=")), "")
    if port:
        break
if not port:
    exposed = sorted((spec["Config"].get("ExposedPorts") or {}).keys())
    port = exposed[0].split("/")[0] if exposed else ""

# Networking, asked of the container. Forcing --network host is what took the bubble hub
# down: it runs on the BRIDGE with -p 127.0.0.1:9183:9083, so recreating it on the host
# network made it try to bind :9083 — already owned by the LIVE hub — and crash-loop. Its
# env gives the tell (AIMARKET_RPC_BASE=http://172.17.0.1:8546 is the bridge gateway; a
# host-network container would say 127.0.0.1).
network = spec["HostConfig"].get("NetworkMode") or "default"
publish = []
host_port = ""
for container_port, bindings in (spec["HostConfig"].get("PortBindings") or {}).items():
    for binding in bindings or []:
        ip = binding.get("HostIp") or ""
        hp = binding.get("HostPort") or ""
        publish.append("-p %s%s:%s" % ((ip + ":") if ip else "", hp, container_port.split("/")[0]))
        if hp and not host_port:
            host_port = hp
# Two ports, two probes, and conflating them marked a healthy hub unhealthy for half an
# hour. `modelmarket-hub-uni` listens on 9083 INSIDE and is published on 127.0.0.1:9183;
# baking the published port into the container healthcheck made curl inside the container
# dial 9183, where nothing listens — a permanently failing check on a container that was
# serving perfectly. So:
#   port       — inside the container: what the app listens on, for the healthcheck.
#   probe_port — from the host: the published port on a bridge container, the same port
#                under --network host, for this script own verification loop.
probe_port = host_port or port

# The command, likewise. Hardcoding the monitor `python main.py` handed it to the hub
# CLI as arguments — `__main__.py: error: unrecognized arguments: python main.py` — and
# crash-looped production until it was recreated by hand. An empty override means "use the
# image own entrypoint", which is what every container here actually does.
container_cmd = spec["Config"].get("Cmd") or []

with open(env_path + ".shape", "w", encoding="utf-8") as fh:
    # Quoted: an unquoted assignment makes the shell try to EXECUTE the mount list.
    fh.write("MOUNTS=%s\n" % json.dumps(" ".join("-v %s" % m for m in mounts)))
    fh.write("PORT=%s\n" % json.dumps(port))
    fh.write("PROBE_PORT=%s\n" % json.dumps(probe_port))
    fh.write("CONTAINER_CMD=%s\n" % json.dumps(" ".join(container_cmd)))
    fh.write("ENTRYPOINT=%s\n" % json.dumps(" ".join(spec["Config"].get("Entrypoint") or [])))
    fh.write("NETWORK=%s\n" % json.dumps(network))
    fh.write("PUBLISH=%s\n" % json.dumps(" ".join(publish)))
print("port %s (probe %s) | network %s | publish %s | cmd %r" % (
    port or "unknown", probe_port or "unknown", network,
    " ".join(publish) or "-", " ".join(container_cmd)))
print("captured %d env vars (values not shown)" % sum(1 for _ in open(env_path, encoding="utf-8")))
'
# Anything the operator wants ADDED to a container nothing created. The captured file is
# rewritten from `docker inspect` on every run, so a hand-edit there survives exactly until
# the next redeploy — which is how a key gets added once and silently lost. Keep additions
# in `/root/.<container>.extra.env` (same 0600 rule) and they are re-applied every time.
if [[ -f "$EXTRA_ENV" ]]; then
  chmod 600 "$EXTRA_ENV"
  added=0
  while IFS= read -r line; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    name="${line%%=*}"
    grep -v "^${name}=" "$ENV_FILE" > "$ENV_FILE.merged" || true
    printf "%s\n" "$line" >> "$ENV_FILE.merged"
    mv "$ENV_FILE.merged" "$ENV_FILE"
    added=$((added + 1))
    echo "extra env : $name (value not shown)"
  done < "$EXTRA_ENV"
  chmod 600 "$ENV_FILE"
  echo "merged    : $added variable(s) from $(basename "$EXTRA_ENV")"
fi

# shellcheck disable=SC1090
source "$ENV_FILE.shape"

# Tag off the image the container already runs, so a rebuild is recognisably its successor.
CURRENT_IMAGE="$(docker inspect "$NAME" --format '{{.Config.Image}}')"
TAG="${CURRENT_IMAGE%%:*}:$(date -u +%Y%m%d-%H%M%S)"

echo "container : $NAME"
echo "own port  : $PORT"
echo "network   : ${NETWORK:-host} ${PUBLISH:-}"
echo "from      : $CURRENT_IMAGE"
echo "mounts    : $MOUNTS"

if (( BUILD )); then
  echo "building  : $TAG (from $DOCKERFILE)"
  case "$DOCKERFILE" in
    alien-monitor/*) ;;                      # the SPA base path is baked in at build time
    *) BUILD_ARGS=() ;;
  esac
  docker build -t "$TAG" "${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}" -f "$ROOT/$DOCKERFILE" "$ROOT"
else
  TAG="${PINNED_IMAGE:-$(docker inspect "$NAME" --format '{{.Config.Image}}')}"
  docker image inspect "$TAG" >/dev/null 2>&1 || { echo "image $TAG not present" >&2; exit 1; }
  echo "reusing   : $TAG"
fi

docker rm -f "$NAME" >/dev/null
# The healthcheck probes THIS container's port. Inheriting the image's :9100 probe under
# --network host tested the OTHER (UNI) container, so LIVE reported healthy no matter what
# state it was in — the same defect this deployment has hit before.
# shellcheck disable=SC2086
HEALTH_ARGS=()
if [[ -n "$PORT" ]]; then
  # Probes THIS container's port. Inheriting an image's probe under --network host tests
  # whatever else is listening there — which is how the LIVE map reported healthy while
  # actually testing the UNI container.
  # $PORT, not $PROBE_PORT: this command runs INSIDE the container.
  HEALTH_ARGS=(--health-cmd "curl -fsS -m 5 http://127.0.0.1:$PORT/api/health >/dev/null || curl -fsS -m 5 http://127.0.0.1:$PORT/.well-known/ai-market.json >/dev/null"
               --health-interval 30s --health-timeout 10s --health-retries 3)
fi
# The command and the ENTRYPOINT belong together. `modelmarket-hub` on the Signal Hunt host
# ran with `--entrypoint python` and the command `-m aimarket_hub serve`; the script captured
# the command, ignored the entrypoint override, and handed those three words to the new
# image's own `python -m aimarket_hub serve` as ARGUMENTS —
# `__main__.py: error: unrecognized arguments: -m aimarket_hub serve`, and a crash loop on a
# live hub. A command captured under one entrypoint is meaningless under another.
RUN_ARGS=()
ENTRY_WORDS=$(printf '%s' "${ENTRYPOINT:-}" | wc -w | tr -d ' ')
if [[ "$ENTRY_WORDS" == "1" ]]; then
  # Reproduce the shape exactly: single-binary override plus its arguments.
  RUN_ARGS=(--entrypoint "$ENTRYPOINT")
  echo "entrypoint: $ENTRYPOINT (override preserved)"
elif [[ "$ENTRY_WORDS" != "0" ]]; then
  # A multi-word override cannot be expressed as one --entrypoint, and the captured command
  # was written for it. Use the image's own and say so, rather than guessing.
  echo "entrypoint: captured multi-word override — using the image's own and dropping the command" >&2
  CONTAINER_CMD=""
fi
# shellcheck disable=SC2086
docker run -d --name "$NAME" \
  --network "${NETWORK:-host}" --restart unless-stopped \
  --env-file "$ENV_FILE" \
  $MOUNTS ${PUBLISH:-} \
  "${RUN_ARGS[@]+"${RUN_ARGS[@]}"}" \
  "${HEALTH_ARGS[@]+"${HEALTH_ARGS[@]}"}" \
  "$TAG" ${CONTAINER_CMD:-}

if [[ -z "$PORT" ]]; then
  echo "no port could be established for $NAME — cannot verify it came up" >&2
  docker logs --tail 20 "$NAME" >&2
  exit 1
fi
for _ in $(seq 1 30); do
  sleep 2
  # A container that is RESTARTING is a failure however the endpoint behaves: something
  # else on this host may answer the same port under --network host.
  state="$(docker inspect "$NAME" --format '{{.State.Status}}')"
  if [[ "$state" == "restarting" || "$state" == "exited" ]]; then
    echo "FAILED: $NAME is $state — last logs:" >&2
    docker logs --tail 40 "$NAME" >&2
    exit 1
  fi
  for probe in /api/health /.well-known/ai-market.json; do
    # From the HOST, so the published port on a bridge container.
    if curl -fsS -m 5 "http://127.0.0.1:${PROBE_PORT:-$PORT}$probe" >/dev/null 2>&1; then
      echo "healthy   : $NAME on http://127.0.0.1:${PROBE_PORT:-$PORT}$probe"
      exit 0
    fi
  done
done
echo "FAILED to come up — last logs:" >&2
docker logs --tail 40 "$NAME" >&2
exit 1
