"""Run on factory-vps; private baseline material never leaves that host."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

os.umask(0o077)
work = Path('/root/symmartys-rollout-20261029')
work.mkdir(mode=0o700, exist_ok=True)
baseline_file = work / 'private-baseline.json'
if baseline_file.exists():
    raise SystemExit('Baseline already exists; retain and review it before another cutover')
container = json.loads(subprocess.check_output(['docker', 'inspect', 'emporion']))[0]
image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', container['Image']]))[0]
assert container['State']['Running']
assert container['Config']['Cmd'] == image['Config']['Cmd'], 'Unexpected runtime command override'
mount = next(m for m in container['Mounts'] if m['Destination'] == '/data')
assert mount['Type'] == 'volume' and mount['Name'] == 'emporion_emporion_data'
data = Path(mount['Source'])
protected = {}
for name in ('emporion_signing_key', 'emporion_signing_key_mldsa', 'calls.salt'):
    p = data / name
    assert p.is_file() and not p.is_symlink(), 'Missing or indirect protected state'
    protected[name] = hashlib.sha256(p.read_bytes()).hexdigest()
with urllib.request.urlopen('http://127.0.0.1:9351/ai-market/v2/manifest', timeout=10) as response:
    manifest = json.load(response)
assert len(manifest['tools']) == 16
assert manifest['signature']['public_key']
baseline = {
    'container': container,
    'protected_hashes': protected,
    'manifest': manifest,
    'volume_name': mount['Name'],
    'data_root': str(data),
    'data_files': [str(p.relative_to(data)) for p in data.rglob('*') if p.is_file()],
}
with baseline_file.open('x') as stream:
    json.dump(baseline, stream)
baseline_file.chmod(0o600)
subprocess.run(['docker', 'image', 'tag', container['Image'], 'emporion:before-symmartys-20261029'], check=True)
print(json.dumps({'preflight_saved': True, 'volume': mount['Name'],
                  'protected_files_recorded_on_server': len(protected),
                  'existing_capabilities': len(manifest['tools']),
                  'baseline_stays_on_server': True}))
