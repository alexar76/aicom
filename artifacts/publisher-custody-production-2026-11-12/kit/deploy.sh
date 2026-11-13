#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

container=modelmarket-hub
previous_kit=/root/hub-3.21.0-rollout-20261112/kit
hub_health=http://127.0.0.1:9083/ai-market/v2/health
themis_health=http://127.0.0.1:9460/health
health_flags=(--health "$hub_health" --health "$themis_health")

live_image() {
    docker inspect -f '{{.Image}}' "$container"
}

snapshot() {
    local kind=$1 target=$2
    docker exec -i "$container" python - "$kind" < snapshot.py > "$target"
    test -s "$target"
}

case "${1:?prepare, switch or rollback required}" in
prepare)
    base=$(live_image)
    basename="modelmarket-publisher-custody-base:${base:7:12}"
    candidate="modelmarket-hub:publisher-custody-20261112-${base:7:12}"
    run_user=$(docker image inspect -f '{{.Config.User}}' "$base")
    docker exec -i "$container" sh -c 'cd /app/aimarket_hub && sha256sum -c -' < preimage.sha256
    docker run --rm --network none -i --entrypoint sh "$base" -c \
        'cd /app/aimarket_hub && sha256sum -c -' < preimage.sha256
    docker tag "$base" "$basename"
    docker build --network=none --build-arg BASE="$basename" --build-arg RUN_USER="${run_user:-root}" -t "$candidate" .
    new=$(docker image inspect -f '{{.Id}}' "$candidate")
    docker run --rm --network none -i --entrypoint sh "$new" -c \
        'cd /app/aimarket_hub && sha256sum -c -' < overlay.sha256
    scratch=$(mktemp -d /root/publisher-custody-smoke-XXXXXXXX)
    trap 'rm -rf -- "$scratch"' EXIT
    snapshot hub "$scratch/hub.db"
    snapshot channels "$scratch/channels.db"
    owner=$(docker run --rm --network none --entrypoint sh "$new" -c 'printf "%s:%s" "$(id -u)" "$(id -g)"')
    chown "$owner" "$scratch" "$scratch/hub.db" "$scratch/channels.db"
    chmod 644 smoke.py
    for mode in new old; do
        image=$new
        if [[ "$mode" == old ]]; then image=$base; fi
        docker run --rm --network none -v "$scratch:/smoke" -v "$PWD/smoke.py:/tmp/custody-smoke.py:ro" \
            --entrypoint python "$image" /tmp/custody-smoke.py "$mode"
    done
    printf '%s\n' "$base" > base.image
    printf '%s\n' "$new" > candidate.image
    printf '%s -> %s\n' "$base" "$new"
    ;;
switch)
    base=$(cat base.image)
    candidate=$(cat candidate.image)
    test "$(live_image)" = "$base"
    args=()
    if [[ -n "${2:-}" ]]; then
        [[ "$2" =~ ^0x[0-9a-fA-F]{40}$ ]]
        args+=(--set "AIMARKET_PUBLISHER_PAYOUT_FROM=$2")
    fi
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    backups="/root/hub-backups/publisher-custody-$stamp"
    mkdir -p "$backups"
    chmod 700 "$backups"
    snapshot hub "$backups/hub.db"
    snapshot channels "$backups/channels.db"
    echo "both ledger backups: $backups"
    test "$(live_image)" = "$base"
    python3 "$previous_kit/rollout_container.py" "$container" --image "$candidate" "${health_flags[@]}" "${args[@]}"
    test "$(live_image)" = "$candidate"
    docker exec -i "$container" sh -c 'cd /app/aimarket_hub && sha256sum -c -' < overlay.sha256
    ;;
rollback)
    base=$(cat base.image)
    candidate=$(cat candidate.image)
    test "$(live_image)" = "$candidate"
    python3 "$previous_kit/rollout_container.py" "$container" --image "$base" "${health_flags[@]}" \
        --set AIMARKET_PUBLISHER_PAYOUT_FROM=
    test "$(live_image)" = "$base"
    ;;
*) exit 2 ;;
esac
