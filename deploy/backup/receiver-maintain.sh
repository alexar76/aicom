#!/usr/bin/env bash
# Weekly, on the receiver, as the aicom-backup user: free the space clients' prunes released,
# then verify every segment's checksum. Neither needs a client's key.
#
# The trade-off of append-only: clients cannot really delete, so a compromised client's
# "delete everything" only becomes final here. Until this runs (Sunday) it can be undone by
# rolling the repository back to an earlier transaction (see README, "Undo a malicious prune").
set -uo pipefail
ROOT=/srv/aicom-backups
rc=0
for repo in "$ROOT"/*/; do
  repo="${repo%/}"
  [[ -f "$repo/config" && -d "$repo/data" ]] || continue
  echo "== $(basename "$repo")"
  borg compact --lock-wait 1800 "$repo" || { echo "compact failed: $repo"; rc=1; }
  borg check --repository-only --lock-wait 1800 "$repo" || { echo "CHECK FAILED: $repo"; rc=1; }
  du -sh "$repo"
done
exit $rc
