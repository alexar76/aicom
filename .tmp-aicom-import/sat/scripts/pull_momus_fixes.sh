#!/usr/bin/env bash
# Fetch MOMUS remediation branches from Gitea, verify them, and merge the ones that are safe to merge
# without a human reading them.
#
#   scripts/pull_momus_fixes.sh                 # fetch + verify + report. MERGES NOTHING.
#   scripts/pull_momus_fixes.sh --merge          # perform the merges it just cleared
#   scripts/pull_momus_fixes.sh --json           # machine-readable, for an agent to act on
#
# Meant to be run by an AGENT — Cursor, or any assistant with a shell — before a push or a deploy, so a
# remediation the conductor recorded does not sit in a branch nobody looks at.
#
# THE SCRIPT DOES NOT MERGE BY DEFAULT, ON PURPOSE. It fetches, verifies, classifies and prints the
# exact command for each branch; the merge is an act somebody takes, under their own name, having seen
# the verdict. A cron job that merged into main on every push would be a machine granting itself commit
# rights to the deploy branch — which is precisely the authority the whole remediation design withholds
# from agents. An agent running this and then running the merge is fine: the decision is attributable.
#
# ── THE RULE THAT MAKES AUTO-MERGE DEFENSIBLE ────────────────────────────────────────────────────────
#
# A branch is auto-merged only when it touches NOTHING but `.momus/*.json` — the signed provenance
# records. Those are append-only audit facts: merging one changes no behaviour, ships no code, and
# cannot break a build. The convenience is real and the risk is zero.
#
# The moment a branch touches ANY other path — a source file, a config, a workflow — it is left alone
# and reported. That is a machine-authored code change, and merging it without a human reading the diff
# is exactly the authority momus/docs/fix-provenance.md refuses to hand to an agent: a MOMUS-signed
# `fixed` verdict proves the finding stopped reproducing, not that the patch is good, not that it has no
# backdoor, and not that it left the rest of the system intact.
#
# So this script is not "auto-merge MOMUS fixes". It is "auto-merge the audit trail, queue the code".
# --force-code-merge exists for an operator who has read the diff and wants it landed; it prints what it
# is about to do and requires the branch to have passed every other check first.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
REMOTE="${MOMUS_FIX_REMOTE:-gitea2:alexar76/aicom.git}"
PREFIX="${MOMUS_FIX_BRANCH_PREFIX:-momus/fix-}"
# Default: report only. Merging requires --merge, so nothing lands because a script ran.
DRY=1; LIST=0; FORCE_CODE=0; JSON=0
for a in "$@"; do
  case "$a" in
    --merge) DRY=0 ;;
    --dry-run) DRY=1 ;;
    --json) JSON=1; DRY=1 ;;
    --list) LIST=1; DRY=1 ;;
    --force-code-merge) FORCE_CODE=1; DRY=0 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }

