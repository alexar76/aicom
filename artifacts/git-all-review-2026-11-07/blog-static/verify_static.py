"""Verify an immutable blog/YAML snapshot inside the remote network-disabled sandbox."""
from __future__ import annotations

import hashlib
import html
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import yaml


INPUT = Path('/input')
RECEIPTS = Path('/receipts')
RESULTS = Path('/results')
WORK = Path('/work')
POSTS = (
    'a-missing-version-broke-verification-of-signed-ard-search-results',
    'a-privacy-warning-became-bad-advice-in-an-ai-reviewers-draft',
    'an-mcp-tool-set-can-gain-a-digest-without-changing',
    'healthy-containers-hid-a-blocked-mcp-marketplace-connection',
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hash_manifest(name: str) -> int:
    count = 0
    for line in (RECEIPTS / name).read_text().splitlines():
        expected, relative = line.split('  ', 1)
        path = (INPUT / 'aicom' / relative).resolve(strict=True)
        assert path.is_relative_to(INPUT), f'Manifest path escapes snapshot: {relative}'
        assert path.is_file() and sha(path) == expected, f'Changed snapshot input: {relative}'
        count += 1
    return count


started = time.monotonic()
RESULTS.mkdir(parents=True, exist_ok=True)
report = {
    'host': os.environ.get('HOST_LABEL', 'unknown'),
    'scope': 'Static blog build and real PyYAML parsing; no deployment or service start',
    'python': sys.version.split()[0],
    'dependencies': {name: importlib.metadata.version(name) for name in ('Markdown', 'Pillow', 'PyYAML')},
    'input_manifests': {},
}
for name in ('blog-source.sha256', 'promo-source.sha256', 'yaml-source.sha256', 'font-source.sha256'):
    report['input_manifests'][name] = {'sha256': sha(RECEIPTS / name), 'files_verified': verify_hash_manifest(name)}

source_blog = INPUT / 'aicom/modelmarket-blog'
asset_manifest = json.loads((source_blog / 'public-assets.json').read_text())
assert asset_manifest['schema'] == 'modelmarket-blog-public-assets/1'
public_assets = []
for target, expected in asset_manifest['files'].items():
    public_assets.append((target, source_blog / target, expected))
for target, entry in asset_manifest.get('promo_files', {}).items():
    relative = Path(entry['source'])
    assert not relative.is_absolute() and not any(part.startswith('.') for part in relative.parts)
    assert relative.suffix.lower() in {'.png', '.webp', '.jpg', '.jpeg', '.svg', '.zip'}
    source = INPUT / 'PromoMaterials' / relative
    assert source.resolve(strict=True).is_relative_to(INPUT / 'PromoMaterials')
    assert not source.is_symlink() and sha(source) == entry['sha256'], f'Changed public promotional asset: {target}'
    public_assets.append((target, source, entry['sha256']))
assert len({target for target, _, _ in public_assets}) == len(public_assets)

shutil.copytree(INPUT / 'aicom', WORK / 'aicom')
shutil.copytree(INPUT / 'PromoMaterials', WORK / 'PromoMaterials')
blog = WORK / 'aicom/modelmarket-blog'
cache_source = Path('/cache')
cache_provenance = json.loads((cache_source / 'cache-provenance.json').read_text())
for entry in cache_provenance['files']:
    assert sha(cache_source / entry['cache_path']) == entry['sha256'], 'Changed public cache input'
shutil.copytree(cache_source / 'cache', blog / '.cache')
report['public_cache'] = {'manifest_sha256': sha(cache_source / 'cache-provenance.json'), 'files_verified': len(cache_provenance['files'])}
with (RESULTS / 'build.log').open('w') as output:
    build = subprocess.run(
        [sys.executable, str(blog / 'build.py'), '--base', 'https://modelmarket.dev/blog'],
        cwd=blog, stdout=output, stderr=subprocess.STDOUT, check=False, timeout=600,
    )
report['build_exit'] = build.returncode
assert build.returncode == 0, 'Blog build failed; see build.log'
dist = blog / 'dist'
for target, source, expected in public_assets:
    assert sha(source) == expected, f'Original public asset mismatch: {target}'
    assert sha(dist / target) == expected, f'Built public asset mismatch: {target}'
report['public_assets_verified'] = len(public_assets)
report['promotional_assets_verified'] = len(asset_manifest.get('promo_files', {}))
report['new_posts'] = []
for slug in POSTS:
    meta = json.loads((blog / 'posts' / slug / 'meta.json').read_text())
    body = blog / 'posts' / slug / 'body.md'
    assert not meta.get('draft'), f'Expected published post marked draft: {slug}'
    page = dist / slug / 'index.html'
    text = page.read_text()
    assert html.escape(meta['title']) in text, f'Built title missing: {slug}'
    assert f'https://modelmarket.dev/blog/{slug}' in text, f'Built canonical URL missing: {slug}'
    report['new_posts'].append({'slug': slug, 'body_sha256': sha(body), 'meta_sha256': sha(blog / 'posts' / slug / 'meta.json'), 'page_bytes': page.stat().st_size})
for required in ('index.html', 'feed.xml', 'sitemap.xml'):
    assert (dist / required).is_file(), f'Full blog output missing: {required}'
report['generated_post_pages'] = len(list(dist.glob('*/index.html')))

yaml_path = INPUT / 'aicom/metis/deploy/skopos-test/servers.yaml'
settings = yaml.safe_load(yaml_path.read_text())
assert isinstance(settings, dict)
for name in ('poll_interval_seconds', 'batch_lines_per_server', 'security_scan_interval_minutes'):
    assert type(settings[name]) is int and settings[name] > 0
assert type(settings['security_auto_scan']) is bool
assert isinstance(settings['db_path'], str) and settings['db_path']
servers = settings['servers']
assert isinstance(servers, list) and servers
names = [server['name'] for server in servers]
assert len(names) == len(set(names)), 'Duplicate SKOPOS server names'
for server in servers:
    assert isinstance(server['name'], str) and server['name']
    assert server['source'] in {'ssh_nginx_access_log', 'ssh_http_access_log'}
    assert server['transport'] == 'agent-push'
    assert isinstance(server['address'], str) and server['address']
    assert not ({'password', 'private_key', 'ssh_key', 'api_key'} & server.keys())
    nginx = server['nginx']
    assert isinstance(nginx, dict)
    for key in ('auto_discover_logs', 'auto_discover_docker_logs'):
        assert type(nginx[key]) is bool
    if 'access_log_path' in nginx:
        assert isinstance(nginx['access_log_path'], str) and nginx['access_log_path'].startswith('/')
    if 'access_log_paths' in nginx:
        assert isinstance(nginx['access_log_paths'], list)
    if 'docker_log_containers' in nginx:
        assert isinstance(nginx['docker_log_containers'], list)
        assert all(isinstance(value, str) and value for value in nginx['docker_log_containers'])
factory = next(server for server in servers if server['name'] == 'factory')
assert factory['address'] == 'lottery.modelmarket.dev'
report['yaml'] = {'sha256': sha(yaml_path), 'server_count': len(servers), 'unique_names': True, 'factory_address_verified': True, 'services_started': False}
report['elapsed_seconds'] = round(time.monotonic() - started, 3)
report['success'] = True
(RESULTS / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
