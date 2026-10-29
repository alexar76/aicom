import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True, capture_output=capture).stdout


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


release = Path(__file__).resolve().parent
repo = Path('/root/claudecode/aicom')
host_source = repo / 'alien-monitor/backend/hub_discovery.py'
redeploy = repo / 'scripts/redeploy_alien_monitor_live.sh'
expected_host = 'ed1d0dd07a51396c0fa1847d82f594a87d8bac019df0459fec686e40761991e9'
expected_running = 'fb0ae50fd944f838a0a79a9e508298d34245d898d42d5426159c1fef9b93a8ca'
expected_image_id = 'sha256:25e8e8eb98a03b80cc8eda3dce74c006504ae4ef158804c3633c38ca35c1c8ad'
expected_script = '596ad7a527c190f3cc7c4f81d1a55384d2be45a252d0fed0a4d89bc729d44850'
spec = json.loads(run('docker', 'inspect', 'alien-monitor-live', capture=True))[0]
old_image = spec['Config']['Image']
assert spec['Image'] == expected_image_id, 'LIVE image changed; recheck baseline'
assert sha(host_source) == expected_host, 'Host source changed; recheck baseline'
assert sha(redeploy) == expected_script, 'Redeploy script changed; inspect first'
container_hash = run('docker', 'exec', 'alien-monitor-live', 'sha256sum',
                     '/app/backend/hub_discovery.py', capture=True).split()[0]
assert container_hash == expected_running, 'Container source changed; recheck baseline'
for mount in spec.get('Mounts', []):
    dest = mount['Destination'].rstrip('/')
    assert not '/app/backend/hub_discovery.py'.startswith(dest + '/') and dest != '/app/backend/hub_discovery.py', 'Source is bind-mounted'
candidate = release / 'hub_discovery.py'
compile(candidate.read_text(), str(candidate), 'exec')
shutil.copy2(host_source, release / 'host-source-before.py')
(release / 'previous-image.txt').write_text(old_image + '\n')
(release / 'previous-image-id.txt').write_text(spec['Image'] + '\n')
image = 'alien-monitor:agent-exec-hub-20261029'
(release / 'Dockerfile').write_text(f'FROM {old_image}\nCOPY --chown=10001:10001 hub_discovery.py /app/backend/hub_discovery.py\n')
run('docker', 'build', '--network=none', '-t', image, str(release))
smoke = run('docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python',
            '-v', f'{release / "smoke.py"}:/tmp/smoke.py:ro', image, '/tmp/smoke.py', capture=True)
(release / 'smoke-result.json').write_text(smoke)
print(smoke, flush=True)
# Recheck before changing the host source or replacing LIVE.
current = json.loads(run('docker', 'inspect', 'alien-monitor-live', capture=True))[0]
assert current['Image'] == expected_image_id and sha(host_source) == expected_host
shutil.copy2(candidate, host_source)
try:
    run(str(redeploy), 'alien-monitor-live', '--image', image)
except BaseException:
    shutil.copy2(release / 'host-source-before.py', host_source)
    run(str(redeploy), 'alien-monitor-live', '--image', old_image)
    raise
result = {'status': 'deployed', 'container': 'alien-monitor-live', 'previous_image': old_image,
          'image': image, 'source_sha256': sha(candidate), 'release_directory': str(release)}
(release / 'deploy-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
