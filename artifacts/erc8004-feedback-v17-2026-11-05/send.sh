#!/bin/bash
# §70 step 2 (owner, 2026-11-05). run.sh installed WARDEN 0.23.0 on admin-vps; its dry run
# (runs/20261105T201744Z) planned 39 transactions: a first feedback for agent 1135859 and revoke + give for
# 19 agents (scores unchanged, re-issued under ruleset v17 with the fields EIP-8004 now requires). That is
# above the per-run cap of 20, so run.sh stopped before asking.
#
# This sends exactly that plan:
#   1. re-plans from the same scan (nothing sent), checks every report is served byte-for-byte,
#      and refuses if the actions differ from the reviewed plan.txt;
#   2. asks; sends only on "yes" (or with --yes, for the chat "!" box, which cannot answer a prompt).
# Gas comes from WARDEN's feedback-only wallet 0x564bE09d06117A106ECC006a19b67768cBd91666
# (~0.00003 ETH for all 39 at the 11-02 prices; balance 0.00046 ETH). Each transaction is logged in
# /var/lib/warden-feedback/feedback.log; the script stops at the first revert.
#
#   artifacts/erc8004-feedback-v17-2026-11-05/send.sh [--yes]
set -euo pipefail
REMOTE_ENV='export WARDEN_FB_STATE=/var/lib/warden-feedback WARDEN_FB_REPORTS=/var/www/warden-feedback
export WARDEN_FB_BASE_URL=https://histor.modelmarket.dev/.well-known/erc-8004/feedback
R=/var/lib/warden-feedback/runs/20261105T201744Z
set -- /opt/warden-feedback/feedback.py --scan "$R/scan_results.json" --tools "$R/tools_raw.jsonl" --key-file /etc/warden-feedback/wallet.json --max-tx 40'

echo "--- plan again from the reviewed scan (nothing is sent) ---"
ssh admin-vps "set -euo pipefail
$REMOTE_ENV
/opt/warden-feedback/.venv/bin/python \"\$@\" > \"\$R/plan-recheck.txt\" 2>&1 || { cat \"\$R/plan-recheck.txt\"; exit 1; }
cat \"\$R/plan-recheck.txt\"
[ \"\$(grep '^actions:' \"\$R/plan.txt\")\" = \"\$(grep '^actions:' \"\$R/plan-recheck.txt\")\" ] || { echo 'the plan changed since the reviewed dry run; nothing sent'; exit 1; }"

if [ "${1:-}" = "--yes" ]; then
  ok=yes
else
  read -r -p "Send these transactions from WARDEN's feedback wallet? Type yes: " ok
fi
[ "$ok" = yes ] || { echo "nothing sent"; exit 0; }

echo "--- sending ---"
ssh admin-vps "set -euo pipefail
$REMOTE_ENV
/opt/warden-feedback/.venv/bin/python \"\$@\" --send 2>&1 | tee \"\$R/send.txt\""
echo DONE
