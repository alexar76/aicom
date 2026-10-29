"""Build an isolated evaluation image from the verified public release artifact.

Run on the enrolled quality host, from the release-candidate staging directory.
This does not read evaluator secrets, invoke evaluation, or start/deploy a container.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

os.umask(0o077)
stage = Path(__file__).resolve().parent
expected_stage = Path('/var/lib/momus-quality/release-candidates/20261027-warden-0.22.2')
assert os.geteuid() == 0 and stage == expected_stage, 'Unexpected staging location or user'
artifact = stage / 'aimarket-warden-0.22.2.tgz'
expected_tar = '0256dad4208f750b56ba7c803dc5fe62c927f7930d621536381c653804751a57'
expected_build = '3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de'
base = 'sha256:befe7e54d444d0d9b2658151725b264fc6bb61dbbdb0927caff60f281ba249d6'
assert artifact.stat().st_size == 936594 and hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_tar
context = stage / 'build-context'
context.mkdir()
with tarfile.open(artifact, 'r:gz') as archive:
    members = archive.getmembers()
    assert len(members) == 345 and sum(m.size for m in members) < 30_000_000
    seen = set()
    for member in members:
        path = PurePosixPath(member.name)
        assert path.parts[0] == 'package' and not path.is_absolute() and '..' not in path.parts
        assert member.name not in seen and (member.isdir() or member.isfile()), 'Unsafe archive entry'
        seen.add(member.name)
        target = context.joinpath(*path.parts)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open('xb') as destination:
                shutil.copyfileobj(source, destination)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
package = context / 'package'
assert json.loads((package / 'package.json').read_text())['version'] == '0.22.2'
files = sorted((package / 'dist').glob('*.js'))
assert files and not any(p.name.startswith('._') for p in files)
h = hashlib.sha256()
for p in files:
    h.update(p.name.encode() + b'\0' + p.read_bytes() + b'\0')
assert h.hexdigest() == expected_build, 'Packed JavaScript build differs'
actual_base = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', 'histor:warden-remediation-base'], text=True).strip()
assert actual_base == base, 'Enrolled base image changed'
shutil.copy2(stage / 'Dockerfile.candidate', context / 'Dockerfile')
with (stage / 'image-build.log').open('xb') as output:
    subprocess.run(['docker', 'build', '--pull=false', '--network', 'none',
                    '--label', 'org.aimarket.release.tarball-sha256=' + expected_tar,
                    '--iidfile', str(stage / 'image.id'), str(context)],
                   stdout=output, stderr=subprocess.STDOUT, check=True, timeout=600)
image = (stage / 'image.id').read_text().strip()
assert image.startswith('sha256:') and len(image) == 71
manifest = {'release': '@aimarket/warden@0.22.2', 'tarballSha256': expected_tar,
            'buildDigest': expected_build, 'baseImageDigest': base, 'imageDigest': image,
            'scope': 'isolated-quality-evaluation', 'deployed': False}
(stage / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest))
