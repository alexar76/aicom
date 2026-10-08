#!/usr/bin/env bash
# Weekly, on the receiver, as the aicom-backup user: verify every segment's checksum (needs no
# client key). Space released by clients' prunes is freed only on request (see below).
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
  # No automatic compact. Compacting is what makes a compromised client's "delete
  # everything" final; until then it is undone by rolling back the transaction log (README).
  # Run it by hand, or set AICOM_BACKUP_COMPACT=1, only after checking that the repo did not
  # just lose its archives (backup-status.json: size_mb vs size_mb_peak_7d).
  if [[ "${AICOM_BACKUP_COMPACT:-0}" == "1" ]]; then
    borg compact --lock-wait 1800 "$repo" || { echo "compact failed: $repo"; rc=1; }
  fi
  borg check --repository-only --lock-wait 1800 "$repo" || { echo "CHECK FAILED: $repo"; rc=1; }
  du -sh "$repo"
done
exit $rc
