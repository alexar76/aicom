#!/usr/bin/env python3
"""Build and certify every mapped satellite locally. Never reads remote Git state.

Uses the production layout functions through their source-only library entry point.
Remote preparation and publication are replaced by explicit offline adapters; the
unmodified trusted secret gate runs on each completed tree in a separate process.
Private/optional entries are included without changing their publication flags.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parent.parent

BOOTSTRAP = r'''
set -euo pipefail
export AICOM_MIRROR_LIBRARY_ONLY=1
source "$AICOM_AUDIT_SOURCE/scripts/mirror_satellites.sh"
ROOT="$AICOM_AUDIT_VIEW"
cd "$ROOT"
WORKDIR="$AICOM_AUDIT_WORKDIR"
FORCE_UNPUBLISHED_SATELLITE=1
# No Git transport is permitted. The profile existence probe is satisfied locally;
# branch probes return absent so production exporters initialize fresh local trees.
git_auth() {
  if [[ "$1" == ls-remote ]]; then
    [[ "$#" -eq 2 && "$AICOM_AUDIT_ID" == profile ]] && return 0
    return 1
  fi
  echo "OFFLINE: refused Git transport" >&2
  return 97
}
python3() {
  case "${1:-}" in
    "$ROOT/scripts/ensure_github_repo.py"|"$ROOT/scripts/ensure_github_pages.py") return 0 ;;
  esac
  "$AICOM_AUDIT_PYTHON" "$@"
}
# Early scans precede post-copy transformations. Certify the final tree separately
# with the real guard; never report a deferred early scan as a passing check.
bash() {
  if [[ "${1:-}" == "$ROOT/scripts/verify_mirror_secrets.sh" ]]; then return 0; fi
  command bash "$@"
}
_post_push_satellite_hook() { :; }
# Remote workflow preservation cannot be certified offline. Audit the source copy;
# the existing production live-tip comparison remains mandatory when publishing.
_preserve_warden_mcp_registry_workflow() {
  local rel=.github/workflows/publish-mcp-registry.yml
  mkdir -p "$1/.github/workflows"
  cp "$ROOT/warden/$rel" "$1/$rel"
}
_commit_and_push() (
  python3 "$ROOT/scripts/aicom_publish_config.py" purge-satellite-excludes "$1" "$2" || exit 1
  python3 "$ROOT/scripts/security/configure_npm_security.py" "$1" || exit 1
  printf '%s\n' "$1" > "$AICOM_AUDIT_RESULT"
)
if [[ "$AICOM_AUDIT_GENERIC" == 1 ]]; then
  export_simple "$AICOM_AUDIT_ID" "$AICOM_AUDIT_FROM" "$AICOM_AUDIT_REPO" mit
else
  export_satellite "$AICOM_AUDIT_ID"
fi
'''


def build_one(satellite: dict, output: Path, python: str) -> dict:
    sid = satellite['id']
    area = output / sid
    area.mkdir()
    work = area / 'trees'
    work.mkdir()
    view = ROOT
    if sid == 'aimarket-courses':
        # The course builder rewrites generated source assets. Isolate those writes.
        view = area / 'source-view'
        view.mkdir()
        for entry in ROOT.iterdir():
            if entry.name == 'courses':
                subprocess.run(['rsync', '-a', '--exclude', '.git', '--exclude', '.venv',
                                '--exclude', '__pycache__', '--exclude', '.pytest_cache',
                                str(entry) + '/', str(view / 'courses') + '/'], check=True)
            else:
                (view / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    layout = satellite.get('export_layout') or {}
    generic = sid in {'attested', 'pingblip', 'protocol-v2-from-spec-rs',
                      'protocol-v2-receipt-from-spec', 'protocol-v2-federator-go', 'emberline'}
    source = layout.get('root_from') or satellite['paths'][0]
    env = {k: v for k, v in os.environ.items() if k not in
           {'GH_PAT', 'GITHUB_TOKEN', 'AICOM_MIRROR_GH_TOKEN', 'BASH_ENV', 'ENV'}}
    env.update(AICOM_AUDIT_SOURCE=str(ROOT), AICOM_AUDIT_VIEW=str(view),
               AICOM_AUDIT_WORKDIR=str(work), AICOM_AUDIT_ID=sid,
               AICOM_AUDIT_RESULT=str(area / 'tree-path.txt'), AICOM_AUDIT_PYTHON=python,
               AICOM_AUDIT_GENERIC=str(int(generic)), AICOM_AUDIT_FROM=source,
               AICOM_AUDIT_REPO=satellite['repo'], GIT_ALLOW_PROTOCOL='',
               PYTHONDONTWRITEBYTECODE='1')
    row = {'id': sid, 'repo': satellite['repo'],
           'github_published': satellite.get('github_published', True),
           'layout': 'local-only source' if generic else 'production exporter',
           'remote_operations': 0}
    with (area / 'build.log').open('w') as log:
        result = subprocess.run(['bash', '-c', BOOTSTRAP], env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=600)
    row['build_exit'] = result.returncode
    result_path = area / 'tree-path.txt'
    if result.returncode or not result_path.is_file():
        row['status'] = 'build-failed'
        return row
    tree = Path(result_path.read_text().strip())
    row['tree'] = str(tree)
    # Manifest fingerprints are evidence of the exact certified bytes, not secrets.
    manifest = []
    for parent, dirs, files in os.walk(tree, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '.git')
        for name in sorted(files):
            path = Path(parent) / name
            if path.is_symlink():
                manifest.append({'path': path.relative_to(tree).as_posix(), 'symlink': os.readlink(path)})
            else:
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                manifest.append({'path': path.relative_to(tree).as_posix(), 'sha256': digest})
    (area / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    row['files'] = len(manifest)
    row['manifest_sha256'] = hashlib.sha256((area / 'manifest.json').read_bytes()).hexdigest()
    with (area / 'secret-check.log').open('w') as log:
        check = subprocess.run(['bash', str(ROOT / 'scripts/verify_mirror_secrets.sh'), str(tree)],
                               env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    row['secret_gate_exit'] = check.returncode
    row['status'] = 'passed' if check.returncode == 0 else 'secret-gate-failed'
    if view != ROOT:
        shutil.rmtree(view)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--satellite', action='append', default=[])
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    output = (args.output or Path(tempfile.mkdtemp(prefix='aicom-satellite-audit-'))).resolve()
    output.mkdir(parents=True, exist_ok=True)
    satellites = [s for s in yaml.safe_load((ROOT / 'scripts/satellite-map.yaml').read_text())['satellites']
                  if s['id'] != 'aicom' and (not args.satellite or s['id'] in args.satellite)]
    if args.satellite and set(args.satellite) - {s['id'] for s in satellites}:
        parser.error('unknown satellite id')
    python = str(ROOT / '.venv/bin/python') if (ROOT / '.venv/bin/python').exists() else sys.executable
    def run(satellite: dict) -> dict:
        try:
            row = build_one(satellite, output, python)
        except Exception as error:
            row = {'id': satellite['id'], 'status': 'audit-failed', 'error': type(error).__name__}
        print(f"{row['id']}: {row['status']}", flush=True)
        return row
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        rows = list(executor.map(run, satellites))
    report = {'satellites': len(rows), 'passed': sum(r['status'] == 'passed' for r in rows),
              'github_writes': 0, 'live_remote_history_verified': False, 'results': rows}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"Report: {output / 'report.json'}", flush=True)
    return int(report['passed'] != report['satellites'])


if __name__ == '__main__':
    raise SystemExit(main())
