#!/usr/bin/env bash
# Ask every provider, on every machine, whether the model ids configured there still exist.
#
# The point of doing it per-machine: the id that actually reaches a provider is not in this
# repository. `data/config/model_providers.yaml` is gitignored, and the federation judge's
# model lives only in a container's environment. A check that reads the repo checks a file
# nobody runs — which is why the existing /v1/models health-check leg never caught the rot
# that this exists to catch (deepseek-chat: 57 occurrences, dead at DeepSeek since before
# anyone noticed).
#
# Read-only. Copies one stdlib-only script in, runs it, copies nothing out. Never prints a key.
#
#   ./scripts/verify_model_ids_fleet.sh            # report
#   ./scripts/verify_model_ids_fleet.sh --quiet    # only the lines that need a human
#
# Exit 1 if any machine reports a configured id its provider no longer serves.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/verify_model_ids.py"
[[ -f "$SCRIPT" ]] || { echo "missing $SCRIPT" >&2; exit 2; }

QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

# host:container — a container because that is where the keys and the effective config are.
# A bare "-" container means run on the host itself.
TARGETS=(
  "my-vps:aicom-app-1"          # the factory: llm/router.py and model_providers.yaml
  "my-vps:modelmarket-hub"      # apex federation judge (env only)
  "competing-lab:modelmarket-hub"   # competing lab judge (env only)
  "competing-lab:signal-hunt-hub-1"
  "not-my-vps:metis-skopos"
)

rc=0
for target in "${TARGETS[@]}"; do
  host="${target%%:*}"; container="${target##*:}"
  echo "── ${host} / ${container}"
  # `docker cp` then exec: the script is stdlib-only precisely so a bare container can run it.
  out=$(ssh -o ConnectTimeout=20 -o BatchMode=yes "$host" \
        "cat > /tmp/vmi.py && docker cp /tmp/vmi.py ${container}:/tmp/vmi.py >/dev/null 2>&1 && docker exec ${container} python3 /tmp/vmi.py 2>&1" \
        < "$SCRIPT" 2>&1)
  status=$?
  (( status != 0 )) && rc=1
  if (( QUIET )); then
    printf '%s\n' "$out" | grep -E "DEAD|ALIAS|warn|^[0-9]+ (configured|id\(s\))" | sed 's/^/  /' || echo "  (clean)"
  else
    printf '%s\n' "$out" | sed 's/^/  /'
  fi
done

if (( rc != 0 )); then
  echo
  echo "At least one machine is configured with a model its provider no longer serves."
fi
exit $rc
