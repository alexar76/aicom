#!/usr/bin/env bash
# Run from the staged directory on an existing Hub host. The previous release's
# backup and container switch helper keeps volumes, settings and network borrowers.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
KIT=/root/hub-3.21.0-rollout-20261112/kit
WHEEL=xoflib-0.4.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
WHEEL_SHA=e6eff28d29b495ec9b8caaec9ca515520a0f10f035d2e065f996e59c52dd57f5
WHEEL_URL=https://files.pythonhosted.org/packages/03/f5/f87574fd5db333bb137df2b36a788ac9dfab9a74e2901ec9408ed054b3d5/$WHEEL

fetch_wheel() {
    mkdir -p wheel
    if [[ ! -f "wheel/$WHEEL" ]]; then
        curl --proto '=https' --tlsv1.2 -fsS --max-time 30 "$WHEEL_URL" -o "wheel/$WHEEL.download"
        printf '%s  %s\n' "$WHEEL_SHA" "wheel/$WHEEL.download" | sha256sum -c -
        mv "wheel/$WHEEL.download" "wheel/$WHEEL"
    fi
    printf '%s  %s\n' "$WHEEL_SHA" "wheel/$WHEEL" | sha256sum -c -
}

operation=${1:?expected prepare, switch, indep-prepare, indep-switch or indep-rollback}
shift

case "$operation" in
prepare)
    container=${1:?container required}
    base=$(docker inspect -f '{{.Image}}' "$container")
    run_user=$(docker image inspect -f '{{.Config.User}}' "$base")
    run_user=${run_user:-root}
    fetch_wheel
    basetag="hub-xoflib-base-${container}:${base:7:12}"
    candidate="hub-xoflib-${container}:0.4.0-20261112"
    docker tag "$base" "$basetag"
    docker build --network=none --build-arg BASE="$basetag" --build-arg RUN_USER="$run_user" \
        -t "$candidate" -f Dockerfile .
    docker run --rm --network none -i --entrypoint python "$candidate" - < verify.py
    docker image inspect -f '{{.Id}}' "$candidate" > "${container}.candidate"
    printf '%s\n' "$base" > "${container}.base"
    printf '%s %s -> %s\n' "$container" "$base" "$(cat "${container}.candidate")"
    ;;
switch)
    container=${1:?container required}
    urls=${2:?health URL required}
    pg_container=${3:-}
    test "$(docker inspect -f '{{.Image}}' "$container")" = "$(cat "${container}.base")"
    candidate=$(cat "${container}.candidate")
    "$KIT/roll.sh" "$container" "$candidate" "$urls" "$pg_container"
    test "$(docker inspect -f '{{.Image}}' "$container")" = "$candidate"
    docker exec -i "$container" python - < verify.py
    ;;
indep-prepare|indep-switch|indep-rollback)
    unit=independentai-hub.service
    old=/opt/independentai/venvs/hub-3.21.0-20261112
    new=/opt/independentai/venvs/hub-3.21.0-xoflib-20261112
    dropin=/etc/systemd/system/$unit.d/99g-hub-xoflib-20261112.conf
    health=http://127.0.0.1:9083/ai-market/v2/health

    live_python() {
        local pid
        pid=$(systemctl show -p MainPID --value "$unit")
        tr '\0' '\n' < "/proc/$pid/cmdline" | sed -n '1p'
    }

    wait_healthy() {
        local expected=$1
        for _ in $(seq 1 40); do
            if systemctl is-active --quiet "$unit" && [[ "$(live_python)" == "$expected" ]] \
                && curl -fsS --max-time 2 "$health" | python3 -c 'import json,sys; assert json.load(sys.stdin)["version"] == "3.21.0"'; then
                return 0
            fi
            sleep 1
        done
        return 1
    }

    rollback() {
        rm -f "$dropin"
        systemctl daemon-reload
        systemctl restart "$unit"
        wait_healthy "$old/bin/python"
    }

    case "$operation" in
    indep-prepare)
        test "$(live_python)" = "$old/bin/python"
        test ! -e "$new"
        fetch_wheel
        cp -a "$old" "$new"
        "$new/bin/python" -m pip install --no-index --no-deps "wheel/$WHEEL"
        "$new/bin/python" verify.py
        ;;
    indep-switch)
        test "$(live_python)" = "$old/bin/python"
        test ! -e "$dropin"
        "$new/bin/python" verify.py
        umask 077
        stamp=$(date -u +%Y%m%dT%H%M%SZ)
        backup="/var/backups/independentai/hub-pre-xoflib-$stamp.dump"
        sudo -u postgres pg_dump -Fc independentai_hub > "$backup"
        test -s "$backup"
        printf 'database backup %s\n' "$backup"
        cat > "$dropin" <<CONF
[Service]
ExecStart=
ExecStart=$new/bin/python -m aimarket_hub serve
CONF
        if ! (systemctl daemon-reload && systemctl restart "$unit" && wait_healthy "$new/bin/python"); then
            rollback
            exit 1
        fi
        systemctl show -p ActiveState -p NRestarts "$unit"
        printf 'live Python %s\n' "$(live_python)"
        ;;
    indep-rollback)
        test "$(live_python)" = "$new/bin/python"
        rollback
        ;;
    esac
    ;;
*) exit 2 ;;
esac