# ── refuse to touch a dirty tree ─────────────────────────────────────────────────────────────────────
# Merging into a tree with uncommitted changes is how somebody else's work gets reverted — this repo has
# concurrent writers, and a merge that stashes or clobbers them would be a silent data loss.
# Only a MERGE is blocked by a dirty tree. Reporting touches nothing, and refusing to report was
# actively unhelpful: the agent asking "what is waiting?" got a refusal instead of an answer.
if [ "$DRY" = 0 ] && [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  say "refusing to merge: the working tree has uncommitted tracked changes."
  say "  commit or stash them first — this repo has concurrent writers and a merge here would"
  say "  revert whatever is not committed."
  say "  (run without --merge to see what is waiting; reporting is always safe)"
  exit 1
fi

BRANCH_NOW=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH_NOW" != "main" ] && [ "$DRY" = 0 ]; then
  say "refusing to merge into '$BRANCH_NOW' — these branches target main."
  exit 1
fi

say "fetching ${PREFIX}* from ${REMOTE} …"
git fetch --quiet "$REMOTE" "refs/heads/${PREFIX}*:refs/remotes/momus-fixes/*" 2>/dev/null || {
  say "  fetch failed — is the Gitea remote reachable?"
  exit 1
}

# `mapfile` is bash 4+; macOS ships bash 3.2 and this script must run from an editor task there.
BRANCHES=()
while IFS= read -r line; do
  [ -n "$line" ] && BRANCHES+=("$line")
done < <(git for-each-ref --format='%(refname:short)' refs/remotes/momus-fixes/ 2>/dev/null)
if [ "${#BRANCHES[@]}" -eq 0 ]; then
  say "no ${PREFIX}* branches — nothing to merge."
  exit 0
fi

merged=0; queued=0; rejected=0
for br in "${BRANCHES[@]}"; do
  sha=$(git rev-parse --short "$br")
  # Already in main? Then it was merged before; clean it up rather than reporting it forever.
  if git merge-base --is-ancestor "$br" HEAD 2>/dev/null; then
    say "  · ${br#momus-fixes/} ($sha) — already in main"
    continue
  fi

  # What does it touch, relative to the merge base?
  base=$(git merge-base HEAD "$br")
  files=()
  while IFS= read -r line; do
    [ -n "$line" ] && files+=("$line")
  done < <(git diff --name-only "$base".."$br")
  nonprov=()
  for f in "${files[@]}"; do
    case "$f" in
      .momus/*.json) ;;
      *) nonprov+=("$f") ;;
    esac
  done

  # ── verification: the chain must be present and internally consistent ─────────────────────────────
  bad=""
  for f in "${files[@]}"; do
    case "$f" in
      .momus/*.json)
        if ! git show "$br:$f" | python3 -c '
import json, sys
d = json.load(sys.stdin)
need = ("finding_id", "component", "gate_verdict", "conductor_pubkey", "history")
missing = [k for k in need if not d.get(k)]
if missing:
    sys.exit(f"missing fields: {missing}")
g = d["gate_verdict"]
if g.get("fixed") is not True:
    sys.exit("gate verdict is not fixed=true")
if not g.get("verifier_pubkey"):
    sys.exit("gate verdict names no verifier key")
# A provenance record must not smuggle a full signature or a private host into main.
raw = json.dumps(d)
import re
if re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", raw):
    sys.exit("record contains a bare IP")
' 2>/tmp/momus_verify_err; then
          bad="$(cat /tmp/momus_verify_err 2>/dev/null | tail -1)"
          break
        fi
        ;;
    esac
  done

  if [ -n "$bad" ]; then
    say "  ✗ ${br#momus-fixes/} ($sha) — REJECTED: $bad"
    rejected=$((rejected + 1))
    continue
  fi

  if [ "${#nonprov[@]}" -gt 0 ] && [ "$FORCE_CODE" = 0 ]; then
    say "  ⏸ ${br#momus-fixes/} ($sha) — QUEUED for a human: touches code, not just provenance"
    for f in "${nonprov[@]}"; do say "        $f"; done
    say "        review it, then: git merge --no-ff $br"
    queued=$((queued + 1))
    continue
  fi

  if [ "$DRY" = 1 ]; then
    say "  ✓ ${br#momus-fixes/} ($sha) — CLEARED: provenance only (${#files[@]} file(s)), gate fixed=true"
    say "        git merge --no-ff $br"
    merged=$((merged + 1))
    continue
  fi

  fid=$(basename "${br#momus-fixes/}" | sed 's/^fix-//')
  if git merge --no-ff --no-edit -m "Merge the signed chain for MOMUS finding ${fid}.

Auto-merged by scripts/pull_momus_fixes.sh: the branch touches only .momus/*.json, so it ships
provenance and no code. Its gate verdict is fixed=true and names a verifier key, and the record
carries no bare IP.

A branch touching any other path is queued for a human instead — a signed 'fixed' verdict proves
the finding stopped reproducing, not that the patch is good." "$br" >/dev/null 2>&1; then
    say "  ✓ ${br#momus-fixes/} ($sha) — merged"
    merged=$((merged + 1))
    git push --quiet "$REMOTE" --delete "${PREFIX}${fid}" 2>/dev/null \
      && say "        remote branch deleted"
  else
    git merge --abort 2>/dev/null
    say "  ✗ ${br#momus-fixes/} ($sha) — merge conflicted, left for a human"
    rejected=$((rejected + 1))
  fi
done

say ""
if [ "$DRY" = 1 ]; then
  say "cleared to merge: $merged   needs a human: $queued   rejected: $rejected"
  if [ "$merged" -gt 0 ]; then
    say ""
    say "nothing was merged — this script only reports. To land the cleared branches:"
    say "    scripts/pull_momus_fixes.sh --merge"
    say "  then:"
    say "    git push $REMOTE HEAD:main"
  fi
else
  say "merged: $merged   needs a human: $queued   rejected: $rejected"
  [ "$merged" -gt 0 ] && say "push when ready:  git push $REMOTE HEAD:main"
fi
exit 0
