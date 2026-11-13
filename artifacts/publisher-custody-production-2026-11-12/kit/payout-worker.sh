#!/usr/bin/env bash
set -euo pipefail

container=modelmarket-hub
key=/root/modelmarket-publisher-payout-20261112/signer.key
sender=$(docker exec "$container" printenv AIMARKET_PUBLISHER_PAYOUT_FROM)
[[ "$sender" == 0xb35100405F7aeA3e11de2F5Bf18316be507f6Eba ]]
image=$(docker inspect -f '{{.Image}}' "$container")
volume=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}{{end}}' "$container")
[[ -n "$volume" ]]
case "${1:-}" in
    run-once|send|reconcile|list) ;;
    *) exit 2 ;;
esac

exec docker run --rm --network "container:$container" --workdir /app \
    --read-only --tmpfs /tmp:rw,nosuid,nodev,noexec,size=16m --cap-drop ALL --security-opt no-new-privileges \
    --mount "type=volume,src=$volume,dst=/app/data" \
    --mount "type=bind,src=$key,dst=/run/publisher-signer.key,readonly" \
    --env PYTHONPATH=/app --env PYTHONDONTWRITEBYTECODE=1 --env AIMARKET_DB_PATH=/app/data/hub.db \
    --env "AIMARKET_PUBLISHER_PAYOUT_FROM=$sender" --env AIMARKET_PUBLISHER_PAYOUT_KEY_FILE=/run/publisher-signer.key \
    --env AIMARKET_SETTLE_RPC_8453=https://mainnet.base.org,https://base-rpc.publicnode.com,https://base.drpc.org \
    --entrypoint python "$image" -m aimarket_hub.publisher_withdrawal_cli "$@"
