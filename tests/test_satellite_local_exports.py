"""Exercise the real export policy against fresh and reused trees without a remote."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import aicom_publish_config as config
import audit_satellite_exports as audit
import sync_knowledge_base as knowledge


def shell(code: str, *args: Path | str) -> subprocess.CompletedProcess:
    return subprocess.run(['bash', '-c', code, 'offline-test', *map(str, args)], cwd=ROOT,
                          env={**os.environ, 'AICOM_MIRROR_LIBRARY_ONLY': '1'},
                          text=True, capture_output=True, timeout=30)


def test_loading_library_does_not_read_auth_or_contact_remote(tmp_path):
    # Fail if library initialization tries git, Python, a temp clone or publication.
    result = shell('''
set -euo pipefail
python3() { echo unexpected-python >&2; return 98; }
git() { echo unexpected-git >&2; return 98; }
mktemp() { echo unexpected-workdir >&2; return 98; }
source "$1/scripts/mirror_satellites.sh"
[[ -z "$WORKDIR" ]]
declare -F export_satellite >/dev/null
''', ROOT)
    assert result.returncode == 0, result.stderr
    assert not result.stdout and not result.stderr


@pytest.mark.parametrize('satellite_id', ['aimarket-desktop', 'aimarket-courses', 'oracles',
                                         'platon', 'aimarket-plugins', 'aicom-products'])
def test_shared_transfer_filters_working_tree_secrets_and_keeps_public_source(tmp_path, satellite_id):
    src, dst = tmp_path / 'src', tmp_path / 'dst'
    src.mkdir()
    excluded = ['nested/.mirror-forbidden-hosts', 'nested/.env.production', 'nested/session_secret',
                'vendor/pkg/treasury_signing_key_mldsa', 'vendor/pkg/.npmrc',
                'node_modules/dependency/index.js', 'nested/data.sqlite3']
    kept = ['README.md', 'nested/.env.example', 'nested/quality-public-key.pem',
            'vendor/pkg/_signing_key_storage.py']
    for rel in excluded + kept:
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture\n')
    result = shell('''
set -euo pipefail
source "$1/scripts/mirror_satellites.sh"
# Even a legacy caller with an earlier broad include cannot override the policy.
_satellite_rsync -a --include '*' "$2/" "$3/"
''', ROOT, src, dst)
    assert result.returncode == 0, result.stderr
    assert all(not (dst / rel).exists() for rel in excluded)
    assert all((dst / rel).is_file() for rel in kept)
    # Confirm this special export uses the shared transfer function.
    script = (ROOT / 'scripts/mirror_satellites.sh').read_text()
    names = {'aimarket-desktop': 'desktop_monorepo', 'aimarket-courses': 'courses_monorepo',
             'oracles': 'oracles', 'platon': 'platon', 'aimarket-plugins': 'plugins',
             'aicom-products': 'aicom_products'}
    body = script.split('export_' + names[satellite_id] + '() {', 1)[1].split('\n}\n', 1)[0]
    assert '_satellite_rsync ' in body


def test_reused_satellite_tree_removes_nested_runtime_and_map_excludes(tmp_path):
    tree = tmp_path / 'export'
    tree.mkdir()
    excluded = ['old/.mirror-forbidden-hosts', 'old/.npmrc', 'old/session_secret',
                'old/unused_signing_key', 'servers.yaml', 'agent.yaml', '.venv/stale.py']
    kept = ['README.md', '.git/HEAD', '.env.example', 'quality-public-key.pem',
            'pkg/_signing_key_storage.py']
    for rel in excluded + kept:
        path = tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture\n')
    assert set(excluded[:-1]) <= set(config.purge_satellite_paths(tree, 'skopos'))
    assert all(not (tree / rel).exists() for rel in excluded)
    assert all((tree / rel).exists() for rel in kept)
    assert config.purge_satellite_paths(tree, 'skopos') == []


def test_purge_never_traverses_an_external_symlink(tmp_path):
    tree, outside = tmp_path / 'export', tmp_path / 'outside'
    tree.mkdir()
    outside.mkdir()
    (outside / 'session_secret').write_text('fixture')
    (tree / 'linked').symlink_to(outside, target_is_directory=True)
    (tree / 'runtime_signing_key').symlink_to(outside, target_is_directory=True)
    config.purge_satellite_paths(tree, 'profile')
    assert (outside / 'session_secret').read_text() == 'fixture'
    assert (tree / 'linked').is_symlink()
    assert not (tree / 'runtime_signing_key').is_symlink()


def test_purge_keeps_restored_warden_live_workflow(tmp_path):
    workflow = tmp_path / '.github/workflows/publish-mcp-registry.yml'
    workflow.parent.mkdir(parents=True)
    workflow.write_text('live tip fixture\n')
    config.purge_satellite_paths(tmp_path, 'warden')
    assert workflow.read_text() == 'live tip fixture\n'


@pytest.mark.parametrize('satellite_id,internal', [
    ('attested', ['DNS-PLAN.md']),
    ('pingblip', ['deploy/deploy_pingblip.sh', 'deploy/nginx/pingblip.conf',
                  'clips/.unfinished.render.mp4']),
])
def test_internal_operator_material_stays_out_of_local_exports(tmp_path, satellite_id, internal):
    for rel in internal:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('operator fixture\n')
    (tmp_path / 'README.md').write_text('Public source\n')
    config.purge_satellite_paths(tmp_path, satellite_id)
    assert all(not (tmp_path / rel).exists() for rel in internal)
    assert (tmp_path / 'README.md').is_file()


@pytest.mark.parametrize('pattern,path,match', [
    ('*.db', 'nested/runtime.db', True),
    ('contracts/cache', 'nested/contracts/cache', False),
    ('contracts/cache', 'contracts/cache', True),
    ('**/broadcast', 'broadcast', True),
    ('**/broadcast', 'a/b/broadcast', True),
    ('web/*/models', 'web/src/deep/models', False),
    ('docs/**/raw', 'docs/a/b/raw', True),
])
def test_cleanup_matches_rsync_glob_boundaries(pattern, path, match):
    assert bool(config._rsync_pattern(pattern).search(path)) is match


def test_purge_refuses_workspace_and_unknown_satellite(tmp_path):
    with pytest.raises(ValueError, match='workspace'):
        config.purge_satellite_paths(ROOT, 'profile')
    with pytest.raises(ValueError, match='unknown'):
        config.purge_satellite_paths(tmp_path, 'does-not-exist')


def test_local_knowledge_visibility_does_not_publish_private_map_entries():
    raw = 'satellites:\n  - id: local-service\n    github_published: false\n    knowledge_visible: true\n  - id: public-service\n'
    assert 'local-service' in knowledge.satellite_map_mirror_text('scripts/satellite-map.yaml', raw)
    assert 'local-service' not in knowledge.satellite_map_mirror_text(
        'scripts/satellite-map.yaml', raw, include_local_knowledge=False)


def test_readme_without_existing_badges_gets_banner(tmp_path):
    readme = tmp_path / 'README.md'
    readme.write_text('A plain README without a heading.\n')
    result = shell('''
set -euo pipefail
source "$1/scripts/mirror_satellites.sh"
_inject_mirror_banner "$2" domain-kit domain-operator-kit
''', ROOT, tmp_path)
    assert result.returncode == 0, result.stderr
    assert '<!-- aicom-mirror-notice -->' in readme.read_text()


def test_dioscuri_export_does_not_purge_workspace_sources():
    script = (ROOT / 'scripts/mirror_satellites.sh').read_text()
    assert '_purge_dioscuri_stray_source' not in script
    assert '_purge_dioscuri_mirror_clone "$clone"' in script


def test_offline_adapter_refuses_transport_and_all_publication(tmp_path):
    # Exercise the actual bootstrap's adapter definitions and fail on an attempted push.
    setup = audit.BOOTSTRAP.split('if [[ "$AICOM_AUDIT_GENERIC" == 1 ]]', 1)[0]
    result = subprocess.run(['bash', '-c', setup + '\ngit_auth push origin main\n'],
        env={**os.environ, 'AICOM_AUDIT_SOURCE': str(ROOT), 'AICOM_AUDIT_VIEW': str(ROOT),
             'AICOM_AUDIT_WORKDIR': str(tmp_path), 'AICOM_AUDIT_ID': 'profile',
             'AICOM_AUDIT_PYTHON': sys.executable}, text=True, capture_output=True)
    assert result.returncode == 97
    assert 'OFFLINE: refused Git transport' in result.stderr


def test_factory_map_uses_the_same_public_filter(tmp_path):
    script = (ROOT / 'scripts/publish_aicom_factory.sh').read_text()
    body = script.split('strip_unpublished_from_factory_map() {', 1)[1].split('\n}\n', 1)[0]
    dest = tmp_path / 'scripts/satellite-map.yaml'
    dest.parent.mkdir()
    dest.write_text((ROOT / 'scripts/satellite-map.yaml').read_text())
    code = 'set -euo pipefail\nROOT="$1"\nstrip_unpublished_from_factory_map() {' + body + '\n}\nstrip_unpublished_from_factory_map "$2"\n'
    result = shell(code, ROOT, tmp_path)
    assert result.returncode == 0, result.stderr
    import yaml
    assert all(s.get('github_published') is not False for s in yaml.safe_load(dest.read_text())['satellites'])


def test_export_stops_when_shared_transfer_policy_fails(tmp_path):
    code = '''
set -euo pipefail
source "$1/scripts/mirror_satellites.sh"
WORKDIR="$2"
python3() {
  case "${1:-}" in "$ROOT/scripts/ensure_github_repo.py") return 0 ;; esac
  command python3 "$@"
}
git_auth() { return 1; }
_satellite_rsync() { return 98; }
_commit_and_push() { echo unexpectedly-reached-publication >&2; return 0; }
# Aggregate export dispatch wraps functions in ||; don't rely on errexit here.
rc=0
export_simple domain-kit domain-kit domain-operator-kit mit || rc=$?
[[ "$rc" -ne 0 ]]
'''
    result = shell(code, ROOT, tmp_path)
    assert result.returncode == 0, result.stderr
    assert 'unexpectedly-reached-publication' not in result.stderr
