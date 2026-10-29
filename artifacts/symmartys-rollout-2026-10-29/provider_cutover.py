"""State-preserving provider cutover; execute only on the authorized Docker host."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

os.umask(0o077)
work = Path('/root/symmartys-rollout-20261029')
baseline = json.loads((work / 'private-baseline.json').read_text())
old = baseline['container']
current = json.loads(subprocess.check_output(['docker', 'inspect', 'emporion']))[0]
assert current['Id'] == old['Id'] and current['Image'] == old['Image'], 'Runtime changed after preflight'
assert not subprocess.run(['docker', 'inspect', 'symmartys'], capture_output=True).returncode == 0, 'New runtime already exists'

# Freeze briefly for a consistent volume archive; the live volume is never replaced.
backup = work / 'provider-data-before.tar'
assert not backup.exists(), 'Do not overwrite the original data backup'
subprocess.run(['docker', 'pause', 'emporion'], check=True, stdout=subprocess.DEVNULL)
try:
    subprocess.run(['tar', '--numeric-owner', '-cf', str(backup), '-C', baseline['data_root'], '.'], check=True)
finally:
    subprocess.run(['docker', 'unpause', 'emporion'], check=True, stdout=subprocess.DEVNULL)
backup.chmod(0o600)

env = dict(item.split('=', 1) for item in old['Config']['Env'] if '=' in item)
updates = {'SYMMARTYS_' + key[len('EMPORION_'):]: value
           for key, value in env.items() if key.startswith('EMPORION_')}
updates.update(SYMMARTYS_PUBLIC_URL='https://modelmarket.dev/providers/symmartys',
               SYMMARTYS_SIGNING_KEY_PATH='/data/emporion_signing_key', SYMMARTYS_STATE_DIR='/data')
audiences = [item.strip().rstrip('/') for item in env.get('ORACLE_HUB_AUDIENCES', '').split(',') if item.strip()]
for url in (env.get('EMPORION_PUBLIC_URL'), updates['SYMMARTYS_PUBLIC_URL']):
    if url and url.rstrip('/') not in audiences:
        audiences.append(url.rstrip('/'))
updates['ORACLE_HUB_AUDIENCES'] = ','.join(audiences)

sys.path.insert(0, '/root/audit-20261025')
spec = importlib.util.spec_from_file_location('provider_rollout_helper', '/root/audit-20261025/rollout_container.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
original_rebase = helper.rebase


def rebase(config, old_image, image):
    result = original_rebase(config, old_image, image)
    # The replacement is owned by the new Compose service after its final rename.
    if image == 'symmartys:rollout-20261029':
        labels = {k: v for k, v in (config.get('Labels') or {}).items()
                  if not k.startswith('com.docker.compose.')}
        labels.update({
            'com.docker.compose.project': 'symmartys',
            'com.docker.compose.service': 'symmartys',
            'com.docker.compose.container-number': '1',
            'com.docker.compose.project.working_dir': '/opt/emporion/src/symmartys',
            'com.docker.compose.project.config_files': '/opt/emporion/src/symmartys/docker-compose.yml',
        })
        config['Labels'] = labels
    return result


helper.rebase = rebase
sys.argv = ['rollout_container.py', 'emporion', '--image', 'symmartys:rollout-20261029',
            '--health', 'http://127.0.0.1:9351/health', '--env-output', str(work / 'runtime.env')]
for key, value in updates.items():
    sys.argv.extend(['--set', key + '=' + value])
log = work / 'provider-rollout.log'
saved_stdout, saved_stderr = sys.stdout, sys.stderr
with log.open('w') as stream:
    try:
        sys.stdout = sys.stderr = stream
        helper.main()
    finally:
        sys.stdout, sys.stderr = saved_stdout, saved_stderr


def load(path):
    with urllib.request.urlopen('http://127.0.0.1:9351/' + path, timeout=10) as response:
        return json.load(response)


try:
    health = load('health')
    manifest = load('ai-market/v2/manifest')
    assert health['service'] == 'symmartys' and health['version'] == '0.5.0'
    assert len(manifest['tools']) == 16
    assert all(t['product_id'] == 'symmartys' and t['capability_id'].startswith('symmartys.')
               for t in manifest['tools'])
    for key in ('public_key', 'pq_public_key'):
        assert manifest['signature'][key] == baseline['manifest']['signature'][key], 'Provider identity changed'
    verify = """import json,urllib.request
from oracle_core.signing import Signer
with urllib.request.urlopen('http://127.0.0.1:9351/ai-market/v2/manifest') as response:
    manifest=json.load(response)
verifier=Signer.__new__(Signer)
assert verifier.verify_manifest_signature(manifest, manifest['signature']['public_key'],
    require_pq=True, pq_public_key_b64=manifest['signature']['pq_public_key'])
"""
    subprocess.run(['docker', 'exec', 'emporion', 'python', '-c', verify], check=True,
                   stdout=subprocess.DEVNULL)
    for name, expected in baseline['protected_hashes'].items():
        assert hashlib.sha256((Path(baseline['data_root']) / name).read_bytes()).hexdigest() == expected, 'Protected state changed'
    runtime = json.loads(subprocess.check_output(['docker', 'inspect', 'emporion']))[0]
    def mounts(info):
        return [{k: m.get(k) for k in ('Type', 'Name', 'Source', 'Destination', 'RW')}
                for m in info['Mounts']]
    assert mounts(runtime) == mounts(old), 'Persistent mount changed'
    now = dict(item.split('=', 1) for item in runtime['Config']['Env'] if '=' in item)
    assert all(now.get(k) == v for k, v in env.items() if k not in updates), 'Existing runtime setting changed'
except Exception:
    # The standard helper restores on health failure. Restore the retained predecessor
    # too if the stricter identity/namespace checks fail after HTTP becomes healthy.
    previous = json.loads(log.read_text()).get('previous_container')
    if previous:
        info = json.loads(subprocess.check_output(['docker', 'inspect', previous]))[0]
        assert info['Image'] == old['Image'], 'Rollback predecessor differs from baseline'
        subprocess.run(['docker', 'stop', 'emporion'], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['docker', 'rename', 'emporion', 'symmartys-failed-' + str(time.time_ns())], check=True)
        subprocess.run(['docker', 'rename', previous, 'emporion'], check=True)
        subprocess.run(['docker', 'start', 'emporion'], check=True, stdout=subprocess.DEVNULL)
    raise

subprocess.run(['docker', 'rename', 'emporion', 'symmartys'], check=True)
subprocess.run(['docker', 'image', 'tag', 'symmartys:rollout-20261029', 'symmartys:latest'], check=True)
summary = {'service': health['service'], 'version': health['version'], 'capabilities': len(manifest['tools']),
           'ed25519_preserved': True, 'mldsa_preserved': True, 'call_salt_preserved': True,
           'volume_preserved': True, 'existing_runtime_settings_preserved': True,
           'volume_backup_on_server': True, 'old_runtime_retained_stopped': True,
           'manifest_hybrid_signature_verified': True, 'container': 'symmartys'}
(work / 'provider-result.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary))
