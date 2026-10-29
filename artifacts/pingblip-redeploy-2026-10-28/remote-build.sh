#!/usr/bin/env bash
set -euo pipefail
cd /opt/pingblip
python3 - <<'PY'
from pathlib import Path
values = {}
for line in Path('.env').read_text().splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('\"\'')
for key in ('NEXT_PUBLIC_APP_URL', 'NEXT_PUBLIC_FORGE_URL', 'NEXT_PUBLIC_WORLD_URL', 'NEXT_PUBLIC_BLIP_URL', 'NEXT_PUBLIC_PLAY_URL'):
    value = values.get(key, '')
    if value and ('localhost' in value or '127.0.0.1' in value or not value.startswith('https://')):
        raise SystemExit('Refusing non-production public origin: ' + key)
print('Production public origins validated; live .env preserved.')
PY
docker compose config --quiet
printf 'CPU/memory before build: '
nproc
free -m
for service in forge pingblip world; do
    cid=$(docker compose ps -q "$service")
    image=$(docker inspect -f '{{.Config.Image}}' "$cid")
    previous="${image%:*}:prev"
    docker tag "$image" "$previous"
    printf 'ROLLBACK %s %s ' "$service" "$previous"
    docker image inspect "$previous" --format '{{.Id}}'
done
for service in forge pingblip world; do
    printf '\nBUILD_START %s\n' "$service"
    docker compose build "$service"
    printf 'BUILD_OK %s\n' "$service"
done
printf '\nRECREATE_APPLICATIONS\n'
docker compose up -d --no-deps pingblip forge world
for check in '3080 /' '3081 /forge' '3082 /'; do
    read -r port route <<< "$check"
    ready=0
    for attempt in $(seq 1 45); do
        if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${port}${route}"; then
            ready=1
            break
        fi
        sleep 2
    done
    if [[ "$ready" != 1 ]]; then
        echo "HEALTH_FAILED ${port}${route}" >&2
        exit 1
    fi
    echo "HEALTH_OK ${port}${route}"
done
docker compose ps --format json
for service in forge pingblip world; do
    cid=$(docker compose ps -q "$service")
    docker inspect -f 'RUNNING {{.Name}} {{.Config.Image}} {{.Image}} {{.State.Status}}' "$cid"
done
echo 'DEPLOY_OK adea1f8a197d4e9badfed559b960518bd1449cf4'
