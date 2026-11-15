#!/usr/bin/env bash
# Deploy MOMUS quality-gate source files from this checkout to admin-vps, one command per change.
#
#   ./scripts/deploy_momus_quality_source.sh --dry-run momus/momus/engine/coverage_semantic.mjs
#   ./scripts/deploy_momus_quality_source.sh momus/momus/engine/coverage_semantic.mjs [more files…]
#
# Owner-run on purpose. MOMUS signs the release-quality receipt that every WARDEN publish and HISTOR
# deploy needs, so the agent that prepares a release must not change the judge (on 2026-11-15 the
# agent's own attempt was refused for exactly that). This script only removes the typing.
#
# For each file (it must be under momus/momus/ and committed, so the deployed text is in git):
#   - compares the local sha256 with the one on admin-vps and skips a file that is already there;
#   - refuses while a MOMUS run is in progress (momus-quality.service or warden-release-quality-*),
#     because a run reads these files;
#   - keeps the remote file as <name>.pre-<UTC time>-<old sha 8>, never overwriting an existing backup
#     (on 2026-11-15 a repeated `cp -p` turned the only backup into the new file);
#   - checks syntax on the host (node --check for .mjs/.js, python3 -m py_compile for .py) before
#     installing, keeps the remote owner and mode, and verifies the installed sha;
#   - prints the rollback command.
set -euo pipefail

HOST="${MOMUS_HOST:-admin-vps}"
REMOTE_ROOT="/opt/momus-quality/source"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=0
FILES=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *) FILES+=("$arg") ;;
  esac
done
[[ ${#FILES[@]} -gt 0 ]] || { echo "usage: $0 [--dry-run] momus/momus/<path>…" >&2; exit 2; }

cd "$ROOT"
for rel in "${FILES[@]}"; do
  rel="${rel#./}"
  case "$rel" in
    momus/momus/*) ;;
    *) echo "refusing $rel: only files under momus/momus/ are MOMUS quality source" >&2; exit 2 ;;
  esac
  [[ -f "$rel" ]] || { echo "missing: $rel" >&2; exit 2; }
  if ! git diff --quiet HEAD -- "$rel" || ! git ls-files --error-unmatch "$rel" >/dev/null 2>&1; then
    echo "refusing $rel: commit it first, so the deployed text is in git" >&2; exit 2
  fi
done

busy="$(ssh -o ConnectTimeout=15 "$HOST" 'systemctl is-active -q momus-quality.service && echo "a daily MOMUS run";
  systemctl list-units --no-legend --state=active "warden-release-quality-*" | grep -q . && echo "a MOMUS candidate run"; true')"
if [[ -n "$busy" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then echo "note: in progress now: ${busy//$'\n'/, } (a real deploy would wait)"
  else echo "in progress: ${busy//$'\n'/, }; a run reads these files, try again after it" >&2; exit 3; fi
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
for rel in "${FILES[@]}"; do
  rel="${rel#./}"
  dest="$REMOTE_ROOT/${rel#momus/}"
  want="$(shasum -a 256 "$rel" | cut -d' ' -f1)"
  have="$(ssh -o ConnectTimeout=15 "$HOST" "sha256sum '$dest' 2>/dev/null | cut -d' ' -f1" || true)"
  echo "== $rel"
  echo "   local  $want"
  echo "   remote ${have:-<absent>}  ($dest)"
  if [[ "$want" == "$have" ]]; then echo "   already deployed"; continue; fi
  if [[ -z "$have" ]]; then echo "refusing: $dest does not exist on $HOST (new files go through a full MOMUS deploy)" >&2; exit 4; fi
  backup="$dest.pre-$stamp-${have:0:8}"
  if [[ "$DRY_RUN" -eq 1 ]]; then echo "   would back up to $backup and install"; continue; fi
  ssh -o ConnectTimeout=15 "$HOST" "set -e
    tmp=\$(mktemp '$dest.new.XXXXXX')
    trap 'rm -f \"\$tmp\"' EXIT
    cat > \"\$tmp\"
    [ \"\$(sha256sum \"\$tmp\" | cut -d' ' -f1)\" = '$want' ] || { echo 'upload corrupted' >&2; exit 5; }
    case '$dest' in
      *.mjs|*.js) node --check \"\$tmp\" ;;
      *.py) python3 -m py_compile \"\$tmp\" ;;
    esac
    [ ! -e '$backup' ] || { echo 'backup name already taken' >&2; exit 5; }
    cp -p '$dest' '$backup'
    chown --reference='$dest' \"\$tmp\"; chmod --reference='$dest' \"\$tmp\"
    mv \"\$tmp\" '$dest'
    trap - EXIT
    [ \"\$(sha256sum '$dest' | cut -d' ' -f1)\" = '$want' ] || { echo 'installed file differs' >&2; exit 5; }
    [ \"\$(sha256sum '$backup' | cut -d' ' -f1)\" = '$have' ] || { echo 'backup differs from the old file' >&2; exit 5; }" < "$rel"
  echo "   installed; backup $backup"
  echo "   rollback: ssh $HOST 'cp -p $backup $dest && sha256sum $dest'   (expect ${have:0:16}…)"
done
