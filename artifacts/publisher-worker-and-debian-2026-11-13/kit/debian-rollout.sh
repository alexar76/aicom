#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

container=modelmarket-hub
previous_kit=/root/hub-3.21.0-rollout-20261112/kit
custody_kit=/root/publisher-custody-20261112
health_flags=(--health http://127.0.0.1:9083/ai-market/v2/health --health http://127.0.0.1:9460/health)
worker=modelmarket-publisher-payout.service
timer=modelmarket-publisher-payout.timer

live_image() {
    docker inspect -f '{{.Image}}' "$container"
}

snapshot() {
    local kind=$1 target=$2
    docker exec -i "$container" python - "$kind" < "$custody_kit/snapshot.py" > "$target"
    test -s "$target"
}

switch_image() {
    local from=$1 to=$2
    test "$(live_image)" = "$from"
    local restore_timer=0 state
    restore_timer_if_needed() {
        if [[ "$restore_timer" == 1 ]]; then
            systemctl start "$timer"
            systemctl is-active --quiet "$timer"
        fi
    }
    trap restore_timer_if_needed EXIT
    if systemctl is-active --quiet "$timer"; then
        restore_timer=1
        systemctl stop "$timer"
    fi
    for _ in $(seq 1 90); do
        state=$(systemctl show -p ActiveState --value "$worker")
        if [[ "$state" == inactive || "$state" == failed ]]; then break; fi
        sleep 2
    done
    [[ "$state" == inactive || "$state" == failed ]]
    local stamp backups
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    backups=$(mktemp -d "/root/hub-backups/publisher-debian-$stamp-XXXXXXXX")
    snapshot hub "$backups/hub.db"
    snapshot channels "$backups/channels.db"
    echo "both ledger backups: $backups"
    test "$(live_image)" = "$from"
    python3 "$previous_kit/rollout_container.py" "$container" --image "$to" "${health_flags[@]}"
    test "$(live_image)" = "$to"
    docker exec "$container" dpkg-query -W apt libapt-pkg7.0 zlib1g
    restore_timer_if_needed
    trap - EXIT
}

case "${1:?prepare, switch or rollback required}" in
prepare)
    base=$(live_image)
    basename="modelmarket-debian-base:${base:7:12}"
    candidate="modelmarket-hub:debian-apt-zlib-20261113-${base:7:12}"
    run_user=$(docker image inspect -f '{{.Config.User}}' "$base")
    test -s bundle/InRelease && test -s bundle/Packages.xz
    cp verify-debian.py bundle/verify-debian.py
    docker tag "$base" "$basename"
    docker build --network=none --progress=plain --build-arg BASE="$basename" \
        --build-arg RUN_USER="${run_user:-root}" -t "$candidate" .
    new=$(docker image inspect -f '{{.Id}}' "$candidate")
    for mode in base candidate; do
        image=$base
        if [[ "$mode" == candidate ]]; then image=$new; fi
        docker run --rm --network none -i --user root --workdir /app --entrypoint python "$image" - \
            < check-image.py > "$mode.inventory.json"
    done
    python3 compare-images.py base.inventory.json candidate.inventory.json | tee image-delta.json
    scratch=$(mktemp -d /root/publisher-debian-smoke-XXXXXXXX)
    trap 'rm -rf -- "$scratch"' EXIT
    snapshot hub "$scratch/hub.db"
    snapshot channels "$scratch/channels.db"
    owner=$(docker run --rm --network none --entrypoint sh "$new" -c 'printf "%s:%s" "$(id -u)" "$(id -g)"')
    chown "$owner" "$scratch" "$scratch/hub.db" "$scratch/channels.db"
    for mode in candidate base; do
        image=$new
        if [[ "$mode" == base ]]; then image=$base; fi
        docker run --rm --network none -i -v "$scratch:/smoke" -e PYTHONPATH=/app \
            --entrypoint python "$image" - < check-ledger-copy.py | tee "$mode.ledger-smoke.json"
    done
    printf '%s\n' "$base" > base.image
    printf '%s\n' "$new" > candidate.image
    printf '%s -> %s\n' "$base" "$new"
    ;;
switch)
    switch_image "$(cat base.image)" "$(cat candidate.image)"
    ;;
rollback)
    switch_image "$(cat candidate.image)" "$(cat base.image)"
    ;;
*) exit 2 ;;
esac
