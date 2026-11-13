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
expected_parent=sha256:3f372add6d130032e21248a8c0e5211dc201980c6c9683e2e072f776ceb074ee

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
    backups=$(mktemp -d "/root/hub-backups/cmc-receipt-$stamp-XXXXXXXX")
    snapshot hub "$backups/hub.db"
    snapshot channels "$backups/channels.db"
    echo "both ledger backups: $backups"
    test "$(live_image)" = "$from"
    python3 "$previous_kit/rollout_container.py" "$container" --image "$to" "${health_flags[@]}"
    test "$(live_image)" = "$to"
    restore_timer_if_needed
    trap - EXIT
}

case "${1:?prepare, switch or rollback required}" in
prepare)
    base=$(live_image)
    test "$base" = "$expected_parent"
    basename="modelmarket-cmc-receipt-base:${base:7:12}"
    candidate="modelmarket-hub:cmc-receipt-${base:7:12}"
    run_user=$(docker image inspect -f '{{.Config.User}}' "$base")
    docker exec -i "$container" sh -c 'cd /app/aimarket_hub && sha256sum -c -' < preimage.sha256
    docker run --rm --network none -i --entrypoint sh "$base" -c \
        'cd /app/aimarket_hub && sha256sum -c -' < preimage.sha256
    docker tag "$base" "$basename"
    docker build --network=none --build-arg BASE="$basename" --build-arg RUN_USER="${run_user:-root}" -t "$candidate" .
    new=$(docker image inspect -f '{{.Id}}' "$candidate")
    docker run --rm --network none -i --entrypoint sh "$new" -c \
        'cd /app/aimarket_hub && sha256sum -c -' < overlay.sha256
    for mode in base candidate; do
        image=$base
        if [[ "$mode" == candidate ]]; then image=$new; fi
        docker run --rm --network none -i --user root --workdir /app --entrypoint python "$image" - \
            < inventory.py > "$mode.inventory.json"
    done
    python3 - <<'PY' | tee image-delta.json
import json
from pathlib import Path
base, candidate = (json.loads(Path(f'{mode}.inventory.json').read_text()) for mode in ('base', 'candidate'))
assert base['debian'] == candidate['debian'] and base['python'] == candidate['python']
assert base['source'].keys() == candidate['source'].keys()
changed = {path: new for path, new in candidate['source'].items() if base['source'][path] != new}
expected = {path: digest for digest, path in (line.split() for line in Path('overlay.sha256').read_text().splitlines())}
assert changed == expected, (changed, expected)
print(json.dumps({'changed_source': changed, 'unchanged_python': len(base['python']),
                  'unchanged_debian': len(base['debian'])}, indent=2))
PY
    scratch=$(mktemp -d /root/cmc-receipt-smoke-XXXXXXXX)
    trap 'rm -rf -- "$scratch"' EXIT
    snapshot hub "$scratch/hub.db"
    snapshot channels "$scratch/channels.db"
    owner=$(docker run --rm --network none --entrypoint sh "$new" -c 'printf "%s:%s" "$(id -u)" "$(id -g)"')
    chown "$owner" "$scratch" "$scratch/hub.db" "$scratch/channels.db"
    for mode in candidate base; do
        image=$new
        if [[ "$mode" == base ]]; then image=$base; fi
        docker run --rm --network none -i -v "$scratch:/smoke" -e PYTHONPATH=/app \
            --entrypoint python "$image" - "$mode" < smoke.py | tee "$mode.smoke.json"
    done
    printf '%s\n' "$base" > base.image
    printf '%s\n' "$new" > candidate.image
    printf '%s -> %s\n' "$base" "$new"
    ;;
switch)
    switch_image "$(cat base.image)" "$(cat candidate.image)"
    docker exec -i "$container" sh -c 'cd /app/aimarket_hub && sha256sum -c -' < overlay.sha256
    ;;
rollback)
    switch_image "$(cat candidate.image)" "$(cat base.image)"
    ;;
*) exit 2 ;;
esac
